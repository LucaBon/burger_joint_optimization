import unittest
import logging


import orders_optimisation.order as ut

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

        branch_id = [[], {}, 1]
        date_time = [0., 3, [8]]
        order_id = [[], {}, 0.]
        hamburgers = [0, 1.7, {}]
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
                         hamburgers=["BLT", "LT", "VLT"])
        limit_time = order.calculate_limit_time()
        self.assertIsInstance(limit_time, str)
        self.assertEqual(limit_time, correct_output)

    def test_calculate_burger_number(self):
        correct_output = 3
        order = ut.Order(branch_id="R1",
                         date_time="2020-12-08 19:15:31",
                         order_id="O1",
                         hamburgers=["BLT", "LT", "VLT"])
        burger_number = order.calculate_burgers_number()
        self.assertIsInstance(burger_number, int)
        self.assertEqual(burger_number, correct_output)

    def test_calculate_order_ingredients(self):
        correct_output = {"burgers_patties": 2,
                          "lettuce": 3,
                          "tomato": 3,
                          "veggie_patties": 1,
                          "bacon": 1}
        order = ut.Order(branch_id="R1",
                         date_time="2020-12-08 19:15:31",
                         order_id="O1",
                         hamburgers=["BLT", "LT", "VLT"])
        ingredients = order.calculate_order_ingredients()
        self.assertIsInstance(ingredients, dict)
        self.assertDictEqual(ingredients, correct_output)
