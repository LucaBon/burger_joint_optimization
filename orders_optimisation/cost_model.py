"""Economic cost / SLA model for scoring scheduler outcomes.

The existing metrics layer ([metrics.py](metrics.py)) counts on-time
orders, tardy seconds, flow time, throughput, etc. That's fine for
comparing two schedulers at a glance, but it says nothing about
business value: is it better to refuse an order or to serve it 10
minutes late? A cost model answers that by attaching explicit units
(currency, utility) to each outcome and summing them.

Usage::

    from orders_optimisation.cost_model import CostModel
    from orders_optimisation.metrics import compute_metrics

    cm = CostModel(margin_per_order=6.0,
                   lateness_penalty_per_second=0.01,
                   rejection_cost=3.0)
    m = compute_metrics(result, cost_model=cm)
    print(m["net_value"])

The model is deliberately linear: net_value = revenue − lateness − rejections.
Richer shapes (quadratic SLA penalties, per-tier margins) can be layered
on top in a subclass without changing the metrics plumbing.
"""
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class CostModel:
    """Linear revenue / penalty model for order fulfilment.

    Attributes:
        margin_per_order: Revenue booked when an order is served
            (regardless of tardiness). Use a per-burger figure if your
            revenue scales with order size.
        lateness_penalty_per_second: Subtracted from revenue for every
            second past the deadline. Zero disables the SLA penalty.
        rejection_cost: Flat cost for every order dropped into
            ``skipped`` (deadline- or inventory-infeasible).
        per_burger_margin: Optional surcharge added per burger beyond
            ``margin_per_order`` — models "bigger orders make more
            money" without changing the baseline revenue semantics.
    """
    margin_per_order: float = 0.0
    lateness_penalty_per_second: float = 0.0
    rejection_cost: float = 0.0
    per_burger_margin: float = 0.0

    def revenue_for(self, order: dict) -> float:
        """Per-served-order revenue given a metrics order row."""
        burgers = len(order.get("burgers", []))
        return self.margin_per_order + burgers * self.per_burger_margin

    def lateness_penalty_for(self, order: dict) -> float:
        """Per-served-order lateness penalty in the model's currency."""
        end = order["end"]
        limit = order["limit"]
        tardy_sec = max(0.0, (end - limit).total_seconds())
        return tardy_sec * self.lateness_penalty_per_second

    def aggregate(self, orders: List[dict],
                  skipped: List[dict]) -> Dict[str, float]:
        """Compute total revenue / penalties / rejections / net_value."""
        total_revenue = sum(self.revenue_for(o) for o in orders)
        total_penalty = sum(self.lateness_penalty_for(o) for o in orders)
        total_rejection = self.rejection_cost * len(skipped)
        return {
            "total_revenue": total_revenue,
            "total_lateness_penalty": total_penalty,
            "total_rejection_cost": total_rejection,
            "net_value": total_revenue - total_penalty - total_rejection,
        }
