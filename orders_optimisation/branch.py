"""Branch domain model.

A :class:`Branch` bundles per-stage workforce (capacity + lead time) with
an initial inventory snapshot and an optional list of scheduled restocks.
The scheduler reads these via :class:`InventoryTimeline`; :class:`Branch`
itself is deliberately a passive container.
"""

import logging
from copy import deepcopy
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


_STAGE_KEYS = ("capacity", "lead_time")
_INVENTORY_KEYS = (
    "burgers_patties", "lettuce", "tomato", "veggie_patties", "bacon",
)


Restock = Tuple[datetime, Dict[str, int]]
# One shift entry: (start, end_unused, extra_capacity) — see note on ``shifts``.
Shift = Tuple[datetime, datetime, int]
# Per-stage shift map: {"cooking": [(start, end, extra), ...], ...}
ShiftMap = Dict[str, List[Shift]]

_STAGE_NAMES = ("cooking", "assembling", "packaging")


class Branch:
    """A single restaurant location with a three-stage kitchen pipeline."""

    def __init__(self,
                 branch_id: str,
                 cooking: Dict[str, int],
                 assembling: Dict[str, int],
                 packaging: Dict[str, int],
                 inventory: Dict[str, int],
                 restocks: Optional[List[Restock]] = None,
                 shifts: Optional[ShiftMap] = None):
        """
        Args:
            branch_id: Stable identifier used by orders and restocks.
            cooking: ``{"capacity": int > 0, "lead_time": int >= 0}``.
            assembling: same shape as ``cooking``.
            packaging: same shape as ``cooking``.
            inventory: **t=0** stock snapshot. Five keys, all non-negative
                ints. Not mutated by the scheduler; live stock at a given
                wall-clock instant is obtained via
                :meth:`BranchScheduler.current_stock`.
            restocks: optional list of ``(datetime, {ingredient: amount})``
                scheduled inflows. Consumed by
                :class:`~orders_optimisation.inventory_timeline.InventoryTimeline`.
            shifts: optional per-stage extra-worker windows. Structured as
                ``{"cooking"|"assembling"|"packaging": [(start, end, extra_cap)]}``.
                During ``start..end`` the scheduler has access to
                ``capacity + extra_cap`` workers for that stage. In this
                iteration an extra worker who comes on shift stays in the
                pool for the rest of the run — the ``end`` field is
                parsed and validated but not used to evict the worker. A
                strict end-of-shift model can be layered on later without
                changing the Branch public API.
        """
        self._check_input(branch_id, cooking, assembling, packaging, inventory)
        self._check_shifts(shifts)

        self.branch_id: str = branch_id
        self._cooking: Dict[str, int] = deepcopy(cooking)
        self._assembling: Dict[str, int] = deepcopy(assembling)
        self._packaging: Dict[str, int] = deepcopy(packaging)
        self._inventory: Dict[str, int] = deepcopy(inventory)
        self._restocks: List[Restock] = list(restocks) if restocks else []
        self._shifts: ShiftMap = (
            {k: list(v) for k, v in shifts.items()} if shifts else {})

    @staticmethod
    def _check_input(branch_id, cooking, assembling, packaging, inventory):
        if not isinstance(branch_id, str):
            raise TypeError(
                "branch_id should be a str, while it is a {}".format(
                    type(branch_id)))
        for name, stage in (("cooking", cooking),
                            ("assembling", assembling),
                            ("packaging", packaging)):
            Branch._check_stage(name, stage)
        if not isinstance(inventory, dict):
            raise TypeError(
                "inventory should be a dict, while it is a {}".format(
                    type(inventory)))
        if len(inventory) != 5:
            raise ValueError(
                "inventory should contain five keys, while it contains {} "
                "keys".format(len(inventory)))
        for k, v in inventory.items():
            if k not in _INVENTORY_KEYS:
                raise ValueError(
                    "inventory should contain keys {}, while it contains {}"
                    "".format(_INVENTORY_KEYS, k))
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise ValueError(
                    "inventory[{}] must be a non-negative int, got {}"
                    "".format(k, v))

    @staticmethod
    def _check_stage(name: str, stage) -> None:
        if not isinstance(stage, dict):
            raise TypeError(
                "{} should be a dict, while it is a {}".format(
                    name, type(stage)))
        if len(stage) != 2 or set(stage.keys()) != set(_STAGE_KEYS):
            raise ValueError(
                "{} should contain keys 'capacity' and 'lead_time', "
                "while it contains {}".format(name, list(stage.keys())))
        cap = stage["capacity"]
        lead = stage["lead_time"]
        if (not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0):
            raise ValueError(
                "{}['capacity'] must be a positive int, got {}".format(
                    name, cap))
        if (not isinstance(lead, int) or isinstance(lead, bool) or lead < 0):
            raise ValueError(
                "{}['lead_time'] must be a non-negative int, got {}".format(
                    name, lead))

    @property
    def cooking(self) -> Dict[str, int]:
        return self._cooking

    @property
    def assembling(self) -> Dict[str, int]:
        return self._assembling

    @property
    def packaging(self) -> Dict[str, int]:
        return self._packaging

    @property
    def inventory(self) -> Dict[str, int]:
        """Read-only view of the t=0 stock snapshot."""
        return self._inventory

    @property
    def restocks(self) -> List[Restock]:
        return sorted(self._restocks, key=lambda e: e[0])

    @property
    def shifts(self) -> ShiftMap:
        return {k: list(v) for k, v in self._shifts.items()}

    def shifts_for(self, stage: str) -> List[Shift]:
        """Return the list of extra-worker windows for ``stage``."""
        return list(self._shifts.get(stage, []))

    @staticmethod
    def _check_shifts(shifts) -> None:
        if shifts is None:
            return
        if not isinstance(shifts, dict):
            raise TypeError(
                "shifts should be a dict or None, got {}".format(type(shifts)))
        for stage, entries in shifts.items():
            if stage not in _STAGE_NAMES:
                raise ValueError(
                    "shifts stage must be one of {}, got {}".format(
                        _STAGE_NAMES, stage))
            if not isinstance(entries, list):
                raise TypeError(
                    "shifts[{}] must be a list, got {}".format(
                        stage, type(entries)))
            for entry in entries:
                if (not isinstance(entry, tuple) or len(entry) != 3):
                    raise ValueError(
                        "shifts[{}] entries must be (start, end, extra) "
                        "tuples, got {}".format(stage, entry))
                start, end, extra = entry
                if not isinstance(start, datetime):
                    raise TypeError(
                        "shift start must be datetime, got {}".format(
                            type(start)))
                if not isinstance(end, datetime):
                    raise TypeError(
                        "shift end must be datetime, got {}".format(type(end)))
                if end < start:
                    raise ValueError(
                        "shift end must be >= start")
                if (not isinstance(extra, int)
                        or isinstance(extra, bool) or extra <= 0):
                    raise ValueError(
                        "shift extra capacity must be a positive int, "
                        "got {}".format(extra))

    def add_restocks(self, new_restocks: List[Restock]) -> None:
        """Append one or more scheduled restocks.

        Each element must be a ``(datetime, {ingredient: amount})`` tuple
        with non-negative amounts.
        """
        for entry in new_restocks:
            _, deltas = entry
            for k, v in deltas.items():
                if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                    raise ValueError(
                        "restock amount must be a non-negative int, got "
                        "{}={}".format(k, v))
        self._restocks.extend(new_restocks)


class ExhaustedIngredientError(ValueError):
    """Raised when a legacy code path would need more stock than available.

    The time-aware inventory model used by :class:`BranchScheduler` does
    not raise this exception directly, but it is kept for backwards
    compatibility with callers that still catch it.
    """
    pass
