import sqlite3
from typing import Any

from ommi.drivers.database_results import async_result
from ommi.drivers.set_fields_actions import SetFieldsAction
from ommi.ext.drivers.sqlite.connection_protocol import SQLiteConnection
from ommi.ext.drivers.sqlite.utils import build_query
from ommi.models import OmmiModel
from ommi.query_ast import search, ASTGroupNode


class SQLiteSetFieldsAction(SetFieldsAction[SQLiteConnection, OmmiModel]):
    @async_result
    async def set_fields(self, **kwargs: Any) -> bool:
        ast = search(*self._predicates)
        session = self._connection.cursor()
        self._update(ast, kwargs, session)
        return True

    def _update(
        self,
        ast: ASTGroupNode,
        set_fields: dict[str, Any],
        session: sqlite3.Cursor,
    ):
        query = build_query(ast)
        fields = query.model.__ommi_metadata__.fields
        assignments = ", ".join(f"{fields[name].get('store_as')} = ?" for name in set_fields.keys())
        session.execute(
            f"UPDATE {query.model.__ommi_metadata__.model_name} SET {assignments} WHERE {query.where};",
            (*set_fields.values(), *query.values),
        )
