import unittest
import logging


import burger_joint_optimization.orders_optimisation.order as ut

formatter = logging.Formatter(
    '%(asctime)s : %(name)s : %(levelname)s : %(message)s'
)
handler = logging.StreamHandler()
handler.setLevel(logging.CRITICAL)
handler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)


class TestOrder(unittest.TestCase):
    def test_input(self):
        # Check TypeError is correctly raised

        branch_id = [[], "", ""]
        date_time = ["", 3, ""]
        order_id = ["", "", ""]
        hamburgers = [[],
                      [],
                      {}]
        for b, d, o, h in zip(branch_id, date_time, order_id, hamburgers):
            with self.assertRaises(TypeError):
                ut.Order(branch_id=b,
                         date_time=d,
                         order_id=o,
                         hamburgers=h)

    def test_calculate_limit_time(self):
        correct_output = "2020-12-08 19:35:31"
        order = ut.Order(branch_id="R1",
                         date_time="2020-12-08 19:15:31",
                         order_id="O1",
                         hamburgers=[])
        limit_time = order.calculate_limit_time()
        self.assertIsInstance(limit_time, str)
        self.assertEqual(limit_time, correct_output)

    def test_calculate_burger_number(self):
        correct_output = 3
        order_id = "O1"
        hamburgers_list = ["BLT", "LT", "VLT"]
        hamburgers_items = []
        for i, burger in enumerate(hamburgers_list):
            hamburgers_items.append(
                ut.Item(order_id=order_id,
                        item_id=i,
                        ingredients=burger)
            )
        order = ut.Order(branch_id="R1",
                         date_time="2020-12-08 19:15:31",
                         order_id=order_id,
                         hamburgers=hamburgers_items)
        burger_number = order.calculate_burgers_number()
        self.assertIsInstance(burger_number, int)
        self.assertEqual(burger_number, correct_output)

    def test_calculate_order_ingredients(self):
        correct_output = {"burgers_patties": 2,
                          "lettuce": 3,
                          "tomato": 3,
                          "veggie_patties": 1,
                          "bacon": 1}
        order_id = "O1"
        hamburgers_list = ["BLT", "LT", "VLT"]
        hamburgers_items = []
        for i, burger in enumerate(hamburgers_list):
            hamburgers_items.append(
                ut.Item(order_id=order_id,
                        item_id=i,
                        ingredients=burger)
            )
        order = ut.Order(branch_id="R1",
                         date_time="2020-12-08 19:15:31",
                         order_id=order_id,
                         hamburgers=hamburgers_items)
        ingredients = order.calculate_order_ingredients()
        self.assertIsInstance(ingredients, dict)
        self.assertDictEqual(ingredients, correct_output)
