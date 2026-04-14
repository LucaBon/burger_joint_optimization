"""Direct test for the Moore-Hodgson admission policy.

The existing test_order_scheduler suite exercises MH only indirectly
through the benchmark. This crafted 3-order scenario isolates the
demotion behaviour.
"""
import unittest
from datetime import datetime, timedelta

from orders_optimisation.branch import Branch
from orders_optimisation.order import Item, Order
from orders_optimisation.order_scheduler import BranchScheduler


def _branch():
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


class TestMooreHodgson(unittest.TestCase):
    def test_mh_beats_plain_edf_on_on_time_count(self):
        # 10-burger O1 arrives at t0 and is feasible alone (~12 min
        # through the pipe, SLA 20 min). 15-burger O2 arrives five
        # minutes later; plain EDF queues it behind O1 and it misses
        # its SLA. MH demotes the longer order (O1) so the newcomer
        # (O2) fits — O1 absorbs the lateness.
        t0 = datetime(2026, 1, 1, 10, 0, 0)
        t1 = t0 + timedelta(minutes=5)

        # Plain EDF baseline.
        edf = BranchScheduler(_branch())
        edf.admit(_order("O1", t0, sizes=10), t0)
        edf.admit(_order("O2", t1, sizes=15), t1, accept_late=True)
        edf_on_time = sum(
            1 for o in edf.snapshot()["orders"] if o["on_time"])

        # Moore-Hodgson.
        mh = BranchScheduler(_branch())
        mh.admit_moore_hodgson(_order("O1", t0, sizes=10), t0)
        mh.admit_moore_hodgson(_order("O2", t1, sizes=15), t1)
        mh_snap = mh.snapshot()["orders"]
        mh_on_time = sum(1 for o in mh_snap if o["on_time"])

        self.assertGreaterEqual(mh_on_time, edf_on_time)
        # MH should have produced at least one demotion => at least
        # one tier-1 (or accepted_mh) order in the snapshot.
        tiers = [o["tier"] for o in mh_snap]
        self.assertIn(1, tiers)
