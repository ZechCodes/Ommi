from contextvars import ContextVar
from contextlib import contextmanager

import ommi.drivers as drivers


active_driver = ContextVar("active_driver")


@contextmanager
def use_driver(driver: "drivers.DatabaseDriver"):
    previous_driver = active_driver.get()
    active_driver.set(driver)
    yield driver
    active_driver.set(previous_driver)
