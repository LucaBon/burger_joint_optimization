## Burger joint optimization

### Build the image
From the root folder

* ```docker build -t burger_joint .```

### Run the image

* ```docker run -it --rm -v $(pwd):/app burger_joint bash```

### Instructions
The main function is `schedule_orders` in 'order_scheduler.py`
