from dataclasses import dataclass, field as dc_field
from typing import Type, Any, TYPE_CHECKING, List, Dict, Iterator

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
    ASTNode,
)

if TYPE_CHECKING:
    from ommi.shared_types import DBModel
    from ommi.models.field_metadata import FieldMetadata


# Operator mappings for PostgreSQL
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
    model: "Type[DBModel] | None" = None
    models: "List[Type[DBModel]]" = dc_field(default_factory=list) # For joins
    offset: int = 0
    order_by: "Dict[str, ResultOrdering]" = dc_field(default_factory=dict)
    values: "List[Any]" = dc_field(default_factory=list) # Parameters for the query
    where_parts: "List[str]" = dc_field(default_factory=list) # Parts of the WHERE clause
    columns: str = "*" # Columns to select, defaults to all

    def add_model(self, *models: "Type[DBModel]"):
        if not self.model:
            self.model, *models = models
        
        if models:
            self.models.extend(
                m for m in models if m not in self.models and m != self.model
            )

    @property
    def where_clause(self) -> str:
        return " ".join(self.where_parts)


def map_to_model(row_data: tuple, model_type: "Type[DBModel]") -> "DBModel":
    """Maps a database row (tuple) to a model instance."""
    field_metas: List["FieldMetadata"] = list(model_type.__ommi__.fields.values())
    
    # Assuming order of fields in SELECT * matches order in __ommi__.fields
    # This is a simplification. A more robust solution would fetch column names
    # from cursor.description and map them.
    if len(row_data) != len(field_metas):
        # This could happen if SELECT * is not used, or if model definition mismatches table
        raise ValueError(
            f"Row data length ({len(row_data)}) does not match number of fields for model {model_type.__name__} ({len(field_metas)})."
        )

    instance_kwargs = {}
    for i, field_meta in enumerate(field_metas):
        python_field_name = field_meta.get("field_name")
        instance_kwargs[python_field_name] = row_data[i]
        
    return model_type(**instance_kwargs)


def _process_ordering(sorting_nodes: List[ASTNode]) -> Dict[str, ResultOrdering]:
    ordering_dict = {}
    field_name = None
    for node in sorting_nodes:
        if isinstance(node, ASTReferenceNode):
            # Assuming field name for ordering is simple, e.g., "id"
            # SQLite version uses model_name.field_name, which is more robust for joins
            field_name = node.field.metadata.get("store_as") 
        elif isinstance(node, ASTLiteralNode) and isinstance(node.value, ResultOrdering):
            if field_name:
                ordering_dict[field_name] = node.value
                field_name = None # Reset for next pair
            else:
                # This case should ideally not happen if AST is well-formed
                pass 
    return ordering_dict


def build_query(ast: ASTGroupNode) -> SelectQuery:
    query = SelectQuery(
        limit=ast.max_results,
        offset=ast.results_page * ast.max_results if ast.max_results > 0 and ast.results_page > 0 else 0,
        order_by=_process_ordering(ast.sorting or []),\
    )
    
    # Ensure iterables are converted to lists for the stack
    node_stack: List[List[ASTNode]] = [list(ast)] # Convert generator from iter(ast) to list

    while node_stack:
        current_level_nodes = node_stack[-1]
        
        if not current_level_nodes:
            node_stack.pop()
            continue

        node = current_level_nodes.pop(0)

        if isinstance(node, ASTGroupNode):
            # Do NOT add explicit "(" here. Rely on ASTGroupFlagNode.OPEN from node.__iter__().
            # If the group node itself needs to be processed, that logic can go here.
            node_stack.append(list(node)) # Convert generator from iter(node) to list

        elif isinstance(node, ASTReferenceNode):
            if node.field is None: # e.g. when(MyModel)
                query.add_model(node.model)
            else: # e.g. when(MyModel.field == ...)
                query.where_parts.append(f'{node.model.__ommi__.model_name}.{node.field.metadata.get("store_as")}')
                query.add_model(node.model)

        elif isinstance(node, ASTLiteralNode):
            query.where_parts.append("%s")
            query.values.append(node.value)

        elif isinstance(node, ASTLogicalOperatorNode):
            query.where_parts.append(logical_operator_mapping[node])

        elif isinstance(node, ASTOperatorNode):
            query.where_parts.append(operator_mapping[node])
        
        elif isinstance(node, ASTComparisonNode):
            # Process in order: left, operator, right.
            # Prepend to the current level's node list in reverse order 
            # so they are popped and processed in the correct order.
            current_level_nodes.insert(0, node.right) # node.right is ASTLiteralNode or ASTReferenceNode
            current_level_nodes.insert(0, node.operator) # node.operator is ASTOperatorNode
            current_level_nodes.insert(0, node.left) # node.left is ASTReferenceNode

        elif node == ASTGroupFlagNode.OPEN:
            # it might indicate a sub-expression starting without a logical join, which might be an implicit AND.
            # However, for now, just ensure we add the parenthesis.
            # Only add if it's a real group start, not from an ASTComparisonNode's internal group.
            query.where_parts.append("(")

        elif node == ASTGroupFlagNode.CLOSE:
            if query.where_parts and query.where_parts[-1] == "(":
                query.where_parts.pop()
            else:
                # Ensure there's a corresponding open paren or the where_parts isn't empty
                # to prevent adding a lone ')'
                if any(p == '(' for p in query.where_parts): # Basic check
                    query.where_parts.append(")")
        
        else:
            # Should not happen with a well-formed AST
            pass

    # Final cleanup: remove any trailing logical operators
    if query.where_parts and query.where_parts[-1] in list(logical_operator_mapping.values()):
        query.where_parts.pop()
        
    # Ensure parentheses are balanced - this is a very basic check and might need improvement
    open_paren_count = query.where_parts.count("(")
    close_paren_count = query.where_parts.count(")")
    while open_paren_count > close_paren_count:
        query.where_parts.append(")")
        close_paren_count += 1
    while close_paren_count > open_paren_count: # Should not happen if logic is correct
        # This case indicates a flaw, perhaps remove last ')' or find unmatched '('
        if query.where_parts and query.where_parts[-1] == ")":
            query.where_parts.pop()
        close_paren_count -=1


    # Remove empty parentheses "()" that might result from processing empty groups
    final_where_parts = []
    i = 0
    while i < len(query.where_parts):
        part = query.where_parts[i]
        if part == "(" and i + 1 < len(query.where_parts) and query.where_parts[i+1] == ")":
            i += 2 # Skip both "(" and ")"
        else:
            final_where_parts.append(part)
            i += 1
    query.where_parts = final_where_parts
    
    return query


def _create_pg_join(main_model: "Type[DBModel]", join_model: "Type[DBModel]") -> str:
    """Creates a single JOIN clause for PostgreSQL.
    Assumes relationships are defined via ReferenceTo and stored in __ommi__.references.
    """
    # Check if join_model references main_model
    if main_model in join_model.__ommi__.references:
        conditions = []
        for ref in join_model.__ommi__.references[main_model]:
            # ref.from_field is in join_model, ref.to_field is in main_model
            main_model_name = main_model.__ommi__.model_name
            join_model_name = join_model.__ommi__.model_name
            from_col = ref.from_field.get("store_as")
            to_col = ref.to_field.get("store_as")
            conditions.append(f"{join_model_name}.\"{from_col}\" = {main_model_name}.\"{to_col}\"")
        join_conditions = " AND ".join(conditions)
        return f"JOIN {join_model.__ommi__.model_name} ON {join_conditions}"
    # Check if main_model references join_model
    elif join_model in main_model.__ommi__.references:
        conditions = []
        for ref in main_model.__ommi__.references[join_model]:
            # ref.from_field is in main_model, ref.to_field is in join_model
            main_model_name = main_model.__ommi__.model_name
            join_model_name = join_model.__ommi__.model_name
            from_col = ref.from_field.get("store_as")
            to_col = ref.to_field.get("store_as")
            conditions.append(f"{main_model_name}.\"{from_col}\" = {join_model_name}.\"{to_col}\"")
        join_conditions = " AND ".join(conditions)
        return f"JOIN {join_model.__ommi__.model_name} ON {join_conditions}"
    else:
        # This case implies no direct ReferenceTo between main_model and join_model found in __ommi__.references.
        # This could be due to an indirect join (via a third table) or a misconfiguration.
        # For now, raise an error or return a specific type of join that might indicate an issue.
        # Or, if the query AST implies a cross join or a differently structured join, that would need specific handling.
        # A simple INNER JOIN without ON might be too broad or incorrect.
        # Let's assume for now that if they are in query.models, a relationship should exist.
        raise ValueError(f"Could not determine join condition between {main_model.__ommi__.model_name} and {join_model.__ommi__.model_name}. No direct reference found.")


def generate_joins(main_model: "Type[DBModel]", join_models: "List[Type[DBModel]]") -> List[str]:
    """
    Generates SQL JOIN clauses for PostgreSQL.
    Iterates through models that need to be joined with the main_model.
    """
    join_clauses = []
    if not main_model: # Should not happen if build_query sets query.model correctly
        return join_clauses 
        
    for jm in join_models:
        if jm != main_model: # Don't try to join a model with itself in this basic logic
            try:
                join_clauses.append(_create_pg_join(main_model, jm))
            except ValueError as e:
                # If _create_pg_join raises a ValueError (e.g., no direct reference found for a join),
                # that specific join clause is omitted. This could lead to UndefinedTable errors later
                # if the query structure relies on this join.
                # The ValueError from _create_pg_join contains details about the problematic models.
                pass 
    return join_clauses
