import unittest
import logging
import os

import orders_optimisation.data_reader as ut

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
        inputs = ['', 'path_to_nowhere', 'Files/wrong_extension_file.pp']
        for input_error in inputs:
            with self.assertRaises(ValueError):
                ut.read_input_txt(path_to_txt_file=input_error)

    def test_normal_behavior(self):
        input_txt = "Files/input.txt"
        branches, orders = ut.read_input_txt(input_txt)

        self.assertIsInstance(branches, list)
        self.assertEqual(len(branches), 1)
        self.assertIsInstance(orders, dict)
        self.assertEqual(len(orders), 1)
        self.assertIsInstance(orders['R1'], list)
        self.assertEqual(len(orders['R1']), 12)

    def test_raises_duplicated_branch_id_error(self):
        input_error = "Files/duplicated_branch_id.txt"
        with self.assertRaises(ut.DuplicatedBranchIdError):
            ut.read_input_txt(path_to_txt_file=input_error)

    def test_raises_no_branch_info_error(self):
        input_error = "Files/no_branch_info_error.txt"
        with self.assertRaises(ut.NoBranchInfoError):
            ut.read_input_txt(path_to_txt_file=input_error)
