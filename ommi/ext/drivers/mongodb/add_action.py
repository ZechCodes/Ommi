from contextlib import suppress

from typing import Iterable

from ommi.drivers.add_actions import AddAction
from ommi.drivers.database_results import async_result
from ommi.drivers.driver_types import TModel
from ommi.ext.drivers.mongodb.connection_protocol import MongoDBConnection
from ommi.ext.drivers.mongodb.utils import model_to_dict
from ommi.models import OmmiModel


class MongoDBAddAction(AddAction[MongoDBConnection, OmmiModel]):
    def __init__(self, connection: MongoDBConnection, database):
        super().__init__(connection)
        self._db = database

    @async_result
    async def items(self, *items: TModel) -> Iterable[TModel]:
        for item in items:
            await self._insert(item)

        return items

    async def _insert(self, item: OmmiModel):
        data = model_to_dict(item)
        result = await self._db[item.__ommi_metadata__.model_name].insert_one(data)
        item.__ommi_mongodb_id__ = result.inserted_id
        await self._set_auto_increment_pk(item)

    async def _set_auto_increment_pk(self, item: OmmiModel):
        pk = item.get_primary_key_field()
        if getattr(item, pk.get("field_name")) is not None:
            return

        if (
            not issubclass(pk.get("field_type"), int)
            or getattr(item, pk.get("field_name")) is not None
        ):
            return

        name = pk.get("store_as")
        with suppress(StopAsyncIteration):
            await self._db[item.__ommi_metadata__.model_name].aggregate(
                [
                    {
                        "$lookup": {
                            "from": item.__ommi_metadata__.model_name,
                            "pipeline": [
                                {
                                    "$match": {
                                        name: {
                                            "$exists": True,
                                        },
                                    },
                                },
                                {
                                    "$sort": {
                                        name: 1,
                                    },
                                },
                                {
                                    "$addFields": {
                                        "next_id": {
                                            "$add": [f"${name}", 1],
                                        },
                                    },
                                },
                            ],
                            "as": "__ommi_autoincrement",
                        },
                    },
                    {
                        "$unwind": {
                            "path": "$__ommi_autoincrement",
                            "preserveNullAndEmptyArrays": True,
                        },
                    },
                    {
                        "$match": {
                            "_id": item.__ommi_mongodb_id__,
                        },
                    },
                    {
                        "$addFields": {
                            name: {
                                "$ifNull": [
                                    "$__ommi_autoincrement.next_id",
                                    0,
                                ],
                            },
                        },
                    },
                    {
                        "$unset": ["__ommi_autoincrement"],
                    },
                    {
                        "$match": {
                            name: {
                                "$exists": True,
                            },
                        },
                    },
                    {
                        "$merge": item.__ommi_metadata__.model_name,
                    },
                ]
            ).next()

        result = await self._db[item.__ommi_metadata__.model_name].find_one(
            {"_id": item.__ommi_mongodb_id__}, {"_id": 0, name: 1}
        )
        setattr(item, pk.get("field_name"), result[name])
