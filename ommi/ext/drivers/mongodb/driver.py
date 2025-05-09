from typing import Type, TypeAlias, Any, Iterable, AsyncIterator
from dataclasses import dataclass, field

import motor.motor_asyncio
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection

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
    def __init__(self, client: AsyncIOMotorClient, database_name: str):
        super().__init__()
        self.client: AsyncIOMotorClient = client
        self.db: AsyncIOMotorDatabase = client[database_name]
        self._database_name: str = database_name

    @classmethod
    def connect(cls, settings: MongoDBSettings | None = None) -> "MongoDBDriver":
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
        self.client.close()

    def transaction(self) -> MongoDBTransaction:
        return MongoDBTransaction(self.client, self.db)

    async def add(self, models: Iterable[DBModel]) -> Iterable[DBModel]:
        return await mongodb_add.add_models(self.db, models)

    async def count(self, predicate: ASTGroupNode) -> int:
        return await mongodb_fetch.count_models(self.db, predicate)

    async def delete(self, predicate: ASTGroupNode) -> int:
        return await mongodb_delete.delete_models(self.db, predicate)

    def fetch(self, predicate: ASTGroupNode) -> AsyncBatchIterator[DBModel]:
        return mongodb_fetch.fetch_models(self.db, predicate)

    async def update(self, predicate: ASTGroupNode, values: dict[str, Any]) -> int:
        return await mongodb_update.update_models(self.db, predicate, values)

    async def apply_schema(self, model_collection: ModelCollection):
        await mongodb_schema.apply_schema(self.db, model_collection)

    async def delete_schema(self, model_collection: ModelCollection):
        await mongodb_schema.delete_schema(self.db, model_collection)
