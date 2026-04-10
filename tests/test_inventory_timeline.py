import unittest
from datetime import datetime

from orders_optimisation.inventory_timeline import InventoryTimeline


def _ing(**kw):
    base = {"burgers_patties": 0, "lettuce": 0, "tomato": 0,
            "veggie_patties": 0, "bacon": 0}
    base.update(kw)
    return base


class TestInventoryTimeline(unittest.TestCase):

    def test_feasible_with_no_events(self):
        tl = InventoryTimeline(initial=_ing(burgers_patties=5))
        self.assertTrue(tl.feasible_with({}))

    def test_consumption_within_initial_ok(self):
        tl = InventoryTimeline(initial=_ing(burgers_patties=2))
        new = {
            ("O1", 0): (datetime(2020, 1, 1, 10, 0, 0),
                        _ing(burgers_patties=1)),
            ("O1", 1): (datetime(2020, 1, 1, 10, 1, 0),
                        _ing(burgers_patties=1)),
        }
        self.assertTrue(tl.feasible_with(new))

    def test_consumption_over_initial_infeasible(self):
        tl = InventoryTimeline(initial=_ing(burgers_patties=1))
        new = {
            ("O1", 0): (datetime(2020, 1, 1, 10, 0, 0),
                        _ing(burgers_patties=1)),
            ("O1", 1): (datetime(2020, 1, 1, 10, 1, 0),
                        _ing(burgers_patties=1)),
        }
        self.assertFalse(tl.feasible_with(new))

    def test_restock_enables_later_consumption(self):
        tl = InventoryTimeline(
            initial=_ing(burgers_patties=1),
            restocks=[(datetime(2020, 1, 1, 10, 5, 0),
                       _ing(burgers_patties=1))],
        )
        new = {
            ("O1", 0): (datetime(2020, 1, 1, 10, 0, 0),
                        _ing(burgers_patties=1)),
            ("O2", 0): (datetime(2020, 1, 1, 10, 5, 0),
                        _ing(burgers_patties=1)),
        }
        self.assertTrue(tl.feasible_with(new))

    def test_restock_tiebreak_applied_before_consumption_at_same_ts(self):
        # Initial 0, restock 1 at T, consumption 1 at T — must be feasible.
        tl = InventoryTimeline(
            initial=_ing(burgers_patties=0),
            restocks=[(datetime(2020, 1, 1, 10, 0, 0),
                       _ing(burgers_patties=1))],
        )
        new = {
            ("O1", 0): (datetime(2020, 1, 1, 10, 0, 0),
                        _ing(burgers_patties=1)),
        }
        self.assertTrue(tl.feasible_with(new))

    def test_replace_order_drops_then_merges(self):
        tl = InventoryTimeline(initial=_ing(burgers_patties=3))
        tl.replace_order("O1", {
            ("O1", 0): (datetime(2020, 1, 1, 10, 0, 0),
                        _ing(burgers_patties=1)),
            ("O1", 1): (datetime(2020, 1, 1, 10, 1, 0),
                        _ing(burgers_patties=1)),
        })
        # Re-assign with a different shape.
        tl.replace_order("O1", {
            ("O1", 0): (datetime(2020, 1, 1, 10, 2, 0),
                        _ing(burgers_patties=1)),
        })
        self.assertEqual(len(tl.consumptions), 1)
        self.assertIn(("O1", 0), tl.consumptions)

    def test_refund_drops_only_unstarted_consumptions(self):
        tl = InventoryTimeline(initial=_ing(burgers_patties=3))
        tl.replace_order("O1", {
            ("O1", 0): (datetime(2020, 1, 1, 10, 0, 0),
                        _ing(burgers_patties=1)),
            ("O1", 1): (datetime(2020, 1, 1, 10, 5, 0),
                        _ing(burgers_patties=1)),
            ("O1", 2): (datetime(2020, 1, 1, 10, 10, 0),
                        _ing(burgers_patties=1)),
        })
        # Refund rule: cook_start >= now is refundable. Cancel at 10:06 —
        # only item 2 (cook_start 10:10) qualifies; items 0 and 1 started
        # strictly before 10:06 and are sunk.
        refunded = tl.refund("O1",
                             min_cook_start=datetime(2020, 1, 1, 10, 6, 0))
        self.assertEqual(refunded["burgers_patties"], 1)
        # Items 0 and 1 stay as orphan entries.
        self.assertEqual(len(tl.consumptions), 2)

    def test_refund_includes_entry_at_exact_now(self):
        # cook_start == now is refundable: the burger has not yet
        # physically consumed its ingredients at the instant cancel fires.
        tl = InventoryTimeline(initial=_ing(burgers_patties=1))
        tl.replace_order("O1", {
            ("O1", 0): (datetime(2020, 1, 1, 10, 0, 0),
                        _ing(burgers_patties=1)),
        })
        refunded = tl.refund("O1",
                             min_cook_start=datetime(2020, 1, 1, 10, 0, 0))
        self.assertEqual(refunded["burgers_patties"], 1)
        self.assertEqual(tl.consumptions, {})

    def test_snapshot_restore_round_trip(self):
        tl = InventoryTimeline(initial=_ing(burgers_patties=3))
        tl.replace_order("O1", {
            ("O1", 0): (datetime(2020, 1, 1, 10, 0, 0),
                        _ing(burgers_patties=1)),
        })
        snap = tl.snapshot()
        tl.replace_order("O2", {
            ("O2", 0): (datetime(2020, 1, 1, 10, 1, 0),
                        _ing(burgers_patties=1)),
        })
        self.assertEqual(len(tl.consumptions), 2)
        tl.restore(snap)
        self.assertEqual(len(tl.consumptions), 1)
        self.assertIn(("O1", 0), tl.consumptions)

    def test_current_stock_at_various_instants(self):
        tl = InventoryTimeline(
            initial=_ing(burgers_patties=3),
            restocks=[(datetime(2020, 1, 1, 10, 5, 0),
                       _ing(burgers_patties=2))],
        )
        tl.replace_order("O1", {
            ("O1", 0): (datetime(2020, 1, 1, 10, 0, 0),
                        _ing(burgers_patties=1)),
            ("O1", 1): (datetime(2020, 1, 1, 10, 10, 0),
                        _ing(burgers_patties=1)),
        })
        # Before anything happens.
        self.assertEqual(
            tl.current_stock(datetime(2019, 12, 31, 0, 0, 0))[
                "burgers_patties"], 3)
        # After burger 0 cooks.
        self.assertEqual(
            tl.current_stock(datetime(2020, 1, 1, 10, 0, 0))[
                "burgers_patties"], 2)
        # After restock.
        self.assertEqual(
            tl.current_stock(datetime(2020, 1, 1, 10, 6, 0))[
                "burgers_patties"], 4)
        # After burger 1 cooks.
        self.assertEqual(
            tl.current_stock(datetime(2020, 1, 1, 10, 11, 0))[
                "burgers_patties"], 3)


if __name__ == "__main__":
    unittest.main()
