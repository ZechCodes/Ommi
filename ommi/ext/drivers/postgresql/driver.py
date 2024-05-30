import psycopg
from dataclasses import dataclass
from typing import Type, cast, TypeAlias

from ommi.drivers import DatabaseDriver, DriverConfig
from ommi.drivers.database_results import async_result
from ommi.drivers.driver_types import TModel
from ommi.drivers.drivers import enforce_connection_protocol, connection_context_manager
from ommi.ext.drivers.postgresql.add_action import PostgreSQLAddAction
from ommi.ext.drivers.postgresql.connection_protocol import PostgreSQLConnection
from ommi.ext.drivers.postgresql.find_action import PostgreSQLFindAction
from ommi.ext.drivers.postgresql.schema_action import PostgreSQLSchemaAction
from ommi.models.collections import ModelCollection
from ommi.models import OmmiModel
from ommi.query_ast import ASTGroupNode

Predicate: TypeAlias = ASTGroupNode | Type[TModel] | bool


@dataclass
class PostgreSQLConfig(DriverConfig):
    host: str
    port: int
    database_name: str
    username: str
    password: str

    def to_uri(self) -> str:
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database_name}"


@enforce_connection_protocol
class PostgreSQLDriver(
    DatabaseDriver[PostgreSQLConnection, OmmiModel], driver_name="postgresql", nice_name="PostgreSQL"
):
    @async_result
    async def disconnect(self) -> bool:
        await self._connection.close()
        self._connected = False
        return True

    @property
    def add(self) -> PostgreSQLAddAction:
        return PostgreSQLAddAction(self._connection)

    def find(self, *predicates: Predicate) -> PostgreSQLFindAction:
        return PostgreSQLFindAction(self._connection, predicates)

    def schema(
        self, model_collection: ModelCollection[Type[OmmiModel]] | None = None
    ) -> PostgreSQLSchemaAction:
        return PostgreSQLSchemaAction(self._connection, model_collection)

    @classmethod
    @connection_context_manager
    async def from_config(cls, config: PostgreSQLConfig) -> "PostgreSQLDriver":
        connection = await psycopg.AsyncConnection.connect(config.to_uri())
        return cls(cast(PostgreSQLConnection, connection))
