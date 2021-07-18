import logging

from orders_optimisation.data_reader import read_input_txt


logger = logging.getLogger(__name__)


def schedule_orders(path_to_txt_file):
    """

    Args:
        path_to_txt_file (str): path to txt file containing orders

    Returns:

    """
    branches, orders = read_input_txt(path_to_txt_file=path_to_txt_file)
    pass
