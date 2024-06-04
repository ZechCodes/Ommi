from typing import Any, Sequence

from ommi.drivers.database_results import async_result
from ommi.drivers.set_fields_actions import SetFieldsAction
from ommi.ext.drivers.mongodb.connection_protocol import MongoDBConnection
from ommi.ext.drivers.mongodb.utils import process_ast, create_lookup_stages
from ommi.models import OmmiModel
from ommi.query_ast import when, ASTGroupNode

Predicate = ASTGroupNode | type[OmmiModel] | bool


class MongoDBSetFieldsAction(SetFieldsAction[MongoDBConnection, OmmiModel]):
    def __init__(
        self, connection: MongoDBConnection, predicates: Sequence[Predicate], database
    ):
        super().__init__(connection, predicates)
        self._db = database

    @async_result
    async def set_fields(self, **kwargs: Any) -> bool:
        query = process_ast(when(*self._predicates))
        pipeline = [
            {
                "$match": {
                    "$and": query.match,
                },
            },
            {
                "$set": {
                    query.collection.__ommi__.fields[name].get("store_as"): value
                    for name, value in kwargs.items()
                },
            },
        ]

        if query.collections:
            lookups, unwind, project = create_lookup_stages(
                query.collection, query.collections
            )
            pipeline = [*lookups, *unwind, *pipeline, project]

        pipeline.append(
            {
                "$merge": {
                    "into": query.collection.__ommi__.model_name,
                    "on": "_id",
                    "whenMatched": "replace",
                },
            }
        )

        await self._db[query.collection.__ommi__.model_name].aggregate(
            pipeline
        ).to_list(1)
        return True
