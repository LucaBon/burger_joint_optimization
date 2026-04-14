"""Domain types for customer orders and individual burger items.

Orders arrive at a branch at a known wall-clock instant and must be
completed within :attr:`Order.max_order_completion_time` minutes of that
instant (default 20). Each order owns a list of :class:`Item` burgers
whose ingredient codes follow the ``[BLTV]+`` alphabet:

* ``B`` -- bacon
* ``L`` -- lettuce
* ``T`` -- tomato
* ``V`` -- veggie patty (absence implies a beef patty)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)


DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_INGREDIENT_KEYS = (
    "burgers_patties", "lettuce", "tomato", "veggie_patties", "bacon",
)


def burger_ingredients(code: str) -> Dict[str, int]:
    """Return the five-key ingredient dict for a single burger ``code``.

    Uses the same "V implies veggie else beef" rule as :class:`Order`.
    Raises :class:`InvalidIngredientError` on any unknown single-letter
    code.
    """
    out = {k: 0 for k in _INGREDIENT_KEYS}
    if "V" not in code:
        out["burgers_patties"] += 1
    for ch in code:
        if ch == "L":
            out["lettuce"] += 1
        elif ch == "T":
            out["tomato"] += 1
        elif ch == "B":
            out["bacon"] += 1
        elif ch == "V":
            out["veggie_patties"] += 1
        else:
            raise InvalidIngredientError(
                "The order contains the following invalid ingredient: "
                "{}".format(ch))
    return out


class Order:
    """A customer order filed at a specific branch.

    ``date_time`` may be passed as either a ``%Y-%m-%d %H:%M:%S`` string
    (historical format used by the data reader) or an already-parsed
    :class:`datetime.datetime`. It is normalised to a ``datetime`` once
    at construction so the scheduler hot path can sort and compare
    without re-parsing on every admission.

    ``max_completion_time`` is the per-order SLA in minutes. Defaults
    to the class constant (20 min) so existing code keeps working; set
    it per instance to model custom SLAs.

    ``priority`` is an optional non-negative integer honoured by
    priority-aware dispatch policies (higher = more important).
    """

    # default SLA in minutes; kept as a class constant for backwards compat.
    max_order_completion_time = 20

    def __init__(self,
                 branch_id: str,
                 date_time: Union[str, datetime],
                 order_id: str,
                 hamburgers: List["Item"],
                 max_completion_time: Optional[int] = None,
                 priority: int = 0):
        self._check_input(branch_id, date_time, hamburgers, order_id,
                          max_completion_time, priority)

        self.branch_id: str = branch_id
        if isinstance(date_time, str):
            self.date_time: datetime = datetime.strptime(date_time, DATE_FORMAT)
        else:
            self.date_time = date_time
        self.order_id: str = order_id
        self.burgers: List["Item"] = hamburgers
        self.max_order_completion_time: int = (
            int(max_completion_time)
            if max_completion_time is not None
            else Order.max_order_completion_time
        )
        self.priority: int = int(priority)

    @property
    def deadline(self) -> datetime:
        """Wall-clock deadline derived from ``date_time`` + SLA."""
        return self.date_time + timedelta(
            minutes=self.max_order_completion_time)

    @property
    def date_time_str(self) -> str:
        """String form of ``date_time`` in the legacy input format."""
        return self.date_time.strftime(DATE_FORMAT)

    @staticmethod
    def _check_input(branch_id, date_time, hamburgers, order_id,
                     max_completion_time, priority):
        if not isinstance(branch_id, str):
            raise TypeError(
                "branch_id should be a str, while it is a {}".format(
                    type(branch_id)))
        if not isinstance(date_time, (str, datetime)):
            raise TypeError(
                "date_time should be a str or datetime, while it is a {}"
                "".format(type(date_time)))
        if not isinstance(order_id, str):
            raise TypeError(
                "order_id should be a str, while it is a {}".format(
                    type(order_id)))
        if not isinstance(hamburgers, list):
            raise TypeError(
                "hamburgers should be a list, while it is a {}".format(
                    type(hamburgers)))
        if max_completion_time is not None:
            if (not isinstance(max_completion_time, int)
                    or isinstance(max_completion_time, bool)
                    or max_completion_time <= 0):
                raise ValueError(
                    "max_completion_time must be a positive int, got {}"
                    "".format(max_completion_time))
        if (not isinstance(priority, int) or isinstance(priority, bool)
                or priority < 0):
            raise ValueError(
                "priority must be a non-negative int, got {}".format(priority))

    def calculate_limit_time(self) -> str:
        """Return the SLA-limit timestamp as a ``%Y-%m-%d %H:%M:%S`` string.

        Kept for backwards compatibility with the v1 public API; new
        code should read the :attr:`deadline` property instead.
        """
        return self.deadline.strftime(DATE_FORMAT)

    def calculate_burgers_number(self) -> int:
        """Return the number of burgers in this order."""
        return len(self.burgers)

    def calculate_order_ingredients(self) -> Dict[str, int]:
        """Aggregate the ingredient requirements across every burger."""
        order_ingredients = {k: 0 for k in _INGREDIENT_KEYS}
        for burger in self.burgers:
            for k, v in burger_ingredients(burger.ingredients).items():
                order_ingredients[k] += v
        return order_ingredients


class Item:
    """A single burger inside an :class:`Order`.

    Ingredient validation runs eagerly at construction so malformed
    burgers are rejected at parse time rather than at admission time.
    """

    def __init__(self, order_id: str, item_id: int, ingredients: str):
        if not isinstance(ingredients, str):
            raise TypeError(
                "ingredients should be a str, while it is a {}".format(
                    type(ingredients)))
        if not ingredients:
            raise InvalidIngredientError(
                "ingredients string must be non-empty")
        # Validate eagerly (raises InvalidIngredientError on unknown codes).
        burger_ingredients(ingredients)

        self.order_id: str = order_id
        self.item_id: int = item_id
        self.ingredients: str = ingredients


class InvalidIngredientError(ValueError):
    """Raised when a burger code contains an unknown single-letter token."""
    pass
