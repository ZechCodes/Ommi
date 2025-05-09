from abc import ABC, abstractmethod
from functools import wraps
from typing import NoReturn, Awaitable, Callable, overload


class DBStatusException(Exception):
    """Base database status exception type."""


class DBStatusNoValueException(DBStatusException):
    """Exception raised when attempting to access a value on a DatabaseSuccess or DatabaseFailure object."""


class DatabaseStatus[T](ABC):
    """Wraps a database result in a status object."""
    __match_args__ = ("value",)

    @abstractmethod
    @property
    def value(self) -> T:
        """Returns the value """

    @abstractmethod
    def value_or[D](self, default: T) -> T | D:
        ...

    @abstractmethod
    def exception_or[D](self, default: D) -> Exception | D:
        ...


class DatabaseSuccess[T](DatabaseStatus):
    """Indicates a successful database operation with no result value."""
    @property
    def value(self) -> NoReturn:
        raise DBStatusNoValueException("DatabaseSuccess does not wrap a value")

    def value_or[D](self, default: D) -> D:
        return default

    def exception_or[D](self, default: D) -> D:
        return default


class DatabaseFailure[T](DatabaseStatus):
    def __init__(self, exception: Exception):
        self._exception = exception

    @property
    def value(self) -> NoReturn:
        raise DBStatusNoValueException("DatabaseFailure does not wrap a value")

    def value_or[D](self, default: D) -> D:
        return default

    def exception_or[E](self, default: E) -> Exception:
        return self._exception


class DatabaseResult[T](DatabaseStatus):
    def __init__(self, value: T):
        self._value = value

    @property
    def value(self) -> T:
        return self._value

    def value_or[D](self, default: D) -> T:
        return self._value

    def exception_or[D](self, default: D) -> D:
        return default


type AsyncCallable[**P, R] = Callable[P, Awaitable[R]]
type DecoratorCallable[**P, R] = Callable[[AsyncCallable[P, R]], AsyncCallable[P, DatabaseStatus[R]]]

@overload
def database_status[**P, R](func: AsyncCallable[P, R]) -> AsyncCallable[P, DatabaseStatus[R]]:
    ...

@overload
def database_status[**P, R](*, expect_result: bool) -> DecoratorCallable[P, R]:
    ...

def database_status[**P, R](
    func: AsyncCallable[P, R] | None = None, *, expect_result: bool = False
) -> DecoratorCallable[P, R] | AsyncCallable[P, DatabaseStatus[R]]:
    def decorator(func_: AsyncCallable[P, R]) -> AsyncCallable[P, DatabaseStatus[R]]:
        @wraps(func_)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> DatabaseStatus[R]:
            try:
                result = await func_(*args, **kwargs)
            except Exception as e:
                return DatabaseFailure(e)
            else:
                if expect_result:
                    return DatabaseResult(result)
                else:
                    return DatabaseSuccess()

        return wrapper

    return decorator(func) if func else decorator
