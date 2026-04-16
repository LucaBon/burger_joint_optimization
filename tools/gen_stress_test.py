"""Generate a full-week, 100-branch stress-test input file.

International multi-joint scenario
===================================
100 branches in 5 capacity tiers (flagship → express).
7 operating days: 2026-04-13 (Mon) through 2026-04-19 (Sun).
Operating window: 10:00 – 22:00 UTC (simplified; real TZ offsets omitted).

Traffic model
-------------
Each day has two zones per branch:

  BACKGROUND  – light trickle throughout the day
  BURST       – a 20-minute micro-burst at lunch (12:00) and dinner (18:00)
                where orders arrive every 40-55 s so the arrival rate
                EXCEEDS the branch pipeline throughput, guaranteeing that
                some orders will be late.

Pipeline throughput ceiling (burgers / 20 min):
  flagship : min(6×20, 4×10, 3×20) = 60 burgers → ~17 orders (at 3.5 avg)
  urban    : min(4×20, 3×10, 2×20) = 30 burgers → ~8 orders
  suburban : min(3×10, 2×10, 2×20) = 20 burgers → ~5 orders
  kiosk    : min(2×10, 2×20, 1×20) = 20 burgers → ~5 orders
  express  : min(2×7,  1×10, 1×20) = 10 burgers → ~3 orders

Each burst sends (capacity+50%) orders in 20 min, ensuring real lateness.

Inventory is sized at ~70 % of estimated weekly consumption for kiosk and
express tiers so that those branches exhaust stock toward end-of-week.
"""

import random
import os
from datetime import datetime, timedelta

random.seed(42)

# -----------------------------------------------------------------------
# Branch tiers
# (cook_cap, cook_lead_min, asm_cap, asm_lead_min, pkg_cap, pkg_lead_min,
#  inv_patties, inv_lettuce, inv_tomato, inv_veggie, inv_bacon)
# -----------------------------------------------------------------------
TIERS = {
    "flagship":  (6, 1, 4, 2, 3, 1, 8000, 14000, 14000, 3500, 5000),
    "urban":     (4, 1, 3, 2, 2, 1, 4000,  7000,  7000, 1800, 2500),
    "suburban":  (3, 2, 2, 2, 2, 1, 2000,  3500,  3500,  900, 1200),
    # kiosk/express: inventory deliberately set at ~65 % of expected weekly
    # consumption (≈ 130 burgers / kiosk and ≈ 85 burgers / express) so
    # that stock runs out by day 4-5 and the last ~35 % of orders are hard-
    # rejected with "inventory_exhausted".
    "kiosk":     (2, 2, 2, 1, 1, 1,   70,   70,   75,   22,  50),
    "express":   (2, 3, 1, 2, 1, 1,   40,   40,   44,   12,  30),
}

BRANCH_TIER_MAP: dict = {}
tier_names = list(TIERS.keys())
for i in range(1, 101):
    BRANCH_TIER_MAP[i] = tier_names[(i - 1) // 20]

# -----------------------------------------------------------------------
# Burger recipes  (weight, ingredient_string)
# B=bacon  L=lettuce  T=tomato  V=veggie patty
# -----------------------------------------------------------------------
BURGER_RECIPES = [
    (22, "BLT"),
    (16, "LT"),
    (12, "BT"),
    (10, "VLT"),
    (8,  "BVLT"),
    (7,  "VT"),
    (7,  "BL"),
    (6,  "T"),
    (5,  "L"),
    (7,  "BLT"),
]
_weights, _recipes = zip(*BURGER_RECIPES)


def random_burger() -> str:
    return random.choices(_recipes, weights=_weights, k=1)[0]


def random_order_size(tier: str) -> int:
    if tier == "flagship":
        return random.choices([1, 2, 3, 4, 5, 6, 7, 8],
                              weights=[5, 10, 15, 20, 20, 15, 10, 5], k=1)[0]
    elif tier == "urban":
        return random.choices([1, 2, 3, 4, 5],
                              weights=[10, 25, 30, 25, 10], k=1)[0]
    elif tier == "suburban":
        return random.choices([1, 2, 3, 4],
                              weights=[20, 35, 30, 15], k=1)[0]
    elif tier == "kiosk":
        return random.choices([1, 2, 3],
                              weights=[35, 45, 20], k=1)[0]
    else:
        return random.choices([1, 2, 3],
                              weights=[50, 40, 10], k=1)[0]


# Per-burst order count per event (intentionally above 20-min pipeline ceiling).
# Pipeline ceilings (burgers/20min): flagship=60→~17 ord, urban=30→~8,
#   suburban=20→~5, kiosk=20→~5, express=10→~3
BURST_ORDERS = {
    "flagship": 22,   # ceiling ≈ 17  → +29 %  overflow
    "urban":    12,   # ceiling ≈  8  → +50 %  overflow
    "suburban":  8,   # ceiling ≈  5  → +60 %  overflow
    "kiosk":     7,   # ceiling ≈  5  → +40 %  overflow
    "express":   5,   # ceiling ≈  3  → +67 %  overflow
}

# Background inter-arrival gap in seconds (very light trickle between bursts).
# Wide gaps keep per-branch total orders under ~250 so scheduling stays fast.
BACKGROUND_GAP = {
    "flagship": 3600,    # 1 order / 60 min
    "urban":    5400,    # 1 order / 90 min
    "suburban": 7200,    # 1 order / 120 min
    "kiosk":   14400,    # 1 order / 4 hr
    "express": 21600,    # 1 order / 6 hr
}

# Weekend multiplier on background gap (more traffic = smaller gap)
WEEKEND_GAP_MULT = {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 0.80, 5: 0.65, 6: 0.75}

START_DATE = datetime(2026, 4, 13)   # Monday

# One burst per day: dinner rush.  One concentrated 20-minute event is
# enough to saturate the pipeline and produce late orders without
# ballooning total order count.
BURST_CENTRES = [(18, 0)]
BURST_DURATION_SECONDS = 20 * 60    # 20-minute burst window


def generate_orders_for_branch(branch_id: int, tier: str):
    """Yield order line strings for one branch over 7 days."""
    order_counter = 0
    bg_gap = BACKGROUND_GAP[tier]
    burst_n = BURST_ORDERS[tier]

    for day_offset in range(7):
        day = START_DATE + timedelta(days=day_offset)
        dow = day.weekday()
        gap_mult = WEEKEND_GAP_MULT[dow]

        # ---- background trickle ----------------------------------------
        op_start = day.replace(hour=10, minute=0, second=0)
        op_end   = day.replace(hour=22, minute=0, second=0)
        t = op_start + timedelta(
            seconds=random.uniform(0, bg_gap * gap_mult * 0.5))
        while t < op_end:
            order_counter += 1
            n = random_order_size(tier)
            burgers = ",".join(random_burger() for _ in range(n))
            yield "R{},{},O{},{}".format(
                branch_id, t.strftime("%Y-%m-%d %H:%M:%S"),
                order_counter, burgers)
            t += timedelta(seconds=bg_gap * gap_mult *
                           random.uniform(0.7, 1.3))

        # ---- micro-bursts -----------------------------------------------
        for bh, bm in BURST_CENTRES:
            burst_start = day.replace(hour=bh, minute=bm, second=0)
            burst_end   = burst_start + timedelta(seconds=BURST_DURATION_SECONDS)
            # Distribute burst_n orders uniformly within the window
            interval = BURST_DURATION_SECONDS / burst_n
            for k in range(burst_n):
                jitter = random.uniform(-interval * 0.3, interval * 0.3)
                t_b = burst_start + timedelta(
                    seconds=k * interval + jitter)
                # clamp within burst window
                t_b = max(burst_start, min(burst_end - timedelta(seconds=1), t_b))
                order_counter += 1
                n = random_order_size(tier)
                burgers = ",".join(random_burger() for _ in range(n))
                yield "R{},{},O{},{}".format(
                    branch_id, t_b.strftime("%Y-%m-%d %H:%M:%S"),
                    order_counter, burgers)


def main():
    out_dir = os.path.join(os.path.dirname(__file__), "..", "tests", "Files")
    out_path = os.path.join(out_dir, "stress_week_100branches.txt")

    lines: list = []

    # Branch headers
    for branch_id in range(1, 101):
        tier = BRANCH_TIER_MAP[branch_id]
        (cc, cl, ac, al, pc, pl,
         inv_p, inv_l, inv_t, inv_v, inv_b) = TIERS[tier]
        lines.append(
            "R{},{}C,{},{}A,{},{}P,{},{},{},{},{},{}".format(
                branch_id, cc, cl, ac, al, pc, pl,
                inv_p, inv_l, inv_t, inv_v, inv_b))

    # Orders
    total_orders = 0
    tier_counts: dict = {t: 0 for t in tier_names}
    for branch_id in range(1, 101):
        tier = BRANCH_TIER_MAP[branch_id]
        for line in generate_orders_for_branch(branch_id, tier):
            lines.append(line)
            total_orders += 1
            tier_counts[tier] += 1

    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    print("Written : {}".format(out_path))
    print("Branches: 100")
    print("Orders  : {:,}".format(total_orders))
    for t in tier_names:
        n = tier_counts[t]
        print("  {:10s}: {:6,} orders  ({:.0f}/branch/wk)".format(
            t, n, n / 20))


if __name__ == "__main__":
    main()
