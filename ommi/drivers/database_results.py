from functools import wraps
from typing import Generic, Type, TypeVar, NoReturn, Callable, Awaitable, ParamSpec

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")


class DatabaseResult(Generic[T]):
    Failure: "Type[DatabaseFailure[T]]"
    Success: "Type[DatabaseSuccess[T]]"

    @property
    def value(self) -> T | NoReturn:
        return

    @property
    def error(self) -> Exception | None:
        return

    def value_or(self, default: T) -> T:
        return

    def __bool__(self) -> bool:
        return False


class DatabaseSuccess(DatabaseResult[T]):
    __match_args__ = ("value",)

    def __init__(self, value: T):
        self._value = value

    @property
    def value(self):
        return self._value

    def value_or(self, default: T) -> T:
        return self._value

    def __bool__(self) -> bool:
        return True


class DatabaseFailure(DatabaseResult[T]):
    __match_args__ = ("error",)

    def __init__(self, error: Exception):
        self._error = error

    @property
    def value(self) -> NoReturn:
        raise RuntimeError("Cannot access value of a failed result") from self._error

    @property
    def error(self) -> Exception:
        return self._error

    def value_or(self, default: T) -> T:
        return default


DatabaseResult.Success = DatabaseSuccess
DatabaseResult.Failure = DatabaseFailure


class AsyncResultWrapper(Generic[T]):
    def __init__(self, awaitable):
        self._awaitable = awaitable

    def __await__(self):
        return self._await_and_wrap().__await__()

    async def raise_on_errors(self):
        match await self._await_and_wrap():
            case DatabaseResult.Failure(error):
                raise error

    @property
    async def value(self) -> T:
        return (await self._await_and_wrap()).value

    async def value_or(self, default: T) -> T:
        return (await self._await_and_wrap()).value_or(default)

    async def _await_and_wrap(self) -> DatabaseResult[T]:
        try:
            return DatabaseResult.Success(await self._awaitable)

        except Exception as error:
            return DatabaseResult.Failure(error)


def async_result(coroutine: Callable[P, Awaitable[R]]) -> Callable[P, AsyncResultWrapper[R]]:
    @wraps(coroutine)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncResultWrapper[R]:
        return AsyncResultWrapper(coroutine(*args, **kwargs))

    return wrapper
