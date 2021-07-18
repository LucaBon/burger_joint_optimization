import logging

logger = logging.getLogger(__name__)


class Branch:
    def __init__(self,
                 branch_id,
                 cooking,
                 assembling,
                 packaging,
                 inventory):
        """

        Args:
            branch_id (str):  the ID of the branch
            cooking (dict): it contains info about the cooking process.
                            It is  structured as follows {"capacity": int,
                                                          "lead_time": int}
            assembling: it contains info about the assembling process.
                        It is  structured as follows {"capacity": int,
                                                      "lead_time": int}
            packaging: it contains info about the packaging process.
                       It is  structured as follows {"capacity": int,
                                                     "lead_time": int}
            inventory: it contains info about the inventory.
                       It is structured as follows {"burgers_patties": int,
                                                    "lettuce": int,
                                                    "tomato": int,
                                                    "veggie_patties": int,
                                                    "bacon": int}
        """

        self._check_input(branch_id, cooking, assembling, packaging, inventory)

        self.branch_id = branch_id
        self._cooking = cooking
        self._assembling = assembling
        self._packaging = packaging
        self._inventory = inventory

    @staticmethod
    def _check_input(branch_id, cooking, assembling, packaging, inventory):
        if not isinstance(branch_id, str):
            raise TypeError("branch_id should be a str, while it is a {}".format(type(branch_id)))
        if not isinstance(cooking, dict):
            raise TypeError("cooking should be a dict, while it is a {}".format(type(cooking)))
        if not isinstance(assembling, dict):
            raise TypeError("assembling should be a dict, while it is a {}".format(type(assembling)))
        if not isinstance(packaging, dict):
            raise TypeError("packaging should be a dict, while it is a {}".format(type(packaging)))
        if not isinstance(inventory, dict):
            raise TypeError("inventory should be a dict, while it is a {}".format(type(packaging)))
        if len(cooking) != 2:
            raise ValueError("cooking should contain two keys, while it contains {} keys".format(len(cooking)))
        for k, v in cooking.items():
            if k not in ["capacity", "lead_time"]:
                raise ValueError("cooking should contain two keys: 'capacity' and 'lead_time', while it contains {}"
                                 "".format(k))
        if len(assembling) != 2:
            raise ValueError("assembling should contain two keys, while it contains {} keys".format(len(assembling)))
        for k, v in assembling.items():
            if k not in ["capacity", "lead_time"]:
                raise ValueError("assembling should contain two keys: 'capacity' and 'lead_time', while it contains {}"
                                 "".format(k))
        if len(packaging) != 2:
            raise ValueError("packaging should contain two keys, while it contains {} keys".format(len(packaging)))
        for k, v in packaging.items():
            if k not in ["capacity", "lead_time"]:
                raise ValueError("packaging should contain two keys: 'capacity' and 'lead_time', while it contains {}"
                                 "".format(k))
        if len(inventory) != 5:
            raise ValueError("inventory should contain five keys, while it contains {} keys".format(len(inventory)))
        for k, v in inventory.items():
            if k not in ["burgers_patties", "lettuce", "tomato", "veggie_patties", "bacon"]:
                raise ValueError("inventory should contain five keys: 'burgers_patties', 'lettuce', 'tomato', "
                                 "'veggie_patties', 'bacon', while it contains {}"
                                 "".format(k))

    @property
    def cooking(self):
        return self._cooking

    @property
    def assembling(self):
        return self._assembling

    @property
    def packaging(self):
        return self._packaging

    @property
    def inventory(self):
        return self._inventory

    def remove_ingredients_from_inventory(self, ingredients_to_remove):
        for (k_inventory, v_inventory), (k_ingredients, v_ingredients) in zip(
                sorted(self._inventory.items()), sorted(ingredients_to_remove.items())):
            difference = v_inventory - v_ingredients
            if difference < 0:
                raise ExhaustedIngredientError("The ingredient {} is exhausted".format(k_inventory))
            self._inventory[k_inventory] = difference


class ExhaustedIngredientError(ValueError):
    pass