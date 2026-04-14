"""Tests for :mod:`orders_optimisation.cost_model` and its metrics integration."""
import unittest
from datetime import datetime, timedelta

from orders_optimisation.cost_model import CostModel
from orders_optimisation.metrics import compute_metrics


def _order(order_id, start, end, limit, burgers=1):
    return {
        "order_id": order_id,
        "start": start,
        "end": end,
        "limit": limit,
        "on_time": end <= limit,
        "tier": 0,
        "status": "accepted",
        "burgers": list(range(burgers)),
    }


class TestCostModel(unittest.TestCase):
    def test_revenue_and_penalty_aggregation(self):
        cm = CostModel(margin_per_order=10.0,
                       lateness_penalty_per_second=0.5,
                       rejection_cost=4.0,
                       per_burger_margin=2.0)
        t0 = datetime(2026, 1, 1, 10, 0, 0)
        orders = [
            _order("O1", t0, t0 + timedelta(minutes=5),
                   t0 + timedelta(minutes=10), burgers=2),   # on time
            _order("O2", t0, t0 + timedelta(minutes=15),
                   t0 + timedelta(minutes=10), burgers=3),   # 5 min late
        ]
        skipped = [{"order_id": "O3", "reason": "deadline_infeasible"}]

        agg = cm.aggregate(orders, skipped)
        # revenue = 2 orders * 10 + (2+3) burgers * 2 = 30
        self.assertAlmostEqual(agg["total_revenue"], 30.0)
        # penalty = 300 sec * 0.5 = 150
        self.assertAlmostEqual(agg["total_lateness_penalty"], 150.0)
        # rejection = 1 * 4
        self.assertAlmostEqual(agg["total_rejection_cost"], 4.0)
        # net = 30 - 150 - 4 = -124
        self.assertAlmostEqual(agg["net_value"], -124.0)

    def test_compute_metrics_injects_cost_fields(self):
        cm = CostModel(margin_per_order=5.0, rejection_cost=1.0)
        t0 = datetime(2026, 1, 1, 10, 0, 0)
        result = {
            "R1": {
                "orders": [
                    _order("O1", t0, t0 + timedelta(minutes=5),
                           t0 + timedelta(minutes=10)),
                ],
                "skipped": [{"order_id": "O2", "reason": "x"}],
            }
        }
        m = compute_metrics(result, cost_model=cm)
        self.assertIn("net_value", m)
        self.assertAlmostEqual(m["total_revenue"], 5.0)
        self.assertAlmostEqual(m["total_rejection_cost"], 1.0)
        self.assertAlmostEqual(m["net_value"], 4.0)

    def test_compute_metrics_omits_cost_fields_when_no_model(self):
        m = compute_metrics({"R1": {"orders": [], "skipped": []}})
        self.assertNotIn("net_value", m)
        self.assertNotIn("total_revenue", m)
