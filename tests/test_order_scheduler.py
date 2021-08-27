import unittest

import logging


import orders_optimisation.order_scheduler as ut

formatter = logging.Formatter(
    '%(asctime)s : %(name)s : %(levelname)s : %(message)s'
)
handler = logging.StreamHandler()
handler.setLevel(logging.CRITICAL)
handler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)


class TestOrderScheduler(unittest.TestCase):
    def test_schedule_orders(self):
        pass

