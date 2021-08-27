import logging
import queue

from burger_joint_optimization.orders_optimisation import data_reader


logger = logging.getLogger(__name__)


def schedule(branches, orders):

    for branch_id, order_list in orders.items():
        order_queue = queue.Queue()
        order_queue.queue = queue.deque(order_list)
        for branch in branches:
            if branch.branch_id == branch_id:
                branch_info = branch
        schedule_branch_orders(branch_info, order_queue)


def schedule_branch_orders(branch_info, order_queue):

    cooking_capacity = branch_info.cooking["capacity"]
    assembling_capacity = branch_info.assembling["capacity"]
    packaging_capacity = branch_info.packaging["capacity"]

    cooking_lead_time = branch_info.cooking["lead_time"]
    assembling_lead_time = branch_info.assembling["lead_time"]
    packaging_lead_time = branch_info.packaging["lead_time"]

    cooking_queues = []
    for i in range(cooking_capacity):
        cooking_queues.append(queue.Queue())

    assembling_queues = []
    for i in range(assembling_capacity):
        assembling_queues.append(queue.Queue())

    packaging_queues = []
    for i in range(packaging_capacity):
        packaging_queues.append(queue.Queue())

    while True:
        order = order_queue.get()
        # print(order.burgers, order.date_time, order.calculate_burgers_number(),
        #       order.calculate_limit_time(), order.calculate_order_ingredients())
        burgers_number = order.calculate_burgers_number()
        print("burgers_number", burgers_number)

        for i in range(burgers_number):
            minimum_size = float('inf')
            for index, cooking_queue in enumerate(cooking_queues):
                queue_size = cooking_queue.qsize()
                if queue_size < minimum_size:
                    minimum_size = queue_size
                    selected_cooking_queue_index = index
            cooking_queues[selected_cooking_queue_index].put(order.burgers[i])
        print(cooking_queues[0].qsize(), cooking_queues[1].qsize(), cooking_queues[2].qsize(), cooking_queues[3].qsize())


if __name__ == "__main__":
    txt_filepath = "../tests/Files/input.txt"
    branches, orders = data_reader.read_input_txt(txt_filepath)
    schedule(branches=branches, orders=orders)
