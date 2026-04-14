import logging
import re
import os
from datetime import datetime

from .order import Order, Item
from .branch import Branch

logger = logging.getLogger(__name__)

_VALID_INGREDIENT_KEYS = {"burgers_patties", "lettuce", "tomato",
                          "veggie_patties", "bacon"}

_RESTOCK_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def is_branch_info_line(line):
    """

    Args:
        line (str): a line extracted from the input file

    Returns:
        bool: whether or not the line contains valid branch info
    """

    branch_info_format = \
        re.compile("^R[0-9]+,[0-9]+C,[0-9]+,[0-9]+A,[0-9]+,[0-9]+P,[0-9]+,"
                   "[0-9]+,[0-9]+,[0-9]+,[0-9]+,[0-9]+$")
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
                              "[0-2][0-9]:[0-5][0-9]:[0-5][0-9],O[0-9]+"
                              "(,[BLTV]+)+(,P=[0-9]+)?$")

    match = re.match(order_format, line)
    if match is not None:
        return True
    else:
        return False


def is_restock_info_line(line):
    """

    Args:
        line (str): a line extracted from the input file

    Returns:
        bool: whether or not the line contains a valid RESTOCK directive
    """
    restock_format = re.compile(
        "^R[0-9]+,RESTOCK,[0-9]{4}-[0-1][0-9]-[0-3][0-9] "
        "[0-2][0-9]:[0-5][0-9]:[0-5][0-9]"
        "(,[a-z_]+:[0-9]+)+$")
    match = re.match(restock_format, line)
    return match is not None


def read_restock_info(restock_line):
    """Parse a RESTOCK line into ``(branch_id, datetime, {ingredient: amount})``.

    Raises :class:`UnknownIngredientError` when a key is not one of the
    five known ingredients.
    """
    parts = restock_line.rstrip("\n").split(",")
    branch_id = parts[0]
    # parts[1] is "RESTOCK"
    ts = datetime.strptime(parts[2], _RESTOCK_DATE_FORMAT)
    deltas = {}
    for tok in parts[3:]:
        key, amount = tok.split(":")
        if key not in _VALID_INGREDIENT_KEYS:
            raise UnknownIngredientError(
                "Unknown ingredient '{}' in restock line for branch"
                " {}".format(key, branch_id))
        amt = int(amount)
        if amt < 0:
            raise ValueError(
                "restock amount for {} must be non-negative, got {} "
                "(branch {})".format(key, amt, branch_id))
        deltas[key] = amt
    return branch_id, ts, deltas


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
                    "lead_time": int(cooking_time)}
    assembling_data = {"capacity": int(assembling_capacity.replace("A", "")),
                       "lead_time": int(assembling_time)}
    packaging_data = {"capacity": int(packaging_capacity.replace("P", "")),
                      "lead_time": int(packaging_time)}
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
    order_info_split = order_info_line.rstrip("\n").split(",")

    branch_id, date_time, order_id, *rest = order_info_split

    # Optional trailing P=<n> priority token.
    priority = 0
    if rest and rest[-1].startswith("P="):
        priority = int(rest[-1][2:])
        rest = rest[:-1]

    items_list = create_items(rest, order_id)

    return Order(branch_id=branch_id,
                 date_time=date_time,
                 order_id=order_id,
                 hamburgers=items_list,
                 priority=priority)


def create_items(hamburgers_list_no_new_line, order_id):
    items_list = []
    for i, ingredients in enumerate(hamburgers_list_no_new_line):
        hamburger = Item(order_id=order_id,
                         item_id=i,
                         ingredients=ingredients)
        items_list.append(hamburger)
    return items_list


def read_input_txt(path_to_txt_file):
    """
    It reads the input txt file and return a tuple containing branches info and
     orders info

    Args:
        path_to_txt_file (str):

    Returns:
        tuple(list(Branch), dict):
    """
    _check_read_input_txt(path_to_txt_file)

    branches_list = []
    branches_by_id = {}
    orders_dict = {}
    pending_restocks = {}

    with open(path_to_txt_file, "r") as f:
        while True:
            line = f.readline()

            # if line is empty end of file is reached
            if not line:
                break

            if is_branch_info_line(line):
                branch = read_branch_info(line)
                if branch.branch_id not in branches_by_id:
                    branches_list.append(branch)
                    branches_by_id[branch.branch_id] = branch
                    orders_dict[branch.branch_id] = []
                    buffered = pending_restocks.pop(branch.branch_id, [])
                    if buffered:
                        branch.add_restocks(buffered)
                else:
                    raise DuplicatedBranchIdError("The branch id {} already"
                                                  " exists".format(branch.branch_id))

            if is_order_info_line(line):
                order = read_order_info(line)
                if order.branch_id in orders_dict:
                    orders_dict[order.branch_id].append(order)
                else:
                    raise NoBranchInfoError("The order created with id {} "
                                            "refers to the branch {} "
                                            "for which no info are present"
                                            "".format(order.order_id,
                                                      order.branch_id))

            if is_restock_info_line(line):
                branch_id, ts, deltas = read_restock_info(line)
                if branch_id in branches_by_id:
                    branches_by_id[branch_id].add_restocks([(ts, deltas)])
                else:
                    pending_restocks.setdefault(branch_id, []).append(
                        (ts, deltas))

    if pending_restocks:
        orphan = next(iter(pending_restocks))
        raise NoBranchInfoError(
            "A restock line refers to branch {} for which no info are"
            " present".format(orphan))

    return branches_list, orders_dict


def _check_read_input_txt(path_to_orders_file):
    if not isinstance(path_to_orders_file, str):
        raise TypeError("path_to_orders_file should be a str, while it is"
                        " {}".format(type(path_to_orders_file)))
    if not os.path.isfile(path_to_orders_file):
        raise ValueError("path_to_orders_file {} does not exist or is not a"
                         " file".format(path_to_orders_file))
    if not path_to_orders_file.endswith(".txt"):
        raise ValueError("path_to_orders_file should have a .txt extension "
                         "while it is {}".format(path_to_orders_file))


class DuplicatedBranchIdError(ValueError):
    pass


class NoBranchInfoError(ValueError):
    pass


class UnknownIngredientError(ValueError):
    pass
