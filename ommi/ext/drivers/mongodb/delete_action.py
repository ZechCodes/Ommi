from typing import Sequence

from ommi.drivers.database_results import async_result
from ommi.drivers.delete_actions import DeleteAction
from ommi.ext.drivers.mongodb.connection_protocol import MongoDBConnection
from ommi.ext.drivers.mongodb.utils import build_pipeline
from ommi.models import OmmiModel
from ommi.query_ast import when, ASTGroupNode

Predicate = ASTGroupNode | type(OmmiModel) | bool


class MongoDBDeleteAction(DeleteAction[MongoDBConnection, OmmiModel]):
    def __init__(self, connection: MongoDBConnection, predicates: Sequence[Predicate], database):
        super().__init__(connection, predicates)
        self._db = database

    @async_result
    async def delete(self) -> bool:
        pipeline, model = build_pipeline(when(*self._predicates))
        query = pipeline[0]["$match"]
        if len(query) == 1 and len(query["$and"]) == 0:
            query = {}

        await self._db[model.__ommi_metadata__.model_name].delete_many(query)
        return True