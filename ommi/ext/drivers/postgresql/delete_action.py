from typing import Type

import psycopg

from ommi.drivers.database_results import async_result
from ommi.drivers.delete_actions import DeleteAction
from ommi.ext.drivers.postgresql.connection_protocol import PostgreSQLConnection
from ommi.ext.drivers.postgresql.utils import build_query, create_join_comparison
from ommi.models import OmmiModel
from ommi.query_ast import when, ASTGroupNode


class PostgreSQLDeleteAction(DeleteAction[PostgreSQLConnection, OmmiModel]):
    @async_result
    async def delete(self) -> bool:
        ast = when(*self._predicates)
        session = self._connection.cursor()
        await self._delete(ast, session)
        return self

    async def _delete(
        self,
        ast: ASTGroupNode,
        session: psycopg.AsyncCursor,
    ):
        query = build_query(ast)
        query_builder = ["DELETE FROM", query.model.__ommi__.model_name]
        where = [query.where]
        if query.models:
            query_builder.append("USING")
            query_builder.append(
                ", ".join(model.__ommi__.model_name for model in query.models)
            )
            using_join = [
                " AND ".join(
                    f"({create_join_comparison(query.model, model)})"
                    for model in query.models
                )
            ]

            where = []
            if query.where:
                where.append(f"({query.where}) AND")

            where.extend(using_join)

        query_builder.append("WHERE")
        query_builder.extend(where)
        await session.execute(f"{' '.join(query_builder)};".encode(), query.values)
