from typing import Any, Iterable, TYPE_CHECKING

from ommi.ext.drivers.sqlite.utils import build_query, build_subquery

if TYPE_CHECKING:
    from ommi.ext.drivers.sqlite.shared_types import Cursor, SQLQuery
    from ommi.query_ast import ASTGroupNode


async def delete_models(cursor: "Cursor", predicate: "ASTGroupNode"):
    sql, params = _generate_delete_sql(predicate)
    cursor.execute(sql, params)


def _generate_delete_sql(predicate: "ASTGroupNode") -> "SQLQuery":
    query = build_query(predicate)
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

    return f"{' '.join(query_builder)};", tuple(query.values)
