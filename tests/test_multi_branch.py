"""Unit tests for :mod:`orders_optimisation.multi_branch`."""
import unittest
from datetime import datetime

from orders_optimisation.branch import Branch
from orders_optimisation.multi_branch import (
    MultiBranchDispatcher, schedule_orders_load_balanced,
)
from orders_optimisation.order import Item, Order


def _branch(bid, cook_cap=1):
    return Branch(
        branch_id=bid,
        cooking={"capacity": cook_cap, "lead_time": 1},
        assembling={"capacity": 1, "lead_time": 1},
        packaging={"capacity": 1, "lead_time": 1},
        inventory={"burgers_patties": 100, "lettuce": 100, "tomato": 100,
                   "veggie_patties": 100, "bacon": 100},
    )


def _order(order_id, arrival, sizes, home="R1"):
    items = [Item(order_id=order_id, item_id=i, ingredients="BLT")
             for i in range(sizes)]
    return Order(branch_id=home, date_time=arrival, order_id=order_id,
                 hamburgers=items)


class TestMultiBranchDispatcher(unittest.TestCase):
    def test_reroutes_to_idle_branch(self):
        # R1 is pre-loaded, R2 is idle. An order filed against R1 should
        # be routed to R2 by the dispatcher because R2's estimate wins.
        branches = [_branch("R1"), _branch("R2")]
        disp = MultiBranchDispatcher(branches)
        t0 = datetime(2026, 1, 1, 10, 0, 0)
        # Pre-load R1 so its queue is non-empty.
        disp._schedulers["R1"].admit(
            _order("O0", t0, sizes=10, home="R1"), t0, accept_late=True)

        result = disp.admit(_order("O1", t0, sizes=1, home="R1"), t0)
        self.assertEqual(result.status, "accepted")

        snap = disp.snapshot()
        r1_ids = [o["order_id"] for o in snap["R1"]["orders"]]
        r2_ids = [o["order_id"] for o in snap["R2"]["orders"]]
        self.assertIn("O1", r2_ids)
        self.assertNotIn("O1", r1_ids)

    def test_unknown_policy_raises(self):
        with self.assertRaises(ValueError):
            MultiBranchDispatcher([_branch("R1")], policy="nope")

    def test_snapshot_has_one_entry_per_branch(self):
        branches = [_branch("R1"), _branch("R2"), _branch("R3")]
        disp = MultiBranchDispatcher(branches)
        snap = disp.snapshot()
        self.assertEqual(set(snap.keys()), {"R1", "R2", "R3"})

    def test_schedule_orders_load_balanced_reroutes(self):
        branches = [_branch("R1"), _branch("R2")]
        t0 = datetime(2026, 1, 1, 10, 0, 0)
        # All 4 orders filed at R1 — without rerouting, R1 alone gets
        # them and the last one runs late. With load balancing, R2
        # picks up half and every order finishes on time.
        orders = {
            "R1": [
                _order("O{}".format(i), t0, sizes=3, home="R1")
                for i in range(4)
            ],
            "R2": [],
        }
        result = schedule_orders_load_balanced(branches, orders)
        all_scheduled = [o for branch_res in result.values()
                         for o in branch_res["orders"]]
        self.assertEqual(len(all_scheduled), 4)
        self.assertTrue(all(o["on_time"] for o in all_scheduled))
        # Work should be genuinely spread, not all concentrated on R1.
        self.assertGreater(len(result["R2"]["orders"]), 0)
