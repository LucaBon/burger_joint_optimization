# Burger-Joint Scheduler — Optimization & Metrics Report

## 1. Goal

The existing scheduler
([orders_optimisation/order_scheduler.py](orders_optimisation/order_scheduler.py))
was evaluated only by counting how many orders finished inside their
20-minute deadline. This report introduces a reusable **metrics** layer
and benchmarks four scheduling **policies** on two fixtures, including a
cross-branch **load balancer**.

## 2. Metrics

Defined in [orders_optimisation/metrics.py](orders_optimisation/metrics.py).
All metrics are derived from the standard
`{branch_id: {"orders": [...], "skipped": [...]}}` snapshot shape, so any
policy can be scored with the same yardstick.

| Metric | Meaning |
| --- | --- |
| `N` | Total orders submitted (scheduled + skipped). |
| `OnT` | Orders delivered within the 20-minute deadline. |
| `Tardy` | Scheduled orders that missed the deadline. |
| `Skip` | Orders rejected (deadline-infeasible or inventory-exhausted). |
| `OnT%` | On-time rate over total submitted. |
| `SumTard(s)` | Σ max(0, end − limit) across all scheduled orders, seconds. |
| `MaxTard(s)` | Worst-case tardiness, seconds. |
| `AvgFlow(s)` | Mean `end − start` time per order, seconds. |
| `Mkspan(s)` | Global makespan (last pkg_end − first arrival). |
| `Thr/h` | Served orders per hour of makespan. |

## 3. Policies under test

All policies live in
[orders_optimisation/order_scheduler.py](orders_optimisation/order_scheduler.py)
except the load balancer, which is in
[orders_optimisation/multi_branch.py](orders_optimisation/multi_branch.py).

1. **`auto_accept`** *(baseline)* — online EDF at burger granularity with
   two tiers. Infeasible orders are committed at tier-1 so they never
   starve feasible tier-0 work.
2. **`reject_late`** — infeasible orders are dropped into `skipped`
   rather than served late. Trades service-rate for zero tardiness.
3. **`moore_hodgson`** *(new)* — online Moore–Hodgson demotion. When a
   newcomer would be tardy, the longest existing tier-0 order (by
   burger count) is demoted to tier-1. Demotion repeats until the
   newcomer fits or tier-0 is empty. If demotion fails, the newcomer
   itself falls back to tier-1. See `BranchScheduler.admit_moore_hodgson`.
4. **`spt_batch`** *(new)* — shortest-processing-time tie-break within
   an arrival timestamp. Orders that land in the same second are fed to
   the scheduler smallest-first, so a tiny order does not queue behind a
   big one it coincidentally arrived with. Otherwise behaves like
   `auto_accept`.
5. **`load_balanced`** *(new, multi-branch only)* — a
   `MultiBranchDispatcher` owning one `BranchScheduler` per branch.
   Each incoming order is offered to **every** branch via the
   non-mutating `BranchScheduler.estimate` verdict, and is dispatched to
   whichever branch ranks best on `(feasible, lateness, projected_end)`.
   The order's original `branch_id` is ignored — think of it as a global
   router in front of the per-branch schedulers.

## 4. Results

Benchmark runner: [orders_optimisation/benchmark.py](orders_optimisation/benchmark.py).
Reproduce with:

```bash
PYTHONPATH=. python3 -m orders_optimisation.benchmark
```

### 4.1 Single-branch suite — `tests/Files/input.txt` (1 branch, 12 orders)

```
Method                          N     OnT   Tardy   Skip   OnT%    SumTard(s)   MaxTard(s)   AvgFlow(s)   Mkspan(s)   Thr/h
-----------------------------------------------------------------------------------------------------------------------------
auto_accept (EDF + tier1)       12    9     3       0      75.0    1973.0       741.0        1069.0       2160.0      20.0
reject_late                     12    9     0       3      75.0    0.0          0.0          806.1        1560.0      20.8
moore_hodgson                   12    9     3       0      75.0    1961.0       856.0        1014.0       2160.0      20.0
spt_batch                       12    9     3       0      75.0    1973.0       741.0        1069.0       2160.0      20.0
```

### 4.2 Multi-branch suite — `tests/Files/multi_branch_input.txt` (3 branches, 12 orders)

Three identical small branches (2 cook / 2 asm / 1 pkg workers). The 12
orders are filed against R1 and R2; R3 carries no orders in the fixture
but can absorb load when the dispatcher reroutes.

```
Method                          N     OnT   Tardy   Skip   OnT%    SumTard(s)   MaxTard(s)   AvgFlow(s)   Mkspan(s)   Thr/h
-----------------------------------------------------------------------------------------------------------------------------
per-branch auto_accept          12    11    1       0      91.7    616.0        616.0        903.2        1920.0      22.5
per-branch reject_late          12    11    0       1      91.7    0.0          0.0          820.2        1500.0      26.4
per-branch moore_hodgson        12    10    2       0      83.3    915.0        616.0        873.2        1920.0      22.5
per-branch spt_batch            12    11    1       0      91.7    616.0        616.0        903.2        1920.0      22.5
load-balanced auto_accept       12    12    0       0      100.0   0.0          0.0          659.6        1201.0      36.0
load-balanced reject_late       12    12    0       0      100.0   0.0          0.0          659.6        1201.0      36.0
load-balanced moore_hodgson     12    12    0       0      100.0   0.0          0.0          659.6        1201.0      36.0
```

## 5. Analysis

### Single-branch fixture
All four policies tie at **9/12 on-time**. The fixture is
bottleneck-limited: three orders physically cannot finish inside the
20-minute window no matter how they're dispatched, so every policy
converges on the same on-time count.

The interesting deltas are in *how* the unavoidable lateness is
distributed:
- **`moore_hodgson`** lowers `SumTard` from 1973 s → 1961 s and
  `AvgFlow` from 1069 s → 1014 s versus `auto_accept`, because demoting
  the longest order lets several shorter ones slip in ahead of it.
  `MaxTard` gets slightly worse (856 vs 741) — the one demoted order
  absorbs a bit more lateness.
- **`reject_late`** is the only policy with zero tardiness, but at a
  3-order service cost. Its `Mkspan` and `AvgFlow` shrink purely because
  three orders are no longer on the schedule at all.
- **`spt_batch`** is identical to `auto_accept` here: no two orders in
  this fixture share a timestamp with meaningfully different sizes, so
  there is no tie to break.

### Multi-branch fixture
This is where the strategies actually separate.

- **Without rerouting** (`per-branch *`), R1 and R2 each carry their
  filed orders, R3 sits idle, and the best policies land 11/12 on-time.
- **`per-branch moore_hodgson` regresses to 10/12.** This is the
  known failure mode of naive online MH: demoting a tier-0 order to
  tier-1 *guarantees* that order becomes late (tier-1 dispatches after
  all tier-0 work), even if it had enough slack to finish on-time under
  plain EDF. Online MH can only see one arrival at a time, so it
  sometimes spends a slack-rich order to buy space for a newcomer that
  `auto_accept` would have parked at tier-1 on its own. Avoidable only
  by making demotion speculative against future arrivals — out of scope.
- **Load balancing is the decisive optimization.** Every load-balanced
  variant hits **12/12 on-time**, drops makespan from 1920 s → **1201 s**
  (−37%), average flow from 903 s → **660 s** (−27%), and lifts
  throughput from 22.5/h → **36.0/h** (+60%). Rerouting pulls work from
  overloaded R1/R2 onto idle R3, which is the cheapest slack there is.
- Once load balancing is in place, `auto_accept`, `reject_late`, and
  `moore_hodgson` collapse onto identical numbers: with enough capacity,
  no order is ever tardy, so the tardy-handling policy becomes
  irrelevant. This is the correct behavior — optimizations compose but
  they don't double-count savings.

## 6. Takeaways

1. **Load balancing dominates.** On a fleet with spare capacity, global
   routing via `estimate` is worth far more than any single-branch
   dispatch trick. Ship it first.
2. **Moore–Hodgson helps on flow time, not on tardy count.** In this
   setup the tardy count is pinned by physical capacity, so MH mostly
   shuffles *which* orders are late and shortens the average. On
   multi-branch it can even regress on-time count; it should only be
   enabled when the operator cares about mean lateness more than strict
   on-time count.
3. **`reject_late` buys zero tardiness by sacrificing service rate.**
   Useful only when a missed deadline is worse than a refused order
   (e.g. SLA penalties). Without load balancing it still drops orders.
4. **`spt_batch` is a free optimization with no downside**, but also no
   upside on these fixtures because timestamps rarely collide. Keep it
   for bursty real-world inputs where multiple orders land in the same
   second.

## 7. Caveats

- Both fixtures are tiny (12 orders). All deltas should be read as
  *directional* rather than statistically significant.
- Load balancing assumes orders may be served from any branch. If a
  real deployment pins customers to their home branch (pickup logistics,
  delivery zones), the router must be restricted to a feasible subset.
- Under load balancing, the reported snapshot is keyed by the
  *executing* branch, not the branch the order was originally filed
  against. That is intentional but worth flagging when comparing with
  non-balanced runs.

## 8. Files touched

| Path | Role |
| --- | --- |
| [orders_optimisation/metrics.py](orders_optimisation/metrics.py) | KPI computation + table formatter (new) |
| [orders_optimisation/order_scheduler.py](orders_optimisation/order_scheduler.py) | `admit_moore_hodgson`, `moore_hodgson`/`spt_batch` policies |
| [orders_optimisation/multi_branch.py](orders_optimisation/multi_branch.py) | `MultiBranchDispatcher`, `schedule_orders_load_balanced` (new) |
| [orders_optimisation/benchmark.py](orders_optimisation/benchmark.py) | Benchmark runner (new) |
| [tests/Files/multi_branch_input.txt](tests/Files/multi_branch_input.txt) | 3-branch fixture for load-balancer runs (new) |

## 9. Verification

```bash
# Existing regression suite — 25 tests, all green.
PYTHONPATH=. python3 -m unittest discover -s tests -t .

# Reproduce the tables in §4.
PYTHONPATH=. python3 -m orders_optimisation.benchmark
```
