from typing import Generic, TypeVar, overload, Type, Awaitable, Any

from ommi.database.actions import OmmiAction, OmmiActionBuilder, OmmiUpdateAction
from ommi.database.transactions import OmmiTransaction
from ommi.drivers import DatabaseDriver
from ommi.models import OmmiModel
from ommi.models.collections import ModelCollection
from ommi.query_ast import ASTGroupNode
from ommi.utils.awaitable_results import AwaitableResult

TDriver = TypeVar("TDriver", bound=DatabaseDriver)
TModel = TypeVar("TModel", bound=OmmiModel)
TResult = TypeVar("TResult")
TTransaction = TypeVar("TTransaction")


class OmmiDatabase(Generic[TDriver]):
    def __init__(self, driver: TDriver):
        self.driver = driver

    def __aenter__(self):
        return self

    def __aexit__(self, exc_type, exc_val, exc_tb):
        return

    def add(self, *items: TModel) -> AwaitableResult[None]:
        return self.transaction().add(*items)

    @property
    def delete(self) -> OmmiActionBuilder[TModel, None]:
        return OmmiActionBuilder(OmmiAction[TModel, None], self._delete)

    def _delete(self, query: ASTGroupNode) -> AwaitableResult[None]:
        return self.transaction().delete(query)

    @property
    def fetch(self) -> OmmiActionBuilder[TModel, TModel]:
        return OmmiActionBuilder(OmmiAction[TModel, TModel], self._fetch)

    def _fetch(self, query: ASTGroupNode) -> AwaitableResult[TModel]:
        return self.transaction().fetch(query)

    @property
    def update(self) -> OmmiActionBuilder[TModel, None]:
        return OmmiActionBuilder(OmmiUpdateAction[TModel], self._update)

    def _update(self, query: ASTGroupNode, **kwargs) -> AwaitableResult[None]:
        return self.transaction().update(query, **kwargs)

    def transaction(self) -> OmmiTransaction[TResult]:
        return OmmiTransaction(self.driver.transaction())

    def sync_schema(self, model_collection: ModelCollection) -> AwaitableResult[None]:
        return self.transaction().sync_schema(model_collection)

    async def _await_with_transaction(self, transaction: OmmiTransaction, action: Awaitable[TResult]) -> TResult:
        async with transaction:
            return await action

    @classmethod
    @overload
    async def connect(cls, driver: TDriver) -> "OmmiDatabase[TDriver]":
        ...

    @classmethod
    @overload
    async def connect(cls, driver: Type[TDriver]) -> "OmmiDatabase[TDriver]":
        ...

    @classmethod
    async def connect(cls, driver: TDriver | Type[TDriver]) -> "OmmiDatabase[TDriver]":
        match driver:
            case DatabaseDriver() as driver_obj:
                return cls(driver_obj)

            case type() as driver_type if issubclass(driver, DatabaseDriver):
                return cls(await driver_type.from_config(cls.find_config(driver_type)))

            case _:
                raise TypeError(f"Expected a DatabaseDriver instance or subclass, got {driver!r}")

    @staticmethod
    async def find_config(driver_type: Type[TDriver]) -> Any:
        raise NotImplemented
