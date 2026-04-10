"""Multi-branch dispatching / load balancing.

Wraps one :class:`~orders_optimisation.order_scheduler.BranchScheduler` per
branch and routes each incoming order to whichever branch's ``estimate``
returns the best verdict (feasible first, then lowest lateness). Orders are
processed in global chronological order so a later arrival can still benefit
from slack freed elsewhere.
"""
from datetime import datetime
from typing import Dict, List

from .branch import Branch
from .order import InvalidIngredientError, Order
from .order_scheduler import (
    AdmissionResult,
    AdmissionVerdict,
    BranchScheduler,
    DATE_FORMAT,
    _inventory_covers,
)


class MultiBranchDispatcher:
    """Routes orders across multiple :class:`BranchScheduler` instances."""

    def __init__(self, branches: List[Branch], policy: str = "auto_accept"):
        if policy not in ("auto_accept", "reject_late", "moore_hodgson"):
            raise ValueError("unknown policy: {}".format(policy))
        self._policy = policy
        self._schedulers: Dict[str, BranchScheduler] = {
            b.branch_id: BranchScheduler(b) for b in branches
        }

    def admit(self, order: Order, now: datetime) -> AdmissionResult:
        try:
            required = order.calculate_order_ingredients()
        except InvalidIngredientError:
            # Let the home branch record the rejection cleanly.
            home = self._schedulers[order.branch_id]
            return home.admit(order, now, accept_late=False)

        candidates = []
        for bid, sch in self._schedulers.items():
            if not _inventory_covers(sch._branch.inventory, required):
                continue
            verdict = sch.estimate(order, now)
            candidates.append((bid, sch, verdict))

        if not candidates:
            home = self._schedulers[order.branch_id]
            return home.admit(order, now, accept_late=False)

        # Rank: feasible first, then smallest lateness, then earliest end.
        candidates.sort(
            key=lambda c: (
                0 if c[2].feasible else 1,
                c[2].lateness,
                c[2].projected_end,
            )
        )
        _bid, sch, _verdict = candidates[0]
        return self._dispatch_admit(sch, order, now)

    def _dispatch_admit(self, sch: BranchScheduler,
                        order: Order, now: datetime) -> AdmissionResult:
        if self._policy == "moore_hodgson":
            return sch.admit_moore_hodgson(order, now, accept_late=True)
        accept_late = (self._policy == "auto_accept")
        return sch.admit(order, now, accept_late=accept_late)

    def snapshot(self) -> Dict[str, dict]:
        return {bid: sch.snapshot() for bid, sch in self._schedulers.items()}


def schedule_orders_load_balanced(branches: List[Branch],
                                  orders: Dict[str, List[Order]],
                                  policy: str = "auto_accept"
                                  ) -> Dict[str, dict]:
    """Batch entry point that uses :class:`MultiBranchDispatcher`.

    Orders from all branches are merged, globally sorted by arrival time,
    and each is offered to every branch via ``estimate``. The best verdict
    wins, regardless of the ``order.branch_id`` the order was filed under.
    """
    dispatcher = MultiBranchDispatcher(branches, policy=policy)

    all_orders: List[Order] = []
    for order_list in orders.values():
        all_orders.extend(order_list)
    all_orders.sort(key=lambda o: o.date_time)

    for order in all_orders:
        now = datetime.strptime(order.date_time, DATE_FORMAT)
        dispatcher.admit(order, now)

    return dispatcher.snapshot()
