"""Scale / perf regression guard for the scheduler.

Asserts that the 1000-order synthetic fixture runs in well under a
generous wall-clock budget. The budget is deliberately loose so CI
doesn't flap on slow runners, but it is tight enough to catch an
accidental reintroduction of O(n^2) worker picking or similar.
"""
import time
import unittest

from orders_optimisation.order_scheduler import schedule_orders

from tests.fixtures.gen_synthetic import make_stream


class TestPerformance(unittest.TestCase):
    def test_scheduler_handles_1000_orders_under_budget(self):
        branches, orders = make_stream(n=1000)

        t0 = time.perf_counter()
        result = schedule_orders(branches, orders, policy="auto_accept")
        elapsed = time.perf_counter() - t0

        scheduled = result["R1"]["orders"]
        self.assertEqual(len(scheduled), 1000)
        # Loose: CI runners vary wildly. The pre-heap O(n^2) version
        # blew well past this on 1000 orders.
        self.assertLess(
            elapsed, 30.0,
            "1000-order schedule took {:.1f}s (budget 30s)".format(elapsed))
