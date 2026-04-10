import os
import unittest
import logging
from datetime import datetime

import orders_optimisation.data_reader as data_reader
import orders_optimisation.order_scheduler as ut
from orders_optimisation.branch import Branch
from orders_optimisation.order import Order, Item

formatter = logging.Formatter(
    '%(asctime)s : %(name)s : %(levelname)s : %(message)s'
)
handler = logging.StreamHandler()
handler.setLevel(logging.CRITICAL)
handler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)

FILES_DIR = os.path.join(os.path.dirname(__file__), "Files")


def _make_branch(branch_id="R1",
                 cook_cap=2, cook_lead=1,
                 asm_cap=2, asm_lead=1,
                 pkg_cap=2, pkg_lead=1,
                 inventory=None):
    if inventory is None:
        inventory = {"burgers_patties": 50, "lettuce": 50, "tomato": 50,
                     "veggie_patties": 50, "bacon": 50}
    return Branch(
        branch_id=branch_id,
        cooking={"capacity": cook_cap, "lead_time": cook_lead},
        assembling={"capacity": asm_cap, "lead_time": asm_lead},
        packaging={"capacity": pkg_cap, "lead_time": pkg_lead},
        inventory=inventory,
    )


def _make_order(order_id, date_time, burger_ingredients, branch_id="R1"):
    items = [Item(order_id=order_id, item_id=i, ingredients=ing)
             for i, ing in enumerate(burger_ingredients)]
    return Order(branch_id=branch_id, date_time=date_time,
                 order_id=order_id, hamburgers=items)


class TestOrderScheduler(unittest.TestCase):
    def test_single_order_pipeline_times(self):
        branch = _make_branch(cook_cap=1, cook_lead=2,
                              asm_cap=1, asm_lead=1,
                              pkg_cap=1, pkg_lead=1)
        order = _make_order("O1", "2020-12-08 19:00:00", ["BLT"])

        result = ut.schedule_orders([branch], {"R1": [order]})

        self.assertIn("R1", result)
        branch_result = result["R1"]
        self.assertEqual(len(branch_result["orders"]), 1)
        self.assertEqual(branch_result["skipped"], [])

        scheduled = branch_result["orders"][0]
        self.assertEqual(scheduled["order_id"], "O1")
        self.assertTrue(scheduled["on_time"])
        self.assertEqual(scheduled["start"], datetime(2020, 12, 8, 19, 0, 0))
        # cook 2m + assemble 1m + package 1m = 4m after order time
        self.assertEqual(scheduled["end"], datetime(2020, 12, 8, 19, 4, 0))
        self.assertEqual(scheduled["limit"],
                         datetime(2020, 12, 8, 19, 20, 0))

    def test_cooking_parallelism_uses_earliest_worker(self):
        branch = _make_branch(cook_cap=2, cook_lead=5,
                              asm_cap=2, asm_lead=0,
                              pkg_cap=2, pkg_lead=0)
        # Two burgers should be cooked in parallel by two workers,
        # so order end is only 5 minutes after start (not 10).
        order = _make_order("O1", "2020-12-08 19:00:00", ["BLT", "LT"])

        result = ut.schedule_orders([branch], {"R1": [order]})
        scheduled = result["R1"]["orders"][0]
        self.assertEqual(scheduled["end"], datetime(2020, 12, 8, 19, 5, 0))

    def test_order_exceeding_deadline_is_flagged(self):
        # Single cooking worker with 10-minute lead must sequentially cook
        # three burgers → 30 minutes, past the 20-minute deadline.
        branch = _make_branch(cook_cap=1, cook_lead=10,
                              asm_cap=1, asm_lead=0,
                              pkg_cap=1, pkg_lead=0)
        order = _make_order("O1", "2020-12-08 19:00:00",
                            ["BLT", "LT", "VLT"])

        result = ut.schedule_orders([branch], {"R1": [order]})
        scheduled = result["R1"]["orders"][0]
        self.assertFalse(scheduled["on_time"])
        self.assertEqual(scheduled["end"], datetime(2020, 12, 8, 19, 30, 0))

    def test_inventory_is_decremented(self):
        branch = _make_branch(inventory={
            "burgers_patties": 2, "lettuce": 3, "tomato": 3,
            "veggie_patties": 1, "bacon": 1,
        })
        order = _make_order("O1", "2020-12-08 19:00:00", ["BLT", "VLT"])

        ut.schedule_orders([branch], {"R1": [order]})

        self.assertEqual(branch.inventory, {
            "burgers_patties": 1,  # only BLT consumed one beef patty
            "lettuce": 1,
            "tomato": 1,
            "veggie_patties": 0,
            "bacon": 0,
        })

    def test_exhausted_inventory_skips_order(self):
        branch = _make_branch(inventory={
            "burgers_patties": 0, "lettuce": 1, "tomato": 1,
            "veggie_patties": 0, "bacon": 1,
        })
        order = _make_order("O1", "2020-12-08 19:00:00", ["BLT"])

        result = ut.schedule_orders([branch], {"R1": [order]})
        self.assertEqual(result["R1"]["orders"], [])
        self.assertEqual(len(result["R1"]["skipped"]), 1)
        self.assertEqual(result["R1"]["skipped"][0]["order_id"], "O1")

    def test_unknown_branch_raises(self):
        branch = _make_branch(branch_id="R1")
        order = _make_order("O1", "2020-12-08 19:00:00", ["BLT"],
                            branch_id="R2")
        with self.assertRaises(data_reader.NoBranchInfoError):
            ut.schedule_orders([branch], {"R2": [order]})

    def test_schedule_orders_on_fixture(self):
        input_txt = os.path.join(FILES_DIR, "input.txt")
        branches, orders = data_reader.read_input_txt(input_txt)

        result = ut.schedule_orders(branches=branches, orders=orders)

        self.assertIn("R1", result)
        branch_result = result["R1"]
        self.assertEqual(
            len(branch_result["orders"]) + len(branch_result["skipped"]), 12)
        for scheduled in branch_result["orders"]:
            self.assertEqual(
                len(scheduled["burgers"]),
                sum(1 for _ in scheduled["burgers"]))
            self.assertLessEqual(scheduled["start"], scheduled["end"])

    def test_schedule_alias(self):
        self.assertIs(ut.schedule, ut.schedule_orders)

    # ------- BranchScheduler / online admission tests -------

    def test_estimate_is_non_mutating(self):
        branch = _make_branch()
        sch = ut.BranchScheduler(branch)
        order = _make_order("O1", "2020-12-08 19:00:00", ["BLT", "LT"])
        inv_before = dict(branch.inventory)

        verdict = sch.estimate(order, datetime(2020, 12, 8, 19, 0, 0))

        self.assertTrue(verdict.feasible)
        self.assertEqual(branch.inventory, inv_before)
        self.assertEqual(sch._order_meta, {})
        self.assertEqual(sch._assignments, {})

    def test_estimate_matches_commit(self):
        branch = _make_branch()
        sch = ut.BranchScheduler(branch)
        o1 = _make_order("O1", "2020-12-08 19:00:00", ["BLT", "LT"])
        sch.admit(o1, datetime(2020, 12, 8, 19, 0, 0))

        o2 = _make_order("O2", "2020-12-08 19:00:30", ["VLT", "LT", "BT"])
        now2 = datetime(2020, 12, 8, 19, 0, 30)
        verdict = sch.estimate(o2, now2)
        result = sch.admit(o2, now2)

        committed_end = max(b.pkg_end for b in result.schedule)
        self.assertEqual(committed_end, verdict.projected_end)
        self.assertEqual(result.status, "accepted")

    def test_tier1_does_not_preempt_tier0(self):
        # Tight branch so the big order is forced to tier 1.
        branch = _make_branch(cook_cap=1, cook_lead=1,
                              asm_cap=1, asm_lead=2,
                              pkg_cap=1, pkg_lead=1)
        sch = ut.BranchScheduler(branch)

        # First a big order arrives and eats all tier-0 slack.
        big = _make_order("BIG", "2020-12-08 19:00:00",
                          ["BLT"] * 20)
        sch.admit(big, datetime(2020, 12, 8, 19, 0, 0),
                  accept_late=True)
        self.assertEqual(sch._order_meta["BIG"].tier, ut.TIER_LATE)

        # A small, tight-deadline order arrives a second later.
        small = _make_order("SMALL", "2020-12-08 19:00:01", ["LT"])
        result = sch.admit(small, datetime(2020, 12, 8, 19, 0, 1))
        self.assertEqual(result.status, "accepted")
        self.assertEqual(sch._order_meta["SMALL"].tier, ut.TIER_ON_TIME)

        snap = sch.snapshot()
        rows = {o["order_id"]: o for o in snap["orders"]}
        self.assertTrue(rows["SMALL"]["on_time"])
        self.assertFalse(rows["BIG"]["on_time"])
        # Small's packaging must finish before Big's does.
        self.assertLess(rows["SMALL"]["end"], rows["BIG"]["end"])

    def test_reject_late_policy_drops_infeasible_orders(self):
        input_txt = os.path.join(FILES_DIR, "input.txt")
        branches, orders = data_reader.read_input_txt(input_txt)
        result = ut.schedule_orders(
            branches=branches, orders=orders, policy="reject_late")

        self.assertGreater(len(result["R1"]["skipped"]), 0)
        for row in result["R1"]["skipped"]:
            self.assertEqual(row["reason"], "deadline_infeasible")
        for row in result["R1"]["orders"]:
            self.assertTrue(row["on_time"])

    def test_auto_accept_beats_fcfs_on_fixture(self):
        input_txt = os.path.join(FILES_DIR, "input.txt")
        branches, orders = data_reader.read_input_txt(input_txt)
        result = ut.schedule_orders(
            branches=branches, orders=orders, policy="auto_accept")

        on_time = sum(
            1 for o in result["R1"]["orders"] if o["on_time"])
        # Baseline FCFS scheduler delivered 5/12. Target is >= 8.
        self.assertGreaterEqual(on_time, 8)
        self.assertEqual(
            len(result["R1"]["orders"]) + len(result["R1"]["skipped"]),
            12)

    def test_rejected_order_does_not_consume_inventory(self):
        branch = _make_branch(cook_cap=1, cook_lead=1,
                              asm_cap=1, asm_lead=2,
                              pkg_cap=1, pkg_lead=1,
                              inventory={
                                  "burgers_patties": 30, "lettuce": 30,
                                  "tomato": 30, "veggie_patties": 30,
                                  "bacon": 30,
                              })
        sch = ut.BranchScheduler(branch)
        huge = _make_order("HUGE", "2020-12-08 19:00:00", ["BLT"] * 25)

        result = sch.admit(huge, datetime(2020, 12, 8, 19, 0, 0),
                           accept_late=False)

        self.assertEqual(result.status, "rejected")
        self.assertFalse(result.verdict.feasible)
        self.assertGreater(result.verdict.lateness.total_seconds(), 0)
        # Inventory must not have been touched.
        self.assertEqual(branch.inventory["burgers_patties"], 30)
        self.assertEqual(branch.inventory["lettuce"], 30)

    def test_admit_twice_raises(self):
        branch = _make_branch()
        sch = ut.BranchScheduler(branch)
        order = _make_order("O1", "2020-12-08 19:00:00", ["BLT"])
        sch.admit(order, datetime(2020, 12, 8, 19, 0, 0))
        with self.assertRaises(ValueError):
            sch.admit(order, datetime(2020, 12, 8, 19, 0, 5))
