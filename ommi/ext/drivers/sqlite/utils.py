from dataclasses import dataclass, field as dc_field
from datetime import date, datetime
from typing import Any, Callable, Generator, get_origin, get_args, Type, TYPE_CHECKING, Union

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

if TYPE_CHECKING:
    from ommi.shared_types import DBModel

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

type_mapping: dict[Type[Any], str] = {
    int: "INTEGER",
    str: "TEXT",
    float: "REAL",
    bool: "INTEGER",
}

type_validators = {
    datetime: lambda value: value,  # No-op to avoid type conflict with date
    date: lambda value: value.split()[0],
    int: lambda value: int(value) if value is not None else None,
    float: lambda value: float(value) if value is not None else None,
    bool: lambda value: bool(value) if value is not None else None,
    str: lambda value: str(value) if value is not None else None,
}


def map_to_model(row: tuple[Any, ...], model: "Type[DBModel]") -> "DBModel":
    return model(**dict(_validate_row_values(model, row)))


def _validate_row_values(model: "Type[DBModel]", row: tuple[Any, ...]) -> Generator[tuple[str, Any], None, None]:
    for field, value in zip(model.__ommi__.fields.values(), row):
        name = field.get("field_name")
        if validator := _find_type_validator(field.get("field_type", value)):
            yield name, validator(value)
        else:
            yield name, value


def _find_type_validator[T](type_hint: Type[T]) -> Callable[[Any], T] | None:
    hint = get_origin(type_hint) or type_hint
    
    # Handle Union types (like Optional[int] which is Union[int, None])
    if hint is Union:
        args = get_args(type_hint)
        # For Optional types, get the non-None type
        non_none_types = [arg for arg in args if arg is not type(None)]
        if non_none_types:
            hint = non_none_types[0]
    
    for validator_type, validator in type_validators.items():
        try:
            if issubclass(hint, validator_type):
                return validator
        except TypeError:
            # hint is not a class (e.g., it's a generic type), skip it
            continue

    return None


def get_sqlite_type(obj_type: Type[Any]) -> str:
    return type_mapping.get(obj_type, "TEXT")


@dataclass
class SelectQuery:
    limit: int = 0
    model: "Type[DBModel] | None" = None
    models: "list[Type[DBModel]]" = dc_field(default_factory=list)
    offset: int = 0
    order_by: dict[str, ResultOrdering] = dc_field(default_factory=dict)
    values: list[Any] = dc_field(default_factory=list)
    where: str = ""

    def add_model(self, *models: "Type[DBModel]"):
        if not self.model:
            self.model, *models = models

        if models:
            self.models.extend(
                m for m in models if m not in self.models and m != self.model
            )


def build_query(ast: ASTGroupNode) -> SelectQuery:
    query = SelectQuery(
        limit=ast.max_results,
        offset=ast.results_page,  # Treat results_page as direct offset, not page number
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
                name = f"\"{model.__ommi__.model_name}\".\"{field.metadata.get('store_as')}\""
                where.append(name)
                query.add_model(model)

            case ASTLiteralNode(value):
                # Handle special SQL keywords
                if value in ("IS", "IS NOT", "NULL"):
                    where.append(value)
                else:
                    where.append("?")
                    # Convert boolean values to integers for SQLite
                    if isinstance(value, bool):
                        query.values.append(int(value))
                    else:
                        query.values.append(value)

            case ASTLogicalOperatorNode() as op:
                where.append(logical_operator_mapping[op])

            case ASTOperatorNode() as op:
                where.append(operator_mapping[op])

            case ASTComparisonNode(left, right, op):
                # Check if this is a NULL comparison and modify the operator
                if isinstance(right, ASTLiteralNode) and right.value is None:
                    if op == ASTOperatorNode.EQUALS:
                        # Replace = with IS for NULL
                        modified_op = ASTLiteralNode("IS")
                        modified_right = ASTLiteralNode("NULL")
                        node_stack.append(iter((left, modified_op, modified_right)))
                    elif op == ASTOperatorNode.NOT_EQUALS:
                        # Replace != with IS NOT for NULL  
                        modified_op = ASTLiteralNode("IS NOT")
                        modified_right = ASTLiteralNode("NULL")
                        node_stack.append(iter((left, modified_op, modified_right)))
                    else:
                        # For other operators, keep as-is (will be false in SQL)
                        node_stack.append(iter((left, op, right)))
                else:
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
        f"\"{ref.model.__ommi__.model_name}\".\"{ref.field.metadata.get('store_as')}\"": ref.ordering for ref in sorting
    }


def build_subquery(
    model: "Type[DBModel]", models: "list[Type[DBModel]]", where: str
) -> str:
    pks = ", ".join(
        f"\"{model.__ommi__.model_name}\".\"{pk.get('store_as')}\""
        for pk in model.get_primary_key_fields()
    )
    sub_query = [
        f"SELECT {pks}",
        f"FROM \"{model.__ommi__.model_name}\"",
    ]
    sub_query.extend(generate_joins(model, models))

    if where:
        sub_query.append(f"WHERE {where}")

    return " ".join(sub_query)


def generate_joins(model: "Type[DBModel]", models: "list[Type[DBModel]]"):
    for join in models:
        yield _create_join(model, join)


def _create_join(model: "Type[DBModel]", join_model: "Type[DBModel]") -> str:
    if model in join_model.__ommi__.references:
        columns = " AND ".join(
            f"\"{join_model.__ommi__.model_name}\".\"{r.from_field.get('store_as')}\" = "
            f"\"{model.__ommi__.model_name}\".\"{r.to_field.get('store_as')}\""
            for r in join_model.__ommi__.references[model]
        )

    else:
        columns = " AND ".join(
            f"\"{join_model.__ommi__.model_name}\".\"{r.to_field.get('store_as')}\" = "
            f"\"{model.__ommi__.model_name}\".\"{r.from_field.get('store_as')}\""
            for r in model.__ommi__.references[join_model]
        )

    return f"JOIN \"{join_model.__ommi__.model_name}\" ON {columns}"
