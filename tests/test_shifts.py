"""Tests for the optional worker-shift capacity layer on ``Branch``."""
import unittest
from datetime import datetime, timedelta

from orders_optimisation.branch import Branch
from orders_optimisation.order import Item, Order
from orders_optimisation.order_scheduler import BranchScheduler


def _tiny_branch(shifts=None):
    return Branch(
        branch_id="R1",
        cooking={"capacity": 1, "lead_time": 1},
        assembling={"capacity": 1, "lead_time": 1},
        packaging={"capacity": 1, "lead_time": 1},
        inventory={"burgers_patties": 100, "lettuce": 100, "tomato": 100,
                   "veggie_patties": 100, "bacon": 100},
        shifts=shifts,
    )


def _order(order_id, arrival, sizes):
    items = [Item(order_id=order_id, item_id=i, ingredients="BLT")
             for i in range(sizes)]
    return Order(branch_id="R1", date_time=arrival, order_id=order_id,
                 hamburgers=items)


class TestShifts(unittest.TestCase):
    def test_shifts_accept_valid_payload(self):
        b = _tiny_branch(shifts={
            "cooking": [
                (datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 12), 2)
            ]
        })
        self.assertEqual(len(b.shifts_for("cooking")), 1)
        self.assertEqual(b.shifts_for("assembling"), [])

    def test_shifts_reject_unknown_stage(self):
        with self.assertRaises(ValueError):
            _tiny_branch(shifts={"frying": []})

    def test_shifts_reject_non_positive_extra(self):
        with self.assertRaises(ValueError):
            _tiny_branch(shifts={
                "cooking": [
                    (datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 12), 0)
                ]
            })

    def test_extra_shift_workers_raise_throughput(self):
        # A burst of 6 1-burger orders hits at exactly the same time.
        # With 1 cook worker and 1-min cook lead, the fastest order
        # finishes at minute 3 (cook+asm+pkg) and the slowest at minute
        # 8. With a shift adding +2 cook workers from the same moment,
        # the bottleneck moves off cooking and overall makespan shrinks.
        now = datetime(2026, 1, 1, 10, 0, 0)

        def _run(shifts):
            sch = BranchScheduler(_tiny_branch(shifts=shifts))
            for i in range(6):
                sch.admit(_order("O{}".format(i), now, sizes=1),
                          now, accept_late=True)
            snap = sch.snapshot()["orders"]
            return max(o["end"] for o in snap)

        baseline_end = _run(None)
        window = (now, now + timedelta(hours=1), 2)
        boosted_end = _run({
            "cooking": [window],
            "assembling": [window],
            "packaging": [window],
        })
        self.assertLess(
            boosted_end, baseline_end,
            "boosted makespan {} should beat baseline {}".format(
                boosted_end, baseline_end))

    def test_future_shift_does_not_help_immediate_burst(self):
        # Extra workers arrive two hours after the burst — they cannot
        # retroactively speed up an already-dispatched workload, so
        # makespan must equal the no-shift baseline.
        now = datetime(2026, 1, 1, 10, 0, 0)
        later = now + timedelta(hours=2)

        def _run(shifts):
            sch = BranchScheduler(_tiny_branch(shifts=shifts))
            for i in range(4):
                sch.admit(_order("O{}".format(i), now, sizes=1),
                          now, accept_late=True)
            snap = sch.snapshot()["orders"]
            return max(o["end"] for o in snap)

        self.assertEqual(
            _run(None),
            _run({"cooking": [(later, later + timedelta(hours=1), 4)]}),
        )
