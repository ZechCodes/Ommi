from typing import TYPE_CHECKING

from ommi.ext.drivers.postgresql.utils import build_query, _create_pg_join

if TYPE_CHECKING:
    from psycopg import AsyncCursor 
    from ommi.query_ast import ASTGroupNode

async def delete_models(cursor: "AsyncCursor", predicate: "ASTGroupNode"):
    """Deletes models from the database based on the predicate."""
    # TODO: This implementation currently does not support joined deletes.
    # This will need to be addressed to pass all tests, specifically those
    # involving deletes with conditions on related models (e.g., test_join_deletes).

    query_info = build_query(predicate)

    if not query_info.model:
        raise ValueError("Cannot delete without a primary model in the predicate.")

    target_table_name = query_info.model.__ommi__.model_name
    
    sql_parts = [f"DELETE FROM {target_table_name}"]
    
    # Store original where parts from AST, these are the filter conditions
    filter_where_parts = list(query_info.where_parts)
    filter_where_values = list(query_info.values) # These are the parameters for the filter conditions

    effective_where_parts = list(filter_where_parts)
    # Parameters for the final query will be built based on effective_where_values for now.
    # Join conditions from _create_pg_join are not parameterized in the same way.
    final_params = list(filter_where_values)

    if query_info.models: # If other models are involved (potential join scenario)
        using_parts = []
        join_conditions_for_where = []

        for other_model in query_info.models:
            if other_model != query_info.model:
                using_parts.append(other_model.__ommi__.model_name)
                try:
                    join_on_clause = _create_pg_join(query_info.model, other_model)
                    on_conditions = join_on_clause.split(" ON ", 1)[1]
                    join_conditions_for_where.append(f"({on_conditions})")
                except ValueError as e:
                    print(f"Warning: Could not generate join condition for DELETE with {other_model.__ommi__.model_name}: {e}")
        
        if using_parts:
            using_statement = ", ".join(using_parts)
            sql_parts.append(f"USING {using_statement}")
            
            if join_conditions_for_where:
                effective_where_parts = join_conditions_for_where + (["AND"] if filter_where_parts else []) + filter_where_parts

    if effective_where_parts:
        final_where_clause = " ".join(effective_where_parts)
        sql_parts.append(f"WHERE {final_where_clause}")
        # final_params will already contain filter_where_values. 
        # Join conditions from _create_pg_join are direct column comparisons and don't add to final_params here.
    elif not query_info.models: 
        pass # Allow deleting all from a single table if no WHERE was specified
    else: # Joined delete without any WHERE conditions
        raise ValueError("Joined DELETE without any WHERE conditions is not allowed.")

    final_sql = " ".join(sql_parts) + ";"
    
    # print(f"Delete SQL: {final_sql}") # For debugging
    # print(f"Delete Params: {final_params}") # For debugging

    await cursor.execute(final_sql, tuple(final_params))
    # DELETE statements also don't typically return rows unless RETURNING is used.
    # The current driver interface for delete doesn't expect anything back. 