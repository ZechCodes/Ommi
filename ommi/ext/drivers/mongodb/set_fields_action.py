from typing import Any, Sequence

from ommi.drivers.database_results import async_result
from ommi.drivers.set_fields_actions import SetFieldsAction
from ommi.ext.drivers.mongodb.connection_protocol import MongoDBConnection
from ommi.ext.drivers.mongodb.utils import process_ast
from ommi.models import OmmiModel
from ommi.query_ast import when, ASTGroupNode

Predicate = ASTGroupNode | type[OmmiModel] | bool


class MongoDBSetFieldsAction(SetFieldsAction[MongoDBConnection, OmmiModel]):
    def __init__(self, connection: MongoDBConnection, predicates: Sequence[Predicate], database):
        super().__init__(connection, predicates)
        self._db = database

    @async_result
    async def set_fields(self, **kwargs: Any) -> bool:
        query = process_ast(when(*self._predicates))
        await self._db[query.collection.__ommi_metadata__.model_name].update_many(
            {
                "$and": query.match,
            },
            {
                "$set": {
                    query.collection.__ommi_metadata__.fields[name].get("store_as"): value
                    for name, value in kwargs.items()
                },
            },
        )
        return True
