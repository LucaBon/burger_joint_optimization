"""Pluggable dispatch policies for :class:`BranchScheduler`.

A dispatch policy decides the order in which burgers are fed to the
three-stage worker heaps inside ``_simulate``. Historically the sort key
was hardcoded as ``(tier, deadline, arrival, oid, item_id)`` — classic
EDF with tier-1 strictly behind tier-0. This module extracts that sort
key into a ``DispatchPolicy`` strategy so alternatives become config.

Ships three policies:

* :class:`EDFPolicy` — Earliest Deadline First, the original behaviour.
* :class:`SPTPolicy` — Shortest Processing Time, sorted by order-level
  burger count. Short orders cut ahead of long ones within the same
  tier / priority, which shortens mean flow time.
* :class:`WSPTPolicy` — Weighted SPT, ``priority / processing_time``
  ratio. Highest-ratio orders dispatch first. Falls back to priority
  alone when SPT weights are not supplied and to arrival time for
  stable tie-breaking.

All policies honour the global tier split and any positive
``Order.priority`` field (higher = more important), so priority-aware
dispatch composes with every strategy.
"""
from typing import Any, Dict, Protocol, Tuple


# A "state" dict is the per-burger payload built by BranchScheduler._simulate.
# Keys the policies may read: "tier", "priority", "deadline", "arrival",
# "oid", "item_id", "order_size".
StateDict = Dict[str, Any]
SortKey = Tuple


class DispatchPolicy(Protocol):
    """Strategy contract consumed by :meth:`BranchScheduler._simulate`."""

    name: str

    def sort_key(self, state: StateDict) -> SortKey:
        ...


class EDFPolicy:
    """Earliest Deadline First (the default, matches v1 behaviour).

    Priority (higher first) is layered on top of the tier split so a
    VIP order still queues ahead of regular tier-0 work, but tier-1
    ("accepted late") stays strictly behind tier-0 regardless of
    priority — that is the invariant that keeps late acceptance from
    starving on-time orders.
    """

    name = "edf"

    def sort_key(self, state: StateDict) -> SortKey:
        return (
            state["tier"],
            -state.get("priority", 0),
            state["deadline"],
            state["arrival"],
            state["oid"],
            state["item_id"],
        )


class SPTPolicy:
    """Shortest Processing Time at order granularity.

    Orders with fewer burgers dispatch ahead of longer orders within
    the same tier / priority bucket, which shortens mean flow time
    without changing the tardy count much. Deadline is still used as a
    secondary tie-break so an urgent short order still beats a
    non-urgent short order.
    """

    name = "spt"

    def sort_key(self, state: StateDict) -> SortKey:
        return (
            state["tier"],
            -state.get("priority", 0),
            state.get("order_size", 1),
            state["deadline"],
            state["arrival"],
            state["oid"],
            state["item_id"],
        )


class WSPTPolicy:
    """Weighted Shortest Processing Time.

    Ranks by ``-(priority / order_size)`` — highest ratio dispatches
    first. Classical Smith's rule for 1-machine weighted completion
    time, adapted to burger granularity. When priority is zero across
    the board it degenerates to SPT.
    """

    name = "wspt"

    def sort_key(self, state: StateDict) -> SortKey:
        priority = max(state.get("priority", 0), 0)
        size = max(state.get("order_size", 1), 1)
        # Higher ratio = more urgent -> sort ascending on the negative.
        ratio = priority / size if priority > 0 else 0.0
        return (
            state["tier"],
            -ratio,
            size,
            state["deadline"],
            state["arrival"],
            state["oid"],
            state["item_id"],
        )


_POLICIES: Dict[str, DispatchPolicy] = {
    EDFPolicy.name: EDFPolicy(),
    SPTPolicy.name: SPTPolicy(),
    WSPTPolicy.name: WSPTPolicy(),
}


def get_policy(name_or_policy) -> DispatchPolicy:
    """Resolve a dispatch policy from a name, an instance, or ``None``.

    ``None`` returns the default EDF policy.
    """
    if name_or_policy is None:
        return _POLICIES[EDFPolicy.name]
    if isinstance(name_or_policy, str):
        try:
            return _POLICIES[name_or_policy]
        except KeyError:
            raise ValueError(
                "unknown dispatch policy: {}. known: {}".format(
                    name_or_policy, sorted(_POLICIES)))
    # Duck-type check: anything exposing sort_key + name is accepted.
    if hasattr(name_or_policy, "sort_key") and hasattr(name_or_policy, "name"):
        return name_or_policy
    raise TypeError(
        "dispatch_policy must be a name, a DispatchPolicy, or None; "
        "got {}".format(type(name_or_policy)))
