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

        self.branch_id = branch_id
        self._cooking = cooking
        self._assembling = assembling
        self._packaging = packaging
        self._inventory = inventory

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