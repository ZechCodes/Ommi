import psycopg
from typing import Any, Iterable, TYPE_CHECKING, TypedDict

from tramp.async_batch_iterator import AsyncBatchIterator

from ommi.drivers import BaseDriver
from ommi.drivers.exceptions import DriverConnectFailed
from ommi.ext.drivers.postgresql.transaction import PostgreSQLTransaction

import ommi.ext.drivers.postgresql.add_query as add_query
import ommi.ext.drivers.postgresql.delete_query as delete_query
import ommi.ext.drivers.postgresql.fetch_query as fetch_query
import ommi.ext.drivers.postgresql.schema_management as schema_management
import ommi.ext.drivers.postgresql.update_query as update_query

if TYPE_CHECKING:
    from ommi.models.collections import ModelCollection
    from ommi.query_ast import ASTGroupNode
    from ommi.shared_types import DBModel
    # class PostgreSQLTransaction: ... # Forward declaration if needed for type hints


class PostgreSQLSettings(TypedDict):
    host: str
    port: int
    database: str
    user: str
    password: str


class PostgreSQLDriver(BaseDriver):
    def __init__(self, connection: psycopg.AsyncConnection):
        super().__init__()
        self.connection = connection
        self._connected = True

    @classmethod
    async def connect(cls, settings: PostgreSQLSettings | None = None) -> "PostgreSQLDriver":
        if settings is None:
            # Default to typical local postgres settings for testing if no settings are provided.
            settings = PostgreSQLSettings(
                host="localhost",
                port=5432,
                user="postgres", # Default user for official postgres image
                password="mysecretpassword", # Matches default in dev environment setup
                database="ommi_test"
            )

        conn_str = f"postgresql://{settings['user']}:{settings['password']}@{settings['host']}:{settings['port']}/{settings['database']}"
        try:
            # Ensure autocommit is True. For psycopg3, autocommit=True on connect means
            # operations outside a transaction block are committed immediately.
            # This is generally simpler for individual operations if not part of a larger transaction.
            connection = await psycopg.AsyncConnection.connect(conn_str, autocommit=True)
            return cls(connection)
        except psycopg.Error as error:
            raise DriverConnectFailed(f"Failed to connect to the PostgreSQL database: {error}", driver=cls) from error

    async def disconnect(self):
        if self.connection and not self.connection.closed:
            await self.connection.close()
        self._connected = False

    def transaction(self) -> PostgreSQLTransaction:
        return PostgreSQLTransaction(self.connection)

    async def add(self, models: "Iterable[DBModel]") -> "Iterable[DBModel]":
        async with self.connection.cursor() as cur:
            return await add_query.add_models(cur, models)

    async def count(self, predicate: "ASTGroupNode") -> int:
        async with self.connection.cursor() as cur:
            return await fetch_query.count_models(cur, predicate)

    async def delete(self, predicate: "ASTGroupNode"):
        async with self.connection.cursor() as cur:
            await delete_query.delete_models(cur, predicate)

    def fetch(self, predicate: "ASTGroupNode") -> "AsyncBatchIterator[DBModel]":
        # psycopg3 connection.cursor() is synchronous, but returns an AsyncCursor.
        # fetch_models is designed to work with this AsyncCursor.
        return fetch_query.fetch_models(self.connection.cursor(), predicate)

    async def update(self, predicate: "ASTGroupNode", values: dict[str, Any]):
        async with self.connection.cursor() as cur:
            await update_query.update_models(cur, predicate, values)

    async def apply_schema(self, model_collection: "ModelCollection"):
        async with self.connection.cursor() as cur:
            await schema_management.apply_schema(cur, model_collection)

    async def delete_schema(self, model_collection: "ModelCollection"):
        async with self.connection.cursor() as cur:
            await schema_management.delete_schema(cur, model_collection)

    @property
    def connected(self) -> bool:
        return self._connected and self.connection is not None and not self.connection.closed
