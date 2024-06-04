import sqlite3

from ommi.drivers.database_results import async_result
from ommi.drivers.delete_actions import DeleteAction
from ommi.ext.drivers.sqlite.connection_protocol import SQLiteConnection
from ommi.ext.drivers.sqlite.utils import build_query, build_subquery
from ommi.models import OmmiModel
from ommi.query_ast import when, ASTGroupNode


class SQLiteDeleteAction(DeleteAction[SQLiteConnection, OmmiModel]):
    @async_result
    async def delete(self) -> bool:
        ast = when(*self._predicates)
        session = self._connection.cursor()
        self._delete(ast, session)
        return True

    def _delete(
        self,
        ast: ASTGroupNode,
        session: sqlite3.Cursor,
    ):
        query = build_query(ast)
        query_builder = ["DELETE FROM", query.model.__ommi__.model_name]
        if query.models:
            pks = ", ".join(
                f"{query.model.__ommi__.model_name}.{pk.get('store_as')}"
                for pk in query.model.get_primary_key_fields()
            )
            sub_query = build_subquery(query.model, query.models, query.where)
            query_builder.append(f"WHERE ({pks}) IN ({sub_query})")

        else:
            query_builder.append("WHERE")
            query_builder.append(query.where)

        session.execute(f"{' '.join(query_builder)};", query.values)
