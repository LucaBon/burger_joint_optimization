import logging

from datetime import datetime
from datetime import timedelta

logger = logging.getLogger(__name__)


class Order:

    # each order should be processed within 20 minutes
    max_order_completion_time = 20

    def __init__(self,
                 branch_id,
                 date_time,
                 order_id,
                 hamburgers):

        self._check_input(branch_id, date_time, hamburgers, order_id)

        self.branch_id = branch_id
        self.date_time = date_time
        self.order_id = order_id
        self.burgers = hamburgers

        self.limit_time = None
        self.burgers_number = None

    @staticmethod
    def _check_input(branch_id, date_time, hamburgers, order_id):
        if not isinstance(branch_id, str):
            raise TypeError("branch_id should be a str, while it is a {}".format(type(branch_id)))
        if not isinstance(date_time, str):
            raise TypeError("date_time should be a str, while it is a {}".format(type(date_time)))
        if not isinstance(order_id, str):
            raise TypeError("order_id should be a str, while it is a {}".format(type(order_id)))
        if not isinstance(hamburgers, list):
            raise TypeError("hamburgers should be a list, while it is a {}".format(type(hamburgers)))

    def calculate_limit_time(self):
        date_format_str = '%Y-%m-%d %H:%M:%S'
        _date_time = datetime.strptime(self.date_time, date_format_str)
        limit_time = _date_time + timedelta(minutes=Order.max_order_completion_time)
        self.limit_time = datetime.strftime(limit_time, date_format_str)
        return self.limit_time

    def calculate_burgers_number(self):
        self.burgers_number = len(self.burgers)
        return self.burgers_number

    def calculate_order_ingredients(self):
        print(self.burgers)
        order_ingredients = {"burgers_patties": 0,
                             "lettuce": 0,
                             "tomato": 0,
                             "veggie_patties": 0,
                             "bacon": 0}
        for burger in self.burgers:
            if "V" not in burger:
                order_ingredients["burgers_patties"] += 1

            for ingredient in burger:
                if ingredient == "L":
                    order_ingredients["lettuce"] += 1
                if ingredient == "T":
                    order_ingredients["tomato"] += 1
                if ingredient == "B":
                    order_ingredients["bacon"] += 1
                if ingredient == "V":
                    order_ingredients["veggie_patties"] += 1
                elif ingredient not in ["L", "T", "B", "V"]:
                    raise InvalidIngredientError("The order contains the following invalid ingredient: {}"
                                                 "".format(ingredient))
        return order_ingredients

    def are_ingredients_in_inventory(self):
        pass


class InvalidIngredientError(ValueError):
    pass