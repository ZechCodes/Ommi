from typing import TypeAlias, Type

import psycopg

from ommi.drivers.count_actions import CountAction
from ommi.drivers.database_results import async_result
from ommi.drivers.driver_types import TModel
from ommi.ext.drivers.postgresql.connection_protocol import PostgreSQLConnection
from ommi.models import OmmiModel
from ommi.query_ast import when, ASTGroupNode, ResultOrdering
from ommi.ext.drivers.postgresql.utils import build_query, SelectQuery, generate_joins

Predicate: TypeAlias = ASTGroupNode | Type[TModel] | bool


class PostgreSQLCountAction(CountAction[PostgreSQLConnection, OmmiModel]):
    @async_result
    async def count(self) -> int:
        ast = when(*self._predicates)
        session = self._connection.cursor()
        return await self._count(ast, session)

    async def _count(self, predicates: ASTGroupNode, session: psycopg.AsyncCursor):
        query = build_query(predicates)
        query_str = self._build_count_query(query)
        result = await (
            await session.execute(query_str.encode(), query.values)
        ).fetchone()
        return result[0]

    def _build_count_query(self, query: SelectQuery):
        query_builder = [f"SELECT Count(*) FROM {query.model.__ommi__.model_name}"]
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
