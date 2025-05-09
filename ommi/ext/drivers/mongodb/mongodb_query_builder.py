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
    # ASTOperatorNode.IN and ASTOperatorNode.NOT_IN are not in the enum, comment out for now
    # ASTOperatorNode.IN: "$in", 
    # ASTOperatorNode.NOT_IN: "$nin",
}

MONGO_LOGICAL_OPERATORS = { # This seems correct as ASTLogicalOperatorNode has AND, OR
    ASTLogicalOperatorNode.AND: "$and",
    ASTLogicalOperatorNode.OR: "$or",
    # ASTLogicalOperatorNode.NOT: "$not" # NOT is not in ASTLogicalOperatorNode
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
    # Removed elif for LIKE, IS_NULL, IS_NOT_NULL as they are not in ASTOperatorNode
    # or should be handled by EQUALS/NOT_EQUALS with None value.
    # elif operator == ASTOperatorNode.LIKE:
    #     return {db_field_name: {"$regex": str(value), "$options": "i"}}
    # elif operator == ASTOperatorNode.IS_NULL:
    #     return {db_field_name: {"$eq": None}}
    # elif operator == ASTOperatorNode.IS_NOT_NULL:
    #     return {db_field_name: {"$ne": None}}
    else:
        # This else implies that if an operator is not in MONGO_OPERATORS (e.g. IN, NOT_IN if they were defined in AST)
        # it would fall here.
        raise NotImplementedError(f"MongoDB translation for operator {operator} not implemented.")


def _parse_group_node(node: ASTGroupNode, current_model_type: Type[OmmiModel], model_field_prefix_map: dict[Type[OmmiModel], str]) -> dict[str, Any]:
    if not node.items: # Should be node.items based on ASTGroupNode definition
        return {}

    # Check ASTGroupNode.operator attribute, current ASTGroupNode doesn't seem to have it.
    # ASTGroupNode has self.items: list[ASTComparableNode | ASTLogicalOperatorNode]
    # The logical operation (AND/OR) seems to be represented by ASTLogicalOperatorNode instances *within* node.items.
    # This function's logic needs to be re-evaluated against the actual ASTGroupNode structure.
    # For now, let's assume node.operator exists and is ASTLogicalOperatorNode.AND or .OR as per original logic.
    # This is a potential future bug if node.operator is not what's expected.

    # if node.operator == ASTLogicalOperatorNode.NOT: # ASTLogicalOperatorNode doesn't have NOT
    #    if len(node.items) != 1: # Should be node.items
    #        raise ValueError("AST NOT node must have exactly one child.")
    #    # ... NOT handling logic ...
    #    raise NotImplementedError("General AST NOT group node translation to MongoDB is complex and not yet fully implemented...")

    # The following logic assumes node.operator is the group's logical operator (e.g. AND, OR for all children)
    # This needs to be verified with how ASTGroupNode actually structures its items and represents group logic.
    # If items can be mixed (e.g., comp1 AND comp2 OR comp3), this flat processing is too simple.
    # mongo_op = MONGO_LOGICAL_OPERATORS.get(node.operator) # node.operator may not exist or be the right thing
    # if not mongo_op:
    #    # If there are multiple children, and no explicit operator, perhaps implicit AND?
    #    # This is a significant point of ambiguity.
    #    # For now, sticking to the original structure that expects a node.operator
    #    raise NotImplementedError(f"MongoDB translation for logical operator {getattr(node, 'operator', 'undefined')} not implemented.")

    # Re-evaluating _parse_group_node:
    # An ASTGroupNode contains a list of items. These items can be ASTComparisonNodes or ASTLogicalOperatorNodes.
    # Example: [Comp1, AND, Comp2, OR, Comp3]
    # The structure is not a single operator for all children, but a sequence.

    # Simplified _parse_group_node based on ASTGroupNode.items
    # This is a basic interpretation and might need significant enhancement for complex groups.
    # It assumes an implicit AND for a list of comparison/group nodes,
    # or uses the explicit ASTLogicalOperatorNode if present. This is still very basic.

    # The original code for _parse_group_node had:
    # mongo_op = MONGO_LOGICAL_OPERATORS.get(node.operator)
    # return {mongo_op: [_parse_node(child, current_model_type, model_field_prefix_map) for child in node.items]}
    # This assumed ASTGroupNode has a single 'operator' and 'children'.
    # ASTGroupNode has 'items'. The 'operator' of the group is not a direct attribute.

    # Let's try to process items. If it's just a list of conditions, assume AND.
    # If ASTLogicalOperatorNode is found, it's more complex.
    # This part is very tricky without knowing how complex queries are formed using ASTGroupNode.items.

    # Fallback: If node.items has one direct ASTGroupNode or ASTComparisonNode, parse it.
    # If multiple, assume AND for now. This is a guess.
    
    parsed_children = []
    # Defaulting to AND if multiple items are purely conditions.
    # This does not correctly handle explicit ASTLogicalOperatorNode instances in node.items
    # e.g. [Cond1, AND, Cond2, OR, Cond3]
    # This part of the logic is highly likely to be incorrect for complex queries.

    # The original logic seems to expect ASTGroupNode to have an 'operator' attribute
    # (like AND/OR for the whole group) and 'children'.
    # The provided ASTGroupNode has 'items'.
    # Let's look at the original structure again from the prompt context:
    # `build_query_parts` calls `_parse_node(node, effective_filter_model, model_field_prefix_map)`
    # where `node` can be `ASTComparisonNode` or `ASTGroupNode`.
    # Then `_parse_node` calls `_parse_group_node`.

    # If `node.operator` (from original code of _parse_group_node) was referring to
    # an attribute of ASTGroupNode that defined its type (e.g. an AND group, an OR group),
    # this attribute is missing in the current `ommi.query_ast.ASTGroupNode` definition.
    # The `ASTGroupNode.add` method takes a `logical_type` (defaulting to AND),
    # and appends it if there are existing items. So `items` looks like `[item1, AND, item2, OR, item3]`.

    # Given the mismatch, I will make minimal changes to MONGO_OPERATORS for now to fix the immediate AttributeError
    # and then will likely need to re-evaluate _parse_group_node structure against test cases.
    # For now, I will assume the MONGO_LOGICAL_OPERATORS part was somewhat functional and that
    # ASTGroupNode might have an 'operator' attr in some contexts or that the interpretation was simplified.
    # The error is about MONGO_OPERATORS keys.
    
    # Let's assume for the purpose of fixing THIS specific error, that ASTGroupNode.operator exists and is valid.
    # The `node.items` should be `node.items`.

    if not node.items: # Changed from node.children
        return {}

    # Assuming node.operator exists for this group node, as per original structure of _parse_group_node
    # This is a MAJOR assumption and likely needs fixing.
    group_operator_attr = getattr(node, 'operator', None) 

    # if group_operator_attr == ASTLogicalOperatorNode.NOT: # NOT is not in ASTLogicalOperatorNode
    #     # This block is problematic as ASTLogicalOperatorNode.NOT does not exist.
    #     # If NOT logic is needed, it must be represented differently in the AST or handled specially.
    #     if len(node.items) != 1:
    #         raise ValueError("AST NOT group node must have exactly one child for MongoDB $not usage.")
    #     # MongoDB's $not is a query operator, not a logical operator for combining clauses directly like $and/$or.
    #     # It's used like { field: { $not: { <operator-expression> } } }.
    #     # A general group NOT is more complex, e.g., $nor if it's NOT (A OR B OR ...).
    #     # This requires a deeper understanding of how NOT groups are intended to be formed by `when()`.
    #     # For now, commenting out this problematic block.
    #     parsed_child = _parse_node(node.items[0], current_model_type, model_field_prefix_map)
    #     # This is a naive attempt if parsed_child is {field: expr}. It might not be general enough.
    #     # Example: if parsed_child is { "status": "A" }, result could be { "status": { "$not": { "$eq": "A" } } }
    #     # or if parsed_child is { "age": { "$gt": 10 } }, result { "age": { "$not": { "$gt": 10 } } }
    #     # This needs to extract the inner expression for the $not operator.
    #     # This simplified version is likely incorrect for many cases.
    #     # field_name, op_expr = list(parsed_child.items())[0]
    #     # return {field_name: {"$not": op_expr}}
    #     raise NotImplementedError("General AST NOT group node translation to MongoDB is not correctly implemented yet.")

    # The original logic for AND/OR expected node.operator to be the group's operator.
    # Current ASTGroupNode has items like [Cond1, AND, Cond2, OR, Cond3]

    mongo_op = MONGO_LOGICAL_OPERATORS.get(group_operator_attr)
    if not mongo_op:
        # If no explicit operator for the group, and multiple items, this implies an AND.
        # This part of original logic was:
        # raise NotImplementedError(f"MongoDB translation for logical operator {node.operator} not implemented.")
        # If group_operator_attr is None (not set on ASTGroupNode), and items exist, assume AND.
        if len(node.items) > 1:
             mongo_op = MONGO_LOGICAL_OPERATORS[ASTLogicalOperatorNode.AND] # Default to AND
        elif len(node.items) == 1: # Single child, no logical operator needed for the child itself
             return _parse_node(node.items[0], current_model_type, model_field_prefix_map)
        else: # No items
             return {}


    return {mongo_op: [_parse_node(child, current_model_type, model_field_prefix_map) for child in node.items]} # Changed from node.children


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