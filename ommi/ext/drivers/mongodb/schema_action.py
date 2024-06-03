from typing import Type, Iterable

from ommi.drivers.database_results import async_result
from ommi.drivers.driver_types import TModel
from ommi.drivers.schema_actions import SchemaAction
from ommi.ext.drivers.mongodb.connection_protocol import MongoDBConnection
from ommi.models.collections import ModelCollection
from ommi.models import OmmiModel


class MongoDBSchemaAction(SchemaAction[MongoDBConnection, OmmiModel]):
    type_mapping = {
        int: "INTEGER",
        str: "TEXT",
        float: "REAL",
        bool: "INTEGER",
    }

    def __init__(self, connection: MongoDBConnection, model_collection: ModelCollection[Type[TModel]] | None, database):
        super().__init__(connection, model_collection)
        self._db = database

    @async_result
    async def create_models(self) -> Iterable[Type[OmmiModel]]:
        for model in self._model_collection.models:
            self._db.create_collection(model.__ommi_metadata__.model_name)

        return self._model_collection.models

    @async_result
    async def delete_models(self) -> None:
        for model in self._model_collection.models:
            await self._db[model.__ommi_metadata__.model_name].drop()
