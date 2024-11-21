from abc import ABC, abstractmethod
from typing import Any, Iterable, TYPE_CHECKING


if TYPE_CHECKING:
    from ommi.query_ast import ASTGroupNode
    from ommi.models import OmmiModel
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
    async def add(self, models: "Iterable[OmmiModel]") -> "Iterable[OmmiModel]":
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
    async def fetch(self, predicate: "ASTGroupNode") -> "AsyncBatchIterator[OmmiModel]":
        """Fetches all models from the database that match the given predicate and returns them using an
        AsyncBatchIterator. This allows for efficient fetching of large datasets."""
        ...

    @abstractmethod
    async def update(self, predicate: "ASTGroupNode", values: dict[str, Any]) -> "Iterable[OmmiModel]":
        """Updates all models in the database that match the given predicate with the given values and returns the
        updated models."""
        ...
