from collections.abc import Callable

from tramp.async_batch_iterator import AsyncBatchIterator
from typing import Awaitable, Iterable, Type, TYPE_CHECKING

from ommi.ext.drivers.sqlite.utils import build_query, generate_joins, map_to_model, SelectQuery
from ommi.query_ast import ASTGroupNode, ResultOrdering

if TYPE_CHECKING:
    from ommi.ext.drivers.sqlite.shared_types import Cursor, SQLQuery, SQLStatement
    from ommi.shared_types import DBModel


BATCH_SIZE = 100


def fetch_models(cursor: "Cursor", predicate: "ASTGroupNode") -> "AsyncBatchIterator[DBModel]":
    return AsyncBatchIterator(_create_fetch_query_batcher(cursor, predicate))


def _create_fetch_query_batcher(
    cursor: "Cursor", predicate: "ASTGroupNode",
) -> "Callable[[int], Awaitable[Iterable[DBModel]]]":
    async def fetch_query_batcher(batch_index: int) -> "Iterable[DBModel]":
        (sql, params), model = _generate_select_sql(predicate, batch_index, BATCH_SIZE)
        cursor.execute(sql, params)
        return (map_to_model(row, model) for row in cursor.fetchall())

    return fetch_query_batcher


def _generate_select_sql(
    predicate: "ASTGroupNode",
    batch_index: int,
    batch_size: int
) -> "tuple[SQLQuery, Type[DBModel]]":
    query = build_query(predicate)
    query_str = _build_select_query(query)
    return (query_str, query.values), query.model


def _build_select_query(query: SelectQuery) -> "SQLStatement":
    query_builder = [f"SELECT * FROM {query.model.__ommi__.model_name}"]
    if query.models:
        query_builder.extend(generate_joins(query.model, query.models))

    if query.where:
        query_builder.append(f"WHERE {query.where}")

    if query.limit > 0:
        query_builder.append(f"LIMIT {query.limit}")

        if query.offset > 0:
            query_builder.append(f"OFFSET {query.offset}")

    if query.order_by:
        ordering = ", ".join(
            f"{column} {'ASC' if ordering is ResultOrdering.ASCENDING else 'DESC'}"
            for column, ordering in query.order_by.items()
        )
        query_builder.append("ORDER BY")
        query_builder.append(ordering)

    return " ".join(query_builder) + ";"
