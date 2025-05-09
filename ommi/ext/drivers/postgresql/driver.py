import psycopg
from typing import Any, Iterable, TYPE_CHECKING, TypedDict

# print("\n*** LOADING REFACTORED POSTGRESQL DRIVER MODULE (driver.py) ***\n") # Debug print removed

from tramp.async_batch_iterator import AsyncBatchIterator

from ommi.drivers import BaseDriver
from ommi.drivers.exceptions import DriverConnectFailed
from ommi.ext.drivers.postgresql.transaction import PostgreSQLTransaction # Restored

# Import new query modules (will have placeholders)
import ommi.ext.drivers.postgresql.add_query as add_query
import ommi.ext.drivers.postgresql.delete_query as delete_query
import ommi.ext.drivers.postgresql.fetch_query as fetch_query
import ommi.ext.drivers.postgresql.schema_management as schema_management
import ommi.ext.drivers.postgresql.update_query as update_query
# import ommi.ext.drivers.postgresql.count_query as count_query


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
            # This will be called by the test fixture without settings.
            # The original postgres driver in tests might have relied on default env vars or a default config.
            # For now, to match test expectations, we should provide some defaults if settings is None.
            # The test fixture passes request.param.connect(), which means it passes no explicit settings.
            # It relies on the driver's connect method to handle this case.
            # The old driver used a PostgreSQLConfig with default values or env var loading.
            # We need to replicate that, or make tests provide settings.
            # For now, let's assume tests expect connect() to work without args for default local connection.
            # This is a common pattern for test fixtures.
            # The error "ValueError: PostgreSQLSettings must be provided for connect." will cause test setup to fail.
            # The original tests/test_drivers.py driver fixture:
            # @pytest_asyncio.fixture(params=[..., PostgreSQLDriver], ...)
            # async def driver(request):
            #     async with request.param.connect() as driver: <--- called with no args
            #         ...
            # This means our connect() must handle settings=None.
            # We need to create a default PostgreSQLSettings if None is provided.
            # Defaulting to typical local postgres settings for testing.
            settings = PostgreSQLSettings(
                host="localhost",
                port=5432,
                user="ommi_test_user", # Placeholder, user might need to create this or use env vars
                password="ommi_test_password", # Placeholder
                database="ommi_test"
            )
            # The podman run command uses: POSTGRES_PASSWORD=mysecretpassword -e POSTGRES_DB=ommi_test
            # User is typically 'postgres' if not specified.
            settings["user"] = "postgres" # Default user for postgres image
            settings["password"] = "mysecretpassword"
            # settings["database_name"] = "ommi_test" # old name

        conn_str = f"postgresql://{settings['user']}:{settings['password']}@{settings['host']}:{settings['port']}/{settings['database']}"
        try:
            # Ensure autocommit is True, as schema operations in tests might rely on it outside explicit transactions.
            # Or, manage commits carefully in each schema/add/update/delete operation if autocommit=False.
            # SQLite driver uses connection.commit() in its transaction, but cursor operations are often autocommitted or need explicit commit.
            # For psycopg3, autocommit=True on connect means operations outside a transaction block are committed immediately.
            # This is generally simpler for individual operations if not part of a larger transaction.
            connection = await psycopg.AsyncConnection.connect(conn_str, autocommit=True)
            return cls(connection)
        except psycopg.Error as error:
            raise DriverConnectFailed(f"Failed to connect to the PostgreSQL database: {error}", driver=cls) from error

    async def disconnect(self):
        if self.connection and not self.connection.closed:
            await self.connection.close()
        self._connected = False

    def transaction(self) -> PostgreSQLTransaction: # Restored
        return PostgreSQLTransaction(self.connection) # Restored

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
        # psycopg3 cursor() is synchronous, but returns an AsyncCursor.
        # The fetch_models function needs to be designed to work with an AsyncCursor.
        # It will likely involve async iteration or await execute/fetchall on the cursor.
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

# Remove old class and imports no longer needed
# The old PostgreSQLConfig can be removed or adapted into PostgreSQLSettings
# The old @enforce_connection_protocol and @connection_context_manager might not be needed
# or will be re-evaluated with the new structure.
