from abc import ABC, abstractmethod
from typing import Any, Iterable, TYPE_CHECKING


if TYPE_CHECKING:
    from ommi.query_ast import ASTGroupNode
    from ommi.models.collections import ModelCollection
    from ommi.shared_types import DBModel
    from tramp.async_batch_iterator import AsyncBatchIterator


class BaseDriverTransaction(ABC):
    # ---------------------------------------- #
    # Transaction Management                   #
    # ---------------------------------------- #
    @abstractmethod
    async def close(self):
        """Closes the transaction to further changes."""
        ...

    @abstractmethod
    async def commit(self):
        """Commits the transaction to the database."""
        ...

    @abstractmethod
    async def open(self):
        """Opens the transaction for changes."""
        ...

    @abstractmethod
    async def rollback(self):
        """Rolls back all changes to the database that have happened inside the transaction."""
        ...

    # ---------------------------------------- #
    # Query Execution                          #
    # ---------------------------------------- #
    @abstractmethod
    async def add(self, models: "Iterable[DBModel]") -> "Iterable[DBModel]":
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
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.rollback() if exc_type else self.commit()
        await self.close()
