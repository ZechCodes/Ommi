from typing import TypeAlias, Type, Sequence

from ommi.drivers.count_actions import CountAction
from ommi.drivers.database_results import async_result
from ommi.drivers.driver_types import TModel
from ommi.ext.drivers.mongodb.connection_protocol import MongoDBConnection
from ommi.models import OmmiModel
from ommi.query_ast import when, ASTGroupNode
from ommi.ext.drivers.mongodb.utils import build_pipeline, process_ast

Predicate: TypeAlias = ASTGroupNode | Type[TModel] | bool


class MongoDBCountAction(CountAction[MongoDBConnection, OmmiModel]):
    def __init__(self, connection: MongoDBConnection, predicates: Sequence[Predicate], database):
        super().__init__(connection, predicates)
        self._db = database

    @async_result
    async def count(self) -> int:
        query = process_ast(when(*self._predicates))
        pipeline, model = build_pipeline(query)
        if pipeline and not pipeline[0].get("$match"):
            del pipeline[0]

        pipeline.append({"$count": "count"})

        print(pipeline)

        result = (
            await self._db[model.__ommi_metadata__.model_name]
            .aggregate(pipeline)
            .to_list(1)
        )
        return result[0].get("count", 0)
