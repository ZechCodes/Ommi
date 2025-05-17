from dataclasses import dataclass

import pytest
import pytest_asyncio
from ommi import Ommi, ommi_model
from ommi.models.collections import ModelCollection
from ommi.ext.drivers.sqlite import SQLiteDriver


test_collection = ModelCollection()

@ommi_model(collection=test_collection)
@dataclass
class TestModel:
    id: int
    name: str


class UseModels:
    def __init__(self, db, collection):
        self.db = db
        self.collection = collection

    async def __aenter__(self):
        await self.collection.setup_on(self.db)
        return self.db

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.collection.remove_from(self.db)


@pytest.fixture
def driver():
    return SQLiteDriver.connect()


@pytest_asyncio.fixture
async def db(driver):
    async with Ommi(driver) as db:
        async with UseModels(db, test_collection) as db_with_models:
            yield db_with_models


@pytest.mark.asyncio
async def test_ommi_creates(db):
    assert isinstance(db, Ommi)


@pytest.mark.asyncio
async def test_ommi_add(db):
    await db.add(TestModel(1, "test")).or_raise()
    result = await db.find(TestModel.id == 1).one.or_raise()
    assert result.id == 1
    assert result.name == "test"


@pytest.mark.asyncio
async def test_ommi_count(db):
    await db.add(TestModel(1, "test")).or_raise()
    result = await db.find(TestModel.id == 1).count.or_raise()
    assert result == 1


@pytest.mark.asyncio
async def test_ommi_delete(db):
    await db.add(TestModel(1, "test")).or_raise()
    await db.find(TestModel.id == 1).delete.or_raise()
    result = await db.find(TestModel.id == 1).count.or_raise()
    assert result == 0


@pytest.mark.asyncio
async def test_ommi_find_multiple(db):
    await db.add(
        TestModel(1, "test"),
        TestModel(2, "test"),
        TestModel(3, "test"),
    ).or_raise()
    result = await db.find(TestModel.id > 1).or_raise()
    assert {m.id async for m in result} == {2, 3}


@pytest.mark.asyncio
async def test_ommi_update(db):
    await db.add(TestModel(1, "test")).or_raise()
    await db.find(TestModel.id == 1).update(name="test2").or_raise()
    result = await db.find(TestModel.id == 1).one.or_raise()
    assert result.name == "test2"
