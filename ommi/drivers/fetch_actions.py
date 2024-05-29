from typing import Generic, Iterable, Type, Awaitable, Sequence, TypeAlias
from abc import ABC, abstractmethod
from contextlib import suppress

from ommi.drivers.driver_types import TConn, TModel

from ommi.drivers.database_results import DatabaseResult, AsyncResultWrapper
import ommi.query_ast

Predicate: TypeAlias = "ommi.query_ast.ASTGroupNode | Type[TModel] | bool"


class FetchAction(Generic[TConn, TModel], ABC):
    def __init__(self, connection: TConn, predicates: Sequence[Predicate]):
        self._connection = connection
        self._predicates = predicates

    def __call__(self) -> AsyncResultWrapper[list[TModel]]:
        return self.fetch()

    @abstractmethod
    def fetch(self) -> AsyncResultWrapper[list[TModel]]:
        ...

    @abstractmethod
    async def first(self) -> TModel:
        ...

    @abstractmethod
    async def last(self) -> TModel:
        ...

    async def all(self) -> list[TModel]:
        match await self.fetch():
            case DatabaseResult.Success(result):
                return result

            case DatabaseResult.Failure(error):
                raise error

    async def first_or(self, default: TModel) -> TModel:
        with suppress(Exception):
            return await self.first()

        return default

    async def last_or(self, default: TModel) -> TModel:
        with suppress(Exception):
            return await self.last()

        return default
