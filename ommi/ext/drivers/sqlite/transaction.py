import sqlite3
from typing import Any, Iterable, TYPE_CHECKING

from tramp.async_batch_iterator import AsyncBatchIterator

from ommi.drivers import BaseDriverTransaction

import ommi.ext.drivers.sqlite.schema_management as schema_management

if TYPE_CHECKING:
    from ommi.models import OmmiModel
    from ommi.models.collections import ModelCollection
    from ommi.query_ast import ASTGroupNode
    from tramp.async_batch_iterator import AsyncBatchIterator


class SQLiteTransaction(BaseDriverTransaction):
    def __init__(self, cursor: sqlite3.Cursor):
        self.cursor = cursor

    async def close(self):
        self.cursor.close()

    async def commit(self):
        self.cursor.connection.commit()

    async def open(self):
        return

    async def rollback(self):
        self.cursor.connection.rollback()

    async def add(self, models: "Iterable[OmmiModel]") -> "Iterable[OmmiModel]":
        pass

    async def count(self, predicate: "ASTGroupNode") -> int:
        pass

    async def delete(self, predicate: "ASTGroupNode"):
        pass

    async def fetch(self, predicate: "ASTGroupNode") -> "AsyncBatchIterator[OmmiModel]":
        pass

    async def update(self, predicate: "ASTGroupNode", values: dict[str, Any]) -> "Iterable[OmmiModel]":
        pass

    async def apply_schema(self, model_collection: "ModelCollection"):
        await schema_management.apply_schema(self.cursor, model_collection)

    async def delete_schema(self, model_collection: "ModelCollection"):
        await schema_management.delete_schema(self.cursor, model_collection)