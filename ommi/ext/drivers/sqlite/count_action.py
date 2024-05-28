import sqlite3
from typing import TypeAlias, Type

from ommi.drivers.count_actions import CountAction
from ommi.drivers.database_results import async_result
from ommi.drivers.driver_types import TModel
from ommi.ext.drivers.sqlite.connection_protocol import SQLiteConnection
from ommi.models import OmmiModel
from ommi.query_ast import when, ASTGroupNode
from ommi.ext.drivers.sqlite.utils import build_query, SelectQuery

Predicate: TypeAlias = ASTGroupNode | Type[TModel] | bool


class SQLiteCountAction(CountAction[SQLiteConnection, OmmiModel]):
    @async_result
    async def count(self) -> int:
        ast = when(*self._predicates)
        session = self._connection.cursor()
        return self._count(ast, session)

    def _count(self, predicates: ASTGroupNode, session: sqlite3.Cursor):
        query = build_query(predicates)
        query_str = self._build_count_query(query)
        session.execute(query_str, query.values)
        result = session.fetchone()
        return result[0]

    def _build_count_query(self, query: SelectQuery):
        query_builder = [
            f"SELECT Count(*) FROM {query.model.__ommi_metadata__.model_name}"
        ]
        if query.where:
            query_builder.append(f"WHERE {query.where}")

        if query.limit > 0:
            query_builder.append(f"LIMIT {query.limit}")

            if query.offset > 0:
                query_builder.append(f"OFFSET {query.offset}")

        return " ".join(query_builder) + ";"
