import os
import tempfile
import unittest
import logging
from datetime import datetime


import orders_optimisation.data_reader as ut

FILES_DIR = os.path.join(os.path.dirname(__file__), "Files")

formatter = logging.Formatter(
    '%(asctime)s : %(name)s : %(levelname)s : %(message)s'
)
handler = logging.StreamHandler()
handler.setLevel(logging.CRITICAL)
handler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)


class TestReadInputTxt(unittest.TestCase):
    def test_input(self):
        # Check TypeError is correctly raised
        inputs = [[], {}, 1]
        for input_error in inputs:
            with self.assertRaises(TypeError):
                ut.read_input_txt(path_to_txt_file=input_error)
        inputs = ['', 'path_to_nowhere', os.path.join(FILES_DIR, 'wrong_extension_file.pp')]
        for input_error in inputs:
            with self.assertRaises(ValueError):
                ut.read_input_txt(path_to_txt_file=input_error)

    def test_normal_behavior(self):
        input_txt = os.path.join(FILES_DIR, "input.txt")
        branches, orders = ut.read_input_txt(input_txt)

        self.assertIsInstance(branches, list)
        self.assertEqual(len(branches), 1)
        self.assertIsInstance(orders, dict)
        self.assertEqual(len(orders), 1)
        self.assertIsInstance(orders['R1'], list)
        self.assertEqual(len(orders['R1']), 12)

    def test_raises_duplicated_branch_id_error(self):
        input_error = os.path.join(FILES_DIR, "duplicated_branch_id.txt")
        with self.assertRaises(ut.DuplicatedBranchIdError):
            ut.read_input_txt(path_to_txt_file=input_error)

    def test_raises_no_branch_info_error(self):
        input_error = os.path.join(FILES_DIR, "no_branch_info_error.txt")
        with self.assertRaises(ut.NoBranchInfoError):
            ut.read_input_txt(path_to_txt_file=input_error)

    def test_restock_line_parsed(self):
        line = ("R1,RESTOCK,2026-04-10 10:15:00,burgers_patties:5,"
                "lettuce:10")
        self.assertTrue(ut.is_restock_info_line(line))
        branch_id, ts, deltas = ut.read_restock_info(line)
        self.assertEqual(branch_id, "R1")
        self.assertEqual(ts, datetime(2026, 4, 10, 10, 15, 0))
        self.assertEqual(deltas, {"burgers_patties": 5, "lettuce": 10})

    def test_restock_unknown_ingredient_raises(self):
        line = "R1,RESTOCK,2026-04-10 10:15:00,bogus:1"
        with self.assertRaises(ut.UnknownIngredientError):
            ut.read_restock_info(line)

    def test_restock_line_before_branch_line_buffers(self):
        content = (
            "R1,RESTOCK,2020-12-08 19:10:00,burgers_patties:3\n"
            "R1,4C,1,3A,2,2P,1,100,200,200,100,100\n"
            "R1,2020-12-08 19:15:31,O1,BLT\n"
        )
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            branches, orders = ut.read_input_txt(path)
            self.assertEqual(len(branches), 1)
            restocks = branches[0].restocks
            self.assertEqual(len(restocks), 1)
            self.assertEqual(
                restocks[0][0], datetime(2020, 12, 8, 19, 10, 0))
            self.assertEqual(restocks[0][1], {"burgers_patties": 3})
        finally:
            os.remove(path)

    def test_orphan_restock_raises_no_branch_info_error(self):
        content = (
            "R1,4C,1,3A,2,2P,1,100,200,200,100,100\n"
            "R2,RESTOCK,2020-12-08 19:10:00,burgers_patties:3\n"
        )
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            with self.assertRaises(ut.NoBranchInfoError):
                ut.read_input_txt(path)
        finally:
            os.remove(path)
