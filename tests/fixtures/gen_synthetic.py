"""Deterministic synthetic fixtures for scale / perf testing.

Produces :class:`Branch` + per-branch :class:`Order` lists without
touching the filesystem. The generated streams are seeded so runs are
reproducible across machines and CI.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from orders_optimisation.branch import Branch
from orders_optimisation.order import Item, Order


_BASE_T = datetime(2026, 1, 1, 9, 0, 0)

_BURGER_PATTERNS = ("BLT", "LT", "VLT", "BL", "VT", "BLTV", "L", "T", "VB")


def make_branch(branch_id: str = "R1",
                cook_cap: int = 20,
                asm_cap: int = 15,
                pkg_cap: int = 10,
                stock: int = 10_000) -> Branch:
    return Branch(
        branch_id=branch_id,
        cooking={"capacity": cook_cap, "lead_time": 1},
        assembling={"capacity": asm_cap, "lead_time": 1},
        packaging={"capacity": pkg_cap, "lead_time": 1},
        inventory={
            "burgers_patties": stock,
            "lettuce": stock,
            "tomato": stock,
            "veggie_patties": stock,
            "bacon": stock,
        },
    )


def make_orders(n: int,
                branch_id: str = "R1",
                seed: int = 1234,
                arrival_spacing_seconds: int = 30,
                burgers_per_order: Tuple[int, int] = (1, 4)
                ) -> List[Order]:
    """Generate ``n`` orders arriving at a steady cadence.

    The cadence is intentionally steady (no bursts) so perf tests
    measure scheduler cost, not inventory contention.
    """
    rng = random.Random(seed)
    orders: List[Order] = []
    lo, hi = burgers_per_order
    for i in range(n):
        arrival = _BASE_T + timedelta(seconds=i * arrival_spacing_seconds)
        k = rng.randint(lo, hi)
        items = [
            Item(order_id="O{}".format(i),
                 item_id=j,
                 ingredients=rng.choice(_BURGER_PATTERNS))
            for j in range(k)
        ]
        orders.append(Order(branch_id=branch_id,
                            date_time=arrival,
                            order_id="O{}".format(i),
                            hamburgers=items))
    return orders


def make_stream(n: int) -> Tuple[List[Branch], Dict[str, List[Order]]]:
    """Return ``(branches, orders_by_branch)`` ready for ``schedule_orders``."""
    branch = make_branch()
    orders = make_orders(n)
    return [branch], {branch.branch_id: orders}
