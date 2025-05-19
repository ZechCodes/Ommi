from typing import TypeAlias, Any, Iterable
from dataclasses import dataclass, field

import motor.motor_asyncio
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from ommi.drivers import BaseDriver
from ommi.drivers.exceptions import DriverConnectFailed
from ommi.models.collections import ModelCollection
from ommi.query_ast import ASTGroupNode
from ommi.ext.drivers.mongodb.transaction import MongoDBTransaction
from ommi.shared_types import DBModel
from tramp.async_batch_iterator import AsyncBatchIterator

import ommi.ext.drivers.mongodb.mongodb_add as mongodb_add
import ommi.ext.drivers.mongodb.mongodb_fetch as mongodb_fetch
import ommi.ext.drivers.mongodb.mongodb_delete as mongodb_delete
import ommi.ext.drivers.mongodb.mongodb_update as mongodb_update
import ommi.ext.drivers.mongodb.mongodb_schema as mongodb_schema

Predicate: TypeAlias = ASTGroupNode


@dataclass
class MongoDBSettings:
    """Configuration settings for MongoDB database connections.
    
    This class defines the settings needed to establish and configure a connection
    to a MongoDB database server.
    
    Attributes:
        host: Hostname or IP address of the MongoDB server (default: "localhost")
        port: Port number the MongoDB server is listening on (default: 27017)
        database_name: Name of the database to connect to (default: "ommi")
        username: Optional username for authentication
        password: Optional password for authentication
        authSource: Authentication database name (default: "admin")
        timeout: Server selection timeout in milliseconds (default: 20000)
        connection_options: Additional connection options to pass to the MongoDB client.
            Example: {"tlsAllowInvalidCertificates": True}
    """
    host: str = "localhost"
    port: int = 27017
    database_name: str = "ommi"
    username: str | None = None
    password: str | None = None
    authSource: str | None = "admin"
    timeout: int = 20000
    # Example: connection_options: dict[str, Any] = field(default_factory=lambda: {"tlsAllowInvalidCertificates": True})
    connection_options: dict[str, Any] = field(default_factory=dict)


class MongoDBDriver(BaseDriver):
    """MongoDB database driver implementation for Ommi ORM.
    
    This driver provides integration with MongoDB, a document-oriented NoSQL
    database. It leverages the Motor library to provide full asynchronous
    support for all database operations.
    
    The driver translates Ommi ORM operations into MongoDB-compatible
    operations, bridging the gap between relational ORM concepts and
    MongoDB's document model.
    
    Attributes:
        client: The underlying AsyncIOMotorClient instance
        db: The AsyncIOMotorDatabase instance for the specified database
    """
    def __init__(self, client: AsyncIOMotorClient, database_name: str):
        """Initialize a new MongoDBDriver.
        
        Args:
            client: An established MongoDB client connection
            database_name: Name of the database to use
        """
        super().__init__()
        self.client: AsyncIOMotorClient = client
        self.db: AsyncIOMotorDatabase = client[database_name]
        self._database_name: str = database_name

    @classmethod
    def connect(cls, settings: MongoDBSettings | None = None) -> "MongoDBDriver":
        """Create a new MongoDB database connection.
        
        This method establishes a connection to a MongoDB database using
        the provided settings, or default settings if none are provided.
        
        Args:
            settings: Optional configuration settings for the connection.
                     If omitted, defaults to a local MongoDB server with
                     default database name "ommi".
                     
        Returns:
            A new MongoDBDriver instance with an established connection
            
        Raises:
            DriverConnectFailed: If the connection initialization fails
        """
        _settings = settings or MongoDBSettings()
        try:
            # Ensure the client is properly awaited if necessary, though Motor is non-blocking init
            client = motor.motor_asyncio.AsyncIOMotorClient(
                host=_settings.host,
                port=_settings.port,
                username=_settings.username,
                password=_settings.password,
                authSource=_settings.authSource,
                serverSelectionTimeoutMS=_settings.timeout,
                **_settings.connection_options
            )
            # A direct ping on connect is not performed here to avoid blocking in an async method.
            # Operations will fail later if the connection is unavailable.
            # An async ping could be added if immediate connection validation is critical.
            return cls(client, _settings.database_name)

        except Exception as error:
            raise DriverConnectFailed(f"Failed to initialize MongoDB client: {error}", driver=cls) from error

    async def disconnect(self):
        """Close the MongoDB database connection.
        
        This method closes the underlying database connection, releasing any
        resources held by the connection.
        """
        self.client.close()

    def transaction(self) -> MongoDBTransaction:
        """Create a new transaction for database operations.
        
        This method creates a new transaction object that can be used to
        perform multiple database operations as a single atomic unit.
        
        Note: MongoDB transactions require a replica set configuration.
        
        Returns:
            A new MongoDBTransaction instance
        """
        return MongoDBTransaction(self.client, self.db)

    async def add(self, models: Iterable[DBModel]) -> Iterable[DBModel]:
        """Add one or more model instances to the database.
        
        Args:
            models: An iterable of model instances to add
            
        Returns:
            The same models, potentially updated with database-generated values
        """
        return await mongodb_add.add_models(self.db, models)

    async def count(self, predicate: ASTGroupNode) -> int:
        """Count the number of documents matching a predicate.
        
        Args:
            predicate: Query conditions to filter documents
            
        Returns:
            The number of matching documents
        """
        return await mongodb_fetch.count_models(self.db, predicate)

    async def delete(self, predicate: ASTGroupNode) -> int:
        """Delete documents matching a predicate.
        
        Args:
            predicate: Query conditions to determine which documents to delete
            
        Returns:
            The number of documents deleted
        """
        return await mongodb_delete.delete_models(self.db, predicate)

    def fetch(self, predicate: ASTGroupNode) -> AsyncBatchIterator[DBModel]:
        """Fetch documents matching a predicate.
        
        Args:
            predicate: Query conditions to filter documents
            
        Returns:
            An AsyncBatchIterator that yields matching model instances
        """
        return mongodb_fetch.fetch_models(self.db, predicate)

    async def update(self, predicate: ASTGroupNode, values: dict[str, Any]) -> int:
        """Update documents matching a predicate.
        
        Args:
            predicate: Query conditions to determine which documents to update
            values: Dictionary of field names and values to update
            
        Returns:
            The number of documents updated
        """
        return await mongodb_update.update_models(self.db, predicate, values)

    async def apply_schema(self, model_collection: ModelCollection):
        """Apply the schema for a collection of models.
        
        This method creates collections for all models in the given collection.
        For MongoDB, this means creating collections and optionally setting up
        any indexes or validations.
        
        Args:
            model_collection: A collection of model classes
        """
        await mongodb_schema.apply_schema(self.db, model_collection)

    async def delete_schema(self, model_collection: ModelCollection):
        """Delete the schema for a collection of models.
        
        This method drops collections for all models in the given collection.
        
        Args:
            model_collection: A collection of model classes
        """
        await mongodb_schema.delete_schema(self.db, model_collection)
