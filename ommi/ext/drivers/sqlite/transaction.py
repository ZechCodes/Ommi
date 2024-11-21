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
        pass

    async def delete(self, predicate: "ASTGroupNode"):
        await delete_query.delete_models(self.cursor, predicate)

    def fetch(self, predicate: "ASTGroupNode") -> "AsyncBatchIterator[DBModel]":
        return fetch_query.fetch_models(self.cursor, predicate)

    async def update(self, predicate: "ASTGroupNode", values: dict[str, Any]) -> "Iterable[DBModel]":
        return await update_query.update_models(self.cursor, predicate, values)

    async def apply_schema(self, model_collection: "ModelCollection"):
        await schema_management.apply_schema(self.cursor, model_collection)

    async def delete_schema(self, model_collection: "ModelCollection"):
        await schema_management.delete_schema(self.cursor, model_collection)