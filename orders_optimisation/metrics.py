"""Performance metrics for burger-joint scheduler evaluation.

Takes a ``schedule_orders`` result (``{branch_id: {"orders": [...], "skipped": [...]}}``)
and returns a flat dict of aggregated KPIs. Metrics are intentionally
scheduler-agnostic so any policy can be scored with the same yardstick.
"""
from datetime import datetime
from typing import Dict, List, Tuple


def _flatten_orders(result: Dict[str, dict]) -> List[dict]:
    out = []
    for branch_id, branch_res in result.items():
        for o in branch_res["orders"]:
            d = dict(o)
            d["_branch_id"] = branch_id
            out.append(d)
    return out


def _flatten_skipped(result: Dict[str, dict]) -> List[dict]:
    out = []
    for branch_id, branch_res in result.items():
        for s in branch_res["skipped"]:
            d = dict(s)
            d["_branch_id"] = branch_id
            out.append(d)
    return out


def compute_metrics(result: Dict[str, dict]) -> dict:
    """Compute global KPIs across all branches in a schedule result."""
    orders = _flatten_orders(result)
    skipped = _flatten_skipped(result)
    total = len(orders) + len(skipped)

    on_time = [o for o in orders if o["on_time"]]
    tardy = [o for o in orders if not o["on_time"]]

    tardiness_sec = [
        max(0.0, (o["end"] - o["limit"]).total_seconds()) for o in orders
    ]
    total_tardiness = sum(tardiness_sec)
    max_tardiness = max(tardiness_sec) if tardiness_sec else 0.0

    flow_times = [(o["end"] - o["start"]).total_seconds() for o in orders]
    avg_flow = sum(flow_times) / len(flow_times) if flow_times else 0.0
    max_flow = max(flow_times) if flow_times else 0.0

    if orders:
        starts = [o["start"] for o in orders]
        ends = [o["end"] for o in orders]
        makespan_sec = (max(ends) - min(starts)).total_seconds()
    else:
        makespan_sec = 0.0

    served = len(orders)
    throughput_per_hour = (
        (served / makespan_sec * 3600.0) if makespan_sec > 0 else 0.0
    )

    tier0 = sum(1 for o in orders if o.get("tier", 0) == 0)
    tier1 = sum(1 for o in orders if o.get("tier", 0) == 1)

    return {
        "orders_total": total,
        "orders_scheduled": len(orders),
        "orders_skipped": len(skipped),
        "on_time_count": len(on_time),
        "tardy_count": len(tardy),
        "on_time_rate": (len(on_time) / total) if total else 0.0,
        "service_rate": (len(orders) / total) if total else 0.0,
        "total_tardiness_sec": total_tardiness,
        "max_tardiness_sec": max_tardiness,
        "avg_flow_sec": avg_flow,
        "max_flow_sec": max_flow,
        "makespan_sec": makespan_sec,
        "throughput_per_hour": throughput_per_hour,
        "tier0_count": tier0,
        "tier1_count": tier1,
    }


_COLUMNS: List[Tuple[str, str, int]] = [
    ("Method",       "label",               30),
    ("N",            "orders_total",         4),
    ("OnT",          "on_time_count",        4),
    ("Tardy",        "tardy_count",          6),
    ("Skip",         "orders_skipped",       5),
    ("OnT%",         "on_time_rate_pct",     6),
    ("SumTard(s)",   "total_tardiness_sec", 11),
    ("MaxTard(s)",   "max_tardiness_sec",   11),
    ("AvgFlow(s)",   "avg_flow_sec",        11),
    ("Mkspan(s)",    "makespan_sec",        10),
    ("Thr/h",        "throughput_per_hour",  7),
]


def format_metrics_table(rows: List[Tuple[str, dict]]) -> str:
    """Render ``[(label, metrics_dict), ...]`` as a fixed-width table."""
    header = "  ".join(name.ljust(w) for name, _, w in _COLUMNS)
    out = [header, "-" * len(header)]
    for label, m in rows:
        m = dict(m)
        m["label"] = label
        m["on_time_rate_pct"] = m["on_time_rate"] * 100.0
        cells = []
        for _, key, w in _COLUMNS:
            v = m[key]
            if key == "label":
                s = str(v)
            elif isinstance(v, float):
                s = "{:.1f}".format(v)
            else:
                s = str(v)
            cells.append(s.ljust(w))
        out.append("  ".join(cells))
    return "\n".join(out)
