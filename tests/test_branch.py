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

    def test_rejects_non_positive_capacity(self):
        with self.assertRaises(ValueError):
            ut.Branch(branch_id="R1",
                      cooking={"capacity": 0, "lead_time": 1},
                      assembling={"capacity": 1, "lead_time": 1},
                      packaging={"capacity": 1, "lead_time": 1},
                      inventory={"burgers_patties": 1, "lettuce": 1,
                                 "tomato": 1, "veggie_patties": 1,
                                 "bacon": 1})

    def test_rejects_negative_lead_time(self):
        with self.assertRaises(ValueError):
            ut.Branch(branch_id="R1",
                      cooking={"capacity": 1, "lead_time": -1},
                      assembling={"capacity": 1, "lead_time": 1},
                      packaging={"capacity": 1, "lead_time": 1},
                      inventory={"burgers_patties": 1, "lettuce": 1,
                                 "tomato": 1, "veggie_patties": 1,
                                 "bacon": 1})

    def test_inventory_is_deepcopied(self):
        inventory = {"burgers_patties": 10, "lettuce": 5, "tomato": 9,
                     "veggie_patties": 2, "bacon": 4}
        branch = ut.Branch(branch_id="R1",
                           cooking={"capacity": 1, "lead_time": 1},
                           assembling={"capacity": 1, "lead_time": 1},
                           packaging={"capacity": 1, "lead_time": 1},
                           inventory=inventory)
        inventory["lettuce"] = 0
        self.assertEqual(branch.inventory["lettuce"], 5)

