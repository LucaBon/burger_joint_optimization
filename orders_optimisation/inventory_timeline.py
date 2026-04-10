from copy import deepcopy
from datetime import datetime
from typing import Dict, List, Optional, Tuple


Consumption = Tuple[datetime, Dict[str, int]]
ConsumptionMap = Dict[Tuple[str, int], Consumption]


class InventoryTimeline:
    """Time-aware inventory model used by :class:`BranchScheduler`.

    The timeline tracks three things:

    * ``initial`` — the t=0 stock snapshot copied from ``Branch.inventory``.
    * ``restocks`` — scheduled future inflows ``(datetime, {ingredient: amount})``.
    * ``consumptions`` — projected per-burger outflows keyed by
      ``(order_id, item_id)`` with value ``(cook_start, per_burger_ingredients)``.

    Feasibility is "running stock never dips below zero" over the merged
    event stream. Restocks arriving at the exact same instant as a
    consumption are applied first, so a just-in-time restock satisfies a
    burger whose cook_start equals the restock time.
    """

    def __init__(self,
                 initial: Dict[str, int],
                 restocks: Optional[List[Tuple[datetime, Dict[str, int]]]] = None):
        self._initial: Dict[str, int] = dict(initial)
        self._restocks: List[Tuple[datetime, Dict[str, int]]] = sorted(
            [(t, dict(d)) for t, d in (restocks or [])],
            key=lambda e: e[0])
        self._consumptions: ConsumptionMap = {}

    # ----- public API -----

    @property
    def consumptions(self) -> ConsumptionMap:
        return self._consumptions

    def feasible_with(self, new_consumptions: ConsumptionMap) -> bool:
        """Return True iff merging ``new_consumptions`` keeps running stock >= 0.

        Entries in ``new_consumptions`` override entries with the same
        ``(order_id, item_id)`` key in the current timeline, which is how
        re-simulation updates a burger's cook_start.
        """
        merged: ConsumptionMap = dict(self._consumptions)
        merged.update(new_consumptions)
        return self._running_sum_nonnegative(merged)

    def replace_order(self,
                      order_id: str,
                      new_consumptions_for_order: ConsumptionMap) -> None:
        """Drop every existing consumption belonging to ``order_id`` and
        merge in ``new_consumptions_for_order``. Atomic within the call."""
        self._consumptions = {
            k: v for k, v in self._consumptions.items() if k[0] != order_id
        }
        self._consumptions.update(new_consumptions_for_order)

    def drop_order(self, order_id: str) -> None:
        """Remove every consumption entry for ``order_id`` unconditionally."""
        self._consumptions = {
            k: v for k, v in self._consumptions.items() if k[0] != order_id
        }

    def refund(self,
               order_id: str,
               min_cook_start: datetime) -> Dict[str, int]:
        """Remove entries for ``order_id`` whose ``cook_start >= min_cook_start``.

        Entries with ``cook_start < min_cook_start`` are sunk cost — the
        burger started cooking strictly before ``min_cook_start`` and its
        ingredients are gone. An entry whose ``cook_start`` equals
        ``min_cook_start`` is treated as refundable: at the exact instant
        cancellation is issued, the burger has not yet physically
        consumed anything. Returns the sum of refunded ingredients.
        """
        refunded: Dict[str, int] = {k: 0 for k in self._initial}
        survivors: ConsumptionMap = {}
        for key, (cs, ing) in self._consumptions.items():
            if key[0] == order_id and cs >= min_cook_start:
                for k, v in ing.items():
                    refunded[k] = refunded.get(k, 0) + v
            else:
                survivors[key] = (cs, ing)
        self._consumptions = survivors
        return refunded

    def current_stock(self, now: datetime) -> Dict[str, int]:
        """Return projected available stock at ``now``: initial + restocks
        applied up to and including ``now``, minus consumptions whose
        cook_start is on or before ``now``."""
        stock = dict(self._initial)
        for t, delta in self._restocks:
            if t <= now:
                for k, v in delta.items():
                    stock[k] = stock.get(k, 0) + v
        for (cs, ing) in self._consumptions.values():
            if cs <= now:
                for k, v in ing.items():
                    stock[k] = stock.get(k, 0) - v
        return stock

    def snapshot(self) -> ConsumptionMap:
        """Return a deep copy of the current consumption map for rollback."""
        return deepcopy(self._consumptions)

    def restore(self, snap: ConsumptionMap) -> None:
        """Restore the consumption map from a ``snapshot()`` return value."""
        self._consumptions = deepcopy(snap)

    # ----- internals -----

    def _running_sum_nonnegative(self, merged: ConsumptionMap) -> bool:
        # Events: (timestamp, sort_key, sign, delta).
        # sort_key 0 = restock (applied first), 1 = consumption.
        events: List[Tuple[datetime, int, int, Dict[str, int]]] = []
        for t, delta in self._restocks:
            events.append((t, 0, +1, delta))
        for (cs, ing) in merged.values():
            events.append((cs, 1, -1, ing))
        events.sort(key=lambda e: (e[0], e[1]))

        stock = dict(self._initial)
        for _, _, sign, delta in events:
            for k, v in delta.items():
                stock[k] = stock.get(k, 0) + sign * v
                if stock[k] < 0:
                    return False
        return True
