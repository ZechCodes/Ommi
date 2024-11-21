from typing import Generator, TYPE_CHECKING

from ommi.ext.drivers.sqlite.utils import get_sqlite_type

if TYPE_CHECKING:
    import sqlite3
    from ommi.models import OmmiModel
    from ommi.models.collections import ModelCollection
    from ommi.models.field_metadata import FieldMetadata


async def apply_schema(cursor: "sqlite3.Cursor", models: "ModelCollection"):
    for create_table_sql in _generate_create_table_sql(models):
        cursor.execute(create_table_sql)


async def delete_schema(cursor: "sqlite3.Cursor", models: "ModelCollection"):
    for drop_table_sql in _generate_drop_table_sql(models):
        cursor.execute(drop_table_sql)


def _generate_create_table_sql(collection: "ModelCollection") -> Generator[str, None, None]:
    for model in collection.models:
        yield _generate_create_table_sql_for_model(model)


def _generate_create_table_sql_for_model(model: "OmmiModel") -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {model.__ommi__.model_name}"
        f"("
        f"{_generate_columns_sql(model)}, "
        f"PRIMARY KEY ({_generate_primary_keys_sql(model)})"
        f");"
    )

def _generate_primary_keys_sql(model: "OmmiModel") -> str:
    return ", ".join(
        pk.get("store_as") for pk in model.get_primary_key_fields()
    )

def _generate_columns_sql(model: "OmmiModel") -> str:
    return ", ".join(
        _generate_column_sql(field) for field in model.__ommi__.fields.values()
    )


def _generate_column_sql(field: "FieldMetadata") -> str:
    return " ".join(
        (
            field.get("store_as"),
            get_sqlite_type(field.get("field_type")),
        )
    )


def _generate_drop_table_sql(collection: "ModelCollection") -> Generator[str, None, None]:
    for model in collection.models:
        yield f"DROP TABLE IF EXISTS {model.__ommi__.model_name};"