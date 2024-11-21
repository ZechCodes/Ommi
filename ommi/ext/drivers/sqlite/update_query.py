from typing import Any, Iterable, TYPE_CHECKING

from ommi.ext.drivers.sqlite.utils import build_query, build_subquery

if TYPE_CHECKING:
    from ommi.ext.drivers.sqlite.shared_types import Cursor, SQLQuery
    from ommi.query_ast import ASTGroupNode
    from ommi.shared_types import DBModel


async def update_models(cursor: "Cursor", predicate: "ASTGroupNode", values: dict[str, Any]) -> "Iterable[DBModel]":
    sql, params = _generate_update_sql(predicate, values)
    cursor.execute(sql, params)
    return


def _generate_update_sql(predicate: "ASTGroupNode", values: dict[str, Any]) -> "SQLQuery":
    query = build_query(predicate)
    fields = query.model.__ommi__.fields
    query_builder = [
        f"UPDATE {query.model.__ommi__.model_name}",
        f"SET",
        ", ".join(
            f"{fields[name].get('store_as')} = ?" for name in values.keys()
        ),
    ]
    if query.models:
        sub_query = build_subquery(query.model, query.models, query.where)
        pks = ", ".join(
            f"{query.model.__ommi__.model_name}.{pk.get('store_as')}"
            for pk in query.model.get_primary_key_fields()
        )
        query_builder.append(f"WHERE ({pks}) IN ({sub_query})")

    else:
        query_builder.append("WHERE")
        query_builder.append(query.where)

    return f"{' '.join(query_builder)};", (*values.values(), *query.values)