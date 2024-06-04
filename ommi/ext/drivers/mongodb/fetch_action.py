import ast
from datetime import datetime, date
from typing import Type, Any, Generator, TypeVar, Callable, get_origin, Sequence

from ommi.drivers.database_results import async_result
from ommi.drivers.fetch_actions import FetchAction
from ommi.ext.drivers.mongodb.connection_protocol import MongoDBConnection
from ommi.ext.drivers.mongodb.utils import build_pipeline
from ommi.models import OmmiModel
from ommi.query_ast import when, ASTGroupNode, ResultOrdering


T = TypeVar("T")
Predicate = ASTGroupNode | Type[OmmiModel] | bool


class Iteratable:
    pass


class MongoDBFetchAction(FetchAction[MongoDBConnection, OmmiModel]):
    def __init__(self, connection: MongoDBConnection, predicates: Sequence[Predicate], database):
        super().__init__(connection, predicates)
        self._db = database

    @async_result
    async def fetch(self) -> list[OmmiModel]:
        pipeline, model = build_pipeline(when(*self._predicates))
        results = self._db[model.__ommi_metadata__.model_name].aggregate(pipeline)
        return [self._create_model(result, model) async for result in results]

    async def one(self) -> OmmiModel:
        return (await self.all())[0]

    def _create_model(self, data: dict[str, Any], model: Type[OmmiModel]) -> OmmiModel:
        field_mapping = {
            field.get("store_as"): field.get("field_name")
            for field in model.__ommi_metadata__.fields.values()
        }
        instance = model(
            **{
                field_mapping[key]: value
                for key, value in data.items()
                if key in field_mapping
            }
        )
        instance.__ommi_mongodb_id__ = data.get("_id")
        return instance




