from contextvars import ContextVar
from contextlib import contextmanager
from typing import Generator, TypeVar, Generic

import ommi.drivers as drivers


T = TypeVar("T", bound="drivers.DatabaseDriver")


active_driver = ContextVar("active_driver")


class UseDriver(Generic[T]):
    def __init__(self, driver: T):
        self.driver = driver
        self._previous_context_token = None

    def __enter__(self) -> T:
        self._previous_context_token = active_driver.set(self.driver)
        return self.driver

    def __exit__(self, *_):
        active_driver.reset(self._previous_context_token)


def use_driver(driver: T) -> UseDriver[T]:
    return UseDriver(driver)
