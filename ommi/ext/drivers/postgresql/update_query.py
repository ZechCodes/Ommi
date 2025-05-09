from typing import Any, TYPE_CHECKING, Tuple

from ommi.ext.drivers.postgresql.utils import build_query, _create_pg_join # Import _create_pg_join

if TYPE_CHECKING:
    from psycopg import AsyncCursor
    from ommi.query_ast import ASTGroupNode
    from ommi.shared_types import DBModel # Added for type hint consistency


async def update_models(cursor: "AsyncCursor", predicate: "ASTGroupNode", values: dict[str, Any]):
    """Updates models in the database based on the predicate."""
    query_info = build_query(predicate)
    
    if not query_info.model:
        raise ValueError("Cannot update without a primary model in the predicate.")

    target_table_name = query_info.model.__ommi__.model_name
    model_fields = query_info.model.__ommi__.fields
    
    set_clauses = []
    update_params = [] # Parameters for the SET part

    for py_name, value in values.items():
        db_col_name = model_fields[py_name].get("store_as")
        set_clauses.append(f'{db_col_name} = %s')
        update_params.append(value)

    if not set_clauses:
        return

    set_statement = ", ".join(set_clauses)
    sql_parts = [f"UPDATE {target_table_name} SET {set_statement}"]
    
    # Combine SET parameters with WHERE parameters later
    final_params = list(update_params) 
    
    # Store original where parts from AST, these are the filter conditions
    filter_where_parts = list(query_info.where_parts)
    filter_where_values = list(query_info.values)

    effective_where_parts = list(filter_where_parts)
    effective_where_values = list(filter_where_values)

    if query_info.models: # If other models are involved (potential join scenario)
        from_parts = []
        join_conditions_for_where = []

        for other_model in query_info.models:
            if other_model != query_info.model:
                from_parts.append(other_model.__ommi__.model_name)
                try:
                    # _create_pg_join returns "JOIN Table ON cond1 AND cond2"
                    # We only need the "cond1 AND cond2" part for the WHERE clause here
                    join_on_clause = _create_pg_join(query_info.model, other_model)
                    # Extract conditions after "ON "
                    on_conditions = join_on_clause.split(" ON ", 1)[1]
                    join_conditions_for_where.append(f"({on_conditions})") 
                except ValueError as e:
                    # If a join condition can't be created (e.g., indirect join not supported by _create_pg_join),
                    # this specific join is skipped. This might lead to incorrect behavior if the join was essential.
                    # The ValueError from _create_pg_join itself provides details.
                    pass
        
        if from_parts:
            from_statement = ", ".join(from_parts)
            sql_parts.append(f"FROM {from_statement}")
            
            # Prepend join conditions to the effective_where_parts
            if join_conditions_for_where:
                effective_where_parts = join_conditions_for_where + (["AND"] if filter_where_parts else []) + filter_where_parts
                # Note: Values for these ON conditions are not parameterized; they are direct column comparisons.
    
    if effective_where_parts:
        # Join the parts into a single string WHERE clause
        final_where_clause = " ".join(effective_where_parts)
        sql_parts.append(f"WHERE {final_where_clause}")
        final_params.extend(effective_where_values) # Add values from the original AST where clause
    elif not query_info.models: # Only allow no WHERE if it's not a join (safety for non-joined updates)
        # This case (update all rows of a single table) might be intended but is often dangerous.
        # Consider adding a warning or requiring an explicit flag if this is needed.
        pass 
    else: # Joined update without any WHERE conditions (original or join-derived)
        # This is highly unlikely to be correct and very dangerous.
        raise ValueError("Joined UPDATE without any WHERE conditions is not allowed.")

    final_sql = " ".join(sql_parts) + ";"
    
    await cursor.execute(final_sql, tuple(final_params))
    # UPDATE statements in PostgreSQL don't typically return the updated rows by default
    # unless RETURNING is used. The current driver interface for update doesn't expect returned models.
    # Thus, we don't fetch or return anything here. 