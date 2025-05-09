from collections.abc import Callable
from typing import Awaitable, Iterable, overload, Type, TYPE_CHECKING, List, Any
import dataclasses

from tramp.async_batch_iterator import AsyncBatchIterator

from ommi.query_ast import ASTGroupNode, ResultOrdering
# Assuming utils.py is in the same directory
from .utils import build_query, map_to_model, SelectQuery, generate_joins 

if TYPE_CHECKING:
    from psycopg import AsyncCursor # Use AsyncCursor from psycopg
    from ommi.shared_types import DBModel
    # Define SQLQuery for PostgreSQL, typically a tuple of (SQL_string, params_tuple_or_list)
    SQLQuery = tuple[str, List[Any] | tuple[Any, ...]] 
    SQLStatement = str


BATCH_SIZE = 100 # Standard batch size, can be configured if needed

def fetch_models(cursor: "AsyncCursor", predicate: "ASTGroupNode") -> "AsyncBatchIterator[DBModel]":
    """Fetches models from the database based on the predicate."""
    return AsyncBatchIterator(_create_fetch_query_batcher(cursor, predicate))


async def count_models(cursor: "AsyncCursor", predicate: "ASTGroupNode") -> int:
    """Counts models in the database based on the predicate."""
    # Build the query, but for counting
    select_query_obj = build_query(predicate)
    select_query_obj.columns = "COUNT(*)" # Override columns for COUNT
    
    # Generate SQL for counting (limit/offset don't apply to count(*))
    (sql, params), _ = _generate_select_sql(select_query_obj, count_mode=True)
    
    await cursor.execute(sql, params)
    result = await cursor.fetchone()
    return result[0] if result else 0


def _create_fetch_query_batcher(
    cursor: "AsyncCursor", predicate: "ASTGroupNode",
) -> "Callable[[int], Awaitable[Iterable[DBModel]]]":
    """Creates a batcher function for the AsyncBatchIterator."""
    # Build the initial query object from the AST predicate
    # This query object will be modified for each batch (limit/offset)
    base_select_query_obj = build_query(predicate)

    async def fetch_query_batcher(batch_index: int) -> "Iterable[DBModel]":
        # For each batch, clone/modify the base query for pagination
        current_batch_query = dataclasses.replace(base_select_query_obj)

        if current_batch_query.limit > 0 and BATCH_SIZE * batch_index >= current_batch_query.limit:
            # If we have a total limit and we've reached/exceeded it
            return ()
        
        # _generate_select_sql will handle setting limit and offset for the batch
        (sql, params), model_type = _generate_select_sql(
            current_batch_query, 
            batch_index=batch_index, 
            batch_size=BATCH_SIZE
        )
        
        if model_type is None:
            # This should not happen if predicate is valid and refers to a model
            raise ValueError("Model type could not be determined from the query predicate.")

        await cursor.execute(sql, params)
        db_rows = await cursor.fetchall()
        
        return (map_to_model(row, model_type) for row in db_rows)

    return fetch_query_batcher


@overload
def _generate_select_sql(
    query: "SelectQuery",
    batch_index: int,
    batch_size: int,
    count_mode: bool = False # Explicitly False for this overload
) -> "tuple[SQLQuery, Type[DBModel] | None]":
    ...


@overload
def _generate_select_sql(
    query: "SelectQuery",
    *,
    count_mode: bool = True # Explicitly True for this overload
) -> "tuple[SQLQuery, Type[DBModel] | None]":
    ...


def _generate_select_sql(
    query: "SelectQuery",
    batch_index: int = 0,
    batch_size: int = -1, # -1 means no batching / use query's own limit if any
    count_mode: bool = False,
) -> "tuple[SQLQuery, Type[DBModel] | None]":
    """Generates the SELECT SQL statement and parameters from a SelectQuery object."""
    
    final_query = dataclasses.replace(query) # Work on a copy

    if not count_mode and batch_size > 0:
        # Apply batching logic if not in count_mode and batch_size is specified
        limit_for_batch = batch_size
        offset_for_batch = batch_index * batch_size

        if final_query.limit > 0: # If original query has a limit
            if offset_for_batch >= final_query.limit:
                # This batch is beyond the original query's total limit
                limit_for_batch = 0 
            elif offset_for_batch + batch_size > final_query.limit:
                limit_for_batch = final_query.limit - offset_for_batch
        
        final_query.limit = limit_for_batch
        final_query.offset = offset_for_batch + query.offset # Add to original offset

    # Determine columns to select
    cols_to_select = final_query.columns
    if not count_mode and cols_to_select == "*" and final_query.model:
        primary_model_name = final_query.model.__ommi__.model_name
        primary_model_fields = final_query.model.__ommi__.fields.values()
        # Corrected f-string for column selection
        cols_to_select = ", ".join(
            f'{primary_model_name}."{field_meta.get("store_as")}"' 
            for field_meta in primary_model_fields
        )
        if not cols_to_select: 
            cols_to_select = "*" 

    # Start building the SQL query string
    query_builder = [f"SELECT {cols_to_select} FROM {final_query.model.__ommi__.model_name}"]

    # Add JOINs
    if final_query.model and final_query.models: 
        join_clauses = generate_joins(final_query.model, final_query.models)
        if join_clauses:
            query_builder.extend(join_clauses)

    # Add WHERE clause if present
    if final_query.where_clause:
        query_builder.append(f"WHERE {final_query.where_clause}")

    # Add ORDER BY clause if specified (not for COUNT(*))
    if not count_mode and final_query.order_by:
        ordering_parts = []
        for column_name, direction in final_query.order_by.items():
            direction_sql = "ASC" if direction == ResultOrdering.ASCENDING else "DESC"
            ordering_parts.append(f"{column_name} {direction_sql}")
        if ordering_parts:
            # Corrected f-string for ORDER BY clause
            query_builder.append(f"ORDER BY {', '.join(ordering_parts)}")

    # Add LIMIT and OFFSET (not for COUNT(*))
    if not count_mode:
        if final_query.limit > 0:
            query_builder.append(f"LIMIT {final_query.limit}")
        if final_query.offset > 0:
            query_builder.append(f"OFFSET {final_query.offset}")

    sql_statement = " ".join(query_builder) + ";"
    return (sql_statement, final_query.values), final_query.model 