from dataclasses import dataclass, field as dc_field
from typing import Type, Any

from ommi.models import OmmiModel
from ommi.query_ast import (
    ASTGroupNode,
    ResultOrdering,
    ASTGroupFlagNode,
    ASTComparisonNode,
    ASTOperatorNode,
    ASTLogicalOperatorNode,
    ASTLiteralNode,
    ASTReferenceNode,
)

logical_operator_mapping = {
    ASTLogicalOperatorNode.AND: "AND",
    ASTLogicalOperatorNode.OR: "OR",
}

operator_mapping = {
    ASTOperatorNode.EQUALS: "=",
    ASTOperatorNode.NOT_EQUALS: "!=",
    ASTOperatorNode.GREATER_THAN: ">",
    ASTOperatorNode.GREATER_THAN_OR_EQUAL: ">=",
    ASTOperatorNode.LESS_THAN: "<",
    ASTOperatorNode.LESS_THAN_OR_EQUAL: "<=",
}


@dataclass
class SelectQuery:
    limit: int = 0
    model: Type[OmmiModel] | None = None
    models: list[Type[OmmiModel]] = dc_field(default_factory=list)
    offset: int = 0
    order_by: dict[str, ResultOrdering] = dc_field(default_factory=dict)
    values: list[Any] = dc_field(default_factory=list)
    where: str = ""

    def add_model(self, *models: Type[OmmiModel]):
        if not self.model:
            self.model, *models = models

        if models:
            self.models.extend(
                m for m in models if m not in self.models and m != self.model
            )


def build_query(ast: ASTGroupNode) -> SelectQuery:
    query = SelectQuery(
        limit=ast.max_results,
        offset=ast.results_page * ast.max_results,
        order_by=_process_ordering(ast.sorting),
    )
    where = []
    node_stack = [iter(ast)]
    while node_stack:
        match next(node_stack[~0], None):
            case ASTGroupNode() as group:
                node_stack.append(iter(group))

            case ASTReferenceNode(None, model):
                query.add_model(model)

            case ASTReferenceNode(field, model):
                name = f"{model.__ommi__.model_name}.{field.metadata.get('store_as')}"
                where.append(name)
                query.add_model(model)

            case ASTLiteralNode(value):
                where.append("%s")
                query.values.append(value)

            case ASTLogicalOperatorNode() as op:
                where.append(logical_operator_mapping[op])

            case ASTOperatorNode() as op:
                where.append(operator_mapping[op])

            case ASTComparisonNode(left, right, op):
                node_stack.append(iter((left, op, right)))

            case ASTGroupFlagNode.OPEN:
                if len(node_stack) > 1:
                    where.append("(")

            case ASTGroupFlagNode.CLOSE:
                if len(node_stack) > 1:
                    where.append(")")

            case None:
                node_stack.pop()

            case node:
                raise TypeError(f"Unexpected node type: {node}")

    query.where = " ".join(where)
    return query


def _process_ordering(sorting: list[ASTReferenceNode]) -> dict[str, ResultOrdering]:
    return {
        f"{ref.model.__model_name__}.{ref.field.name}": ref.ordering for ref in sorting
    }


def generate_joins(model: Type[OmmiModel], models: list[Type[OmmiModel]]):
    for join in models:
        yield create_join(model, join)


def create_join(model: Type[OmmiModel], join_model: Type[OmmiModel]) -> str:
    return f"JOIN {join_model.__ommi__.model_name} ON {create_join_comparison(model, join_model)}"


def create_join_comparison(model: Type[OmmiModel], join_model: Type[OmmiModel]) -> str:
    if model in join_model.__ommi__.references:
        columns = " AND ".join(
            f"{join_model.__ommi__.model_name}.{r.from_field.get('store_as')} = "
            f"{model.__ommi__.model_name}.{r.to_field.get('store_as')}"
            for r in join_model.__ommi__.references[model]
        )

    else:
        columns = " AND ".join(
            f"{join_model.__ommi__.model_name}.{r.to_field.get('store_as')} = "
            f"{model.__ommi__.model_name}.{r.from_field.get('store_as')}"
            for r in model.__ommi__.references[join_model]
        )

    return columns
