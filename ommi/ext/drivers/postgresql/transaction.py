from typing import Any, Iterable, TYPE_CHECKING

import psycopg

from ommi.drivers import BaseDriverTransaction
from tramp.async_batch_iterator import AsyncBatchIterator

# Import query modules
import ommi.ext.drivers.postgresql.add_query as add_query
import ommi.ext.drivers.postgresql.delete_query as delete_query
import ommi.ext.drivers.postgresql.fetch_query as fetch_query
import ommi.ext.drivers.postgresql.schema_management as schema_management
import ommi.ext.drivers.postgresql.update_query as update_query


if TYPE_CHECKING:
    from psycopg import AsyncConnection, AsyncCursor
    from ommi.models.collections import ModelCollection
    from ommi.query_ast import ASTGroupNode
    from ommi.shared_types import DBModel


class PostgreSQLTransaction(BaseDriverTransaction):
    def __init__(self, connection: "AsyncConnection"):
        self._connection = connection
        self._transaction: psycopg.AsyncTransaction | None = None
        self._cursor: AsyncCursor | None = None

    async def _get_cursor(self) -> "AsyncCursor":
        if self._cursor is None or self._cursor.closed:
            if self._transaction is None:
                # This case should ideally not happen if open() is always called.
                # However, as a fallback, start a transaction.
                await self.open()
            self._cursor = self._connection.cursor() # type: ignore # transaction is not None here
        return self._cursor # type: ignore


    async def open(self):
        if self._transaction is None:
            self._transaction = self._connection.transaction() # type: ignore
            await self._transaction.__aenter__()
        # The cursor is obtained on-demand to ensure it's associated with the active transaction.

    async def close(self):
        # Commits by default if not already handled by __aexit__ (e.g. due to an exception)
        if self._transaction is not None:
            await self._transaction.__aexit__(None, None, None)
            self._transaction = None
        if self._cursor and not self._cursor.closed:
            await self._cursor.close()
            self._cursor = None

    async def commit(self):
        # For psycopg3, commit is handled by the transaction context manager's exit.
        # Explicit commit might not be needed if using `async with transaction:` block properly
        # However, if called, we ensure the transaction is exited cleanly, which implies commit.
        if self._transaction is not None:
            await self._transaction.__aexit__(None, None, None) # type: ignore
            self._transaction = None # Reset transaction state

    async def rollback(self):
        if self._transaction is not None:
            # Signal rollback to the context manager
            await self._transaction.__aexit__(ValueError, ValueError("Rollback"), None) # type: ignore
            self._transaction = None # Reset transaction state


    async def add(self, models: "Iterable[DBModel]") -> "Iterable[DBModel]":
        cur = await self._get_cursor()
        return await add_query.add_models(cur, models) # type: ignore

    async def count(self, predicate: "ASTGroupNode") -> int:
        cur = await self._get_cursor()
        return await fetch_query.count_models(cur, predicate) # Changed from count_query # type: ignore

    async def delete(self, predicate: "ASTGroupNode"):
        cur = await self._get_cursor()
        await delete_query.delete_models(cur, predicate) # type: ignore

    async def fetch(self, predicate: "ASTGroupNode") -> "AsyncBatchIterator[DBModel]":
        """Fetches models using the transaction's cursor."""
        # The fetch_models function from fetch_query.py expects an AsyncCursor.
        # self._get_cursor() provides an AsyncCursor associated with the current transaction.
        # This allows fetch operations within a transaction to be part of that transaction.
        cur = await self._get_cursor()
        return fetch_query.fetch_models(cur, predicate)

    async def update(self, predicate: "ASTGroupNode", values: dict[str, Any]):
        cur = await self._get_cursor()
        await update_query.update_models(cur, predicate, values) # type: ignore

    async def apply_schema(self, model_collection: "ModelCollection"):
        cur = await self._get_cursor()
        await schema_management.apply_schema(cur, model_collection) # type: ignore

    async def delete_schema(self, model_collection: "ModelCollection"):
        cur = await self._get_cursor()
        await schema_management.delete_schema(cur, model_collection) # type: ignore 