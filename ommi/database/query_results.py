from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Self, Type

from tramp.async_batch_iterator import AsyncBatchIterator

import ommi
from ommi.database import DBResult
from ommi.database.results import DBStatusNoResultException
from contextlib import suppress


class DBEmptyQueryException(Exception):
    pass


class DBQueryResult[T](ABC):
    __match_args__ = ("result", "exception")

    DBQuerySuccess: "Type[DBQuerySuccess[T]]"
    DBQueryFailure: "Type[DBQueryFailure[T]]"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.__name__ in DBQueryResult.__annotations__:
            setattr(DBQueryResult, cls.__name__, cls)

    @property
    @abstractmethod
    def result(self) -> T:
        ...

    @property
    @abstractmethod
    def exception(self) -> Exception:
        ...

    @abstractmethod
    def result_or[D](self, default: D) -> T | D:
        ...

    @abstractmethod
    def exception_or[D](self, default: D) -> Exception | D:
        ...

    @classmethod
    def build(
        cls, driver: "ommi.drivers.BaseDriver", predicate: "ommi.query_ast.ASTGroupNode"
    ) -> "DBQueryResultBuilder[T]":
        return DBQueryResultBuilder(driver, predicate)


class DBQuerySuccess[T](DBQueryResult[T]):
    __match_args__ = ("result",)

    def __init__(self, result: T):
        self._result = result

    @property
    def result(self) -> T:
        return self._result

    @property
    def exception(self) -> Exception:
        raise DBStatusNoResultException("DBQueryResult does not wrap an exception")

    def result_or[D](self, default: D) -> T:
        return self._result

    def exception_or[D](self, default: D) -> D:
        return default


class DBQueryFailure[T](DBQueryResult[T]):
    __match_args__ = ("exception",)

    def __init__(self, exception: Exception):
        self._exception = exception

    @property
    def result(self) -> T:
        raise DBStatusNoResultException("DBQueryResult does not wrap a result")

    @property
    def exception(self) -> Exception:
        return self._exception

    def result_or[D](self, default: D) -> D:
        return default

    def exception_or[D](self, default: D) -> Exception:
        return self._exception



class WrapInResult[T, **P]:
    def __init__(self, func: Callable[P, T]):
        self._func = func
        self._args = ()
        self._kwargs = {}

    def __await__(self):
        return self.__get().__await__()

    def __call__(self, *args, **kwargs) -> Self:
        self._args = args
        self._kwargs = kwargs
        return self

    def __get__(self, instance, owner):
        return type(self)(self._func.__get__(instance, owner))

    async def __get(self) -> DBQueryResult[T]:
        try:
            result = await self.or_raise()
        except Exception as e:
            return DBQueryFailure(e)
        else:
            return DBQuerySuccess(result)

    async def or_use[D](self, default: D) -> T | D:
        with suppress(Exception):
            return await self.or_raise()

        return default

    async def or_raise(self):
        return await self._func(*self._args, **self._kwargs)


class DBQueryResultBuilder[T]:
    def __init__(self, driver: "ommi.drivers.BaseDriver", predicate: "ommi.query_ast.ASTGroupNode"):
        self._driver = driver
        self._predicate = predicate
        self._result: DBQueryResult[T] | None = None

    def __await__(self):
        return self.all().__await__()

    def or_use[D](self, default: D) -> Awaitable[T | D]:
        return self.all().or_use(default)

    def or_raise(self) -> Awaitable[T]:
        return self.all().or_raise()

    @WrapInResult
    async def all(self) -> AsyncBatchIterator[T]:
        return self._driver.fetch(self._predicate)

    @WrapInResult
    async def one(self) -> T:
        result_iterator = self._driver.fetch(self._predicate.limit(1))
        try:
            return await result_iterator.one()
        except ValueError as e:
            raise DBStatusNoResultException("Query returned no results") from e

    @WrapInResult
    async def count(self) -> int:
        return await self._driver.count(self._predicate)

    @WrapInResult
    async def delete(self) -> None:
        await self._driver.delete(self._predicate)
