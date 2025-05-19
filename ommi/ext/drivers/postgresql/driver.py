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
    """Configuration settings for PostgreSQL database connections.
    
    This class defines the settings needed to establish and configure a connection
    to a PostgreSQL database server.
    
    Attributes:
        host: Hostname or IP address of the PostgreSQL server (e.g., "localhost")
        port: Port number the PostgreSQL server is listening on (default: 5432)
        database: Name of the database to connect to
        user: Username for authentication
        password: Password for authentication
    """
    host: str
    port: int
    database: str
    user: str
    password: str


class PostgreSQLDriver(BaseDriver):
    """PostgreSQL database driver implementation for Ommi ORM.
    
    This driver provides integration with PostgreSQL, a powerful, open-source
    object-relational database system. It leverages the psycopg3 library to
    provide full asynchronous support for all database operations.
    
    The driver translates Ommi ORM operations into PostgreSQL-compatible
    queries, handling the complexities of communication with the database server.
    
    Attributes:
        connection: The underlying psycopg.AsyncConnection instance
        _connected: Boolean flag indicating if the connection is active
    """
    def __init__(self, connection: psycopg.AsyncConnection):
        """Initialize a new PostgreSQLDriver.
        
        Args:
            connection: An established asynchronous PostgreSQL connection
        """
        super().__init__()
        self.connection = connection
        self._connected = True

    @classmethod
    async def connect(cls, settings: PostgreSQLSettings | None = None) -> "PostgreSQLDriver":
        """Create a new PostgreSQL database connection asynchronously.
        
        This method establishes an asynchronous connection to a PostgreSQL database
        using the provided settings, or default settings if none are provided.
        
        Args:
            settings: Optional configuration settings for the connection.
                     If omitted, defaults to a local PostgreSQL server with standard
                     testing credentials.
                     
        Returns:
            A new PostgreSQLDriver instance with an established connection
            
        Raises:
            DriverConnectFailed: If the connection attempt fails
        """
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
        """Close the PostgreSQL database connection asynchronously.
        
        This method closes the underlying database connection, releasing any
        resources held by the connection.
        """
        if self.connection and not self.connection.closed:
            await self.connection.close()
        self._connected = False

    def transaction(self) -> PostgreSQLTransaction:
        """Create a new transaction for database operations.
        
        This method creates a new transaction object that can be used to
        perform multiple database operations as a single atomic unit.
        
        Returns:
            A new PostgreSQLTransaction instance
        """
        return PostgreSQLTransaction(self.connection)

    async def add(self, models: "Iterable[DBModel]") -> "Iterable[DBModel]":
        """Add one or more model instances to the database.
        
        Args:
            models: An iterable of model instances to add
            
        Returns:
            The same models, potentially updated with database-generated values
        """
        async with self.connection.cursor() as cur:
            return await add_query.add_models(cur, models)

    async def count(self, predicate: "ASTGroupNode") -> int:
        """Count the number of records matching a predicate.
        
        Args:
            predicate: Query conditions to filter records
            
        Returns:
            The number of matching records
        """
        async with self.connection.cursor() as cur:
            return await fetch_query.count_models(cur, predicate)

    async def delete(self, predicate: "ASTGroupNode"):
        """Delete records matching a predicate.
        
        Args:
            predicate: Query conditions to determine which records to delete
        """
        async with self.connection.cursor() as cur:
            await delete_query.delete_models(cur, predicate)

    def fetch(self, predicate: "ASTGroupNode") -> "AsyncBatchIterator[DBModel]":
        """Fetch records matching a predicate.
        
        Args:
            predicate: Query conditions to filter records
            
        Returns:
            An AsyncBatchIterator that yields matching model instances
        """
        # psycopg3 connection.cursor() is synchronous, but returns an AsyncCursor.
        # fetch_models is designed to work with this AsyncCursor.
        return fetch_query.fetch_models(self.connection.cursor(), predicate)

    async def update(self, predicate: "ASTGroupNode", values: dict[str, Any]):
        """Update records matching a predicate.
        
        Args:
            predicate: Query conditions to determine which records to update
            values: Dictionary of field names and values to update
        """
        async with self.connection.cursor() as cur:
            await update_query.update_models(cur, predicate, values)

    async def apply_schema(self, model_collection: "ModelCollection"):
        """Apply the schema for a collection of models.
        
        This method creates or updates database tables for all models
        in the given collection.
        
        Args:
            model_collection: A collection of model classes
        """
        async with self.connection.cursor() as cur:
            await schema_management.apply_schema(cur, model_collection)

    async def delete_schema(self, model_collection: "ModelCollection"):
        """Delete the schema for a collection of models.
        
        This method drops database tables for all models in the given collection.
        
        Args:
            model_collection: A collection of model classes
        """
        async with self.connection.cursor() as cur:
            await schema_management.delete_schema(cur, model_collection)

    @property
    def connected(self) -> bool:
        """Check if the database connection is active.
        
        Returns:
            True if the connection is established and open, False otherwise
        """
        return self._connected and self.connection is not None and not self.connection.closed
