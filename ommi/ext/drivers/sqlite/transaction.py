"""Provides SQLite-specific implementations for database transactions.

This module contains classes that adapt Ommi's transaction management to the
specifics of SQLite, including a base class for standard transaction handling and
a specialized class for manual transaction control (BEGIN, COMMIT, ROLLBACK).
"""
import sqlite3
from typing import Any, Iterable, TYPE_CHECKING

from tramp.async_batch_iterator import AsyncBatchIterator

from ommi.drivers import BaseDriverTransaction

import ommi.ext.drivers.sqlite.add_query as add_query
import ommi.ext.drivers.sqlite.delete_query as delete_query
import ommi.ext.drivers.sqlite.fetch_query as fetch_query
import ommi.ext.drivers.sqlite.schema_management as schema_management
import ommi.ext.drivers.sqlite.update_query as update_query

if TYPE_CHECKING:
    from ommi.ext.drivers.sqlite.shared_types import Cursor
    from ommi.models.collections import ModelCollection
    from ommi.query_ast import ASTGroupNode
    from ommi.shared_types import DBModel
    from tramp.async_batch_iterator import AsyncBatchIterator


class SQLiteTransaction(BaseDriverTransaction):
    """Handles standard SQLite transactions.

    This class implements the `BaseDriverTransaction` interface for SQLite, providing
    the fundamental operations required to manage transactions, such as committing,
    rolling back, and executing database operations like adding, fetching, or
    updating records within the scope of a transaction.

    Most operations are delegated to specific query modules (e.g., `add_query`,
    `fetch_query`) designed for SQLite.

    Attributes:
        cursor: The SQLite cursor object used to execute database commands.
    """
    def __init__(self, cursor: "Cursor"):
        """Args:
            cursor: The SQLite cursor to be used for all operations within this
                    transaction.
        """
        self.cursor = cursor

    async def close(self):
        """Closes the database cursor.

        This method should be called when the transaction is finished to release
        the cursor resource.
        """
        self.cursor.close()

    async def commit(self):
        """Commits the current transaction to the database.

        This makes all changes performed within the transaction permanent.
        """
        self.cursor.connection.commit()

    async def open(self):
        """A no-op method for this transaction type.

        In this basic SQLite transaction implementation, the transaction typically
        starts implicitly with the first database operation or is managed by the
        connection's autocommit behavior. Explicit `open` is not required.
        """
        return

    async def rollback(self):
        """Rolls back the current transaction.

        This discards all changes made within the transaction since the last commit.
        """
        self.cursor.connection.rollback()

    async def add(self, models: "Iterable[DBModel]") -> "Iterable[DBModel]":
        """Adds a collection of models to the database within the transaction.

        Delegates to `ommi.ext.drivers.sqlite.add_query.add_models`.

        Args:
            models: An iterable of `DBModel` instances to be added.

        Returns:
            An iterable of the added `DBModel` instances, potentially updated with
            database-generated values (e.g., primary keys).
        """
        return await add_query.add_models(self.cursor, models)

    async def count(self, predicate: "ASTGroupNode") -> int:
        """Counts models matching the given predicate within the transaction.

        Delegates to `ommi.ext.drivers.sqlite.fetch_query.count_models`.

        Args:
            predicate: An `ASTGroupNode` representing the query conditions.

        Returns:
            The number of models that match the predicate.
        """
        return await fetch_query.count_models(self.cursor, predicate)

    async def delete(self, predicate: "ASTGroupNode"):
        """Deletes models matching the given predicate within the transaction.

        Delegates to `ommi.ext.drivers.sqlite.delete_query.delete_models`.

        Args:
            predicate: An `ASTGroupNode` representing the query conditions for deletion.
        """
        await delete_query.delete_models(self.cursor, predicate)

    def fetch(self, predicate: "ASTGroupNode") -> "AsyncBatchIterator[DBModel]":
        """Fetches models matching the given predicate within the transaction.

        Delegates to `ommi.ext.drivers.sqlite.fetch_query.fetch_models`.

        Args:
            predicate: An `ASTGroupNode` representing the query conditions.

        Returns:
            An `AsyncBatchIterator` that yields `DBModel` instances matching
            the predicate.
        """
        return fetch_query.fetch_models(self.cursor, predicate)

    async def update(self, predicate: "ASTGroupNode", values: dict[str, Any]):
        """Updates models matching the given predicate with new values within the transaction.

        Delegates to `ommi.ext.drivers.sqlite.update_query.update_models`.

        Args:
            predicate: An `ASTGroupNode` representing the query conditions for the update.
            values: A dictionary of field names and their new values.
        """
        await update_query.update_models(self.cursor, predicate, values)

    async def apply_schema(self, model_collection: "ModelCollection"):
        """Applies the schema for a model collection to the database.

        Delegates to `ommi.ext.drivers.sqlite.schema_management.apply_schema`.
        This typically involves creating tables and indexes as defined by the models.

        Args:
            model_collection: The collection of models whose schema needs to be applied.
        """
        await schema_management.apply_schema(self.cursor, model_collection)

    async def delete_schema(self, model_collection: "ModelCollection"):
        """Deletes the schema for a model collection from the database.

        Delegates to `ommi.ext.drivers.sqlite.schema_management.delete_schema`.
        This typically involves dropping tables associated with the models.

        Args:
            model_collection: The collection of models whose schema needs to be removed.
        """
        await schema_management.delete_schema(self.cursor, model_collection)


class SQLiteTransactionExplicitTransactions(SQLiteTransaction):
    """Manages SQLite transactions with explicit BEGIN, COMMIT, and ROLLBACK statements.

    This class extends `SQLiteTransaction` to provide fine-grained control over
    the transaction lifecycle. It's suitable for scenarios where the standard
    autocommit behavior or implicit transaction management is not desired.

    The transaction is explicitly started with `BEGIN` upon calling `open()` (or
    entering the async context manager) and concluded with `COMMIT` or `ROLLBACK`.

    This implementation is only necessary for transactions wrapping DDL operations.
    The Ommi SQLite driver only uses this transaction implementation when the isolation
    level setting is set to `OMMI_DEFAULT` which sets `isolation_level` to `None` on the
    connection.
    """
    def __init__(self, cursor: "Cursor"):
        """
        Args:
            cursor: The SQLite cursor to be used for all operations.
        """
        super().__init__(cursor)
        self._is_open = False

    async def open(self):
        """Starts a new transaction if one is not already open.

        Executes a `BEGIN;` statement to explicitly start the SQLite transaction.
        """
        if not self._is_open:
            self.cursor.execute("BEGIN;", ())
            self._is_open = True

    async def close(self):
        """Closes the transaction and the underlying cursor.

        Sets calls the parent class's `close` method to close the cursor.
        """
        self._is_open = False
        await super().close()

    async def commit(self):
        """Commits the active transaction.

        If a transaction is open, it executes a `COMMIT;` statement.
        """
        if self._is_open:
            self.cursor.execute("COMMIT;", ())

    async def rollback(self):
        """Rolls back the active transaction.

        If a transaction is open, it executes a `ROLLBACK;` statement.
        """
        if self._is_open:
            self.cursor.execute("ROLLBACK;", ())

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Handles exiting the asynchronous context manager.

        Attempts to commit the transaction if no exception occurred, or roll it back
        if an exception did occur. It gracefully handles `sqlite3.OperationalError`
        that might occur if, for example, a rollback is attempted on a connection
        that's already been closed or is in an inconsistent state.

        Finally, it ensures the transaction is closed.
        """
        try:
            await self.rollback() if exc_type else self.commit()
        except sqlite3.OperationalError:
            # This can happen if the connection is already closed or if trying
            # to rollback a transaction that was never started or already completed.
            # It's generally safe to ignore in the context of __aexit__.
            pass
        finally:
            await self.close()