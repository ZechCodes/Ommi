from collections.abc import Callable

from tramp.async_batch_iterator import AsyncBatchIterator
from typing import Awaitable, Iterable, overload, Type, TYPE_CHECKING

from ommi.ext.drivers.sqlite.utils import build_query, generate_joins, map_to_model, SelectQuery
from ommi.query_ast import ASTGroupNode, ResultOrdering

if TYPE_CHECKING:
    from ommi.ext.drivers.sqlite.shared_types import Cursor, SQLQuery, SQLStatement
    from ommi.shared_types import DBModel


BATCH_SIZE = 100


def fetch_models(cursor: "Cursor", predicate: "ASTGroupNode") -> "AsyncBatchIterator[DBModel]":
    return AsyncBatchIterator(_create_fetch_query_batcher(cursor, predicate))


async def count_models(cursor: "Cursor", predicate: "ASTGroupNode") -> "int":
    (sql, params), model = _generate_select_sql(predicate, count=True)
    cursor.execute(sql, params)
    return cursor.fetchone()[0]


def _create_fetch_query_batcher(
    cursor: "Cursor", predicate: "ASTGroupNode",
) -> "Callable[[int], Awaitable[Iterable[DBModel]]]":
    async def fetch_query_batcher(batch_index: int) -> "Iterable[DBModel]":
        (sql, params), model = _generate_select_sql(predicate, batch_index, BATCH_SIZE)
        cursor.execute(sql, params)
        return (map_to_model(row, model) for row in cursor.fetchall())

    return fetch_query_batcher

@overload
def _generate_select_sql(
    predicate: "ASTGroupNode",
    batch_index: int,
    batch_size: int,
) -> "tuple[SQLQuery, Type[DBModel]]":
    ...


@overload
def _generate_select_sql(
    predicate: "ASTGroupNode",
    *,
    count: bool,
) -> "tuple[SQLQuery, Type[DBModel]]":
    ...


def _generate_select_sql(
    predicate: "ASTGroupNode",
    batch_index: int = 0,
    batch_size: int = -1,
    *,
    count: bool = False,
) -> "tuple[SQLQuery, Type[DBModel]]":
    query = build_query(predicate)
    if not count and batch_size > 0:
        query.offset = batch_index * batch_size
        if 0 < query.limit < query.offset + batch_size:
            query.limit = query.limit - query.offset
        else:
            query.limit = batch_size

    query_str = _build_select_query(query, count=count)
    return (query_str, query.values), query.model


def _build_select_query(query: SelectQuery, *, count: bool = False) -> "SQLStatement":
    columns = "Count(*)" if count else "*"
    query_builder = [f"SELECT {columns} FROM {query.model.__ommi__.model_name}"]
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
