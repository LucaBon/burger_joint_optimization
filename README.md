# Burger joint optimization

An online, deadline-aware scheduler for a chain of burger joints. Each branch
owns three sequential processing stages (cooking → assembling → packaging),
each with a fixed number of parallel workers and a fixed per-burger lead time,
plus a finite ingredient stock with optional scheduled restocks. Orders arrive
over time and must be completed within 20 minutes of their arrival; the
scheduler decides, for every burger, **which worker runs it at each stage and
when**, so that as many orders as possible finish on time without ever
over-committing workers or ingredients.

## Build and run

From the repository root:

```bash
docker build -t burger_joint .
docker run -it --rm -v $(pwd):/app burger_joint bash
```

Inside the container (or any Python 3.8 environment) run the sample fixture:

```bash
PYTHONPATH=. python3 -m orders_optimisation.order_scheduler
```

Run the unit tests:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -t .
```

## Input format

The scheduler reads a plaintext file ([orders_optimisation/data_reader.py](orders_optimisation/data_reader.py))
with three line types. Each line is regex-validated and classified:

- **Branch**:
  `R<id>,<C>C,<t>,<A>A,<t>,<P>P,<t>,<patties>,<lettuce>,<tomato>,<veggie>,<bacon>`
  — declares a branch's three-stage capacity/lead-time and its initial stock.
- **Order**:
  `R<branchId>,<YYYY-MM-DD HH:MM:SS>,O<orderId>,<burger1>,<burger2>,...`
  — each burger is a string over the alphabet `{B,L,T,V}` (bacon, lettuce,
  tomato, veggie patty; absence of `V` implies a beef patty).
- **Restock** (optional):
  `R<id>,RESTOCK,<YYYY-MM-DD HH:MM:SS>,<ingredient>:<amount>,...`
  — schedules a future ingredient inflow for a branch.

Parsing returns `(list[Branch], dict[branch_id, list[Order]])` and surfaces
`DuplicatedBranchIdError` / `NoBranchInfoError` / `UnknownIngredientError` on
malformed input.

## Domain model

- [Branch](orders_optimisation/branch.py) — owns `cooking`, `assembling`,
  `packaging` (each `{"capacity", "lead_time"}`), an initial `inventory`
  snapshot, and an optional list of scheduled `restocks`. Inventory is **not**
  mutated in place by the scheduler: live stock is tracked through an
  `InventoryTimeline`.
- [Order and Item](orders_optimisation/order.py) — an `Order` is a list of
  `Item` burgers with an arrival time and a 20-minute deadline.
  `calculate_order_ingredients()` aggregates required stock; unknown ingredient
  codes raise `InvalidIngredientError`.

## Scheduling — how it works

The core is `BranchScheduler` in
[orders_optimisation/order_scheduler.py](orders_optimisation/order_scheduler.py),
an **online** scheduler: orders are admitted one at a time via
`admit(order, now, accept_late=…)`, and each admission re-optimizes all
not-yet-started work from scratch. The batch entry point
`schedule_orders(branches, orders, policy=…)` drives one `BranchScheduler` per
branch and feeds orders in arrival order.

### Tiered EDF dispatch at burger granularity

Every burger in the plan carries a `(tier, deadline, arrival, order_id,
item_id)` sort key. `_simulate` dispatches burgers in that lexicographic order
onto per-stage worker lists, always picking the earliest-free worker:

1. **Tier 0 (on-time)** — orders admitted with a feasible verdict. Dispatched
   first at every stage, ordered by **Earliest Deadline First** (EDF).
2. **Tier 1 (accepted-late)** — orders admitted despite an infeasible verdict.
   They are dispatched strictly *after* all tier-0 work at every stage, so a
   late order can never starve an on-time one.

Because the sort key is applied independently at each stage, freezing is **per
stage**, not per burger: a burger whose cook has already started is locked at
cook, but its assembly and packaging can still be reassigned in favor of a
newly arrived tier-0 order. This is what lets a late-arriving on-time order
cut the assembly queue past a tier-1 burger that has finished cooking but not
yet been assembled.

### Admission by simulation — `estimate` then `admit`

`estimate(order, now)` is the read-only projection used by `admit`. It runs
two simulations:

- a **baseline** containing only the already-admitted orders, and
- a **projected** run that adds the newcomer at tier 0.

From the two plans it computes:

- `projected_end` — when the newcomer's last burger leaves packaging;
- `deadline_feasible` — whether `projected_end` ≤ `now + 20 min`;
- `lateness` — overshoot vs. the 20-minute budget;
- `displaced_orders` — existing tier-0 orders whose baseline finish was on
  time but whose projected finish is now late (i.e., the newcomer would bump
  them); and
- `inventory_feasible` — a non-mutating check against the `InventoryTimeline`,
  which walks the projected consumption events and the scheduled restocks to
  confirm running stock never goes negative.

`admit` turns a verdict into a decision. Inventory infeasibility is always a
hard reject. Otherwise the policy (see below) decides whether to commit at
tier 0, commit at tier 1, or reject. Commit is transactional against the
inventory timeline: if re-optimizing shifts a predecessor's `cook_start` past
a restock such that stock would go negative, the commit is rolled back.

### Admission policies (`schedule_orders(..., policy=…)`)

- **`auto_accept`** (default) — infeasible orders are committed at tier 1 so
  they do not block feasible ones. Mirrors the legacy batch behaviour but
  with EDF burger-level dispatch.
- **`reject_late`** — infeasible orders go into `skipped` with
  `reason="deadline_infeasible"` instead of consuming capacity.
- **`moore_hodgson`** — an online variant of the classical Moore–Hodgson rule
  for *minimizing the number of tardy jobs*. When a newcomer would be tardy,
  `admit_moore_hodgson` demotes existing tier-0 orders (longest-processing-
  time first, measured in burger count) to tier 1 until the newcomer fits.
  Demoted orders keep their inventory reservations and schedule slots but
  lose tier-0 priority. If no sequence of demotions makes the newcomer
  feasible, all demotions are rolled back and the classic path applies.
- **`spt_batch`** — Shortest-Processing-Time tie-break on arrival time.
  Orders sharing a timestamp are admitted smallest-first, which shrinks mean
  flow time when bursts arrive together. Combined with `auto_accept`
  semantics for late orders.
- **`backorder`** — infeasible orders are parked in a retry queue instead of
  rejected. Every successful commit and every cancellation drains the queue,
  so capacity freed later in the run can rescue an earlier infeasible order.
  Orders still queued at end-of-run land in `skipped` with
  `reason="backorder_stale"`.

### Pluggable dispatch policies

The sort key fed to `_simulate` is extracted into
[orders_optimisation/dispatch_policies.py](orders_optimisation/dispatch_policies.py).
Pass `dispatch_policy=` to `BranchScheduler` or `schedule_orders` to swap the
strategy:

- `"edf"` *(default)* — Earliest Deadline First, the legacy behaviour.
- `"spt"` — Shortest Processing Time at order granularity.
- `"wspt"` — Weighted SPT (`priority / order_size`), classical Smith's rule.

All dispatch policies honour `Order.priority` (higher = more important), so
VIP handling composes with every strategy.

### Priority / VIP orders

`Order` accepts an optional `priority: int` field and the input file format
grows an optional trailing `,P=<n>` token:

```
R1,2026-01-01 10:00:00,O1,BLT,BLT,BLT
R1,2026-01-01 10:00:00,O2,BLT,P=5
```

Higher-priority orders queue ahead of regular work within the same tier.

### Worker shifts / time-varying capacity

`Branch` accepts an optional `shifts` map:

```python
branch = Branch(
    branch_id="R1",
    cooking={"capacity": 2, "lead_time": 1},
    assembling={"capacity": 2, "lead_time": 1},
    packaging={"capacity": 1, "lead_time": 1},
    inventory={...},
    shifts={
        "cooking": [(start, end, 3)],    # +3 cook workers from start
        "assembling": [(start, end, 2)],
        "packaging": [(start, end, 1)],
    },
)
```

Each shift entry adds `extra_cap` workers whose availability begins at
`start`. In this iteration the scheduler does **not** evict workers at
`end` — once a shift-worker comes on, they stay in the pool for the rest
of the run. This captures the common "peak-hour reinforcements" pattern
while keeping the core scheduler semantics simple.

### Cost / SLA model

`orders_optimisation/cost_model.py` defines `CostModel(margin_per_order,
lateness_penalty_per_second, rejection_cost, per_burger_margin)`. Pass it
to `metrics.compute_metrics(result, cost_model=cm)` and the returned dict
gains `total_revenue`, `total_lateness_penalty`, `total_rejection_cost`,
and `net_value` — the economic score for the schedule.

### Time-aware inventory and cancellations

`InventoryTimeline` tracks the ingredient stock as a function of wall-clock
time: it holds the initial snapshot, the scheduled restocks, and one
consumption event per burger pinned at its planned `cook_start`.
`feasible_with(extra)` walks the merged event stream and verifies the running
stock never goes negative — this is what makes `estimate` honest about future
restocks instead of looking only at the current dict.

`cancel(order_id, now)` refunds ingredients for burgers whose recorded
`cook_start >= now` (nothing was physically consumed yet); burgers already in
flight are sunk cost. After cancellation, every surviving order is
re-simulated and its consumption events re-pinned, because freeing capacity
typically pulls other burgers' `cook_start` earlier.

`current_stock(now)` returns the projected available stock at any wall-clock
instant.

## Results on the sample fixture

On `tests/Files/input.txt`, the online tiered-EDF policy schedules **9/12
orders on time** versus 5/12 for the original FCFS baseline, with no change
to branch capacity or lead times.

See [REPORT.md](REPORT.md) for the full benchmark comparison across every
policy, the multi-branch load-balanced results, and the scale-profile
appendix that drives the
[tests/test_performance.py](tests/test_performance.py) regression guard.

## Common commands

| Task | Command |
| --- | --- |
| Run unit tests | `make test` (or `PYTHONPATH=. python3 -m unittest discover -s tests -t .`) |
| Run the single-branch sample | `make run` |
| Reproduce the benchmark tables | `make benchmark` |
