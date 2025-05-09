from typing import Awaitable, Callable, Type

from ommi import BaseDriver, BaseDriverTransaction
from ommi.database_statuses import (
    DatabaseFailure,
    DatabaseResult,
    DatabaseStatus,
    DatabaseSuccess,
)
from ommi.models import OmmiModel
from ommi.query_ast import ASTGroupNode, when

type ActionCallable = Callable[
    [ASTGroupNode, BaseDriver | BaseDriverTransaction], Awaitable[None]
]


class Action[T]:
    def __init__(
        self,
        action: ActionCallable,
        predicate: ASTGroupNode,
        driver: BaseDriver,
        transaction: BaseDriverTransaction | None,
        success_factory: Callable[[T], DatabaseSuccess[T] | DatabaseResult[T]],
    ):
        self._action = action
        self._driver = driver
        self._predicate = predicate
        self._transaction = transaction
        self._success_factory = success_factory

    def __await__(self):
        return self.get().__await__()

    async def get(self) -> DatabaseStatus[T]:
        try:
            result = await self.on_error_raise()
        except Exception as e:
            return DatabaseFailure(e)
        else:
            return self._success_factory(result)

    async def on_error_raise(self) -> T:
        return await self._action(self._predicate, self._transaction or self._driver)

    async def on_error_rollback(self) -> DatabaseStatus[T]:
        self._transaction = self._transaction or self._driver.transaction()
        try:
            result = await self.on_error_raise()
        except Exception as e:
            await self._transaction.rollback()
            return DatabaseFailure(e)
        else:
            return self._success_factory(result)


class ActionBuilder[T]:
    def __init__(
        self,
        driver: BaseDriver,
        action: ActionCallable,
        transaction: BaseDriverTransaction | None = None,
        capture_result: bool = False,
    ):
        self._action = action
        self._driver = driver
        self._transaction = transaction
        self._success_factory = (
            DatabaseResult if capture_result else lambda _: DatabaseSuccess()
        )

    def __call__(self, predicate: Type[OmmiModel] | ASTGroupNode) -> Action[T]:
        return self.matching(predicate)

    def matching(self, predicate: Type[OmmiModel] | ASTGroupNode) -> Action[T]:
        return Action(
            self._action,
            when(predicate),
            self._driver,
            self._transaction,
            self._success_factory,
        )
