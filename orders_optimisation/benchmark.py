"""Benchmark every scheduling policy on the shipped fixtures.

Run with::

    PYTHONPATH=. python3 -m orders_optimisation.benchmark

Each row re-parses its fixture because ``schedule_orders`` mutates
``Branch.inventory`` in place — sharing a branch across runs would
silently bias later policies.
"""
import os
from typing import List, Tuple

from . import data_reader, metrics, order_scheduler
from .multi_branch import schedule_orders_load_balanced

FILES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "tests", "Files")

SINGLE_FIXTURE = os.path.join(FILES_DIR, "input.txt")
MULTI_FIXTURE = os.path.join(FILES_DIR, "multi_branch_input.txt")


def _run_single_branch() -> List[Tuple[str, dict]]:
    rows: List[Tuple[str, dict]] = []
    for label, policy in [
        ("auto_accept (EDF + tier1)", "auto_accept"),
        ("reject_late",                "reject_late"),
        ("moore_hodgson",              "moore_hodgson"),
        ("spt_batch",                  "spt_batch"),
    ]:
        branches, orders = data_reader.read_input_txt(SINGLE_FIXTURE)
        result = order_scheduler.schedule_orders(
            branches, orders, policy=policy)
        rows.append((label, metrics.compute_metrics(result)))
    return rows


def _run_multi_branch() -> List[Tuple[str, dict]]:
    rows: List[Tuple[str, dict]] = []

    for label, policy in [
        ("per-branch auto_accept",   "auto_accept"),
        ("per-branch reject_late",   "reject_late"),
        ("per-branch moore_hodgson", "moore_hodgson"),
        ("per-branch spt_batch",     "spt_batch"),
    ]:
        branches, orders = data_reader.read_input_txt(MULTI_FIXTURE)
        result = order_scheduler.schedule_orders(
            branches, orders, policy=policy)
        rows.append((label, metrics.compute_metrics(result)))

    for label, policy in [
        ("load-balanced auto_accept",   "auto_accept"),
        ("load-balanced reject_late",   "reject_late"),
        ("load-balanced moore_hodgson", "moore_hodgson"),
    ]:
        branches, orders = data_reader.read_input_txt(MULTI_FIXTURE)
        result = schedule_orders_load_balanced(
            branches, orders, policy=policy)
        rows.append((label, metrics.compute_metrics(result)))

    return rows


def main() -> None:
    print("=" * 100)
    print("Single-branch suite  (tests/Files/input.txt, 1 branch / 12 orders)")
    print("=" * 100)
    print(metrics.format_metrics_table(_run_single_branch()))
    print()
    print("=" * 100)
    print("Multi-branch suite   (tests/Files/multi_branch_input.txt, "
          "3 branches / 12 orders)")
    print("=" * 100)
    print(metrics.format_metrics_table(_run_multi_branch()))


if __name__ == "__main__":
    main()
