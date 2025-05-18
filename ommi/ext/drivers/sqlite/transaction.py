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
    def __init__(self, cursor: "Cursor"):
        self.cursor = cursor

    async def close(self):
        self.cursor.close()

    async def commit(self):
        self.cursor.connection.commit()

    async def open(self):
        return

    async def rollback(self):
        self.cursor.connection.rollback()

    async def add(self, models: "Iterable[DBModel]") -> "Iterable[DBModel]":
        return await add_query.add_models(self.cursor, models)

    async def count(self, predicate: "ASTGroupNode") -> int:
        return await fetch_query.count_models(self.cursor, predicate)

    async def delete(self, predicate: "ASTGroupNode"):
        await delete_query.delete_models(self.cursor, predicate)

    def fetch(self, predicate: "ASTGroupNode") -> "AsyncBatchIterator[DBModel]":
        return fetch_query.fetch_models(self.cursor, predicate)

    async def update(self, predicate: "ASTGroupNode", values: dict[str, Any]):
        await update_query.update_models(self.cursor, predicate, values)

    async def apply_schema(self, model_collection: "ModelCollection"):
        await schema_management.apply_schema(self.cursor, model_collection)

    async def delete_schema(self, model_collection: "ModelCollection"):
        await schema_management.delete_schema(self.cursor, model_collection)


class SQLiteTransactionManualTransactions(SQLiteTransaction):
    def __init__(self, cursor: "Cursor"):
        super().__init__(cursor)
        self._is_open = False

    async def open(self):
        if not self._is_open:
            self.cursor.execute("BEGIN;", ())
            self._is_open = True

    async def close(self):
        self._is_open = False
        await super().close()

    async def commit(self):
        if self._is_open:
            self.cursor.execute("COMMIT;", ())

    async def rollback(self):
        if self._is_open:
            self.cursor.execute("ROLLBACK;", ())

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            await self.rollback() if exc_type else self.commit()
        except sqlite3.OperationalError:
            pass
        finally:
            await self.close()