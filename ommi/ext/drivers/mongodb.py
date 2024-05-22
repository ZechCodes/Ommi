from dataclasses import dataclass

import motor.motor_asyncio

from ommi.drivers import DatabaseDriver, DriverConfig, database_action
from ommi.models import OmmiModel
from typing import Type, Any

from ommi.query_ast import ASTGroupNode, ASTReferenceNode, ASTLiteralNode, ASTLogicalOperatorNode, ASTOperatorNode, \
    ASTComparisonNode, ASTGroupFlagNode, ResultOrdering, when


@dataclass
class MongoDBConfig(DriverConfig):
    host: str
    port: int
    database_name: str
    timeout: int = 20000


class MongoDBDriver(DatabaseDriver, driver_name="mongodb", nice_name="MongoDB"):
    config: MongoDBConfig

    logical_operator_mapping = {
        ASTLogicalOperatorNode.AND: "$and",
        ASTLogicalOperatorNode.OR: "$or",
    }

    operator_mapping = {
        ASTOperatorNode.EQUALS: "$eq",
        ASTOperatorNode.NOT_EQUALS: "$ne",
        ASTOperatorNode.GREATER_THAN: "$gt",
        ASTOperatorNode.GREATER_THAN_OR_EQUAL: "$gte",
        ASTOperatorNode.LESS_THAN: "$lt",
        ASTOperatorNode.LESS_THAN_OR_EQUAL: "$lte",
    }

    # Field references need to be on the left, so if they're on the right the operator needs to be flipped
    flipped_operator_mapping = operator_mapping | {
        ASTOperatorNode.GREATER_THAN: "$lt",
        ASTOperatorNode.GREATER_THAN_OR_EQUAL: "$lte",
        ASTOperatorNode.LESS_THAN: "$gt",
        ASTOperatorNode.LESS_THAN_OR_EQUAL: "$gte",
    }

    def __init__(self, *args):
        super().__init__(*args)
        self._connected = False
        self._client = None
        self._db = None

    @property
    def connected(self) -> bool:
        return self._connected

    @database_action
    async def connect(self) -> "MongoDBDriver":
        self._client = motor.motor_asyncio.AsyncIOMotorClient(self.config.host, self.config.port, timeoutMS=self.config.timeout)
        self._db = self._client.get_database(self.config.database_name)
        self._connected = True
        return self

    @database_action
    async def disconnect(self) -> "MongoDBDriver":
        self._client.close()
        self._connected = False
        return self

    @database_action
    async def add(self, *items: OmmiModel) -> "MongoDBDriver":
        for item in items:
            await self._insert(item)

        return self

    @database_action
    async def count(self, *predicates: ASTGroupNode | Type[OmmiModel]) -> int:
        pipeline, model = self._process_ast(when(*predicates))
        pipeline["$count"] = "count"
        if not pipeline["$match"]:
            del pipeline["$match"]

        result = await self._db[model.__ommi_metadata__.model_name].aggregate([pipeline]).to_list(1)
        return result[0].get("count", 0)

    @database_action
    async def delete(self, *items: OmmiModel) -> "MongoDBDriver":
        for item in items:
            await self._db[item.__ommi_metadata__.model_name].delete_one({'_id': getattr(item, "__ommi_mongodb_id__")})

        return self

    @database_action
    async def fetch(
        self, *predicates: ASTGroupNode | Type[OmmiModel]
    ) -> list[OmmiModel]:
        return await self._fetch(when(*predicates))

    @database_action
    async def sync_schema(
        self, models: "ommi.model_collections.ModelCollection | None"
    ) -> "MongoDBDriver":
        return self

    @database_action
    async def update(self, *items: OmmiModel) -> "MongoDBDriver":
        for item in items:
            await self._update(item)

        return self

    async def _fetch(self, ast: ASTGroupNode) -> list[OmmiModel]:
        pipeline, model = self._process_ast(ast)
        results = self._db[model.__ommi_metadata__.model_name].aggregate([pipeline])
        return [self._create_model(result, model) async for result in results]

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

    async def _insert(self, item: OmmiModel):
        data = self._model_to_dict(item)
        result = await self._db[item.__ommi_metadata__.model_name].insert_one(data)
        item.__ommi_mongodb_id__ = result.inserted_id

    async def _update(self, item: OmmiModel):
        await self._db[item.__ommi_metadata__.model_name].replace_one(
            {'_id': getattr(item, "__ommi_mongodb_id__")},
            self._model_to_dict(item)
        )

    def _model_to_dict(self, model: OmmiModel) -> dict[str, Any]:
        fields = list(model.__ommi_metadata__.fields.values())
        return {
            field.get("store_as"): getattr(model, field.get("field_name"))
            for field in fields
        }

    def _process_ast(self, ast: ASTGroupNode) -> tuple[dict[str, Any], Type[OmmiModel]]:
        pipeline = {
            "$match": {}
        }

        if ast.sorting:
            pipeline["$sort"] = {
                reference.field.name: 1 if reference.ordering == ResultOrdering.ASCENDING else -1
                for reference in ast.sorting
            }

        if ast.max_results > 0:
            pipeline["$limit"] = ast.max_results

            if ast.results_page:
                pipeline["$skip"] = ast.results_page * ast.max_results

        collections = []
        query = []
        group_stack = [query]
        logical_operator_stack = [ASTLogicalOperatorNode.AND]
        node_stack = [iter(ast)]
        while node_stack:
            match next(node_stack[~0], None):
                case ASTReferenceNode(field=None, model=model):
                    collections.append(model)

                case ASTGroupNode() as group:
                    node_stack.append(iter(group))

                case ASTComparisonNode(left, right, op):
                    expression, collections_ = self._process_comparison_ast(left, op, right)
                    group_stack[~0].append(expression)
                    collections.extend(collections_)

                case ASTLogicalOperatorNode() as op:
                    if len(node_stack) <= 1:
                        continue

                    if logical_operator_stack[~0] is None:
                        logical_operator_stack[~0] = op
                        group_stack[~1].append({self.logical_operator_mapping[op]: group_stack[~0]})

                    elif logical_operator_stack[~0] != op:
                        logical_operator_stack.append(op)
                        group_stack.append([])
                        group_stack[~1].append({self.logical_operator_mapping[op]: group_stack[~0]})

                case ASTGroupFlagNode.OPEN:
                    if len(node_stack) > 1:
                        group_stack.append([])
                        logical_operator_stack.append(None)

                case ASTGroupFlagNode.CLOSE:
                    group_stack.pop()

                case None:
                    node_stack.pop()

                case node:
                    raise TypeError(f"Unexpected node type: {node}")

        if query:
            pipeline["$match"]["$and"] = query

        return pipeline, collections[0]

    def _process_comparison_ast(
            self,
            left: ASTLiteralNode | ASTReferenceNode,
            op: ASTOperatorNode,
            right: ASTLiteralNode | ASTReferenceNode
    ) -> tuple[dict[str, Any], list[Type[OmmiModel]]]:
        expr = {}
        collections = []
        match left, right:
            case (ASTReferenceNode(field=field, model=model), ASTLiteralNode(value=value)):
                collections.append(model)
                expr = {field.name: {self.operator_mapping.get(op, "$eq"): value}}

            case (ASTLiteralNode(value=value), ASTReferenceNode(field=field, model=model)):
                collections.append(model)
                expr = {field.name: {self.flipped_operator_mapping.get(op, "$eq"): value}}

            case _:
                raise TypeError(f"Unexpected node type: {left} or {right}")

        return expr, collections
