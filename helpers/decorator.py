import time
from datetime import datetime


def func_default_wrapper(func):
    def wrapper(*args, **kwargs):
        print(f"-- Running [{func.__name__}]:")
        func(*args, **kwargs)
        print("-- Complete")

    return wrapper

def func_timer(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        func(*args, **kwargs)
        output_time = time.strftime("%H:%M:%S", time.localtime(time.time()-start_time))
        print(f"-- Ran in {output_time} seconds")
    return wrapper