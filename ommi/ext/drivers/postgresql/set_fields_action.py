from typing import Any

import psycopg

from ommi.drivers.database_results import async_result
from ommi.drivers.set_fields_actions import SetFieldsAction
from ommi.ext.drivers.postgresql.connection_protocol import PostgreSQLConnection
from ommi.ext.drivers.postgresql.utils import build_query, create_join_comparison
from ommi.ext.drivers.postgresql.utils import generate_joins
from ommi.models import OmmiModel
from ommi.query_ast import when, ASTGroupNode


class PostgreSQLSetFieldsAction(SetFieldsAction[PostgreSQLConnection, OmmiModel]):
    @async_result
    async def set_fields(self, **kwargs: Any) -> bool:
        ast = when(*self._predicates)
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
        fields = query.model.__ommi__.fields
        where = query.where
        query_builder = [
            f"UPDATE {query.model.__ommi__.model_name}",
            f"SET",
            ", ".join(
                f"{fields[name].get('store_as')} = %s" for name in set_fields.keys()
            ),
        ]
        if query.models:
            from_join = query.models.pop(0)
            from_join_comparison = f"{create_join_comparison(query.model, from_join)}"
            query_builder.append(f"FROM {from_join.__ommi__.model_name}")
            query_builder.extend(generate_joins(query.model, query.models))

            if where:
                where = f"{from_join_comparison} AND ({where})"

            else:
                where = from_join_comparison

        if where:
            query_builder.append(f"WHERE {where}")

        await session.execute(
            f"{' '.join(query_builder)};".encode(),
            (*set_fields.values(), *query.values),
        )
