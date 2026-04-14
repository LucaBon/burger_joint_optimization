import heapq
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from .order import InvalidIngredientError, Order, burger_ingredients
from .branch import Branch
from .dispatch_policies import DispatchPolicy, get_policy
from .inventory_timeline import InventoryTimeline
from . import data_reader


logger = logging.getLogger(__name__)

DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

TIER_ON_TIME = 0
TIER_LATE = 1


@dataclass
class BurgerAssignment:
    order_id: str
    item_id: int
    ingredients: str
    tier: int
    cook_worker: int
    cook_start: datetime
    cook_end: datetime
    asm_worker: int
    asm_start: datetime
    asm_end: datetime
    pkg_worker: int
    pkg_start: datetime
    pkg_end: datetime


@dataclass
class _OrderMeta:
    order: Order
    arrival: datetime
    deadline: datetime
    tier: int
    status: str


@dataclass
class AdmissionVerdict:
    feasible: bool
    projected_end: datetime
    lateness: timedelta
    displaced_orders: List[str] = field(default_factory=list)
    inventory_feasible: bool = True
    deadline_feasible: bool = True


@dataclass
class AdmissionResult:
    status: str  # "accepted" | "accepted_late" | "rejected"
    verdict: AdmissionVerdict
    schedule: List[BurgerAssignment] = field(default_factory=list)
    reason: Optional[str] = None


@dataclass
class CancelResult:
    order_id: str
    refunded: Dict[str, int]
    status: str = "cancelled"


class BranchScheduler:
    """Online deadline-aware scheduler for a single branch.

    Orders are admitted one at a time via :meth:`admit`. Each admission
    triggers a full re-optimization of all not-yet-started work using an
    EDF dispatch rule at burger granularity, split into two priority tiers:

    - **Tier 0 (on-time):** orders admitted with a feasible verdict.
    - **Tier 1 (accepted-late):** orders admitted despite infeasibility.
      They are dispatched strictly after all tier-0 work at every stage.

    Burgers whose cooking has already started at ``now`` are frozen and
    never reassigned. Inventory is decremented inside :meth:`admit` — the
    read-only :meth:`estimate` never mutates state.
    """

    def __init__(self, branch: Branch,
                 dispatch_policy: Optional[object] = None):
        self._branch = branch
        self._order_meta: Dict[str, _OrderMeta] = {}
        self._assignments: Dict[str, List[BurgerAssignment]] = {}
        self._rejected: List[dict] = []
        # Deadline-infeasible orders parked for later re-evaluation.
        # Populated only when callers pass ``backorder=True`` to admit.
        self._backorder_queue: List[Order] = []
        self._dispatch_policy: DispatchPolicy = get_policy(dispatch_policy)

        self._cook_lead = timedelta(minutes=branch.cooking["lead_time"])
        self._asm_lead = timedelta(minutes=branch.assembling["lead_time"])
        self._pkg_lead = timedelta(minutes=branch.packaging["lead_time"])
        self._cook_cap = branch.cooking["capacity"]
        self._asm_cap = branch.assembling["capacity"]
        self._pkg_cap = branch.packaging["capacity"]

        # Extra-worker shift starts, flattened to (start_datetime, idx)
        # tuples. Each extra shift worker is a distinct heap slot whose
        # free_at begins at the shift start; once a shift starts, that
        # worker stays in the pool for the rest of the run.
        self._cook_shift_starts = _flatten_shift_starts(
            branch.shifts_for("cooking"), self._cook_cap)
        self._asm_shift_starts = _flatten_shift_starts(
            branch.shifts_for("assembling"),
            self._cook_cap + len(self._cook_shift_starts))
        self._pkg_shift_starts = _flatten_shift_starts(
            branch.shifts_for("packaging"),
            self._asm_cap + len(self._asm_shift_starts))

        self._timeline = InventoryTimeline(
            initial=branch.inventory, restocks=branch.restocks)

    # ----- public API -----

    def estimate(self, order: Order, now: datetime) -> AdmissionVerdict:
        """Project the effect of admitting ``order`` at tier 0 without mutating state."""
        baseline = self._simulate(now=now)
        projected = self._simulate(
            now=now, new_order=order, new_tier=TIER_ON_TIME)

        new_end = _projected_end(projected, order.order_id)
        deadline = now + timedelta(
            minutes=order.max_order_completion_time)
        deadline_feasible = new_end <= deadline
        lateness = new_end - deadline if new_end > deadline else timedelta(0)

        displaced: List[str] = []
        for oid, meta in self._order_meta.items():
            if meta.tier != TIER_ON_TIME:
                continue
            base_end = _projected_end(baseline, oid)
            new_end_other = _projected_end(projected, oid)
            if base_end <= meta.deadline < new_end_other:
                displaced.append(oid)

        projected_consumptions = _consumptions_from_plan(projected)
        inventory_feasible = self._timeline.feasible_with(
            projected_consumptions)

        return AdmissionVerdict(
            feasible=deadline_feasible and inventory_feasible,
            projected_end=new_end,
            lateness=lateness,
            displaced_orders=displaced,
            inventory_feasible=inventory_feasible,
            deadline_feasible=deadline_feasible,
        )

    def admit_moore_hodgson(self, order: Order, now: datetime,
                            accept_late: bool = True) -> AdmissionResult:
        """Admit ``order`` using Moore-Hodgson demotion.

        Classical Moore-Hodgson minimizes the number of tardy jobs by
        removing the longest-processing-time job from the on-time set
        whenever a newcomer would otherwise make it tardy. This online
        variant keeps the newcomer on tier-0 whenever possible and
        demotes existing tier-0 orders (longest first, measured in
        burger count) to tier-1 until the newcomer fits. Demoted orders
        keep their inventory and schedule slots but lose tier-0
        priority, so they are dispatched strictly after tier-0 work.

        If demotion cannot make the newcomer feasible, all demotions are
        rolled back and the normal ``admit`` fallback applies.
        """
        if order.order_id in self._order_meta:
            raise ValueError(
                "order {} already admitted".format(order.order_id))

        try:
            order.calculate_order_ingredients()
        except InvalidIngredientError as exc:
            return self._record_rejection(
                order, "invalid_ingredient: {}".format(exc))

        verdict = self.estimate(order, now)
        if verdict.feasible and not verdict.displaced_orders:
            return self._commit(order, now,
                                TIER_ON_TIME, "accepted", verdict)

        # Track original (tier, status) so we can roll back on failure.
        saved: List[tuple] = []

        def _demote(oid: str) -> None:
            meta = self._order_meta[oid]
            saved.append((oid, meta.tier, meta.status))
            meta.tier = TIER_LATE
            meta.status = "demoted_mh"

        # First demote anything the estimate says we'd displace.
        for oid in verdict.displaced_orders:
            if self._order_meta[oid].tier == TIER_ON_TIME:
                _demote(oid)

        # Then demote remaining tier-0 orders longest-first until the
        # newcomer fits.
        def _remaining_candidates() -> List[str]:
            return sorted(
                (oid for oid, m in self._order_meta.items()
                 if m.tier == TIER_ON_TIME),
                key=lambda oid: (
                    -len(self._order_meta[oid].order.burgers), oid))

        new_verdict = self.estimate(order, now)
        while (not new_verdict.feasible or new_verdict.displaced_orders):
            cands = _remaining_candidates()
            if not cands:
                break
            _demote(cands[0])
            new_verdict = self.estimate(order, now)

        if new_verdict.feasible and not new_verdict.displaced_orders:
            return self._commit(order, now,
                                TIER_ON_TIME, "accepted_mh", new_verdict)

        # Roll back demotions and fall through to the classic path.
        for oid, tier, status in saved:
            meta = self._order_meta[oid]
            meta.tier = tier
            meta.status = status

        if not verdict.inventory_feasible:
            return self._record_rejection(order, "inventory_exhausted")

        if accept_late:
            return self._commit(order, now,
                                TIER_LATE, "accepted_late", verdict)

        reason = ("deadline_infeasible" if not verdict.deadline_feasible
                  else "would_displace")
        self._rejected.append({
            "order_id": order.order_id,
            "reason": reason,
            "lateness_seconds": int(verdict.lateness.total_seconds()),
            "displaced_orders": list(verdict.displaced_orders),
        })
        return AdmissionResult(
            status="rejected", verdict=verdict, reason=reason)

    def _commit(self, order: Order, now: datetime,
                tier: int, status: str,
                verdict: AdmissionVerdict) -> AdmissionResult:
        """Shared commit path for :meth:`admit` and :meth:`admit_moore_hodgson`.

        Transactional against the inventory timeline: if re-optimizing the
        plan with the newcomer pushes any consumption event such that the
        running stock would go negative, the commit is rolled back and the
        newcomer rejected with ``inventory_exhausted``.
        """
        snap = self._timeline.snapshot()
        previous_assignments = self._assignments
        self._order_meta[order.order_id] = _OrderMeta(
            order=order,
            arrival=now,
            deadline=now + timedelta(
                minutes=order.max_order_completion_time),
            tier=tier,
            status=status,
        )
        new_plan = self._simulate(
            now=now, new_order=order, new_tier=tier)

        for oid in new_plan:
            per_order = _consumptions_from_plan(new_plan, oid)
            self._timeline.replace_order(oid, per_order)

        if not self._timeline.feasible_with({}):
            # Re-optimization shifted a predecessor's cook_start past a
            # restock such that running stock goes negative. Roll back.
            self._timeline.restore(snap)
            self._order_meta.pop(order.order_id)
            self._assignments = previous_assignments
            return self._record_rejection(order, "inventory_exhausted")

        self._assignments = new_plan
        return AdmissionResult(
            status=status if status != "accepted_mh" else "accepted",
            verdict=verdict,
            schedule=list(self._assignments[order.order_id]),
        )

    def admit(self, order: Order, now: datetime,
              accept_late: bool = False,
              backorder: bool = False) -> AdmissionResult:
        """Attempt to admit ``order``.

        ``accept_late=True`` forces acceptance even when the estimate is
        deadline-infeasible or would displace existing tier-0 orders;
        infeasible orders are committed at tier 1 so they cannot starve
        tier-0 work. Inventory infeasibility is always a hard stop, even
        with ``accept_late=True``.

        ``backorder=True`` parks a deadline-infeasible order into an
        internal queue instead of rejecting it. Queued orders are
        retried automatically after every successful commit and every
        cancellation — at which point they may become feasible thanks
        to freed capacity. Inventory-infeasible orders are never
        queued (no point waiting for stock that is not scheduled to
        appear). ``backorder`` is orthogonal to ``accept_late`` and
        wins over it: when both are set, the order is queued rather
        than committed at tier 1.
        """
        if order.order_id in self._order_meta:
            raise ValueError(
                "order {} already admitted".format(order.order_id))

        try:
            order.calculate_order_ingredients()
        except InvalidIngredientError as exc:
            return self._record_rejection(
                order, "invalid_ingredient: {}".format(exc))

        verdict = self.estimate(order, now)

        if not verdict.inventory_feasible:
            return self._record_rejection(order, "inventory_exhausted")

        if verdict.feasible and not verdict.displaced_orders:
            tier, status = TIER_ON_TIME, "accepted"
        elif backorder:
            self._backorder_queue.append(order)
            return AdmissionResult(
                status="backordered",
                verdict=verdict,
                reason="deadline_infeasible")
        elif accept_late:
            if verdict.feasible:
                tier, status = TIER_ON_TIME, "accepted"
            else:
                tier, status = TIER_LATE, "accepted_late"
        else:
            reason = ("deadline_infeasible"
                      if not verdict.deadline_feasible
                      else "would_displace")
            self._rejected.append({
                "order_id": order.order_id,
                "reason": reason,
                "lateness_seconds": int(verdict.lateness.total_seconds()),
                "displaced_orders": list(verdict.displaced_orders),
            })
            return AdmissionResult(
                status="rejected", verdict=verdict, reason=reason)

        result = self._commit(order, now, tier, status, verdict)
        self._drain_backorder_queue(now)
        return result

    def _drain_backorder_queue(self, now: datetime) -> None:
        """Retry every queued backorder once. Successful admissions
        leave the queue and flow through the normal accepted path;
        everything else stays parked for a future drain call."""
        if not self._backorder_queue:
            return
        pending = self._backorder_queue
        self._backorder_queue = []
        for order in pending:
            verdict = self.estimate(order, now)
            if verdict.feasible and not verdict.displaced_orders:
                self._commit(order, now, TIER_ON_TIME, "accepted", verdict)
            else:
                self._backorder_queue.append(order)

    def cancel(self, order_id: str, now: datetime) -> CancelResult:
        """Cancel an accepted order and refund its unstarted burgers.

        Burgers whose recorded ``cook_start >= now`` have their
        ingredients returned to the timeline (the burger has not yet
        physically consumed anything at ``now``). Burgers whose cook
        started strictly before ``now`` are sunk cost — their consumption
        events remain in the timeline even after the order is forgotten.
        After cancellation, all surviving orders are re-simulated and
        their consumption events re-pinned to the new cook_starts.
        """
        if order_id not in self._order_meta:
            raise KeyError(
                "order {} is not admitted".format(order_id))

        refunded = self._timeline.refund(order_id, min_cook_start=now)
        self._order_meta.pop(order_id)
        self._assignments.pop(order_id, None)

        new_plan = self._simulate(now=now)
        for oid in self._order_meta:
            per_order = _consumptions_from_plan(new_plan, oid)
            self._timeline.replace_order(oid, per_order)
        self._assignments = new_plan

        self._drain_backorder_queue(now)
        return CancelResult(order_id=order_id, refunded=refunded)

    def current_stock(self, now: datetime) -> Dict[str, int]:
        """Return the projected available stock at wall-clock ``now``."""
        return self._timeline.current_stock(now)

    @property
    def backorder_queue(self) -> List[Order]:
        """Read-only view of orders parked pending retry."""
        return list(self._backorder_queue)

    def snapshot(self) -> dict:
        """Return a batch-shaped view compatible with the legacy API."""
        orders_out = []
        for oid, meta in sorted(
                self._order_meta.items(),
                key=lambda kv: (kv[1].arrival, kv[0])):
            burgers = self._assignments.get(oid, [])
            if not burgers:
                continue
            end = max(b.pkg_end for b in burgers)
            orders_out.append({
                "order_id": oid,
                "start": meta.arrival,
                "end": end,
                "limit": meta.deadline,
                "on_time": end <= meta.deadline,
                "tier": meta.tier,
                "status": meta.status,
                "burgers": [_burger_to_dict(b) for b in burgers],
            })
        return {
            "orders": orders_out,
            "skipped": list(self._rejected),
            "backordered_pending": [o.order_id
                                    for o in self._backorder_queue],
        }

    # ----- internals -----

    def _record_rejection(self, order: Order, reason: str) -> AdmissionResult:
        self._rejected.append({"order_id": order.order_id, "reason": reason})
        return AdmissionResult(
            status="rejected",
            verdict=AdmissionVerdict(
                feasible=False,
                projected_end=datetime.min,
                lateness=timedelta(0),
            ),
            reason=reason,
        )

    def _simulate(self,
                  now: datetime,
                  new_order: Optional[Order] = None,
                  new_tier: int = TIER_ON_TIME
                  ) -> Dict[str, List[BurgerAssignment]]:
        """Produce a fresh per-order assignment dict reflecting the current
        plan plus (optionally) a hypothetical new order.

        Freezing is **per stage**: a burger whose cook has started is locked
        at cook, but its assembly and packaging can still be reassigned by
        a higher-priority newcomer. This is what lets a late-arriving
        tier-0 order jump the assembly queue past a tier-1 burger that is
        done cooking but has not yet been assembled.
        """
        states: List[dict] = []

        for oid, burgers in self._assignments.items():
            meta = self._order_meta[oid]
            order_size = len(meta.order.burgers)
            priority = getattr(meta.order, "priority", 0)
            for ba in burgers:
                states.append({
                    "tier": meta.tier,
                    "priority": priority,
                    "order_size": order_size,
                    "deadline": meta.deadline,
                    "arrival": meta.arrival,
                    "oid": oid,
                    "item_id": ba.item_id,
                    "ingredients": ba.ingredients,
                    "cook_frozen": ba.cook_start <= now,
                    "asm_frozen": ba.asm_start <= now,
                    "pkg_frozen": ba.pkg_start <= now,
                    "cook_worker": ba.cook_worker,
                    "cook_start": ba.cook_start,
                    "cook_end": ba.cook_end,
                    "asm_worker": ba.asm_worker,
                    "asm_start": ba.asm_start,
                    "asm_end": ba.asm_end,
                    "pkg_worker": ba.pkg_worker,
                    "pkg_start": ba.pkg_start,
                    "pkg_end": ba.pkg_end,
                })

        if new_order is not None:
            new_deadline = now + timedelta(
                minutes=new_order.max_order_completion_time)
            new_priority = getattr(new_order, "priority", 0)
            new_order_size = len(new_order.burgers)
            for item in new_order.burgers:
                states.append({
                    "tier": new_tier,
                    "priority": new_priority,
                    "order_size": new_order_size,
                    "deadline": new_deadline,
                    "arrival": now,
                    "oid": new_order.order_id,
                    "item_id": item.item_id,
                    "ingredients": item.ingredients,
                    "cook_frozen": False,
                    "asm_frozen": False,
                    "pkg_frozen": False,
                    "cook_worker": -1,
                    "cook_start": None,
                    "cook_end": None,
                    "asm_worker": -1,
                    "asm_start": None,
                    "asm_end": None,
                    "pkg_worker": -1,
                    "pkg_start": None,
                    "pkg_end": None,
                })

        # Track per-worker "earliest free" wall-clock times so we can honour
        # frozen burgers before the heap is built. Base workers are free
        # from ``now``; extra shift workers are free from their shift
        # start (or ``now`` if the shift has already begun).
        cook_free = [now] * self._cook_cap + [
            max(now, s) for s in self._cook_shift_starts]
        asm_free = [now] * self._asm_cap + [
            max(now, s) for s in self._asm_shift_starts]
        pkg_free = [now] * self._pkg_cap + [
            max(now, s) for s in self._pkg_shift_starts]

        for s in states:
            if s["cook_frozen"] and s["cook_end"] > cook_free[s["cook_worker"]]:
                cook_free[s["cook_worker"]] = s["cook_end"]
            if s["asm_frozen"] and s["asm_end"] > asm_free[s["asm_worker"]]:
                asm_free[s["asm_worker"]] = s["asm_end"]
            if s["pkg_frozen"] and s["pkg_end"] > pkg_free[s["pkg_worker"]]:
                pkg_free[s["pkg_worker"]] = s["pkg_end"]

        # Min-heap of (free_at, worker_idx) per stage: O(log w) per pick
        # vs O(w) scan in the previous linear implementation.
        cook_heap = [(t, i) for i, t in enumerate(cook_free)]
        asm_heap = [(t, i) for i, t in enumerate(asm_free)]
        pkg_heap = [(t, i) for i, t in enumerate(pkg_free)]
        heapq.heapify(cook_heap)
        heapq.heapify(asm_heap)
        heapq.heapify(pkg_heap)

        states.sort(key=self._dispatch_policy.sort_key)

        for s in states:
            if not s["cook_frozen"]:
                free_at, ci = heapq.heappop(cook_heap)
                not_before = s["arrival"]
                cs = free_at if free_at > not_before else not_before
                ce = cs + self._cook_lead
                heapq.heappush(cook_heap, (ce, ci))
                s["cook_worker"] = ci
                s["cook_start"] = cs
                s["cook_end"] = ce

            if not s["asm_frozen"]:
                free_at, ai = heapq.heappop(asm_heap)
                cook_end = s["cook_end"]
                as_ = free_at if free_at > cook_end else cook_end
                ae = as_ + self._asm_lead
                heapq.heappush(asm_heap, (ae, ai))
                s["asm_worker"] = ai
                s["asm_start"] = as_
                s["asm_end"] = ae

            if not s["pkg_frozen"]:
                free_at, pi = heapq.heappop(pkg_heap)
                asm_end = s["asm_end"]
                ps = free_at if free_at > asm_end else asm_end
                pe = ps + self._pkg_lead
                heapq.heappush(pkg_heap, (pe, pi))
                s["pkg_worker"] = pi
                s["pkg_start"] = ps
                s["pkg_end"] = pe

        grouped: Dict[str, List[BurgerAssignment]] = {}
        for s in states:
            ba = BurgerAssignment(
                order_id=s["oid"],
                item_id=s["item_id"],
                ingredients=s["ingredients"],
                tier=s["tier"],
                cook_worker=s["cook_worker"],
                cook_start=s["cook_start"],
                cook_end=s["cook_end"],
                asm_worker=s["asm_worker"],
                asm_start=s["asm_start"],
                asm_end=s["asm_end"],
                pkg_worker=s["pkg_worker"],
                pkg_start=s["pkg_start"],
                pkg_end=s["pkg_end"],
            )
            grouped.setdefault(ba.order_id, []).append(ba)
        for oid in grouped:
            grouped[oid].sort(key=lambda b: b.item_id)
        return grouped


# ----- helpers -----


def _flatten_shift_starts(shifts, _base_offset: int) -> List[datetime]:
    """Return one start-time per extra worker defined by ``shifts``.

    Each shift entry ``(start, end, extra_cap)`` contributes
    ``extra_cap`` entries — one per additional worker. The ``end`` field
    is ignored in this iteration (see Branch.shifts docstring).
    """
    out: List[datetime] = []
    for start, _end, extra in shifts:
        for _ in range(extra):
            out.append(start)
    return out


def _projected_end(plan: Dict[str, List[BurgerAssignment]],
                   order_id: str) -> datetime:
    burgers = plan.get(order_id)
    if not burgers:
        return datetime.min
    return max(b.pkg_end for b in burgers)


def _consumptions_from_plan(
    plan: Dict[str, List[BurgerAssignment]],
    order_id: Optional[str] = None,
) -> Dict[Tuple[str, int], Tuple[datetime, Dict[str, int]]]:
    """Extract per-burger consumption events from a simulated plan.

    Returns ``{(order_id, item_id): (cook_start, per_burger_ingredients)}``.
    If ``order_id`` is given, restrict the output to burgers belonging to
    that order.
    """
    out: Dict[Tuple[str, int], Tuple[datetime, Dict[str, int]]] = {}
    for oid, burgers in plan.items():
        if order_id is not None and oid != order_id:
            continue
        for b in burgers:
            out[(oid, b.item_id)] = (
                b.cook_start, burger_ingredients(b.ingredients))
    return out


def _burger_to_dict(b: BurgerAssignment) -> dict:
    return {
        "item_id": b.item_id,
        "ingredients": b.ingredients,
        "tier": b.tier,
        "cook_start": b.cook_start,
        "cook_end": b.cook_end,
        "assemble_start": b.asm_start,
        "assemble_end": b.asm_end,
        "package_start": b.pkg_start,
        "package_end": b.pkg_end,
    }


# ----- batch wrapper (backwards-compatible) -----


def schedule_orders(branches, orders, policy: str = "auto_accept",
                    dispatch_policy: Optional[object] = None):
    """Batch entry point. Drives a :class:`BranchScheduler` per branch,
    feeding orders in arrival order.

    policy:
        - ``"auto_accept"`` (default): infeasible orders are committed at
          tier 1 so they don't block feasible ones. Mirrors the v1
          behaviour but with EDF burger-level dispatch.
        - ``"reject_late"``: infeasible orders are dropped into ``skipped``
          with ``reason="deadline_infeasible"``.
        - ``"moore_hodgson"``: online Moore-Hodgson demotion. When a
          newcomer would be tardy, demote the longest tier-0 order(s)
          to tier-1 until the newcomer fits. Minimizes tardy count.
        - ``"spt_batch"``: shortest-processing-time tie-break on arrival.
          Orders sharing a timestamp are admitted smallest-first, which
          shrinks flow time when bursts arrive together. Combined with
          ``auto_accept`` semantics for late orders.
    """
    valid = ("auto_accept", "reject_late", "moore_hodgson",
             "spt_batch", "backorder")
    if policy not in valid:
        raise ValueError("unknown policy: {}".format(policy))

    branches_by_id = {b.branch_id: b for b in branches}
    result = {}

    for branch_id, order_list in orders.items():
        if branch_id not in branches_by_id:
            raise data_reader.NoBranchInfoError(
                "No branch info for branch_id {}".format(branch_id))
        scheduler = BranchScheduler(
            branches_by_id[branch_id],
            dispatch_policy=dispatch_policy)

        if policy == "spt_batch":
            sorted_orders = sorted(
                order_list,
                key=lambda o: (o.date_time, len(o.burgers), o.order_id))
        else:
            sorted_orders = sorted(order_list, key=lambda o: o.date_time)

        for order in sorted_orders:
            now = order.date_time
            if policy == "moore_hodgson":
                scheduler.admit_moore_hodgson(
                    order, now, accept_late=True)
            elif policy == "backorder":
                scheduler.admit(order, now, backorder=True)
            else:
                accept_late = (policy in ("auto_accept", "spt_batch"))
                scheduler.admit(order, now, accept_late=accept_late)

        # Orders still parked in the backorder queue at end-of-run
        # never found a feasible slot; surface them as skipped.
        if policy == "backorder":
            end_snap = scheduler.snapshot()
            for oid in end_snap["backordered_pending"]:
                scheduler._rejected.append({
                    "order_id": oid,
                    "reason": "backorder_stale",
                })

        result[branch_id] = scheduler.snapshot()
    return result


schedule = schedule_orders


if __name__ == "__main__":
    txt_filepath = os.path.join(
        os.path.dirname(__file__), "..", "tests", "Files", "input.txt")
    branches, orders = data_reader.read_input_txt(txt_filepath)
    result = schedule_orders(branches=branches, orders=orders)
    for branch_id, branch_result in result.items():
        on_time = sum(1 for o in branch_result["orders"] if o["on_time"])
        print("Branch {}: {} scheduled ({} on time), {} skipped".format(
            branch_id,
            len(branch_result["orders"]),
            on_time,
            len(branch_result["skipped"])))
        for o in branch_result["orders"]:
            tag = "OK  " if o["on_time"] else "LATE"
            print("  [{}] {} tier={} end={} limit={}".format(
                tag, o["order_id"], o["tier"], o["end"], o["limit"]))
        for s in branch_result["skipped"]:
            print("  [SKIP] {} reason={}".format(
                s["order_id"], s.get("reason")))
