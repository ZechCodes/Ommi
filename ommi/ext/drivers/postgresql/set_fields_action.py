from typing import Any

import psycopg

from ommi.drivers.database_results import async_result
from ommi.drivers.set_fields_actions import SetFieldsAction
from ommi.ext.drivers.postgresql.connection_protocol import PostgreSQLConnection
from ommi.ext.drivers.postgresql.utils import build_query
from ommi.models import OmmiModel
from ommi.query_ast import search, ASTGroupNode


class PostgreSQLSetFieldsAction(SetFieldsAction[PostgreSQLConnection, OmmiModel]):
    @async_result
    async def set_fields(self, **kwargs: Any) -> bool:
        ast = search(*self._predicates)
        session = self._connection.cursor()
        await self._update(ast, kwargs, session)
        return True

    async def _update(
        self,
        ast: ASTGroupNode,
        set_fields: dict[str, Any],
        session: psycopg.AsyncCursor,
    ):
        query = build_query(ast)
        fields = query.model.__ommi_metadata__.fields
        assignments = ", ".join(f"{fields[name].get('store_as')} = %s" for name in set_fields.keys())
        await session.execute(
            f"UPDATE {query.model.__ommi_metadata__.model_name} SET {assignments} WHERE {query.where};",
            (*set_fields.values(), *query.values),
        )
