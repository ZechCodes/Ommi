import sqlite3
from typing import Any, Iterable, NotRequired, TYPE_CHECKING, TypedDict, Literal, Optional

from tramp.async_batch_iterator import AsyncBatchIterator

from ommi.drivers import BaseDriver
from ommi.drivers.exceptions import DriverConnectFailed
from ommi.ext.drivers.sqlite.transaction import SQLiteTransaction, SQLiteTransactionExplicitTransactions

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
    """Configuration settings for SQLite database connections.
    
    This class defines the settings needed to establish and configure a connection
    to a SQLite database. SQLite is a file-based database engine that requires
    minimal configuration.
    
    Attributes:
        database: Path to the SQLite database file. Use ":memory:" for an in-memory database.
        isolation_level: Transaction isolation level to use. Available options:

            - `"OMMI_DEFAULT"`: Uses autocommit mode (`isolation_level=None`) for immediate commits
            - `"SQLITE_DEFAULT"`: Uses SQLite's default isolation level
            - `"DEFERRED"`: Defers locking the database until the first read/write (default SQLite behavior)
            - `"IMMEDIATE"`: Acquires a lock immediately when transaction begins
            - `"EXCLUSIVE"`: Acquires an exclusive lock on the entire database
            - `"NONE"`: Same as `OMMI_DEFAULT`, uses autocommit mode
    """
    database: str
    isolation_level: NotRequired[SQLiteIsolationLevelAlias]


class SQLiteDriver(BaseDriver):
    """SQLite database driver implementation for Ommi ORM.
    
    This driver provides integration with SQLite, a lightweight, file-based database
    engine. It supports both file-based and in-memory databases, making it ideal for
    development, testing, and small applications.
    
    The driver handles all database operations through the sqlite3 standard library
    module, translating Ommi ORM operations into SQLite-compatible queries.
    
    Attributes:
        connection: The underlying sqlite3.Connection instance
        _settings: The configuration settings used for this connection
    """
    _default_settings = SQLiteSettings(database=":memory:", isolation_level="OMMI_DEFAULT")

    def __init__(self, connection: sqlite3.Connection, settings: SQLiteSettings):
        """Initialize a new SQLiteDriver.
        
        Args:
            connection: An established SQLite database connection
            settings: Configuration settings used for this connection
        """
        super().__init__()
        self.connection = connection
        self._settings = settings

    @classmethod
    def connect(cls, settings: SQLiteSettings | None = None) -> "SQLiteDriver":
        """Create a new SQLite database connection.
        
        This method establishes a connection to a SQLite database using the provided
        settings, or default settings if none are provided.
        
        Args:
            settings: Optional configuration settings for the connection.
                     If omitted, defaults to an in-memory database with autocommit mode.
                     
        Returns:
            A new SQLiteDriver instance with an established connection
            
        Raises:
            DriverConnectFailed: If the connection attempt fails
        """
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
        """Close the SQLite database connection.
        
        This method closes the underlying database connection, releasing any
        resources held by the connection.
        """
        self.connection.close()

    def transaction(self) -> SQLiteTransaction:
        """Create a new transaction for database operations.
        
        This method creates a new transaction object that can be used to
        perform multiple database operations as a single atomic unit.
        
        Returns:
            A new SQLiteTransaction instance. If isolation_level is set to
            "OMMI_DEFAULT" or "NONE", returns a SQLiteTransactionExplicitTransactions
            instance which handles commits explicitly.
        """
        cursor = self.connection.cursor()
        transaction_type = SQLiteTransaction
        if self._settings.get("isolation_level", "OMMI_DEFAULT") in ["OMMI_DEFAULT", "NONE"]:
            transaction_type = SQLiteTransactionExplicitTransactions

        return transaction_type(cursor)

    async def add(self, models: "Iterable[DBModel]") -> "Iterable[DBModel]":
        """Add one or more model instances to the database.
        
        Args:
            models: An iterable of model instances to add
            
        Returns:
            The same models, potentially updated with database-generated values
        """
        return await add_query.add_models(self.connection.cursor(), models)

    async def count(self, predicate: "ASTGroupNode") -> int:
        """Count the number of records matching a predicate.
        
        Args:
            predicate: Query conditions to filter records
            
        Returns:
            The number of matching records
        """
        return await fetch_query.count_models(self.connection.cursor(), predicate)

    async def delete(self, predicate: "ASTGroupNode"):
        """Delete records matching a predicate.
        
        Args:
            predicate: Query conditions to determine which records to delete
        """
        await delete_query.delete_models(self.connection.cursor(), predicate)

    def fetch(self, predicate: "ASTGroupNode") -> "AsyncBatchIterator[DBModel]":
        """Fetch records matching a predicate.
        
        Args:
            predicate: Query conditions to filter records
            
        Returns:
            An AsyncBatchIterator that yields matching model instances
        """
        return fetch_query.fetch_models(self.connection.cursor(), predicate)

    async def update(self, predicate: "ASTGroupNode", values: dict[str, Any]):
        """Update records matching a predicate.
        
        Args:
            predicate: Query conditions to determine which records to update
            values: Dictionary of field names and values to update
        """
        await update_query.update_models(self.connection.cursor(), predicate, values)

    async def apply_schema(self, model_collection: "ModelCollection"):
        """Apply the schema for a collection of models.
        
        This method creates or updates database tables for all models
        in the given collection.
        
        Args:
            model_collection: A collection of model classes
        """
        await schema_management.apply_schema(self.connection.cursor(), model_collection)

    async def delete_schema(self, model_collection: "ModelCollection"):
        """Delete the schema for a collection of models.
        
        This method drops database tables for all models in the given collection.
        
        Args:
            model_collection: A collection of model classes
        """
        await schema_management.delete_schema(self.connection.cursor(), model_collection)