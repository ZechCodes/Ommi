from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ommi.drivers import BaseDriver


class BaseDriverException(Exception):
    """Base exception for driver exceptions."""
    def __init__(self, *args, driver: "BaseDriver"):
        super().__init__(*args)

        self.driver = driver
        self.add_note(f" - Using Driver: {driver!r}")


class FailedToConnect(BaseDriverException):
    """Raised when a driver fails to connect to a database."""


class FailedToAdd(BaseDriverException):
    """Raised when a driver fails to add models to a database."""


class FailedQuery(BaseDriverException):
    """Raised when a driver fails to execute a predicate query."""
