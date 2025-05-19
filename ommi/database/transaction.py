"""Provides the `OmmiTransaction` class for managing database transactions.

This module defines `OmmiTransaction`, which acts as an asynchronous context manager
to group database operations into atomic units. It wraps a driver-specific
transaction object and mirrors the core API of the `Ommi` class (e.g., `add`, `find`),
ensuring that all operations performed on the `OmmiTransaction` instance occur
within the scope of the underlying database transaction.

Transactions are crucial for maintaining data integrity, especially when multiple
database modifications need to succeed or fail together. `OmmiTransaction` simplifies
this by automatically handling commit and rollback based on the successful completion
or failure of the `async with` block.

Key Features:

-   **Atomic Operations**: Ensures that a series of database changes are either all
    applied (committed) or all discarded (rolled back).
-   **Consistent API**: Provides methods like `add`, `find`, `use_models`, etc., similar
    to the main `Ommi` class, but scoped to the current transaction.
-   **Automatic Lifecycle Management**: Commits on successful exit from the `async with`
    block and rolls back if an unhandled exception occurs.
-   **Explicit Control**: Also offers `commit()` and `rollback()` methods for manual
    transaction control within the `async with` block if needed.

> # Important Usage Note
> When inside an `async with db.transaction() as t:` block, always call database
> operation methods (like `t.add(...)`, `t.find(...)`) on the transaction
> object (`t` in this example), **not** on the original `Ommi` instance (`db`).
> Using the original `Ommi` instance will likely perform operations outside the
> current transaction's scope.

Example:
    ```python
    from ommi import Ommi, ommi_model
    from ommi.drivers.sqlite import SQLiteDriver # Example driver

    @ommi_model
    class Account:
        id: int
        balance: float


    async def transfer_money(from_account_id: int, to_account_id: int, amount: float):
        async with Ommi(SQLiteDriver.connect()) as db:
            async with db.transaction() as t:
                from_account_res = await t.find(Account.id == from_account_id).one()
                to_account_res = await t.find(Account.id == to_account_id).one()

                match from_account_res, to_account_res:
                    case DBResult.DBSuccess(from_account), DBResult.DBSuccess(to_account):
                        # Both accounts found, proceed with transfer
                        if from_account.balance < amount:
                            print("Insufficient funds.")
                            await tx.rollback()
                            return

                        await t.find(Account.id == from_account_id).update(balance=from_account.balance - amount)
                        await t.find(Account.id == to_account_id).update(balance=to_account.balance + amount)

                        print(f"Transferred {amount} successfully.")
                        # Commit happens automatically on successful exit if not manually rolled back.
                    case _:
                        # One or both accounts not found, handle error
                        print("Failed to find one or both accounts.")
                        await t.rollback() # Or let exception propagate to auto-rollback
                        return

    ```
"""

from typing import Awaitable, TYPE_CHECKING

import ommi
from ommi.query_ast import when

if TYPE_CHECKING:
    from ommi.drivers import BaseDriverTransaction
    from ommi.models.collections import ModelCollection
    from ommi.shared_types import DBModel


class OmmiTransaction:
    """An asynchronous context manager for performing database operations within a transaction.

    This class wraps a driver-specific transaction (a `BaseDriverTransaction`)
    and provides a subset of the `Ommi` class's API (like `add`, `find`, etc.).
    All operations performed through an `OmmiTransaction` instance are executed
    within the context of the underlying database transaction.

    The transaction is automatically committed when the `async with` block is exited
    without an unhandled exception. If an exception occurs and propagates out of
    the block, the transaction is automatically rolled back.

    > **⚠️ Warning**
    >
    > Always use the methods on the `OmmiTransaction` instance itself
    > (e.g., `t.add(...)`) when inside an `async with t:` block. Calling methods
    > on the original `Ommi` instance from which the transaction was created will
    > likely result in operations being performed outside the transaction's scope.

    Example:
        ```python
        # Assuming `db` is an initialized Ommi instance
        async with db.transaction() as t:
            await t.add(MyModel(name="Example"))
            # Further operations like t.find(...), t.delete(...)
            # If this block completes without error, changes are committed.
            # If an error occurs, changes are rolled back.
        ```
    """

    def __init__(self, transaction: "BaseDriverTransaction"):
        """
        Args:
            transaction: The driver-specific `BaseDriverTransaction` object that
                         this OmmiTransaction will manage.
        """
        self._transaction = transaction

    @property
    def transaction(self) -> "BaseDriverTransaction":
        """Provides access to the underlying driver-specific transaction object.

        While most operations should be performed via the `OmmiTransaction`'s own
        methods (like `add`, `find`), this property allows access to the raw driver
        transaction if needed for driver-specific functionalities not exposed directly
        by `OmmiTransaction`.

        Returns:
            The `BaseDriverTransaction` instance being wrapped.
        """
        return self._transaction

    def add(
        self, *models: "DBModel"
    ) -> "Awaitable[ommi.database.results.DBResult[DBModel]]":
        """Adds one or more model instances to the database within the current transaction.

        This method delegates to the underlying driver transaction's `add` method.
        The behavior is analogous to `ommi.Ommi.add` but occurs within the transactional
        context.

        Args:
            *models: The `DBModel` instances to be added.

        Returns:
            An awaitable that resolves to a `ommi.database.results.DBResult`.
            This result object will contain the added models (potentially with updated,
            database-generated fields like primary keys) on success, or an exception
            on failure.
        """
        return ommi.database.results.DBResult.build(self.transaction.add, models)

    def find(
        self, *predicates: "ommi.query_ast.ASTGroupNode | DBModel | bool"
    ) -> "Awaitable[ommi.database.query_results.DBQueryResultBuilder[DBModel]]":
        """Initiates a query to find models in the database within the current transaction.

        This method delegates to the underlying driver transaction to build a query.
        It returns a `ommi.database.query_results.DBQueryResultBuilder`, allowing for
        fluent construction and execution of the query (e.g., `.all()`, `.one()`, `.count()`).
        The behavior is analogous to `ommi.Ommi.find` but occurs within the transactional
        context.

        Args:
            *predicates: Query conditions, typically involving model fields or `ASTGroupNode`
                         instances created with `ommi.query_ast.when()`.

        Returns:
            An awaitable that resolves to a `DBQueryResultBuilder` for executing the query
            within the transaction.
        """
        return ommi.database.query_results.DBQueryResult.build(
            self.transaction, when(*predicates)
        )

    async def use_models(self, model_collection: "ModelCollection") -> None:
        """Applies the schema for a model collection within the current transaction.

        This involves deleting any existing schema for the collection and then applying
        the new one, all within the transaction's scope. If the transaction is later
        rolled back, these schema changes will also be reverted (if the database supports
        transactional DDL).

        Args:
            model_collection: The `ModelCollection` whose schema needs to be applied.
        """
        await self.transaction.delete_schema(model_collection)
        await self.transaction.apply_schema(model_collection)

    async def remove_models(self, model_collection: "ModelCollection") -> None:
        """Removes the schema for a model collection from the database within the transaction.

        This operation is performed within the transaction's scope. If the transaction
        is rolled back, the schema removal may also be reverted (database-dependent).

        Args:
            model_collection: The `ModelCollection` whose schema is to be removed.
        """
        await self.transaction.delete_schema(model_collection)

    async def commit(self) -> None:
        """Explicitly commits the current transaction.

        Once committed, all changes made within the transaction become permanent.
        It is often not necessary to call this directly, as the transaction will
        auto-commit upon successful exit from the `async with` block.
        However, it can be used for finer-grained control within the block.
        """
        await self.transaction.commit()

    async def rollback(self) -> None:
        """Explicitly rolls back the current transaction.

        This discards all changes made within the transaction since it began or since
        the last commit. If an exception occurs within the `async with` block, the
        transaction will typically auto-rollback, making direct calls to this method
        necessary only in specific control-flow scenarios.
        """
        await self.transaction.rollback()

    async def __aenter__(self):
        """Enters the asynchronous context, starting the underlying driver transaction.

        This method is called when entering an `async with` block. It delegates
        to the wrapped driver transaction, which typically starts a new transaction.

        Returns:
            The `OmmiTransaction` instance itself, allowing it to be used as the
            target of the `as` clause in the `async with` statement.
        """
        await self.transaction.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exits the asynchronous context, committing or rolling back the transaction.

        This method is called when exiting the `async with` block. It delegates to
        the wrapped driver transaction.
        Typically, the driver transaction will:

        - Commit if `exc_type` is `None` (no exception occurred).
        - Roll back if `exc_type` is not `None` (an exception occurred).
        """
        return await self.transaction.__aexit__(exc_type, exc_val, exc_tb)
