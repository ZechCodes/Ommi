from typing import Type, Iterable, Any

import psycopg

from ommi.drivers.database_results import async_result
from ommi.drivers.schema_actions import SchemaAction
from ommi.ext.drivers.postgresql.connection_protocol import PostgreSQLConnection
from ommi.models.field_metadata import FieldMetadata
from ommi.models import OmmiModel
from ommi.models.models import get_collection
from tramp.optionals import Optional


class PostgreSQLSchemaAction(SchemaAction[PostgreSQLConnection, OmmiModel]):
    type_mapping = {
        int: "INTEGER",
        str: "TEXT",
        float: "REAL",
        bool: "BOOLEAN",
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
                await self._create_table(model, session)

        except:
            await self._connection.rollback()
            raise

        else:
            return models

        finally:
            await session.close()

    @async_result
    async def delete_models(self) -> None:
        session = self._connection.cursor()
        models = get_collection(
            Optional.Some(self._model_collection)
            if self._model_collection
            else Optional.Nothing
        ).models

        try:
            for model in models:
                await session.execute(
                    f"DROP TABLE IF EXISTS {model.__ommi__.model_name};"
                )

        except:
            await self._connection.rollback()
            raise

        else:
            return None

        finally:
            await session.close()

    async def _create_table(self, model: Type[OmmiModel], session: psycopg.AsyncCursor):
        pks = model.get_primary_key_fields()
        columns = ", ".join(
            self._build_column(field, len(pks) == 1 and field in pks)
            for field in model.__ommi__.fields.values()
        )
        await session.execute(
            f"CREATE TABLE IF NOT EXISTS {model.__ommi__.model_name}"
            f"("
            f"{columns}, "
            f"PRIMARY KEY ({', '.join(pk.get('store_as') for pk in pks)})"
            f");"
        )

    def _build_column(self, field: FieldMetadata, pk: bool) -> str:
        column = [
            field.get("store_as"),
            self._get_postgresql_type(field.get("field_type"), pk),
        ]
        return " ".join(column)

    def _get_postgresql_type(self, type_: Type[Any], pk: bool) -> str:
        if pk and isinstance(type_, type) and issubclass(type_, int):
            return "SERIAL"

        return self.type_mapping.get(type_, "TEXT")
