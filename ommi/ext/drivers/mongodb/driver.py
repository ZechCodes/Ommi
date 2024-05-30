from typing import Type, TypeAlias
from dataclasses import dataclass

import motor.motor_asyncio

from ommi.drivers import DatabaseDriver, DriverConfig
from ommi.drivers.database_results import async_result
from ommi.drivers.driver_types import TModel
from ommi.drivers.drivers import enforce_connection_protocol, connection_context_manager
from ommi.ext.drivers.mongodb.add_action import MongoDBAddAction
from ommi.ext.drivers.mongodb.connection_protocol import MongoDBConnection
from ommi.ext.drivers.mongodb.find_action import MongoDBFindAction
from ommi.ext.drivers.mongodb.schema_action import MongoDBSchemaAction
from ommi.models.collections import ModelCollection
from ommi.models import OmmiModel
from ommi.query_ast import ASTGroupNode

Predicate: TypeAlias = ASTGroupNode | Type[TModel] | bool


@dataclass
class MongoDBConfig(DriverConfig):
    host: str
    port: int
    database_name: str
    timeout: int = 20000


@enforce_connection_protocol
class MongoDBDriver(
    DatabaseDriver[MongoDBConnection, OmmiModel], driver_name="mongodb", nice_name="MongoDB"
):
    def __init__(self, connection: MongoDBConnection, database):
        super().__init__(connection)
        self._db = database

    @async_result
    async def disconnect(self) -> bool:
        self._connection.close()
        self._connected = False
        return True

    @property
    def add(self) -> MongoDBAddAction:
        return MongoDBAddAction(self._connection, self._db)

    def find(self, *predicates: Predicate) -> MongoDBFindAction:
        return MongoDBFindAction(self._connection, predicates, self._db)

    def schema(
        self, model_collection: ModelCollection[Type[OmmiModel]] | None = None
    ) -> MongoDBSchemaAction:
        return MongoDBSchemaAction(self._connection, model_collection, self._db)

    @classmethod
    @connection_context_manager
    async def from_config(cls, config: MongoDBConfig) -> "MongoDBDriver":
        connection = motor.motor_asyncio.AsyncIOMotorClient(
            config.host, config.port, timeoutMS=config.timeout
        )
        db = connection.get_database(config.database_name)
        return cls(connection, db)

