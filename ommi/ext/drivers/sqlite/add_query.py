from typing import Any, Generator, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from ommi.ext.drivers.sqlite.shared_types import Cursor, SQLQuery
    from ommi.shared_types import DBModel


async def add_models(cursor: "Cursor", models: "Iterable[DBModel]") -> "Iterable[DBModel]":
    return list(_add_models(cursor, models))


def _add_models(cursor: "Cursor", models: "Iterable[DBModel]") -> "Generator[DBModel, None, None]":
    for (sql, params), model in _generate_insert_query(models):
        cursor.execute(sql, params)
        new_id = cursor.execute("SELECT last_insert_rowid();", ()).fetchone()[0]
        pk = model.get_primary_key_fields()[0].get("store_as")
        setattr(model, pk, new_id)
        yield model


def _generate_insert_query(models: "Iterable[DBModel]") -> "Generator[tuple[SQLQuery, DBModel], None, None]":
    for model in models:
        yield _generate_insert_query_for_model(model), model


def _generate_insert_query_for_model(model: "DBModel") -> "SQLQuery":
    fields = _get_model_fields(model)
    return (
        f"INSERT INTO {model.__ommi__.model_name} "
        f"({', '.join(name for name in fields)})"
        f"VALUES "
        f"({', '.join(['?'] * len(fields))});",
        tuple(fields.values()),
    )


def _get_model_fields(model: "DBModel") -> "dict[str, Any]":
    return {
        field.get("store_as"): getattr(model, field.get("field_name"))
        for field in list(model.__ommi__.fields.values())
    }