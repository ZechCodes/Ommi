"""Drivers are the interface between Ommi and the database. They are responsible for connecting to the database,
managing transactions, and executing queries. Each driver must implement the BaseDriver interface, which defines the
methods that Ommi uses to interact with the database.

Drivers should avoid over engineering and should allow exceptions to bubble up to the caller. Common exceptions should
be replaced with the Ommi driver exceptions in ommi.drivers.exceptions. This allows the caller to handle exceptions in a
way that makes sense for their application. OmmiDatabase catches exceptions raised by the driver and wraps them in
DatabaseFailure results, which are then returned to the caller."""
from abc import ABC, abstractmethod
from typing import Any, Iterable, TYPE_CHECKING

import ommi

if TYPE_CHECKING:
    from ommi.drivers import BaseDriverTransaction
    from ommi.models import OmmiModel
    from ommi.models.collections import ModelCollection
    from ommi.query_ast import ASTGroupNode
    from ommi.shared_types import DBModel
    from tramp.async_batch_iterator import AsyncBatchIterator


class BaseDriver(ABC):
    # ---------------------------------------- #
    # Connection Management                    #
    # ---------------------------------------- #
    @classmethod
    @abstractmethod
    def connect(cls, settings: dict[str, Any] | None = None) -> "BaseDriver":
        """Connects to the database."""
        ...

    @abstractmethod
    async def disconnect(self):
        """Disconnects from the database."""
        ...

    # ---------------------------------------- #
    # Transaction Management                   #
    # ---------------------------------------- #
    @abstractmethod
    def transaction(self) -> "BaseDriverTransaction":
        """Creates a transaction for the database."""
        ...

    # ---------------------------------------- #
    # Query Execution                          #
    # ---------------------------------------- #
    @abstractmethod
    async def add[DBModel:"DBModel"](self, models: Iterable[DBModel]) -> Iterable[DBModel]:
        """Adds a series of models to the database and returns the models with their primary keys set."""
        ...

    @abstractmethod
    async def count(self, predicate: "ASTGroupNode") -> int:
        """Counts the number of models in the database that match the given predicate."""
        ...

    @abstractmethod
    async def delete(self, predicate: "ASTGroupNode"):
        """Deletes all models in the database that match the given predicate."""
        ...

    @abstractmethod
    def fetch(self, predicate: "ASTGroupNode") -> "AsyncBatchIterator[DBModel]":
        """Fetches all models from the database that match the given predicate and returns them using an
        AsyncBatchIterator. This allows for efficient fetching of large datasets."""
        ...

    @abstractmethod
    async def update(self, predicate: "ASTGroupNode", values: dict[str, Any]):
        """Updates all models in the database that match the given predicate with the given values."""
        ...

    # ---------------------------------------- #
    # Schema Management                        #
    # ---------------------------------------- #
    @abstractmethod
    async def apply_schema(self, model_collection: "ModelCollection"):
        """Applies the schema for the given model collection to the database."""
        ...

    @abstractmethod
    async def delete_schema(self, model_collection: "ModelCollection"):
        """Deletes the schema for the given model collection from the database."""
        ...

    # ---------------------------------------- #
    # Context Management                       #
    # ---------------------------------------- #
    async def __aenter__(self):
        self.__active_driver_reset_token = ommi.driver_context.active_driver.set(self)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            ommi.driver_context.active_driver.reset(self.__active_driver_reset_token)
        except ValueError:
            pass

        await self.disconnect()

