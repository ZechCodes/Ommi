import sqlite3
from typing import Iterable

from ommi.drivers.add_actions import AddAction
from ommi.drivers.database_results import async_result
from ommi.drivers.driver_types import TModel
from ommi.ext.drivers.sqlite.connection_protocol import SQLiteConnection
from ommi.models import OmmiModel


class SQLiteAddAction(AddAction[SQLiteConnection, OmmiModel]):
    @async_result
    async def items(self, *items: TModel) -> Iterable[TModel]:
        session = self._connection.cursor()
        try:
            for item in items:
                self._insert(item, session)
                self._sync_with_last_inserted(item, session)

        except Exception as error:
            self._connection.rollback()
            raise

        else:
            return items

        finally:
            session.close()

    def _insert(self, item: OmmiModel, session: sqlite3.Cursor):
        fields = list(item.__ommi_metadata__.fields.values())
        data = {
            field.get("store_as"): getattr(item, field.get("field_name"))
            for field in fields
        }
        qs = ", ".join(["?"] * len(data))
        columns = ", ".join(data.keys())
        values = tuple(data.values())
        session.execute(
            f"INSERT INTO {item.__ommi_metadata__.model_name} ({columns}) VALUES ({qs});",
            values,
        )

    def _sync_with_last_inserted(self, item: OmmiModel, session: sqlite3.Cursor):
        pk = item.get_primary_key_field().get("store_as")
        result = session.execute("SELECT last_insert_rowid();").fetchone()
        setattr(item, pk, result[0])
