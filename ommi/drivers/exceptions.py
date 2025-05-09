from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ommi.drivers import BaseDriver


class BaseDriverException(Exception):
    """Base exception for driver exceptions."""
    def __init__(self, *args, driver: "BaseDriver | Type[BaseDriver] | None" = None):
        super().__init__(*args)

        self.driver = driver
        if driver:
            self.add_note(f" - Using Driver: {driver!r}")


class DriverConnectFailed(BaseDriverException):
    """Raised when a driver fails to connect to a database."""


class DriverAddFailed(BaseDriverException):
    """Raised when a driver fails to add models to a database."""


class DriverQueryFailed(BaseDriverException):
    """Raised when a driver fails to execute a predicate query."""


class DriverModelNotFound(BaseDriverException):
    """Raised when a model is not found using a driver."""


class DriverOperationError(BaseDriverException):
    """Raised for general errors during driver operations not covered by more specific exceptions."""
    pass


class ModelInsertError(DriverAddFailed):
    """Raised specifically when inserting a model instance fails (subset of DriverAddFailed)."""
    pass


class SchemaError(BaseDriverException):
    """Raised for errors encountered during schema manipulation (apply/delete)."""
    pass


class TransactionError(Exception):
    """Raised for errors related to transaction lifecycle (e.g., commit, rollback, already open)."""
    pass


class LockError(BaseDriverException):
    """Raised when there is an issue with database locking during a transaction or operation."""
    pass


class UnsupportedError(BaseDriverException):
    """Raised when a driver does not support a feature or operation."""
    pass
