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


def model_to_dict(model: OmmiModel, *, preserve_pk: bool = False) -> dict[str, Any]:
    fields = list(model.__ommi_metadata__.fields.values())
    pk = model.get_primary_key_field()
    return {
        field.get("store_as"): getattr(model, field.get("field_name"))
        for field in fields
        if field is not pk or preserve_pk or getattr(model, pk.get("field_name")) is not None
    }


def build_pipeline(ast: ASTGroupNode) -> tuple[list[dict[str, Any]], Type[OmmiModel]]:
    pipeline = [{"$match": (match := {})}]
    if ast.sorting:
        pipeline.append(
            {
                "$sort":  {
                    reference.field.name: (
                        1 if reference.ordering == ResultOrdering.ASCENDING else -1
                    )
                    for reference in ast.sorting

                }
            }
        )

    if ast.max_results > 0:
        pipeline.append(
            {
                "$limit": ast.max_results,
            }
        )

        if ast.results_page:
            pipeline.append(
                {
                    "$skip": ast.results_page * ast.max_results
                }
            )

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
                expression, collections_ = _process_comparison_ast(
                    left, op, right, collections[0] if collections else None
                )
                group_stack[~0].append(expression)
                collections.extend(collections_)

            case ASTLogicalOperatorNode() as op:
                if len(node_stack) <= 1:
                    continue

                if logical_operator_stack[~0] is None:
                    logical_operator_stack[~0] = op
                    group_stack[~1].append(
                        {logical_operator_mapping[op]: group_stack[~0]}
                    )

                elif logical_operator_stack[~0] != op:
                    logical_operator_stack.append(op)
                    group_stack.append([])
                    group_stack[~1].append(
                        {logical_operator_mapping[op]: group_stack[~0]}
                    )

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
        match["$and"] = query

    model = collections[0]
    collections = set(collections)
    collections.remove(model)
    if len(collections) >= 1:
        lookups = []
        project_hide = []
        unwind = []
        for collection in set(collections):
            local_field, foreign_field = _get_reference_fields(model, collection)
            lookups.append(
                {
                    "$lookup": {
                        "from": collection.__ommi_metadata__.model_name,
                        "localField": local_field,
                        "foreignField": foreign_field,
                        "as": f"__join__{collection.__ommi_metadata__.model_name}",
                    }
                }
            )
            project_hide.append(f"__join__{collection.__ommi_metadata__.model_name}")
            unwind.append(
                {
                    "$unwind": {
                        "path": f"$__join__{collection.__ommi_metadata__.model_name}",
                        "preserveNullAndEmptyArrays": True,
                    }
                }
            )

            pipeline = lookups + unwind + pipeline + [{"$project": {field: 0 for field in project_hide}}]

    return pipeline, model


def _get_reference_fields(model: Type[OmmiModel], collection: Type[OmmiModel]) -> tuple[str, str]:
    if model in collection.__ommi_metadata__.references:
        reference = collection.__ommi_metadata__.references[model][0]
        foreign, local = reference.from_field, reference.to_field

    else:
        reference = model.__ommi_metadata__.references[collection][0]
        foreign, local = reference.to_field, reference.from_field

    return local.get("store_as"), foreign.get("store_as")

def _process_comparison_ast(
    left: ASTLiteralNode | ASTReferenceNode,
    op: ASTOperatorNode,
    right: ASTLiteralNode | ASTReferenceNode,
    querying_model: Type[OmmiModel] | None,
) -> tuple[dict[str, Any], list[Type[OmmiModel]]]:
    collections = []
    match left, right:
        case (
            ASTReferenceNode(field=field, model=model),
            ASTLiteralNode(value=value),
        ):
            collections.append(model)

            name = field.metadata.get("store_as")
            if (querying_model and model != querying_model) or (not querying_model and collections and model != collections[0]):
                name = f"__join__{model.__ommi_metadata__.model_name}.{name}"

            expr = {
                name: (
                    value
                    if op == ASTOperatorNode.EQUALS
                    else {operator_mapping[op]: value}
                )
            }


        case (
            ASTLiteralNode(value=value),
            ASTReferenceNode(field=field, model=model),
        ):
            collections.append(model)

            name = field.metadata.get("store_as")
            if model != querying_model or (not querying_model and model != collections[0]):
                name = f"__join__{model.__ommi_metadata__.model_name}.{name}"

            expr = {
                name: (
                    value
                    if op == ASTOperatorNode.EQUALS
                    else {flipped_operator_mapping[op]: value}
                )
            }

        case _:
            raise TypeError(f"Unexpected node type: {left} or {right}")

    return expr, collections
