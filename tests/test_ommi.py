from dataclasses import dataclass

import pytest

import ommi
from ommi.models.collections import ModelCollection


test_collection = ModelCollection()

@ommi.ommi_model(collection=test_collection)
@dataclass
class TestModel:
    id: int
    name: str


class UseModels:
    def __init__(self, db, collection):
        self.db = db
        self.collection = collection

    async def __aenter__(self):
        await self.db.apply_models(self.collection)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.db.remove_models(self.collection)


@pytest.mark.asyncio
async def test_ommi(driver):
    async with ommi.Database(driver) as db:
        async with UseModels(db, test_collection):
            assert await db.add(TestModel(id=1, name="test"))
