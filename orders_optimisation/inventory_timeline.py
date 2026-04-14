"""Time-aware inventory model used by the scheduler.

The timeline tracks three things:

* ``initial`` — the t=0 stock snapshot copied from ``Branch.inventory``.
* ``restocks`` — scheduled future inflows ``(datetime, {ingredient: amount})``.
* ``consumptions`` — projected per-burger outflows, grouped per-order so
  that re-assigning one order is O(1) instead of O(total burgers).

Feasibility is "running stock never dips below zero" over the merged
event stream. Restocks arriving at the exact same instant as a
consumption are applied first, so a just-in-time restock satisfies a
burger whose cook_start equals the restock time.
"""
from datetime import datetime
from typing import Dict, List, Optional, Tuple


Consumption = Tuple[datetime, Dict[str, int]]
# Per-order map: {item_id: (cook_start, per_burger_ingredients)}
PerOrderConsumptions = Dict[int, Consumption]
# Legacy flat view: {(order_id, item_id): (cook_start, ingredients)}
ConsumptionMap = Dict[Tuple[str, int], Consumption]


class InventoryTimeline:
    """Time-aware inventory model used by :class:`BranchScheduler`."""

    def __init__(self,
                 initial: Dict[str, int],
                 restocks: Optional[List[Tuple[datetime, Dict[str, int]]]] = None):
        self._initial: Dict[str, int] = dict(initial)
        self._restocks: List[Tuple[datetime, Dict[str, int]]] = sorted(
            [(t, dict(d)) for t, d in (restocks or [])],
            key=lambda e: e[0])
        self._by_order: Dict[str, PerOrderConsumptions] = {}

    # ----- public API -----

    @property
    def consumptions(self) -> ConsumptionMap:
        """Flat view kept for external readers that still expect it."""
        out: ConsumptionMap = {}
        for oid, per in self._by_order.items():
            for item_id, cons in per.items():
                out[(oid, item_id)] = cons
        return out

    def feasible_with(self, new_consumptions: ConsumptionMap) -> bool:
        """Return True iff merging ``new_consumptions`` keeps running stock >= 0.

        Entries in ``new_consumptions`` override entries with the same
        ``(order_id, item_id)`` key in the current timeline, which is how
        re-simulation updates a burger's cook_start.
        """
        return self._running_sum_nonnegative(new_consumptions)

    def replace_order(self,
                      order_id: str,
                      new_consumptions_for_order: ConsumptionMap) -> None:
        """Drop every existing consumption belonging to ``order_id`` and
        merge in ``new_consumptions_for_order``. Atomic within the call."""
        per: PerOrderConsumptions = {}
        for (oid, item_id), cons in new_consumptions_for_order.items():
            if oid != order_id:
                # Defensive: caller should only pass entries for this order.
                continue
            per[item_id] = cons
        if per:
            self._by_order[order_id] = per
        else:
            self._by_order.pop(order_id, None)

    def drop_order(self, order_id: str) -> None:
        """Remove every consumption entry for ``order_id`` unconditionally."""
        self._by_order.pop(order_id, None)

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
        per = self._by_order.get(order_id)
        if not per:
            return refunded
        survivors: PerOrderConsumptions = {}
        for item_id, (cs, ing) in per.items():
            if cs >= min_cook_start:
                for k, v in ing.items():
                    refunded[k] = refunded.get(k, 0) + v
            else:
                survivors[item_id] = (cs, ing)
        if survivors:
            self._by_order[order_id] = survivors
        else:
            self._by_order.pop(order_id, None)
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
        for per in self._by_order.values():
            for (cs, ing) in per.values():
                if cs <= now:
                    for k, v in ing.items():
                        stock[k] = stock.get(k, 0) - v
        return stock

    def snapshot(self) -> Dict[str, PerOrderConsumptions]:
        """Return a shallow structural copy for rollback.

        Safe as long as callers never mutate existing inner dicts in
        place — :meth:`replace_order` always rebinds a fresh
        :class:`PerOrderConsumptions` dict, and per-burger ingredient
        dicts are produced fresh by ``burger_ingredients`` and never
        edited downstream.
        """
        # Outer dict copy is enough because every mutation path
        # (replace_order, drop_order, refund) rebinds the per-order entry
        # rather than mutating it in place.
        return dict(self._by_order)

    def restore(self, snap: Dict[str, PerOrderConsumptions]) -> None:
        """Restore the consumption map from a ``snapshot()`` return value."""
        self._by_order = dict(snap)

    # ----- internals -----

    def _running_sum_nonnegative(
            self,
            overrides: ConsumptionMap) -> bool:
        # Events: (timestamp, sort_key, sign, delta).
        # sort_key 0 = restock (applied first), 1 = consumption.
        events: List[Tuple[datetime, int, int, Dict[str, int]]] = []
        for t, delta in self._restocks:
            events.append((t, 0, +1, delta))

        # Override keys replace same-keyed current entries.
        override_keys = set(overrides.keys())
        for oid, per in self._by_order.items():
            for item_id, (cs, ing) in per.items():
                if (oid, item_id) in override_keys:
                    continue
                events.append((cs, 1, -1, ing))
        for (cs, ing) in overrides.values():
            events.append((cs, 1, -1, ing))

        events.sort(key=lambda e: (e[0], e[1]))

        stock = dict(self._initial)
        for _, _, sign, delta in events:
            for k, v in delta.items():
                stock[k] = stock.get(k, 0) + sign * v
                if stock[k] < 0:
                    return False
        return True
