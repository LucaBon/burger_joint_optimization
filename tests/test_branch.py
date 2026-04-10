import unittest
import logging

import orders_optimisation.branch as ut

formatter = logging.Formatter(
    '%(asctime)s : %(name)s : %(levelname)s : %(message)s'
)
handler = logging.StreamHandler()
handler.setLevel(logging.CRITICAL)
handler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)


class TestBranch(unittest.TestCase):
    def test_input(self):
        # Check TypeError is correctly raised

        branch_id = [[], {}, 1]
        cooking = [[], 3, 1.]
        assembling = [[], 3, 1.]
        packaging = [[], 3, 1.]
        inventory = [[], 3, 1.]

        for b, c, a, p, i in zip(branch_id, cooking, assembling, packaging, inventory):
            with self.assertRaises(TypeError):
                ut.Branch(branch_id=b,
                          cooking=c,
                          assembling=a,
                          packaging=p,
                          inventory=i)

    def test_remove_ingredients_from_inventory(self):
        branch_id = "R1"
        cooking = {"capacity": 4,
                   "lead_time": 2}
        assembling = {"capacity": 3,
                      "lead_time": 1}
        packaging = {"capacity": 4,
                     "lead_time": 3}
        inventory = {"burgers_patties": 10,
                     "lettuce": 5,
                     "tomato": 9,
                     "veggie_patties": 2,
                     "bacon": 4}
        branch = ut.Branch(branch_id=branch_id,
                           cooking=cooking,
                           assembling=assembling,
                           packaging=packaging,
                           inventory=inventory)

        ingredients_to_remove = {"burgers_patties": 5,
                                 "lettuce": 3,
                                 "tomato": 6,
                                 "veggie_patties": 2,
                                 "bacon": 4}

        correct_output = {"burgers_patties": 5,
                          "lettuce": 2,
                          "tomato": 3,
                          "veggie_patties": 0,
                          "bacon": 0}

        branch.remove_ingredients_from_inventory(ingredients_to_remove=ingredients_to_remove)
        self.assertIsInstance(branch.inventory, dict)
        self.assertDictEqual(branch.inventory, correct_output)

