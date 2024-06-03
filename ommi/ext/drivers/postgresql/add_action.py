from typing import Iterable, Type, Sequence

import psycopg

from ommi.drivers.add_actions import AddAction
from ommi.drivers.database_results import async_result
from ommi.drivers.driver_types import TModel
from ommi.ext.drivers.postgresql.connection_protocol import PostgreSQLConnection
from ommi.models import OmmiModel


class PostgreSQLAddAction(AddAction[PostgreSQLConnection, OmmiModel]):
    @async_result
    async def items(self, *items: TModel) -> Iterable[TModel]:
        session = self._connection.cursor()
        try:
            for model, group in self._group_by_model_type(items).items():
                await self._insert(group, session, model)

        except Exception:
            await self._connection.rollback()
            raise

        else:
            return items

        finally:
            await session.close()

    def _group_by_model_type(self, items: Sequence[OmmiModel]):
        model_groups = {}
        for item in items:
            model_groups.setdefault(type(item), []).append(item)

        return model_groups

    async def _insert(
            self,
            items: Sequence[OmmiModel],
            session: psycopg.AsyncCursor,
            model: Type[OmmiModel],
    ):
        query = [f"INSERT INTO {model.__ommi_metadata__.model_name}"]

        fields = list(model.__ommi_metadata__.fields.values())
        pk = model.get_primary_key_field()
        allow_pk = getattr(items[0], pk.get("field_name")) is not None
        columns = [
            field.get("store_as")
            for field in fields
            if field != pk or allow_pk
        ]
        query.append(f"({','.join(columns)})")

        values = []
        inserts = []
        for item in items:
            qs = ",".join(["%s"] * len(columns))
            inserts.append(f"({qs})")
            values.extend(
                getattr(item, field.get("field_name"))
                for field in fields
                if field != pk or allow_pk
            )

        query.append(f"VALUES {','.join(inserts)}")
        query.append(f"RETURNING {pk.get('store_as')};")

        result = await session.execute(" ".join(query).encode(), values)

        # Update the primary key field of the models that were inserted if the primary key is an auto-incrementing field
        item_stack = iter(items)
        async for record in result:
            item = next(item_stack)
            setattr(item, pk.get("field_name"), record[0])
