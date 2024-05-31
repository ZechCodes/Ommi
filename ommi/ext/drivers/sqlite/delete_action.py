import sqlite3

from ommi.drivers.database_results import async_result
from ommi.drivers.delete_actions import DeleteAction
from ommi.ext.drivers.sqlite.connection_protocol import SQLiteConnection
from ommi.ext.drivers.sqlite.utils import build_query
from ommi.models import OmmiModel
from ommi.query_ast import search, ASTGroupNode


class SQLiteDeleteAction(DeleteAction[SQLiteConnection, OmmiModel]):
    @async_result
    async def delete(self) -> bool:
        ast = search(*self._predicates)
        session = self._connection.cursor()
        self._delete(ast, session)
        return True

    def _delete(
        self,
        ast: ASTGroupNode,
        session: sqlite3.Cursor,
    ):
        query = build_query(ast)
        session.execute(
            f"DELETE FROM {query.model.__ommi_metadata__.model_name} WHERE {query.where};",
            query.values,
        )

