import sqlite3
from dataclasses import dataclass
from typing import Type, cast, TypeAlias

from ommi.drivers import DatabaseDriver, DriverConfig
from ommi.drivers.database_results import async_result
from ommi.drivers.driver_types import TModel
from ommi.drivers.drivers import enforce_connection_protocol, connection_context_manager
from ommi.ext.drivers.sqlite.add_action import SQLiteAddAction
from ommi.ext.drivers.sqlite.connection_protocol import SQLiteConnection
from ommi.ext.drivers.sqlite.find_action import SQLiteFindAction
from ommi.ext.drivers.sqlite.schema_action import SQLiteSchemaAction
from ommi.models.collections import ModelCollection
from ommi.models import OmmiModel
from ommi.query_ast import ASTGroupNode

Predicate: TypeAlias = ASTGroupNode | Type[TModel] | bool


@dataclass
class SQLiteConfig(DriverConfig):
    filename: str


@enforce_connection_protocol
class SQLiteDriver(
    DatabaseDriver[SQLiteConnection, OmmiModel], driver_name="sqlite", nice_name="SQLite"
):
    @async_result
    async def disconnect(self) -> bool:
        self._connection.close()
        self._connected = False
        return True

    @property
    def add(self) -> SQLiteAddAction:
        return SQLiteAddAction(self._connection)

    def find(self, *predicates: Predicate) -> SQLiteFindAction:
        return SQLiteFindAction(self._connection, predicates)

    def schema(
        self, model_collection: ModelCollection[Type[OmmiModel]] | None = None
    ) -> SQLiteSchemaAction:
        return SQLiteSchemaAction(self._connection, model_collection)

    @classmethod
    @connection_context_manager
    async def from_config(cls, config: SQLiteConfig) -> "SQLiteDriver":
        return cls(cast(SQLiteConnection, sqlite3.connect(config.filename)))
