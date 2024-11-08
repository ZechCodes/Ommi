from contextlib import suppress
from functools import wraps
from typing import Callable, Generic, ParamSpec, TypeVar, Awaitable
from tramp.results import ResultBuilder, Result

R = TypeVar("R")
P = ParamSpec("P")
T = TypeVar("T")
TDefault = TypeVar("TDefault")


class AwaitableResult(Generic[T]):
    def __init__(self, awaitable: Awaitable[T]):
        self._awaitable = awaitable

    def __await__(self):
        return self._await().__await__()

    async def value_or(self, default: TDefault) -> T | TDefault:
        with suppress(Exception):
            return await self._awaitable

        return default

    async def raise_on_errors(self):
        return await self._awaitable

    async def _await(self) -> Result[T]:
        with ResultBuilder() as builder:
            builder.set(await self._awaitable)

        return builder.result


def awaitable_result(func: Callable[P, Awaitable[R]]) -> Callable[P, AwaitableResult[R]]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> AwaitableResult[R]:
        return AwaitableResult(func(*args, **kwargs))

    return wrapper
