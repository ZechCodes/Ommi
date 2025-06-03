"""Provides classes for handling the results of database operations that return a single value or status.

This module defines a structured way to represent the outcomes of database
operations like adding a single record or performing an update/delete that might
not return data but can succeed or fail. This is primarily through the `DBResult`
family of classes and the `DBResultBuilder`.

It is similar in purpose to `ommi.database.query_results` but is geared towards
operations that are expected to yield a single result object or just a success/failure
status, rather than a collection of results (like a query fetching multiple rows).

Key Components:

-   `DBResult[T]`: An abstract base class representing the outcome of an operation.
    It has two concrete subclasses:
    -   `DBSuccess[T]`: Indicates a successful operation, potentially holding a
        result value (e.g., a newly added model instance).
    -   `DBFailure[T]`: Indicates a failed operation, holding the exception.
-   `DBResultBuilder[T]`: A builder and awaitable wrapper. It takes a callback
    (an awaitable function) and its arguments. When awaited, it executes the
    callback and wraps the outcome in `DBSuccess` or `DBFailure`.
    This is used internally by `Ommi.add()` and similar methods.
-   `DBStatusNoResultException`: An exception typically raised when attempting to
    access a `.result` on `DBFailure` or `.exception` on `DBSuccess`.

Workflow:
1.  An operation like `db.add(my_model)` is called.
2.  Internally, this might use `DBResult.build(driver_add_method, my_model)`,
    which creates a `DBResultBuilder` instance.
3.  The `DBResultBuilder` is then `await`ed.
4.  The `await` triggers the execution of the `driver_add_method(my_model)`.
5.  The outcome (the added model or an exception) is wrapped in `DBSuccess`
    or `DBFailure`, which is the final result.

Example:
    ```python
    # Assuming `db` is an Ommi instance and `User` is an @ommi_model
    user_to_add = User(name="Eve")

    # db.add() internally uses DBResultBuilder
    match await db.add(user_to_add):
        case DBResult.DBSuccess([added_user, *_]):
            print(f"Successfully added user: {added_user.name}, ID: {added_user.id}")
        case DBResult.DBFailure(exception):
            print(f"Failed to add user: {exception}")
    ```
"""
from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Type


class DBStatusNoResultException(Exception):
    """Exception raised when attempting to access a non-existent result or exception.

    This typically occurs if you try to access:
    -   `.result` on a `DBFailure` instance (as failures don't have a data result).
    -   `.exception` on a `DBSuccess` instance (as successes don't have an exception).
    """
    pass


class DBResult[T](ABC):
    """Abstract base class for representing the outcome of a single database operation.

    Provides a structured way (`DBSuccess`, `DBFailure`) to handle results or errors
    from operations like adding a record or a simple update/delete confirmation.
    Supports Python's `match/case` for pattern matching.

    Class Attributes:
        DBSuccess (Type[DBSuccess[T]]): Reference to the `DBSuccess` class.
        DBFailure (Type[DBFailure[T]]): Reference to the `DBFailure` class.
    """
    __match_args__ = ("result", "exception")

    DBSuccess: "Type[DBSuccess[T]]"
    DBFailure: "Type[DBFailure[T]]"

    def __init_subclass__(cls, **kwargs):
        """Registers `DBSuccess` and `DBFailure` subclasses for pattern matching convenience."""
        if cls.__name__ in DBResult.__annotations__:
            setattr(DBResult, cls.__name__, cls)

    @property
    @abstractmethod
    def result(self) -> T:
        """The successful result of the operation.

        Raises:
            DBStatusNoResultException: If called on `DBFailure`.
        """
        ...

    @property
    @abstractmethod
    def exception(self) -> Exception:
        """The exception from a failed operation.

        Raises:
            DBStatusNoResultException: If called on `DBSuccess`.
        """
        ...

    @abstractmethod
    def result_or[D](self, default: D) -> T | D:
        """Returns the operation result if successful, else a default.

        Args:
            default: Value to return if the operation failed.

        Returns:
            The result or the default.
        """
        ...

    @abstractmethod
    def exception_or[D](self, default: D) -> Exception | D:
        """Returns the exception if the operation failed, else a default.

        Args:
            default: Value to return if the operation was successful.

        Returns:
            The exception or the default.
        """
        ...

    @classmethod
    def build[**P](cls, callback: Callable[P, Awaitable[T]], *args: P.args, **kwargs: P.kwargs) -> "DBResultBuilder[T]":
        """Creates a `DBResultBuilder` to execute a callback and wrap its outcome.

        This factory method is the primary way `DBResultBuilder` instances are created
        internally within Ommi (e.g., by `Ommi.add`). It prepares an awaitable operation
        to be executed such that its result or exception is captured in a `DBResult` object.

        Args:
            callback: An asynchronous function (awaitable callable) to be executed.
            *args: Positional arguments to pass to the `callback`.
            **kwargs: Keyword arguments to pass to the `callback`.

        Returns:
            A `DBResultBuilder[T]` instance, ready to be awaited.
        """
        return DBResultBuilder(callback, *args, **kwargs)


class DBSuccess[T](DBResult[T]):
    """Represents a successful database operation, potentially with a result value.
    """
    __match_args__ = ("result",)

    def __init__(self, result: T):
        """
        Args:
            result: The result payload from the successful operation.
        """
        self._result = result

    @property
    def exception(self) -> Exception:
        """Accessing `exception` on `DBSuccess` raises `DBStatusNoResultException`."""
        raise DBStatusNoResultException("DBResult does not wrap an exception")

    @property
    def result(self) -> T:
        """The data payload of the successful operation."""
        return self._result

    def result_or[D](self, default: D) -> T | D:
        """Returns the successful operation result (default is ignored)."""
        return self._result

    def exception_or[D](self, default: D) -> D:
        """Returns the default value, as `DBSuccess` implies no exception."""
        return default


class DBFailure[T](DBResult[T]):
    """Represents a failed database operation, capturing the exception.
    """
    __match_args__ = ("exception",)

    def __init__(self, exception: Exception):
        """
        Args:
            exception: The exception that occurred.
        """
        self._exception = exception

    @property
    def exception(self) -> Exception:
        """The exception that caused the operation to fail."""
        return self._exception

    @property
    def result(self) -> T:
        """Accessing `result` on `DBFailure` raises `DBStatusNoResultException`."""
        raise DBStatusNoResultException(
            f"DBResult.{type(self).__name__} does not wrap a result, it only contains an exception"
        )

    def result_or[D](self, default: D) -> D:
        """Returns the default value, as `DBFailure` implies no data result."""
        return default

    def exception_or[D](self, default: D) -> Exception:
        """Returns the captured exception (default is ignored)."""
        return self._exception


class DBResultBuilder[T]:
    """An awaitable builder that executes a callback and wraps its outcome in a `DBResult`.

    This class is used to defer the execution of an awaitable function (`callback`)
    and ensure its result (or any exception during its execution) is properly
    encapsulated within either a `DBSuccess[T]` or `DBFailure[T]` object. The deferred
    execution can be triggered with the use of methods like `or_raise()`, `or_use()`,
    or simply by awaiting the `DBResultBuilder` instance itself.

    Instances are typically created via `DBResult.build()` and then awaited.

    Attributes:
        _callback (Callable): The awaitable function to be executed.
        _args: Positional arguments for the `_callback`.
        _kwargs: Keyword arguments for the `_callback`.
    """
    def __init__(self, callback: Callable, *args, **kwargs):
        """Initializes the DBResultBuilder.

        Args:
            callback: The awaitable function to execute.
            *args: Positional arguments to pass to the callback.
            **kwargs: Keyword arguments to pass to the callback.
        """
        self._callback = callback
        self._args = args
        self._kwargs = kwargs

    def __await__(self):
        """Makes the `DBResultBuilder` instance awaitable and executes the callback,
        wrapping the result.

        It attempts to execute `self.or_raise()` and wraps the outcome resolving to a
        `DBResult` type.
        """
        return self._get().__await__()

    async def or_raise(self) -> T:
        """Executes the callback and raises any exceptions directly.

        This method bypasses the `DBSuccess`/`DBFailure` wrapping and allows
        the caller to handle exceptions from the callback directly.

        Returns:
            The result of the callback if successful.

        Raises:
            Exception: Any exception raised by the underlying callback.
        """
        return await self._callback(*self._args, **self._kwargs)

    async def _get(self) -> DBResult[T]:
        """Internal method to execute the callback and wrap the result.

        This is called when the `DBResultBuilder` instance is awaited.
        It attempts to execute `self.or_raise()` and wraps the outcome.

        Returns:
            A `DBSuccess[T]` instance containing the result if the callback succeeded,
            or a `DBFailure[T]` instance containing the exception if it failed.
        """
        try:
            return DBResult.DBSuccess(await self.or_raise())
        except Exception as e:
            return DBResult.DBFailure(e)
