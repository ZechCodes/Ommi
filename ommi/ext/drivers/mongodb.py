from idlelib import query

import motor.motor_asyncio

from ommi import models
from ommi.drivers import DatabaseDriver, DriverConfig, database_action
from ommi.models import OmmiModel
from typing import Type, Any

from ommi.query_ast import ASTGroupNode, ASTReferenceNode, ASTLiteralNode, ASTLogicalOperatorNode, ASTOperatorNode, \
    ASTComparisonNode, ASTGroupFlagNode, ResultOrdering


class MongoDBConfig(DriverConfig):
    host: str
    port: int


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

    @property
    def connected(self) -> bool:
        return self._connected

    @database_action
    async def connect(self) -> "MongoDBDriver":
        self._client = motor.motor_asyncio.AsyncIOMotorClient(self.config.host, self.config.port)
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
            await self._db[item.__class__.__name__].insert_one(item.to_dict())

        return self

    @database_action
    async def delete(self, *items: OmmiModel) -> "MongoDBDriver":
        for item in items:
            await self._db[item.__class__.__name__].delete_one({'_id': item._id})

        return self

    @database_action
    async def fetch(self, model: Type[OmmiModel]) -> list[OmmiModel]:
        cursor = self._db[model.__name__].find()
        result = await cursor.to_list(length=100)
        return [model(**doc) for doc in result]

    @database_action
    async def update(self, *items: OmmiModel) -> "MongoDBDriver":
        for item in items:
            await self._db[item.__class__.__name__].replace_one({'_id': item._id}, item.to_dict())
        return self

    def _process_ast(self, ast: ASTGroupNode) -> tuple[dict[str, Any], Type[OmmiModel]]:
        pipeline = {
            "$match": {
                "$and": []
            }
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
        group_stack = [pipeline["$match"]["$and"]]
        logical_operator_stack = [ASTLogicalOperatorNode.AND]
        node_stack = [iter(ast)]
        while node_stack:
            match next(node_stack[~0], None):
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
