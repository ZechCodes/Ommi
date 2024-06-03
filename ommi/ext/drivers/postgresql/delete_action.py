import psycopg

from ommi.drivers.database_results import async_result
from ommi.drivers.delete_actions import DeleteAction
from ommi.ext.drivers.postgresql.connection_protocol import PostgreSQLConnection
from ommi.ext.drivers.postgresql.utils import build_query
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
        await session.execute(
            f"DELETE FROM {query.model.__ommi_metadata__.model_name} WHERE {query.where};",
            query.values,
        )

