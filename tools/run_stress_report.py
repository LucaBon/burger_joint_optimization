"""Run the scheduler against the 100-branch week-long stress fixture
and print a structured analysis report.
"""
import os
import sys
import time
from collections import defaultdict
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orders_optimisation import data_reader
from orders_optimisation.order_scheduler import schedule_orders

TIERS = {
    "flagship":  list(range(1, 21)),
    "urban":     list(range(21, 41)),
    "suburban":  list(range(41, 61)),
    "kiosk":     list(range(61, 81)),
    "express":   list(range(81, 101)),
}
BRANCH_TIER = {}
for tier, ids in TIERS.items():
    for bid in ids:
        BRANCH_TIER["R{}".format(bid)] = tier


def fmt_td(td: timedelta) -> str:
    total_s = int(td.total_seconds())
    m, s = divmod(abs(total_s), 60)
    return "{}m{:02d}s".format(m, s)


def main():
    fixture = os.path.join(
        os.path.dirname(__file__), "..", "tests", "Files",
        "stress_week_100branches.txt")

    print("=" * 70)
    print("  BURGER JOINT GLOBAL STRESS TEST — FULL WEEK / 100 BRANCHES")
    print("=" * 70)
    print()

    print("[1/3] Parsing input …")
    t0 = time.perf_counter()
    branches, orders = data_reader.read_input_txt(fixture)
    parse_s = time.perf_counter() - t0
    total_orders_in = sum(len(v) for v in orders.values())
    print("      {} branches, {:,} orders read in {:.2f}s".format(
        len(branches), total_orders_in, parse_s))
    print()

    print("[2/3] Scheduling (policy=auto_accept) …")
    t0 = time.perf_counter()
    result = schedule_orders(branches=branches, orders=orders,
                             policy="auto_accept")
    sched_s = time.perf_counter() - t0
    print("      Done in {:.2f}s  ({:.1f} orders/s)".format(
        sched_s, total_orders_in / sched_s))
    print()

    # ------------------------------------------------------------------
    # Aggregate metrics
    # ------------------------------------------------------------------
    print("[3/3] Generating report …")
    print()

    tier_stats = defaultdict(lambda: {
        "branches": 0,
        "total": 0, "on_time": 0, "late": 0, "skipped": 0,
        "lateness_total_s": 0, "lateness_max_s": 0,
        "burgers_total": 0,
    })
    global_total = global_on_time = global_late = global_skip = 0
    global_lateness_s = 0
    global_max_lateness_s = 0
    global_burgers = 0

    per_branch = {}

    for branch_id, br in result.items():
        tier = BRANCH_TIER.get(branch_id, "unknown")
        t = tier_stats[tier]
        t["branches"] += 1

        scheduled = br["orders"]
        skipped = br["skipped"]
        on_time = [o for o in scheduled if o["on_time"]]
        late = [o for o in scheduled if not o["on_time"]]

        t["total"] += len(scheduled) + len(skipped)
        t["on_time"] += len(on_time)
        t["late"] += len(late)
        t["skipped"] += len(skipped)

        for o in late:
            ls = int((o["end"] - o["limit"]).total_seconds())
            t["lateness_total_s"] += ls
            if ls > t["lateness_max_s"]:
                t["lateness_max_s"] = ls
            if ls > global_max_lateness_s:
                global_max_lateness_s = ls

        burger_count = sum(len(o["burgers"]) for o in scheduled)
        t["burgers_total"] += burger_count

        global_total += len(scheduled) + len(skipped)
        global_on_time += len(on_time)
        global_late += len(late)
        global_skip += len(skipped)
        global_lateness_s += sum(
            int((o["end"] - o["limit"]).total_seconds())
            for o in late)
        global_burgers += burger_count

        per_branch[branch_id] = {
            "tier": tier,
            "total": len(scheduled) + len(skipped),
            "on_time": len(on_time),
            "late": len(late),
            "skipped": len(skipped),
            "burgers": burger_count,
        }

    # ------------------------------------------------------------------
    # Print global summary
    # ------------------------------------------------------------------
    def pct(a, b):
        return 100.0 * a / b if b else 0.0

    print("┌─────────────────────────────────────────────────────────────────────┐")
    print("│                        GLOBAL SUMMARY                              │")
    print("├──────────────────────┬──────────────────────────────────────────────┤")
    print("│ Total orders         │ {:>10,}                                    │".format(global_total))
    print("│ On-time              │ {:>10,}  ({:5.1f}%)                          │".format(
        global_on_time, pct(global_on_time, global_total)))
    print("│ Late (accepted)      │ {:>10,}  ({:5.1f}%)                          │".format(
        global_late, pct(global_late, global_total)))
    print("│ Skipped / rejected   │ {:>10,}  ({:5.1f}%)                          │".format(
        global_skip, pct(global_skip, global_total)))
    print("│ Total burgers made   │ {:>10,}                                    │".format(global_burgers))
    avg_lat = global_lateness_s / global_late if global_late else 0
    print("│ Avg lateness (late)  │ {:>10}                                    │".format(
        fmt_td(timedelta(seconds=avg_lat))))
    print("│ Max lateness         │ {:>10}                                    │".format(
        fmt_td(timedelta(seconds=global_max_lateness_s))))
    print("│ Parse time           │ {:>10.2f}s                                  │".format(parse_s))
    print("│ Schedule time        │ {:>10.2f}s                                  │".format(sched_s))
    print("└──────────────────────┴──────────────────────────────────────────────┘")
    print()

    # ------------------------------------------------------------------
    # Per-tier breakdown
    # ------------------------------------------------------------------
    print("PER-TIER BREAKDOWN")
    print("{:<12} {:>8} {:>8} {:>8} {:>8} {:>7} {:>10} {:>10}".format(
        "Tier", "Branches", "Orders", "OnTime", "Late", "Skip",
        "OnTime%", "AvgLate"))
    print("-" * 80)
    for tier in ["flagship", "urban", "suburban", "kiosk", "express"]:
        t = tier_stats[tier]
        tot = t["total"]
        avg_l = (t["lateness_total_s"] / t["late"]
                 if t["late"] else 0)
        print("{:<12} {:>8} {:>8,} {:>8,} {:>8,} {:>7,} {:>9.1f}% {:>10}".format(
            tier,
            t["branches"],
            tot,
            t["on_time"],
            t["late"],
            t["skipped"],
            pct(t["on_time"], tot),
            fmt_td(timedelta(seconds=avg_l))))
    print()

    # ------------------------------------------------------------------
    # Top 10 worst branches (by on-time %)
    # ------------------------------------------------------------------
    ranked = sorted(per_branch.items(),
                    key=lambda kv: pct(kv[1]["on_time"], kv[1]["total"]))
    print("TOP 10 WORST-PERFORMING BRANCHES (by on-time %)")
    print("{:<8} {:<12} {:>8} {:>8} {:>8} {:>8} {:>9}".format(
        "Branch", "Tier", "Orders", "OnTime", "Late", "Skip", "OnTime%"))
    print("-" * 65)
    for bid, s in ranked[:10]:
        print("{:<8} {:<12} {:>8,} {:>8,} {:>8,} {:>8,} {:>8.1f}%".format(
            bid, s["tier"], s["total"], s["on_time"],
            s["late"], s["skipped"], pct(s["on_time"], s["total"])))
    print()

    # ------------------------------------------------------------------
    # Top 10 best branches
    # ------------------------------------------------------------------
    print("TOP 10 BEST-PERFORMING BRANCHES (by on-time %)")
    print("{:<8} {:<12} {:>8} {:>8} {:>8} {:>8} {:>9}".format(
        "Branch", "Tier", "Orders", "OnTime", "Late", "Skip", "OnTime%"))
    print("-" * 65)
    for bid, s in reversed(ranked[-10:]):
        print("{:<8} {:<12} {:>8,} {:>8,} {:>8,} {:>8,} {:>8.1f}%".format(
            bid, s["tier"], s["total"], s["on_time"],
            s["late"], s["skipped"], pct(s["on_time"], s["total"])))
    print()

    # ------------------------------------------------------------------
    # Throughput headline
    # ------------------------------------------------------------------
    print("THROUGHPUT")
    print("  Scheduler processed {:,} orders across 100 branches in {:.2f}s".format(
        total_orders_in, sched_s))
    print("  = {:.0f} orders/s  |  {:.1f} ms/order  |  {:.1f} ms/branch".format(
        total_orders_in / sched_s,
        1000 * sched_s / total_orders_in,
        1000 * sched_s / 100))
    print()
    print("Done.")


if __name__ == "__main__":
    main()
