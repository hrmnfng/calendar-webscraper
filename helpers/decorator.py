'''
Adds simple wrappers and decorator functions for timing and method callout.
'''

import time

def func_default_wrapper(func):
    '''
    Default wrapper that calls out function start and end.

    Args:
        func (func): Function being called.

    Returns:
        Start and end print statements.
    '''
    def wrapper(*args, **kwargs):
        print(f"-- Running [{func.__name__}]:")
        func(*args, **kwargs)
        print("-- Complete")

    return wrapper

def func_timer(func):
    '''
    Wrapper that gives runtime of specified function.

    Args:
        func (func): Function being called.

    Returns:
        Total func runtime printed after the function runs.
    '''
    def wrapper(*args, **kwargs):
        start_time = time.time()
        func(*args, **kwargs)
        output_time = time.strftime("%H:%M:%S", time.localtime(time.time()-start_time))
        print(f"-- Ran in {output_time} seconds")

    return wrapper
