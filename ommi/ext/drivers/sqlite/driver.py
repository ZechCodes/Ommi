import sqlite3
from typing import Any, Iterable, NotRequired, TYPE_CHECKING, TypedDict, Literal, Optional

from tramp.async_batch_iterator import AsyncBatchIterator

from ommi.drivers import BaseDriver
from ommi.drivers.exceptions import DriverConnectFailed
from ommi.ext.drivers.sqlite.transaction import SQLiteTransaction, SQLiteTransactionManualTransactions

import ommi.ext.drivers.sqlite.add_query as add_query
import ommi.ext.drivers.sqlite.delete_query as delete_query
import ommi.ext.drivers.sqlite.fetch_query as fetch_query
import ommi.ext.drivers.sqlite.schema_management as schema_management
import ommi.ext.drivers.sqlite.update_query as update_query


if TYPE_CHECKING:
    from ommi.models.collections import ModelCollection
    from ommi.query_ast import ASTGroupNode
    from ommi.shared_types import DBModel


# Define the user-facing literal type for clarity
SQLiteIsolationLevelAlias = Literal["OMMI_DEFAULT", "SQLITE_DEFAULT", "DEFERRED", "IMMEDIATE", "EXCLUSIVE", "NONE"]

class SQLiteSettings(TypedDict):
    database: str
    isolation_level: NotRequired[SQLiteIsolationLevelAlias]


class SQLiteDriver(BaseDriver):
    _default_settings = SQLiteSettings(database=":memory:", isolation_level="OMMI_DEFAULT")

    def __init__(self, connection: sqlite3.Connection, settings: SQLiteSettings):
        super().__init__()
        self.connection = connection
        self._settings = settings

    @classmethod
    def connect(cls, settings: SQLiteSettings | None = None) -> "SQLiteDriver":
        try:
            _settings = cls._default_settings
            if settings:
                _settings |= settings

            connection = sqlite3.connect(_settings["database"])
            match isolation_level := _settings["isolation_level"]:
                case "SQLITE_DEFAULT":
                    pass # Do nothing, it's the default
                case "OMMI_DEFAULT" | "NONE":
                    connection.isolation_level = None
                case _: # DEFERRED, IMMEDIATE, EXCLUSIVE, any other string
                    connection.isolation_level = isolation_level

            return cls(connection, _settings)

        except sqlite3.Error as error:
            raise DriverConnectFailed("Failed to connect to the SQLite database.", driver=cls) from error

    async def disconnect(self):
        self.connection.close()

    def transaction(self) -> SQLiteTransaction:
        cursor = self.connection.cursor()
        transaction_type = SQLiteTransaction
        if self._settings.get("isolation_level", "OMMI_DEFAULT") in ["OMMI_DEFAULT", "NONE"]:
            transaction_type = SQLiteTransactionManualTransactions

        return transaction_type(cursor)

    async def add(self, models: "Iterable[DBModel]") -> "Iterable[DBModel]":
        return await add_query.add_models(self.connection.cursor(), models)

    async def count(self, predicate: "ASTGroupNode") -> int:
        return await fetch_query.count_models(self.connection.cursor(), predicate)

    async def delete(self, predicate: "ASTGroupNode"):
        await delete_query.delete_models(self.connection.cursor(), predicate)

    def fetch(self, predicate: "ASTGroupNode") -> "AsyncBatchIterator[DBModel]":
        return fetch_query.fetch_models(self.connection.cursor(), predicate)

    async def update(self, predicate: "ASTGroupNode", values: dict[str, Any]):
        await update_query.update_models(self.connection.cursor(), predicate, values)

    async def apply_schema(self, model_collection: "ModelCollection"):
        await schema_management.apply_schema(self.connection.cursor(), model_collection)

    async def delete_schema(self, model_collection: "ModelCollection"):
        await schema_management.delete_schema(self.connection.cursor(), model_collection)