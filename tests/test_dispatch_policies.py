"""Tests for pluggable dispatch policies and Order priority plumbing."""
import unittest
from datetime import datetime

from orders_optimisation.branch import Branch
from orders_optimisation.data_reader import read_input_txt
from orders_optimisation.dispatch_policies import (
    EDFPolicy, SPTPolicy, WSPTPolicy, get_policy,
)
from orders_optimisation.order import Item, Order
from orders_optimisation.order_scheduler import (
    BranchScheduler, schedule_orders,
)


def _branch(cook=1, asm=1, pkg=1):
    return Branch(
        branch_id="R1",
        cooking={"capacity": cook, "lead_time": 1},
        assembling={"capacity": asm, "lead_time": 1},
        packaging={"capacity": pkg, "lead_time": 1},
        inventory={"burgers_patties": 100, "lettuce": 100, "tomato": 100,
                   "veggie_patties": 100, "bacon": 100},
    )


def _order(order_id, arrival, sizes, priority=0):
    items = [Item(order_id=order_id, item_id=i, ingredients="BLT")
             for i in range(sizes)]
    return Order(branch_id="R1", date_time=arrival, order_id=order_id,
                 hamburgers=items, priority=priority)


class TestDispatchPolicies(unittest.TestCase):
    def test_get_policy_default_is_edf(self):
        p = get_policy(None)
        self.assertIsInstance(p, EDFPolicy)

    def test_get_policy_by_name(self):
        self.assertIsInstance(get_policy("spt"), SPTPolicy)
        self.assertIsInstance(get_policy("wspt"), WSPTPolicy)
        self.assertIsInstance(get_policy("edf"), EDFPolicy)

    def test_get_policy_unknown_name_raises(self):
        with self.assertRaises(ValueError):
            get_policy("nope")

    def test_priority_order_finishes_before_regular_under_edf(self):
        # Same arrival -> same deadline. Without priority, EDF would
        # tiebreak on order_id (O1 first). With priority=5 on O2, O2
        # should finish strictly before O1 even though it arrived
        # simultaneously.
        now = datetime(2026, 1, 1, 10, 0, 0)
        sch = BranchScheduler(_branch())
        big = _order("O1", now, sizes=3, priority=0)
        vip = _order("O2", now, sizes=1, priority=5)
        sch.admit(big, now, accept_late=True)
        sch.admit(vip, now, accept_late=True)
        snap = sch.snapshot()["orders"]
        by_id = {o["order_id"]: o for o in snap}
        self.assertLess(by_id["O2"]["end"], by_id["O1"]["end"])

    def test_spt_policy_prefers_shorter_orders(self):
        # Two orders, simultaneous arrival, no priority. EDF will honour
        # order_id; SPT should pick the 1-burger order first regardless.
        now = datetime(2026, 1, 1, 10, 0, 0)
        big = _order("O1", now, sizes=4)
        small = _order("O2", now, sizes=1)

        edf_sch = BranchScheduler(_branch(), dispatch_policy="edf")
        edf_sch.admit(big, now, accept_late=True)
        edf_sch.admit(small, now, accept_late=True)
        edf_ends = {o["order_id"]: o["end"]
                    for o in edf_sch.snapshot()["orders"]}

        spt_sch = BranchScheduler(_branch(), dispatch_policy="spt")
        spt_sch.admit(big, now, accept_late=True)
        spt_sch.admit(small, now, accept_late=True)
        spt_ends = {o["order_id"]: o["end"]
                    for o in spt_sch.snapshot()["orders"]}

        # SPT gets the small order out sooner than EDF does.
        self.assertLess(spt_ends["O2"], edf_ends["O2"])

    def test_schedule_orders_accepts_dispatch_policy_arg(self):
        branches, orders = read_input_txt(
            "tests/Files/priority_input.txt")
        result_edf = schedule_orders(branches, orders, policy="auto_accept")
        result_spt = schedule_orders(branches, orders, policy="auto_accept",
                                     dispatch_policy="spt")
        # Both should schedule all orders without skips on this fixture.
        for r in (result_edf, result_spt):
            self.assertEqual(len(r["R1"]["orders"]), 2)
            self.assertEqual(len(r["R1"]["skipped"]), 0)

    def test_priority_parser_reads_p_token(self):
        branches, orders = read_input_txt(
            "tests/Files/priority_input.txt")
        by_id = {o.order_id: o for o in orders["R1"]}
        self.assertEqual(by_id["O1"].priority, 0)
        self.assertEqual(by_id["O2"].priority, 5)

    def test_order_priority_validation(self):
        with self.assertRaises(ValueError):
            Order(branch_id="R1",
                  date_time="2026-01-01 10:00:00",
                  order_id="O1",
                  hamburgers=[],
                  priority=-1)


class TestInvalidIngredientItem(unittest.TestCase):
    def test_item_rejects_unknown_ingredient_code(self):
        from orders_optimisation.order import InvalidIngredientError
        with self.assertRaises(InvalidIngredientError):
            Item(order_id="O1", item_id=0, ingredients="BLX")

    def test_item_rejects_empty_ingredients(self):
        from orders_optimisation.order import InvalidIngredientError
        with self.assertRaises(InvalidIngredientError):
            Item(order_id="O1", item_id=0, ingredients="")


if __name__ == "__main__":
    unittest.main()
