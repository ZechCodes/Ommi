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
"""A context variable that holds the currently active database driver.

This variable is managed by the `UseDriver` context manager (typically accessed
via the `use_driver` function). It allows different parts of an application,
particularly those that might be handling concurrent requests or tasks, to have
their own isolated notion of the "current" database driver.

Framework code or utilities within Ommi can then call `active_driver.get()`
to retrieve the driver appropriate for the current execution context.
"""


class UseDriver(Generic[T]):
    """A context manager for setting and resetting the active database driver.

    This class allows a specific database driver to be designated as "active" within
    a `with` statement's scope. Upon entering the `with` block, the provided driver
    is set on the `active_driver` context variable. Upon exiting, the previous state
    of `active_driver` is restored.

    This is crucial for scenarios where multiple drivers might be configured or used
    within an application, or when managing driver instances per request/task in an
    asynchronous environment.

    It's generally more convenient to use the `ommi.use_driver()` function, which
    returns an instance of this class.

    Attributes:
        driver (T): The database driver instance to be activated within the context.
    """
    def __init__(self, driver: T):
        """
        Args:
            driver: The database driver instance to activate.
        """
        self.driver = driver
        self._previous_context_token = None

    def __enter__(self) -> T:
        """Sets the provided driver as the active one in the current context.

        Returns:
            The driver instance that was set as active.
        """
        self._previous_context_token = active_driver.set(self.driver)
        return self.driver

    def __exit__(self, *_):
        """Resets the active driver to its state before entering the context."""
        active_driver.reset(self._previous_context_token)


def use_driver(driver: T) -> UseDriver[T]:
    """Factory function to create a `UseDriver` context manager instance.

    This is the recommended way to use the `UseDriver` context manager.

    Args:
        driver: The database driver instance to be activated within the context.

    Returns:
        A `UseDriver` instance configured with the provided driver.

    Example:
        ```python
        from ommi import use_driver
        from my_app.drivers import my_specific_driver

        async def some_database_operation():
            # ... code that needs the active driver ...
            pass

        async def main():
            with use_driver(my_specific_driver):
                await some_database_operation() # active_driver is my_specific_driver here
            # active_driver is restored to its previous state (or unset)
        ```
    """
    return UseDriver(driver)
