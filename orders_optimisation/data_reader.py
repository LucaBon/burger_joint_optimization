import logging
import re
import os

from orders_optimisation.order import Order
from orders_optimisation.branch import Branch

logger = logging.getLogger(__name__)


def is_branch_info_line(line):
    """

    Args:
        line (str): a line extracted from the input file

    Returns:
        bool: whether or not the line contains valid branch info
    """

    branch_info_format = re.compile("^R[0-9]+,[0-9]+C,[0-9]+,[0-9]+A,[0-9]+,[0-9]+P,[0-9]+,[0-9]+,[0-9]+,[0-9]+,"
                                    "[0-9]+,[0-9]+$")
    match = re.match(branch_info_format, line)
    if match is not None:
        return True
    else:
        return False


def is_order_info_line(line):
    """

    Args:
        line (str):  a line extracted from the input file

    Returns:
        bool: whether or not the line contains valid order info
    """
    order_format = re.compile("^R[0-9]+,[0-9]{4}-[0-1][0-9]-[0-3][0-9] "
                              "[0-2][0-9]:[0-5][0-9]:[0-5][0-9],O[0-9]+(,[BLTV]+)+$")

    match = re.match(order_format, line)
    if match is not None:
        return True
    else:
        return False


def read_branch_info(branch_info_line):
    """

    Args:
        branch_info_line (str): a validated line that contains branch info

    Returns:
        Branch
    """
    branch_info_split = branch_info_line.split(",")

    branch_id, \
        cooking_capacity, \
        cooking_time, \
        assembling_capacity, \
        assembling_time, \
        packaging_capacity, \
        packaging_time, \
        burgers_number, \
        lettuce_number, \
        tomato_number, \
        veggie_burgers_number, \
        bacon_number = branch_info_split

    cooking_data = {"capacity": int(cooking_capacity.replace("C", "")),
                    "lead_time": int(cooking_time)},
    assembling_data = {"capacity": int(assembling_capacity.replace("A", "")),
                       "lead_time": int(assembling_time)},
    packaging_data = {"capacity": int(packaging_capacity.replace("P", "")),
                      "lead_time": int(packaging_time)},
    inventory = {"burgers_patties": int(burgers_number),
                 "lettuce": int(lettuce_number),
                 "tomato": int(tomato_number),
                 "veggie_patties": int(veggie_burgers_number),
                 "bacon": int(bacon_number)}

    return Branch(branch_id=branch_id,
                  cooking=cooking_data,
                  assembling=assembling_data,
                  packaging=packaging_data,
                  inventory=inventory)


def read_order_info(order_info_line):
    """

    Args:
        order_info_line (str): a validated string that contains order info

    Returns:
        Order
    """
    order_info_split = order_info_line.split(",")

    branch_id, date_time, order_id, *hamburgers_list = order_info_split

    # remove new line
    hamburgers_list_no_new_line = [hamburger.rstrip("\n") for hamburger in hamburgers_list]
    print(hamburgers_list_no_new_line)

    return Order(branch_id=branch_id,
                 date_time=date_time,
                 order_id=order_id,
                 hamburgers=hamburgers_list_no_new_line)


def read_input_txt(path_to_txt_file):
    """
    It reads the input txt file and return a tuple containing branches info and orders info

    Args:
        path_to_txt_file (str):

    Returns:
        tuple(list(Branch), dict):
    """
    _check_read_input_txt(path_to_txt_file)

    branches_list = []
    orders_dict = {}

    with open(path_to_txt_file, "r") as f:
        while True:
            line = f.readline()

            # if line is empty end of file is reached
            if not line:
                break

            if is_branch_info_line(line):
                branch = read_branch_info(line)
                branches_id_list = [branch_obj.branch_id for branch_obj in branches_list]
                if branch.branch_id not in branches_id_list:
                    branches_list.append(branch)
                    orders_dict[branch.branch_id] = []
                else:
                    raise DuplicatedBranchIdError("The branch id {} already exists".format(branch.branch_id))

            if is_order_info_line(line):
                order = read_order_info(line)
                if order.branch_id in orders_dict:
                    orders_dict[order.branch_id].append(order)
                else:
                    raise NoBranchInfoError("The order created with id {} refers to the branch {} "
                                            "for which no info are present".format(order.order_id, order.branch_id))

    return branches_list, orders_dict


def _check_read_input_txt(path_to_orders_file):
    if not isinstance(path_to_orders_file, str):
        raise TypeError("path_to_orders_file should be a str, while it is {}".format(type(path_to_orders_file)))
    if not os.path.isfile(path_to_orders_file):
        raise ValueError("path_to_orders_file {} does not exist or is not a file".format(path_to_orders_file))
    if not path_to_orders_file.endswith(".txt"):
        raise ValueError("path_to_orders_file should have a .txt extension while it is {}".format(path_to_orders_file))


class DuplicatedBranchIdError(ValueError):
    pass


class NoBranchInfoError(ValueError):
    pass
