import time
import random
import sys

def retry(ExceptionToCheck, tries=10, timeout_secs=1.0):
    """
    Retry calling the decorated function using an exponential backoff.
    """
    def deco_retry(f):
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, timeout_secs
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except ExceptionToCheck as e:
                    half_interval = mdelay * 0.10 #interval size
                    actual_delay = random.uniform(mdelay - half_interval, mdelay + half_interval)
                    time.sleep(actual_delay)
                    mtries -= 1
                    mdelay *= 2
                    if mtries <= 1:
                    	raise
            return f(*args, **kwargs)
        return f_retry  # true decorator
    return deco_retry