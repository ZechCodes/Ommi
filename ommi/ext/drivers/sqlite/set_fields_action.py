import sqlite3
from typing import Any

from ommi.drivers.database_results import async_result
from ommi.drivers.set_fields_actions import SetFieldsAction
from ommi.ext.drivers.sqlite.connection_protocol import SQLiteConnection
from ommi.ext.drivers.sqlite.utils import build_query, build_subquery
from ommi.models import OmmiModel
from ommi.query_ast import when, ASTGroupNode


class SQLiteSetFieldsAction(SetFieldsAction[SQLiteConnection, OmmiModel]):
    @async_result
    async def set_fields(self, **kwargs: Any) -> bool:
        ast = when(*self._predicates)
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
        query_builder = [
            f"UPDATE {query.model.__ommi_metadata__.model_name}",
            f"SET",
            ", ".join(f"{fields[name].get('store_as')} = ?" for name in set_fields.keys()),
        ]
        if query.models:
            pk = query.model.get_primary_key_field().get("store_as")
            sub_query = build_subquery(query.model, query.models, query.where)
            query_builder.append(f"WHERE {query.model.__ommi_metadata__.model_name}.{pk} IN ({sub_query})")

        else:
            query_builder.append("WHERE")
            query_builder.append(query.where)

        session.execute(
            f"{' '.join(query_builder)};",
            (*set_fields.values(), *query.values),
        )
