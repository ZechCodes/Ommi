from typing import Any, Type, cast
from dataclasses import dataclass

from ommi.query_ast import ( 
    ASTNode, ASTGroupNode, ASTComparisonNode, ASTOperatorNode, ASTLiteralNode, ASTReferenceNode,
    ResultOrdering, ASTLogicalOperatorNode
)
from ommi.models import OmmiModel
from ommi.models.field_metadata import FieldMetadata, ReferenceTo
from ommi.ext.drivers.mongodb.mongodb_utils import get_collection_name, get_model_field_name


MONGO_OPERATORS = {
    ASTOperatorNode.EQUALS: "$eq",
    ASTOperatorNode.NOT_EQUALS: "$ne",
    ASTOperatorNode.GREATER_THAN: "$gt",
    ASTOperatorNode.GREATER_THAN_OR_EQUAL: "$gte",
    ASTOperatorNode.LESS_THAN: "$lt",
    ASTOperatorNode.LESS_THAN_OR_EQUAL: "$lte",
    # ASTOperatorNode.IN: "$in", 
    # ASTOperatorNode.NOT_IN: "$nin",
}

MONGO_LOGICAL_OPERATORS = {
    ASTLogicalOperatorNode.AND: "$and",
    ASTLogicalOperatorNode.OR: "$or",
    # ASTLogicalOperatorNode.NOT: "$not"
}

@dataclass
class MongoDBQueryParts:
    filter: dict[str, Any]
    sort: list[tuple[str, int]] | None = None
    skip: int | None = None
    limit: int | None = None
    # For aggregation pipeline when joins are involved
    pipeline: list[dict[str, Any]] | None = None 
    target_collection_name: str | None = None # The final collection to query after joins


# Helper function (similar to one added in mongodb_fetch.py)
def _determine_model_type_from_ast_items(items: list[ASTNode]) -> Type[OmmiModel] | None:
    for item in items:
        if isinstance(item, ASTReferenceNode): 
            return item.model
        elif isinstance(item, ASTComparisonNode):
            if isinstance(item.left, ASTReferenceNode):
                return item.left.model
        elif isinstance(item, ASTGroupNode):
            model_from_group = _determine_model_type_from_ast_items(item.items)
            if model_from_group:
                return model_from_group
    return None


def _parse_comparison_node(node: ASTComparisonNode, current_model_type: Type[OmmiModel], model_field_prefix_map: dict[Type[OmmiModel], str]) -> dict[str, Any]:
    field_node = cast(ASTReferenceNode, node.left)
    literal_node = cast(ASTLiteralNode, node.right)
    
    field_model_type = field_node.model
    # field_node.field is QueryableFieldDescriptor, get its string name from its metadata
    queryable_descriptor = field_node.field
    attr_name_str = queryable_descriptor.metadata.get("field_name")
    if not attr_name_str:
        # Fallback or error if field_name is not in metadata, though it should be.
        # For safety, could try getattr(queryable_descriptor, 'name', None) or raise
        raise ValueError(f"Could not determine field name string from QueryableFieldDescriptor: {queryable_descriptor}")

    raw_db_field_name = get_model_field_name(field_model_type, attr_name_str)

    # Apply prefix if field is from a joined model
    prefix = model_field_prefix_map.get(field_model_type, "")
    db_field_name = f"{prefix}{raw_db_field_name}" if prefix else raw_db_field_name

    operator = node.operator
    value = literal_node.value

    if operator in MONGO_OPERATORS:
        return {db_field_name: {MONGO_OPERATORS[operator]: value}}
    # LIKE, IS_NULL, IS_NOT_NULL are not in ASTOperatorNode
    # or should be handled by EQUALS/NOT_EQUALS with None value.
    else:
        # This implies that if an operator is not in MONGO_OPERATORS
        # it would fall here (e.g., IN, NOT_IN if they were defined in ASTOperatorNode and handled).
        raise NotImplementedError(f"MongoDB translation for operator {operator} not implemented.")


def _parse_group_node(node: ASTGroupNode, current_model_type: Type[OmmiModel], model_field_prefix_map: dict[Type[OmmiModel], str]) -> dict[str, Any]:
    if not node.items:
        return {}

    # Attempt to determine the logical operator for the group.
    # The ASTGroupNode structure has 'items' like [Cond1, AND, Cond2, OR, Cond3].
    # This function currently assumes a simpler model where a group has one overarching operator
    # or implies AND for a list of conditions. This might need future refinement for complex nested logic.
    group_operator_attr = getattr(node, 'operator', None) # 'operator' is not a standard attr of ASTGroupNode

    # Note: Handling of logical NOT for a group is not straightforward with MongoDB's $not operator
    # and is currently not implemented here. $not is field-level or requires $nor for group-level negation.

    mongo_op_str: str | None = None
    children_to_parse = node.items

    if group_operator_attr and group_operator_attr in MONGO_LOGICAL_OPERATORS:
        mongo_op_str = MONGO_LOGICAL_OPERATORS[group_operator_attr]
    else:
        # If no explicit group operator, or not a recognized one, analyze items.
        # This simplified logic doesn't fully parse sequences like [Cond1, AND, Cond2, OR, Cond3].
        # It currently defaults to AND if multiple conditions are present without a clear group operator.
        
        # Filter out ASTLogicalOperatorNodes from items for now, as they are not directly parsed as children here.
        # This is a simplification; proper parsing would handle them to structure nested $and/$or.
        conditions = [item for item in node.items if not isinstance(item, ASTLogicalOperatorNode)]
        
        if not conditions:
            return {} # Only logical operators, or empty after filter
        
        if len(conditions) == 1:
            # Single condition in the group, parse it directly without a surrounding $and/$or.
            return _parse_node(conditions[0], current_model_type, model_field_prefix_map)
        else:
            # Multiple conditions, default to $and.
            mongo_op_str = MONGO_LOGICAL_OPERATORS[ASTLogicalOperatorNode.AND]
            children_to_parse = conditions # Parse only the condition nodes

    if not mongo_op_str:
        # Fallback or error if no mongo_op could be determined (should ideally be handled above)
        # This might happen if group_operator_attr was something unexpected and items didn't fall into AND default.
        if children_to_parse: # If there was only one child, it should have returned directly.
             # This path indicates multiple children but no resolvable group operator, which implies an issue.
             # Defaulting to AND as a last resort if multiple children remain.
             mongo_op_str = MONGO_LOGICAL_OPERATORS[ASTLogicalOperatorNode.AND]
        else: # No children to parse, e.g. group was empty or only logical ops
            return {}

    parsed_children = [_parse_node(child, current_model_type, model_field_prefix_map) for child in children_to_parse]
    # Filter out empty dicts that might result from parsing non-condition nodes (e.g. ASTLogicalOperatorNode if not filtered earlier)
    parsed_children = [pc for pc in parsed_children if pc]
    if not parsed_children:
        return {}
    if len(parsed_children) == 1 and mongo_op_str == MONGO_LOGICAL_OPERATORS[ASTLogicalOperatorNode.AND]:
        # If only one condition results after parsing for an AND group, no need for explicit $and
        return parsed_children[0]

    return {mongo_op_str: parsed_children}


def _parse_node(node: ASTNode, current_model_type: Type[OmmiModel], model_field_prefix_map: dict[Type[OmmiModel], str]) -> dict[str, Any]:
    if isinstance(node, ASTComparisonNode):
        return _parse_comparison_node(node, current_model_type, model_field_prefix_map)
    elif isinstance(node, ASTGroupNode):
        return _parse_group_node(node, current_model_type, model_field_prefix_map)
    # JoinNode will be handled by build_query_parts as it affects the pipeline more than just the filter
    # LiteralNode and ASTReferenceNode are handled within ComparisonNode
    # SortNode will be handled by build_query_parts
    else:
        raise NotImplementedError(f"AST node type {type(node)} not yet supported in MongoDB query builder filter construction.")


def _create_join_stages(
    pipeline_base_model: Type[OmmiModel], 
    model_to_join: Type[OmmiModel], 
    base_model_field_prefix: str, # Prefix for fields in pipeline_base_model if it was joined
    join_alias_suffix: str
) -> tuple[list[dict[str, Any]], str]:
    """
    Creates $lookup and $unwind stages for joining model_to_join to pipeline_base_model.
    Returns the list of stages and the alias for the joined data.
    """
    foreign_collection_name = get_collection_name(model_to_join)
    join_conditions: list[tuple[str, str]] = [] # List of (local_field_db_name, foreign_field_db_name)

    # Scenario 1: pipeline_base_model has ReferenceTo(s) model_to_join
    if hasattr(pipeline_base_model, "__ommi__"):
        for field_name, meta_obj in pipeline_base_model.__ommi__.fields.items():
            actual_ref_payload = meta_obj.metadata.get('reference_to')
            if actual_ref_payload and isinstance(actual_ref_payload, ASTReferenceNode) and actual_ref_payload.model == model_to_join:
                ref_target_node = actual_ref_payload
                raw_local_field_name = get_model_field_name(pipeline_base_model, field_name)
                current_local_field_db_name = f"{base_model_field_prefix}{raw_local_field_name}" if base_model_field_prefix else raw_local_field_name
                
                foreign_pk_attr_name = ref_target_node.field.metadata.get("field_name")
                if not foreign_pk_attr_name:
                     raise ValueError(f"Could not get field_name from target reference node's field metadata: {ref_target_node.field.metadata}")
                current_foreign_field_db_name = get_model_field_name(model_to_join, foreign_pk_attr_name)
                join_conditions.append((current_local_field_db_name, current_foreign_field_db_name))
    
    # Scenario 2: model_to_join has ReferenceTo(s) pipeline_base_model
    # This scenario might be less common for typical "forward" joins but good to cover.
    # Ensure it doesn't add duplicate/conflicting conditions if Scenario 1 already found some.
    if not join_conditions and hasattr(model_to_join, "__ommi__"): # Only if Scenario 1 found nothing
        for field_name_on_foreign, meta_obj_on_foreign in model_to_join.__ommi__.fields.items():
            actual_ref_payload = meta_obj_on_foreign.metadata.get('reference_to')
            if actual_ref_payload and isinstance(actual_ref_payload, ASTReferenceNode) and actual_ref_payload.model == pipeline_base_model:
                ref_target_node = actual_ref_payload
                current_foreign_field_db_name = get_model_field_name(model_to_join, field_name_on_foreign)
                
                local_pk_attr_name = ref_target_node.field.metadata.get("field_name")
                if not local_pk_attr_name:
                    raise ValueError(f"Could not get field_name from target reference node's field metadata (Scenario 2): {ref_target_node.field.metadata}")
                raw_local_field_name = get_model_field_name(pipeline_base_model, local_pk_attr_name)
                current_local_field_db_name = f"{base_model_field_prefix}{raw_local_field_name}" if base_model_field_prefix else raw_local_field_name
                join_conditions.append((current_local_field_db_name, current_foreign_field_db_name))

    if not join_conditions:
        raise ValueError(
            f"Could not determine any join fields between {pipeline_base_model.__name__} and {model_to_join.__name__}. "
            f"Ensure a ReferenceTo metadata is defined on one of the models pointing to the other's key field(s)."
        )

    as_field = f"_ommi_joined_{model_to_join.__name__.lower()}_{join_alias_suffix}"

    # Construct $lookup with let and pipeline for multi-field joins
    let_vars = {}
    match_expr_conditions = []
    for i, (local_f, foreign_f) in enumerate(join_conditions):
        let_var_name = f"local_join_var_{i}"
        let_vars[let_var_name] = f"${local_f}" # Prepend $ for field path
        match_expr_conditions.append({"$eq": [f"$${let_var_name}", f"${foreign_f}"]})

    lookup_pipeline = [
        {
            "$match": {
                "$expr": {
                    "$and": match_expr_conditions
                }
            }
        }
    ]

    lookup_stage = {
        "$lookup": {
            "from": foreign_collection_name,
            "let": let_vars,
            "pipeline": lookup_pipeline,
            "as": as_field,
        }
    }
    unwind_stage = {"$unwind": {"path": f"${as_field}", "preserveNullAndEmptyArrays": True}}
    
    return [lookup_stage, unwind_stage], as_field


def build_query_parts(predicate: ASTGroupNode) -> MongoDBQueryParts:
    """Translates an ASTGroupNode into MongoDB query components (filter, sort, limit, skip, pipeline)."""
    
    model_type_from_predicate: Type[OmmiModel] | None = None
    if predicate and predicate.items:
        model_type_from_predicate = _determine_model_type_from_ast_items(predicate.items)

    if not model_type_from_predicate:
        raise ValueError("Could not determine model_type from the predicate ASTGroupNode for MongoDB queries.")

    primary_model_type: Type[OmmiModel] = model_type_from_predicate
    main_collection_name = get_collection_name(primary_model_type)
    
    pipeline: list[dict[str, Any]] = []
    sort_spec: list[tuple[str, int]] = []
    model_field_prefix_map: dict[Type[OmmiModel], str] = {primary_model_type: ""} # Primary model fields have no prefix initially

    # --- Join Logic ---
    conditions_to_parse_for_filter: list[ASTNode] = []
    models_encountered_in_conditions: set[Type[OmmiModel]] = {primary_model_type}
    
    # First pass: collect all conditions and identify all models involved
    # This simplistic pass assumes predicate.items are either ModelType or Condition
    temp_conditions_store = []
    for node in predicate.items:
        if isinstance(node, ASTReferenceNode) and node.field is None and node.model == primary_model_type:
            continue # Skip the primary model type if listed directly
        temp_conditions_store.append(node) # Store all other nodes (conditions, other models)

    # Recursive function to extract all comparison nodes and referenced models
    def extract_comparisons_and_models(items_list: list[ASTNode], current_models_set: set[Type[OmmiModel]], comparison_list: list[ASTComparisonNode | ASTGroupNode]):
        for item in items_list:
            if isinstance(item, ASTComparisonNode):
                comparison_list.append(item)
                if isinstance(item.left, ASTReferenceNode):
                    current_models_set.add(item.left.model)
            elif isinstance(item, ASTGroupNode):
                # Add the group itself for parsing, and recurse for models
                comparison_list.append(item) 
                extract_comparisons_and_models(item.items, current_models_set, comparison_list)
            # ASTReferenceNode for models are handled by _determine_model_type_from_ast_items for primary, others are joined below.

    extract_comparisons_and_models(temp_conditions_store, models_encountered_in_conditions, conditions_to_parse_for_filter)

    join_alias_counter = 0
    # Join models other than the primary model
    # This simplified join order might not be correct for complex chained joins (A-B-C)
    # It assumes all other models join directly to the primary_model_type for now.
    current_pipeline_base_model_for_join = primary_model_type
    current_base_model_prefix = ""

    for model_to_join in models_encountered_in_conditions:
        if model_to_join != primary_model_type and model_to_join not in model_field_prefix_map: # Avoid re-joining, join only if not primary
            join_stages, as_field = _create_join_stages(
                current_pipeline_base_model_for_join, # For now, always join from primary
                model_to_join,
                current_base_model_prefix, # Prefix of the current base for join
                str(join_alias_counter)
            )
            pipeline.extend(join_stages)
            model_field_prefix_map[model_to_join] = f"{as_field}."
            join_alias_counter += 1
            # For more complex scenarios, current_pipeline_base_model_for_join and current_base_model_prefix
            # would need to update based on the last joined model if chaining A->B->C.

    # --- Filter Parsing ---
    parsed_filter_conditions = []
    for node in conditions_to_parse_for_filter: # Parse collected conditions
        parsed_node = _parse_node(node, primary_model_type, model_field_prefix_map)
        if parsed_node: # _parse_node can return None for non-filter nodes
            parsed_filter_conditions.append(parsed_node)
    
    final_filter_query = {}
    if parsed_filter_conditions:
        if len(parsed_filter_conditions) == 1:
            final_filter_query = parsed_filter_conditions[0]
        else: 
            final_filter_query = {"$and": [cond for cond in parsed_filter_conditions if cond]} # Filter out potential Nones

    # Add $match stage if there are filters and a pipeline is being used (i.e., joins happened)
    if pipeline and final_filter_query:
        pipeline.append({"$match": final_filter_query})
    elif not pipeline and final_filter_query: # No joins, but filters exist
        pass # final_filter_query will be used directly
    elif pipeline and not final_filter_query: # Joins, but no filters (e.g. fetch all B joined with A)
        pass
    # else: no pipeline, no filters - query is empty for filter part.

    # --- Sorting, Skip, Limit ---
    limit_val: int | None = None
    if hasattr(predicate, 'max_results') and predicate.max_results > 0:
        limit_val = predicate.max_results

    skip_val: int | None = None
    if hasattr(predicate, 'results_page') and hasattr(predicate, 'max_results') and predicate.max_results > 0 and predicate.results_page > 0:
        skip_val = predicate.results_page * predicate.max_results
    elif hasattr(predicate, 'offset_val'):
        skip_val = predicate.offset_val 

    if hasattr(predicate, 'sorting') and predicate.sorting:
        for sort_ref_node in predicate.sorting:
            if isinstance(sort_ref_node, ASTReferenceNode):
                field_model_type = sort_ref_node.model
                queryable_descriptor_for_sort = sort_ref_node.field
                attr_name_str_for_sort = queryable_descriptor_for_sort.metadata.get("field_name")
                if not attr_name_str_for_sort:
                    raise ValueError(f"Could not determine field name for sorting: {queryable_descriptor_for_sort}")

                raw_db_field_name = get_model_field_name(field_model_type, attr_name_str_for_sort)
                prefix = model_field_prefix_map.get(field_model_type, "") # Use prefix if sorting on joined field
                sort_db_field_name = f"{prefix}{raw_db_field_name}" if prefix else raw_db_field_name
                
                sort_order = 1 if sort_ref_node.ordering == ResultOrdering.ASCENDING else -1
                sort_spec.append((sort_db_field_name, sort_order))

    if pipeline: 
        if sort_spec: pipeline.append({"$sort": dict(sort_spec)})
        if skip_val is not None: pipeline.append({"$skip": skip_val})
        if limit_val is not None: pipeline.append({"$limit": limit_val})
        
        return MongoDBQueryParts(
            filter={}, 
            pipeline=pipeline, 
            sort=None, 
            limit=None, 
            skip=None, 
            target_collection_name=main_collection_name
        )
    else: 
        return MongoDBQueryParts(
            filter=final_filter_query,
            sort=sort_spec if sort_spec else None,
            limit=limit_val,
            skip=skip_val,
            target_collection_name=main_collection_name
        )


# TODO:
# - Composite Keys: How are they represented in AST and translated?
#   MongoDB naturally handles composite _id if it's a document. For query, it's matching multiple fields.
#   If Key metadata defines multiple fields as PK, queries for PK need to use all those fields.
# - ReferenceTo across composite keys: $lookup localField/foreignField might need to be arrays.
# - More complex $not scenarios.
# - Robust field name qualification in aggregation pipelines for filters and sorts across multiple joins.
# - Subqueries / $graphLookup for more complex relationships if needed.
# - Handling of Association Tables (many-to-many): This typically requires multiple $lookup stages or specific pipeline logic.
#   e.g., A -> AssociationTable -> B.
#   1. $lookup AssociationTable from A.
#   2. $unwind.
#   3. $lookup B from AssociationTable.
#   4. $unwind.
#   5. Potentially $group to reconstruct A with a list of B's.

# The following code block is added based on the new implementation

# The following code block is added based on the new implementation 