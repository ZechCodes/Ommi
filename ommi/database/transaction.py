"""
Transaction support for Ommi.

This module provides the OmmiTransaction class, which wraps a driver transaction
and provides the same interface as the Ommi class.
"""

from typing import Awaitable, TYPE_CHECKING

import ommi
from ommi.query_ast import when

if TYPE_CHECKING:
    from ommi.drivers import BaseDriverTransaction
    from ommi.models.collections import ModelCollection
    from ommi.shared_types import DBModel


class OmmiTransaction:
    """An async context manager for performing database operations within a transaction.

    This class provides the same interface as the Ommi class, but operates within
    a transaction context. The transaction is automatically committed when the context
    is exited without an exception, or rolled back if an exception occurs.

    > # ⚠️ Important Consideration
    > You **must** use the methods on the `transaction` object itself. Do not use the
    > methods on the `Ommi` instance within the transaction context. There's no guarantee
    > that the operations will be performed within the transaction context.

    Example:
        ```python
        async with db.transaction() as transaction:
            await transaction.add(model)
            # If an exception occurs here, the transaction will be rolled back
        ```
    """

    def __init__(self, transaction: "BaseDriverTransaction"):
        self._transaction = transaction

    @property
    def transaction(self) -> "BaseDriverTransaction":
        """Get the underlying driver transaction."""
        return self._transaction

    def add(
        self, *models: "DBModel"
    ) -> "Awaitable[ommi.database.results.DBResult[DBModel]]":
        """Add models to the database within the transaction. See [`Ommi.add`](/api/core/#ommi.database.Ommi.add) for more details.

        Args:
            *models: The models to add.

        Returns:
            Resolves to a `DBResult` wrapping the added models or any exceptions that occurred.
        """
        return ommi.database.results.DBResult.build(self.transaction.add, models)

    def find(
        self, *predicates: "ommi.query_ast.ASTGroupNode | DBModel | bool"
    ) -> "Awaitable[ommi.database.query_results.DBQueryResult[DBModel]]":
        """Find models in the database within the transaction. See [`Ommi.find`](/api/core/#ommi.database.Ommi.find) for more details.

        Args:
            *predicates: The predicates to filter by.

        Returns:
            Resolves to a `DBQueryResult` containing the found models or any exceptions that occurred.
        """
        return ommi.database.query_results.DBQueryResult.build(
            self.transaction, when(*predicates)
        )

    async def use_models(self, model_collection: "ModelCollection") -> None:
        """Apply the schema for the given model collection to the database within the transaction. See
        [`Ommi.use_models`](/api/core/#ommi.database.Ommi.use_models) for more details.

        Args:
            model_collection: The model collection to apply the schema for.
        """
        await self.transaction.delete_schema(model_collection)
        await self.transaction.apply_schema(model_collection)

    async def remove_models(self, model_collection: "ModelCollection") -> None:
        """Remove the schema for the given model collection from the database within the transaction. See
        [`Ommi.remove_models`](/api/core/#ommi.database.Ommi.remove_models) for more details.

        Args:
            model_collection: The model collection to remove the schema for.
        """
        await self.transaction.delete_schema(model_collection)

    async def commit(self) -> None:
        """Commit the operations that have happened within the transaction."""
        await self.transaction.commit()

    async def rollback(self) -> None:
        """Rollback the operations that have happened within the transaction."""
        await self.transaction.rollback()

    async def __aenter__(self):
        await self.transaction.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self.transaction.__aexit__(exc_type, exc_val, exc_tb)
