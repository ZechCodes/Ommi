from dataclasses import dataclass, field as dc_field
from typing import Type, Any, TypeAlias, TypedDict

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

LocalField: TypeAlias = str
ForeignField: TypeAlias = str

LookupStage = TypedDict(
    "LookupStage",
    {
        "$lookup": TypedDict(
            "LookupStageFields",
            {
                "from": str,
                "localField": str,
                "foreignField": str,
                "as": str,
            },
        )
    },
)


ProjectStage = TypedDict(
    "ProjectStage",
    {
        "$project": dict[str, int],
    },
)


UnwindStage = TypedDict(
    "UnwindStage",
    {
        "$unwind": TypedDict(
            "UnwindStageFields",
            {
                "path": str,
                "preserveNullAndEmptyArrays": bool,
            },
        )
    },
)


LookupStages: TypeAlias = list[LookupStage]
UnwindStages: TypeAlias = list[UnwindStage]


@dataclass
class Query:
    collection: Type[OmmiModel] | None = None
    collections: list[Type[OmmiModel]] = dc_field(default_factory=list)
    match: list[Any] = dc_field(default_factory=list)

    sorts: list[ASTReferenceNode] = dc_field(default_factory=list)
    max_results: int = 0
    results_page: int = 0

    def add_collection(self, *collections: Type[OmmiModel]) -> None:
        if not self.collection:
            self.collection, *collections = collections

        if collections:
            self.collections.extend(
                collection
                for collection in collections
                if collection not in self.collections and collection != self.collection
            )


def model_to_dict(model: OmmiModel, *, preserve_pk: bool = False) -> dict[str, Any]:
    fields = list(model.__ommi__.fields.values())
    pks = model.get_primary_key_fields()
    return {
        field.get("store_as"): getattr(model, field.get("field_name"))
        for field in fields
        if field not in pks
        or preserve_pk
        or getattr(model, field.get("field_name")) is not None
    }


def process_ast(ast: ASTGroupNode) -> Query:
    query = Query()
    group_stack = [query.match]
    logical_operator_stack = [ASTLogicalOperatorNode.AND]
    node_stack = [iter(ast)]
    while node_stack:
        match next(node_stack[~0], None):
            case ASTReferenceNode(field=None, model=model):
                query.add_collection(model)

            case ASTGroupNode() as group:
                node_stack.append(iter(group))

            case ASTComparisonNode(left, right, op):
                expression, collections = _process_comparison_ast(
                    left, op, right, query.collection
                )
                group_stack[~0].append(expression)
                query.add_collection(*collections)

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

    if ast.sorting:
        query.sorts = ast.sorting

    if ast.max_results:
        query.max_results = ast.max_results

    if ast.results_page:
        query.results_page = ast.results_page

    return query


def build_pipeline(query: Query) -> tuple[list[dict[str, Any]], Type[OmmiModel]]:
    pipeline = []
    if query.match:
        pipeline.append({"$match": {"$and": query.match}})

    if query.sorts:
        pipeline.append(_create_sort_stage(query.sorts))

    if query.max_results > 0:
        pipeline.append(_create_limit_stage(query.max_results))

        if query.results_page:
            pipeline.append(_create_skip_stage(query.max_results, query.results_page))

    if len(query.collections):
        lookups, unwind, project = create_lookup_stages(
            query.collection, query.collections
        )
        pipeline = [*lookups, *unwind, *pipeline, project]

    return pipeline, query.collection


def _create_sort_stage(sorts: list[ASTReferenceNode]) -> dict[str, Any]:
    return {
        "$sort": {
            ref.field.name: 1 if ref.ordering == ResultOrdering.ASCENDING else -1
            for ref in sorts
        }
    }


def create_lookup_stages(
    model: Type[OmmiModel], collections: list[Type[OmmiModel]]
) -> tuple[LookupStages, UnwindStages, ProjectStage]:
    lookups = []
    project = {
        "$project": (hide := {}),
    }
    unwind = []
    for collection in collections:
        hide[f"__join__{collection.__ommi__.model_name}"] = 0

        refs = _get_reference_fields(model, collection)
        model_name = model.__ommi__.model_name.lower()
        lookups.append(
            {
                "$lookup": {
                    "from": collection.__ommi__.model_name,
                    "let": {
                        f"{model_name}_{local_field}": f"${local_field}"
                        for local_field, _ in refs
                    },
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {
                                    "$and": [
                                        {
                                            "$eq": [
                                                f"${foreign_field}",
                                                f"$${model_name}_{local_field}",
                                            ]
                                        }
                                        for local_field, foreign_field in refs
                                    ]
                                }
                            }
                        }
                    ],
                    "as": f"__join__{collection.__ommi__.model_name}",
                }
            }
        )

        unwind.append(
            {
                "$unwind": {
                    "path": f"$__join__{collection.__ommi__.model_name}",
                    "preserveNullAndEmptyArrays": True,
                }
            }
        )

    return lookups, unwind, project


def _create_limit_stage(max_results: int) -> dict[str, Any]:
    return {"$limit": max_results}


def _create_skip_stage(max_results: int, results_page: int) -> dict[str, Any]:
    return {"$skip": max_results * results_page}


def _get_reference_fields(
    model: Type[OmmiModel], collection: Type[OmmiModel]
) -> tuple[tuple[LocalField, ForeignField], ...]:
    if ref := collection.__ommi__.references.get(model):
        return tuple(
            (r.from_field.get("store_as"), r.to_field.get("store_as")) for r in ref
        )

    ref = model.__ommi__.references[collection]
    return tuple(
        (r.from_field.get("store_as"), r.to_field.get("store_as")) for r in ref
    )


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
            if (querying_model and model != querying_model) or (
                not querying_model and collections and model != collections[0]
            ):
                name = f"__join__{model.__ommi__.model_name}.{name}"

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
            if model != querying_model or (
                not querying_model and model != collections[0]
            ):
                name = f"__join__{model.__ommi__.model_name}.{name}"

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
