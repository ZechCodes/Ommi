import sqlite3
from typing import Type, Iterable, Any

from ommi.drivers.database_results import async_result
from ommi.drivers.schema_actions import SchemaAction
from ommi.ext.drivers.sqlite.connection_protocol import SQLiteConnection
from ommi.models.field_metadata import FieldMetadata
from ommi.models import OmmiModel
from ommi.models.models import get_collection
from tramp.optionals import Optional


class SQLiteSchemaAction(SchemaAction[SQLiteConnection, OmmiModel]):
    type_mapping = {
        int: "INTEGER",
        str: "TEXT",
        float: "REAL",
        bool: "INTEGER",
    }

    @async_result
    async def create_models(self) -> Iterable[Type[OmmiModel]]:
        session = self._connection.cursor()
        models = get_collection(
            Optional.Some(self._model_collection)
            if self._model_collection
            else Optional.Nothing
        ).models

        try:
            for model in models:
                self._create_table(model, session)

        except:
            self._connection.rollback()
            raise

        else:
            return models

        finally:
            session.close()

    @async_result
    async def delete_models(self) -> Iterable[Type[OmmiModel]]:
        session = self._connection.cursor()
        models = get_collection(
            Optional.Some(self._model_collection)
            if self._model_collection
            else Optional.Nothing
        ).models

        try:
            for model in models:
                session.execute(f"DROP TABLE IF EXISTS {model.__ommi__.model_name};")

        except:
            self._connection.rollback()
            raise

        else:
            return models

        finally:
            session.close()

    def _create_table(self, model: Type[OmmiModel], session: sqlite3.Cursor):
        pks = model.get_primary_key_fields()
        columns = ", ".join(
            self._build_column(field) for field in model.__ommi__.fields.values()
        )
        session.execute(
            f"CREATE TABLE IF NOT EXISTS {model.__ommi__.model_name}"
            f"("
            f"{columns}, "
            f"PRIMARY KEY ({', '.join(pk.get('store_as') for pk in pks)})"
            f");"
        )

    def _build_column(self, field: FieldMetadata) -> str:
        column = [
            field.get("store_as"),
            self._get_sqlite_type(field.get("field_type")),
        ]

        return " ".join(column)

    def _get_sqlite_type(self, type_: Type[Any]) -> str:
        return self.type_mapping.get(type_, "TEXT")
