"""Provides classes for building and handling the results of database queries.

This module defines a structured way to represent the outcomes of database query
operations, primarily through the `DBQueryResult` family of classes and the
`DBQueryResultBuilder`. It aims to provide a fluent and robust API for fetching,
counting, updating, or deleting records based on query predicates.

Key Components:

-   `DBQueryResult[T]`: An abstract base class representing the result of a query.
    It has two concrete subclasses:
    -   `DBQuerySuccess[T]`: Indicates a successful query execution, holding the
        result (e.g., a model instance, an iterator of models, or a count).
    -   `DBQueryFailure[T]`: Indicates a failed query execution, holding the
        exception that occurred.
-   `DBQueryResultBuilder[T]`: A builder class that is typically returned by
    `Ommi.find()`. It allows for the construction and deferred execution of
    queries. It provides methods like `all()`, `one()`, `count()`, `delete()`, and
    `update()`, each of which, when awaited, executes the query and returns a
    `DBQueryResult` (or `DBResult` for non-data-returning operations like delete/update).
-   `WrapInResult[T, **P]`: A utility decorator/class used internally by
    `DBQueryResultBuilder` to wrap the results of its awaitable methods (like `all`, `one`)
    into `DBQuerySuccess` or `DBQueryFailure` objects.
-   `DBEmptyQueryException`: An exception that can be used to indicate issues with
    empty or invalid query parameters, though its direct usage in this module is minimal.

Workflow:
1.  A query is initiated (e.g., `db.find(User.name == "Alice")`), which returns
    a `DBQueryResultBuilder` instance.
2.  A method on the builder is called to specify how to execute the query
    (e.g., `builder.one()`, `builder.all()`). This call itself might return an
    awaitable wrapper (like an instance of `WrapInResult`).
3.  This awaitable is then `await`ed.
4.  The `await` triggers the actual database operation through the driver.
5.  The result or exception from the driver is wrapped in a `DBQuerySuccess` or
    `DBQueryFailure` object, which is the final result of the awaited call.

Example: Getting a Single User and Handling Errors
    ```python
    # Assuming `db` is an Ommi instance and `User` is an @ommi_model
    query_builder = db.find(User.age > 18)

    # Get one user
    match await query_builder.one():
        case DBQueryResult.DBQuerySuccess(user):
            print(f"Found user: {user.name}")
        case DBQueryResult.DBQueryFailure(DBStatusNoResultException()):
            print("No user found matching criteria.")
        case DBQueryResult.DBQueryFailure(exception):
            print(f"Error fetching user: {exception}")
    ```

Example: Fetching All Users and Handling Errors
    ```python
    # Get all users
    match await query_builder.all():
        case DBQueryResult.DBQuerySuccess(all_users_iterator):
            async for user in all_users_status.result:
                print(f"User from iterator: {user.name}")
        case DBQueryResult.DBQueryFailure(exception):
            print(f"Error fetching all users: {exception}")
        case value:
            raise RuntimeError(f"Impossible state, received {value!r}")  # Best practice to include for exhaustiveness
    ```
"""
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, overload, Self, Type

from tramp.async_batch_iterator import AsyncBatchIterator

import ommi
from ommi.database.results import DBResult, DBStatusNoResultException
from contextlib import suppress


class DBEmptyQueryException(Exception):
    """Exception raised when a query operation returns no results and an empty result is not possible (e.g. `one()`).
    """
    pass


class DBQueryResult[T](ABC):
    """Abstract base class for representing the outcome of a database query.

    This class, along with its concrete subclasses `DBQuerySuccess` and `DBQueryFailure`,
    provides a structured way to handle the results of data retrieval operations.
    It supports Python's `match/case` statement for pattern matching on query outcomes.

    The `__match_args__` are defined to allow matching on `result` (for success)
    or `exception` (for failure).

    Class Attributes:
        DBQuerySuccess (Type[DBQuerySuccess[T]]): A reference to the `DBQuerySuccess` class.
            Automatically populated by `__init_subclass__`.
        DBQueryFailure (Type[DBQueryFailure[T]]): A reference to the `DBQueryFailure` class.
            Automatically populated by `__init_subclass__`.
    """
    __match_args__ = ("result", "exception")

    DBQuerySuccess: "Type[DBQuerySuccess[T]]"
    DBQueryFailure: "Type[DBQueryFailure[T]]"

    def __init_subclass__(cls, **kwargs):
        """Registers concrete subclasses `DBQuerySuccess` and `DBQueryFailure` as class attributes.

        This allows for convenient access and eliminates the need to import all three classes. You
        can access them as `DBQueryResult.DBQuerySuccess` which enables pattern matching like:
        ```python
        from ommi import DBQueryResult
        ...
        match await db.find(User.id == 1).one():
            case DBQueryResult.DBQuerySuccess(user):
                print(user)
            case DBQueryResult.DBQueryFailure(exc):
                print(f"Error: {exc}")
        ```
        """
        super().__init_subclass__(**kwargs)
        if cls.__name__ in DBQueryResult.__annotations__:
            setattr(DBQueryResult, cls.__name__, cls)

    @property
    @abstractmethod
    def result(self) -> T:
        """The successful result of the query.

        Raises:
            DBStatusNoResultException: If accessed on `DBQueryFailure`, as there is no result.
        """
        ...

    @property
    @abstractmethod
    def exception(self) -> Exception:
        """The exception that occurred during a failed query.

        Raises:
            DBStatusNoResultException: If called on `DBQuerySuccess`, as there is no exception.
        """
        ...

    @abstractmethod
    def result_or[D](self, default: D) -> T | D:
        """Returns the query result if successful, otherwise returns the provided default.

        Args:
            default: The value to return if the query failed or yielded no specific result value.

        Returns:
            The query result or the default value.
        """
        ...

    @abstractmethod
    def exception_or[D](self, default: D) -> Exception | D:
        """Returns the exception if the query failed, otherwise returns the provided default.

        Args:
            default: The value to return if the query was successful (i.e., no exception).

        Returns:
            The exception object or the default value.
        """
        ...

    @classmethod
    def build(
        cls, driver: "ommi.drivers.BaseDriver", predicate: "ommi.query_ast.ASTGroupNode"
    ) -> "DBQueryResultBuilder[T]":
        """Creates a `DBQueryResultBuilder` for the given driver and predicate.

        This is the typical entry point for constructing a query that will eventually
        yield a `DBQueryResult`. It's used internally by `Ommi.find()` and `OmmiTransaction.find()`.

        Args:
            driver: The database driver instance to be used for executing the query.
            predicate: An `ASTGroupNode` representing the query conditions.

        Returns:
            A `DBQueryResultBuilder` instance, ready to have an execution method
            (e.g., `.all()`, `.one()`) called on it.
        """
        return DBQueryResultBuilder(driver, predicate)


class DBQuerySuccess[T](DBQueryResult[T]):
    """Represents a successfully executed database query that yielded a result.

    The actual result (e.g., a model instance, an iterator of models, a count)
    is accessible via the `result` property.
    """
    __match_args__ = ("result",)

    def __init__(self, result: T):
        """
        Args:
            result: The result payload from the successful database query.
        """
        self._result = result

    @property
    def result(self) -> T:
        """The data payload of the successful query."""
        return self._result

    @property
    def exception(self) -> Exception:
        """Accessing `exception` on `DBQuerySuccess` raises `DBStatusNoResultException`.

        Successful queries do not have an exception.
        """
        raise DBStatusNoResultException("DBQueryResult does not wrap an exception")

    def result_or[D](self, default: D) -> T:
        """Returns the successful query result.

        The `default` argument is ignored as a result is always present.
        """
        return self._result

    def exception_or[D](self, default: D) -> D:
        """Returns the default value as there is no exception."""
        return default


class DBQueryFailure[T](DBQueryResult[T]):
    """Represents a database query that failed during execution.

    The exception that caused the failure is accessible via the `exception` property.
    """
    __match_args__ = ("exception",)

    def __init__(self, exception: Exception):
        """
        Args:
            exception: The exception that occurred.
        """
        self._exception = exception

    @property
    def result(self) -> T:
        """Accessing `result` on `DBQueryFailure` raises `DBStatusNoResultException`.

        Failed queries do not produce a data result.
        """
        raise DBStatusNoResultException("DBQueryResult does not wrap a result")

    @property
    def exception(self) -> Exception:
        """The exception that caused the query to fail."""
        return self._exception

    def result_or[D](self, default: D) -> D:
        """Returns the default value as there is no result."""
        return default

    def exception_or[D](self, default: D) -> Exception:
        """Returns the captured exception.

        The `default` argument is ignored as an exception is always present.
        """
        return self._exception



class WrapInResult[T, **P]:
    """A descriptor and awaitable wrapper for methods that should return a `DBQueryResult`.

    This class is used as a decorator for methods within `DBQueryResultBuilder` (like
    `all`, `one`, `count`). When such a decorated method is called, it returns an
    instance of `WrapInResult`. This instance is awaitable.

    Upon awaiting, it executes the original decorated method, catches any exceptions,
    and wraps the outcome (either the successful result or the caught exception) into
    a `DBQuerySuccess` or `DBQueryFailure` object.

    It also allows the decorated method to be callable to pass arguments before awaiting.
    """
    def __init__(self, func: Callable[P, T]):
        """
        Args:
            func: The async function whose result needs to be wrapped in a `DBQueryResult`.
        """
        self._func = func
        self._args = ()
        self._kwargs = {}

    def __await__(self):
        """Executes the wrapped function and resolves to a `DBQueryResult`.

        It calls the original function (`self._func`) with the captured arguments,
        handles exceptions, and returns the appropriate `DBQuerySuccess` or
        `DBQueryFailure`.
        """
        return self.__get().__await__()

    def __call__(self, *args, **kwargs) -> Self:
        """Captures arguments for the wrapped function call.

        This allows the decorated method to be called with arguments before being awaited.
        Example: `await builder.update(name="new_name")` first calls `update()` which returns
        `WrapInResult`, then `__call__` on `WrapInResult` captures `name="new_name"`,
        then `__await__` executes it.

        Args:
            *args: Positional arguments for the original function.
            **kwargs: Keyword arguments for the original function.

        Returns:
            The `WrapInResult` instance itself, to allow awaiting after argument capture.
        """
        self._args = args
        self._kwargs = kwargs
        return self

    def __get__(self, instance, owner):
        """Descriptor protocol method to ensure correct binding of the wrapped function.

        If the wrapped function is a method of a class, this ensures that `self` (or `cls`)
        is correctly passed when the function is eventually called. It re-wraps the newly
        bound method in a new `WrapInResult` instance and returns it.

        Returns:
            A new `WrapInResult` instance with the newly bound method.
        """
        return type(self)(self._func.__get__(instance, owner))

    async def __get(self) -> DBQueryResult[T]:
        """Internal method that executes the wrapped function and returns a `DBQueryResult`.

        This is called when the `WrapInResult` instance is awaited.
        It calls the original function (`self._func`) with the captured arguments,
        handles exceptions, and returns the appropriate `DBQuerySuccess` or
        `DBQueryFailure`.
        """
        try:
            result = await self.or_raise()
        except Exception as e:
            return DBQueryFailure(e)
        else:
            return DBQuerySuccess(result)

    async def or_use[D](self, default: D) -> T | D:
        """Executes the wrapped function, returning its result or a default on failure.

        If the wrapped function executes successfully, its result is returned.
        If any exception occurs during its execution, the `default` value is returned.

        Args:
            default: The value to return in case of any exception.

        Returns:
            The result of the wrapped function or the default value.
        """
        with suppress(Exception):
            return await self.or_raise()

        return default

    async def or_raise(self):
        """Executes the wrapped function and raises any exceptions that occur.

        This provides a way to bypass the `DBQueryResult` wrapping if the caller
        prefers to handle exceptions directly.

        Returns:
            The result of the wrapped function if successful.

        Raises:
            Exception: Any exception raised by the wrapped function.
        """
        return await self._func(*self._args, **self._kwargs)


class DBQueryResultBuilder[T]:
    """Builds and executes database queries, returning results wrapped in `DBQueryResult`.

    Instances of this class are typically obtained by calling `ommi.Ommi.find()` or
    `ommi.OmmiTransaction.find()`. The builder holds a reference to the database
    driver and the query predicate.

    It provides several methods to execute the query:

    -   `all()`: To fetch all matching records as an `AsyncBatchIterator`.
    -   `one()`: To fetch a single matching record.
    -   `count()`: To get the number of matching records.
    -   `delete()`: To delete matching records.
    -   `update()`: To update fields of matching records.

    Each of these methods, when called and then awaited, performs the database
    operation and returns a `DBQueryResult` (or `DBResult` for delete/update).
    The builder itself can be directly awaited, which has the same effect as awaiting `all()`.
    """
    def __init__(self, driver: "ommi.drivers.BaseDriver", predicate: "ommi.query_ast.ASTGroupNode"):
        """Initializes the DBQueryResultBuilder.

        Args:
            driver: The database driver to use for executing the query.
            predicate: The `ASTGroupNode` representing the query conditions.
        """
        self._driver = driver
        self._predicate = predicate
        self._result: DBQueryResult[T] | None = None

    def __await__(self):
        """Allows the builder to be directly awaited, has the same effect as `all()`.

        Example:
            ```python
            async for user in await db.find(User.is_active == True).or_raise():
                print(user.name)
            ```
            This is equivalent to `await db.find(User.is_active == True).all.or_raise()`.
        """
        return self.all().__await__()

    def or_use[D](self, default: D) -> Awaitable[AsyncBatchIterator[T] | D]:
        """Executes the query (defaulting to `all()`), returning results or a default on failure.

        This is a convenience method that calls `or_use()` on the result of `self.all()`.

        Args:
            default: The value to return if `all()` fails.

        Returns:
            An awaitable that yields the query results as an `AsyncBatchIterator`.
            or the default value.
        """
        return self.all().or_use(default)

    def or_raise(self) -> Awaitable[AsyncBatchIterator[T]]:
        """Executes the query (defaulting to `all()`) and raises exceptions directly.

        This is a convenience method that calls `or_raise()` on the result of `self.all()`.

        Returns:
            An awaitable that yields the query results as an `AsyncBatchIterator`.

        Raises:
            Exception: Any exception raised during query execution.
        """
        return self.all().or_raise()

    @WrapInResult
    async def all(self) -> AsyncBatchIterator[T]:
        """Executes the query to fetch all matching records.

        Returns:
            An awaitable that resolves to a `DBQueryResult`. If successful,
            `DBQuerySuccess.result` will contain an `AsyncBatchIterator[T]` yielding
            the matching model instances.
        """
        return self._driver.fetch(self._predicate)

    @WrapInResult
    async def one(self) -> T:
        """Executes the query to fetch a single matching record.

        The query is automatically limited to 1 result. If no records match, a
        `DBStatusNoResultException` is raised.

        Returns:
            The first model instance matching the query.
        """
        result_iterator = self._driver.fetch(self._predicate.limit(1))
        try:
            return await result_iterator.one()
        except ValueError as e:
            raise DBStatusNoResultException("Query returned no results") from e

    @WrapInResult
    async def count(self) -> int:
        """Executes the query to count the number of matching records.

        Returns:
            The integer count of records matching the query.
        """
        return await self._driver.count(self._predicate)

    @WrapInResult
    async def delete(self) -> None:
        """Executes a delete operation for all records matching the predicate.
        """
        await self._driver.delete(self._predicate)

    @overload
    def update(self, values: dict[str, Any]) -> Awaitable[None]:
        ...

    @overload
    def update(self, **values: Any) -> Awaitable[None]:
        ...

    @WrapInResult
    async def update(self, values: dict[str, Any] | None = None, **kwargs: Any) -> None:
        """Executes an update operation for all records matching the predicate.

        Updates the specified fields with new values.
        You can pass values either as a dictionary or as keyword arguments. If you pass both,
        the keyword arguments will overwrite the dictionary values for matching keys.

        Args:
            values: A dictionary mapping field names to their new values.
            **kwargs: Field names and their new values as keyword arguments.

        Raises:
            ValueError: If no field values are provided for the update.
        """
        if values is None:
            values = {}

        values |= kwargs

        if not values:
            raise ValueError("Update requires at least one field to update")

        await self._driver.update(self._predicate, values)
