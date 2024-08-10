"""
Context Manager for managing the active database driver

This module provides a context management utility for handling the active
database driver within the Ommi framework using Python's contextvars module.

The context management implemented here ensures that the active driver is
properly set and reset when entering and exiting the context, maintaining
the correct driver context across different parts of the application.
"""


from contextvars import ContextVar
from typing import TypeVar, Generic


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
