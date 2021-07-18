## SATIS AI coding challenge

### Build the image
From the root folder

* ```docker build -t satis_ai .```

### Run the image

* ```docker run -it --rm -v $(pwd):/app satis_ai bash```

### Instructions
The main function is `schedule_orders` in 'order_scheduler.py`