from abc import ABC, abstractmethod
from contextlib import AsyncExitStack
from typing import Any, AsyncContextManager, Awaitable, Generic, Type

import ommi.drivers.drivers as drivers
from ommi.drivers.driver_types import TConn, TModel
import ommi.drivers.add_actions as add_action
import ommi.drivers.find_actions as find_action
import ommi.drivers.schema_actions as schema_action
from ommi.models.collections import ModelCollection


class Transaction(Generic[TConn, TModel], ABC):
    def __init__(
        self,
        driver: "drivers.AbstractDatabaseDriver",
        contexts: list[AsyncContextManager] | None = None,
        **extra_args: Any,
    ):
        self.driver = driver
        self._exit_stack = AsyncExitStack()
        self._contexts = contexts or []
        self._extra_args = extra_args or {}
        self._rolled_back = False

    async def __aenter__(self):
        for context in self._contexts:
            await self._exit_stack.enter_async_context(context)

        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return await self._exit_stack.__aexit__(exc_type, exc_value, traceback)

    @abstractmethod
    async def _commit(self):
        ...

    @abstractmethod
    async def _rollback(self):
        ...

    async def commit(self):
        if self._rolled_back:
            return

        await self._commit()

    async def rollback(self):
        if self._rolled_back:
            return

        self._rolled_back = True
        await self._rollback()

    @property
    def add(self) -> "add_action.AddAction[TConn, TModel]":
        return lambda *a, **k: self.driver.add(*a, **self._extra_args | k)

    def find(self, *predicates: "drivers.Predicate") -> "find_action.FindAction[TConn, TModel]":
        return self.driver.find(*predicates, **self._extra_args)

    def schema(
        self, model_collection: ModelCollection[Type[TModel]] | None = None
    ) -> "schema_action.SchemaAction[TConn, TModel]":
        return self.driver.schema(model_collection, **self._extra_args)