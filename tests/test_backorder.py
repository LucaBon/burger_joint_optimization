"""Tests for the backorder queue feature."""
import unittest
from datetime import datetime

from orders_optimisation.branch import Branch
from orders_optimisation.order import Item, Order
from orders_optimisation.order_scheduler import (
    BranchScheduler, schedule_orders,
)


def _tight_branch():
    # One worker per stage, 1-min lead. Anything more than ~1 burger in
    # a 20-min SLA window past a backlog becomes deadline-infeasible.
    return Branch(
        branch_id="R1",
        cooking={"capacity": 1, "lead_time": 1},
        assembling={"capacity": 1, "lead_time": 1},
        packaging={"capacity": 1, "lead_time": 1},
        inventory={"burgers_patties": 100, "lettuce": 100, "tomato": 100,
                   "veggie_patties": 100, "bacon": 100},
    )


def _order(order_id, arrival, sizes):
    items = [Item(order_id=order_id, item_id=i, ingredients="BLT")
             for i in range(sizes)]
    return Order(branch_id="R1", date_time=arrival, order_id=order_id,
                 hamburgers=items)


class TestBackorderQueue(unittest.TestCase):
    def test_infeasible_order_is_parked_not_rejected(self):
        sch = BranchScheduler(_tight_branch())
        t0 = datetime(2026, 1, 1, 10, 0, 0)
        # Fill the pipeline with a large feasible order first.
        sch.admit(_order("O1", t0, sizes=5), t0, accept_late=True)
        # A 30-burger order at the same time can't possibly hit the
        # 20-min SLA; with backorder=True it's parked instead.
        big = _order("O2", t0, sizes=30)
        result = sch.admit(big, t0, backorder=True)
        self.assertEqual(result.status, "backordered")
        self.assertIn("O2", [o.order_id for o in sch.backorder_queue])
        self.assertEqual(len(sch.snapshot()["skipped"]), 0)

    def test_backorder_becomes_accepted_after_cancel(self):
        sch = BranchScheduler(_tight_branch())
        t0 = datetime(2026, 1, 1, 10, 0, 0)

        # O1 is a feasible tier-0 order that still hogs 15 minutes
        # worth of the pipeline. O2, arriving right after, can no
        # longer fit inside its own 20-minute SLA while O1 holds the
        # queue, so it goes into the backorder parking lot.
        sch.admit(_order("O1", t0, sizes=15), t0)
        result = sch.admit(_order("O2", t0, sizes=5), t0, backorder=True)
        self.assertEqual(result.status, "backordered")

        # Cancelling O1 frees enough capacity for O2 to come through.
        sch.cancel("O1", now=t0)
        self.assertEqual(sch.backorder_queue, [])
        snap = sch.snapshot()
        scheduled_ids = [o["order_id"] for o in snap["orders"]]
        self.assertIn("O2", scheduled_ids)
        self.assertEqual(len(snap["backordered_pending"]), 0)

    def test_inventory_exhausted_bypasses_backorder(self):
        # No inventory => immediate reject, not queueing.
        branch = Branch(
            branch_id="R1",
            cooking={"capacity": 1, "lead_time": 1},
            assembling={"capacity": 1, "lead_time": 1},
            packaging={"capacity": 1, "lead_time": 1},
            inventory={"burgers_patties": 0, "lettuce": 0, "tomato": 0,
                       "veggie_patties": 0, "bacon": 0},
        )
        sch = BranchScheduler(branch)
        result = sch.admit(
            _order("O1", datetime(2026, 1, 1, 10, 0, 0), sizes=1),
            datetime(2026, 1, 1, 10, 0, 0), backorder=True)
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reason, "inventory_exhausted")
        self.assertEqual(sch.backorder_queue, [])

    def test_schedule_orders_backorder_policy_marks_stale_as_skipped(self):
        # A flood of same-timestamp orders with no chance of clearing.
        branch = _tight_branch()
        t0 = datetime(2026, 1, 1, 10, 0, 0)
        orders = [_order("O{}".format(i), t0, sizes=10) for i in range(5)]
        result = schedule_orders(
            [branch], {"R1": orders}, policy="backorder")
        # At least one should be marked stale (couldn't clear by EoR).
        reasons = [s["reason"] for s in result["R1"]["skipped"]]
        self.assertIn("backorder_stale", reasons)
