from dataclasses import dataclass
from typing import Annotated

import pymongo.errors
import pytest
import pytest_asyncio

from ommi import StoreAs
from ommi.model_collections import ModelCollection
from ommi.models import ommi_model

try:
    from ommi.ext.drivers.mongodb import MongoDBDriver, MongoDBConfig
except ImportError:
    MongoDBDriver = None


skip_if_motor_not_installed = pytest.mark.skipif(
    MongoDBDriver is None,
    reason="Could not import motor. Skipping MongoDB tests."
)

test_mongo_config = MongoDBConfig(host="127.0.0.1", port=27017, database_name="tests", timeout=100)
test_models = ModelCollection()


@ommi_model(collection=test_models)
@dataclass
class TestModel:
    name: Annotated[str, StoreAs("username")]
    id: int = None


@pytest.fixture
def mongo_driver() -> MongoDBDriver:
    """Need to use a pytest fixture so that the contextvar exists in the same context as the test. pytest-asyncio seems
    to create its own event loop which causes the contextvar to create an entirely new context.

    There may be a more elegant solution to this, but this works for now."""
    with MongoDBDriver(test_mongo_config) as driver:
        yield driver


@pytest_asyncio.fixture
async def driver(mongo_driver):
    async with mongo_driver as driver:
        try:
            await driver._db.drop_collection("TestModel")
        except pymongo.errors.ServerSelectionTimeoutError as exc:
            raise RuntimeError(f"Could not connect to MongoDB. Is it running? {test_mongo_config}") from exc
        else:
            await driver.sync_schema(test_models).or_raise()
            yield driver


@skip_if_motor_not_installed
@pytest.mark.asyncio
async def test_mongo_driver(driver):
    model = TestModel(name="dummy")
    await model.add().or_raise()

    result = await driver.fetch(TestModel.name == "dummy").or_raise()
    assert result.value[0].name == model.name

    model.name = "Dummy"
    await model.sync().or_raise()
    result = await driver.fetch(TestModel.name == "Dummy").or_raise()
    assert result.value[0].name == model.name

    await model.delete().or_raise()
    result = await driver.fetch(TestModel.name == "Dummy").or_raise()
    assert len(result.value) == 0


@skip_if_motor_not_installed
@pytest.mark.asyncio
async def test_mongo_fetch(driver):
    model = TestModel(name="dummy")
    await model.add().or_raise()

    result = await driver.fetch(TestModel.name == "dummy").or_raise()
    assert result.value[0].name == model.name


@skip_if_motor_not_installed
@pytest.mark.asyncio
async def test_mongo_update(driver):
    model = TestModel(name="dummy")
    await model.add().or_raise()

    model.name = "Dummy"
    await model.sync().or_raise()

    result = await driver.fetch(TestModel.name == "Dummy").or_raise()
    assert result.value[0].name == model.name


@skip_if_motor_not_installed
@pytest.mark.asyncio
async def test_mongo_delete(driver):
    model = TestModel(name="dummy")
    await model.add().or_raise()

    await model.delete().or_raise()
    result = await driver.fetch(TestModel).or_raise()
    assert len(result.value) == 0


@skip_if_motor_not_installed
@pytest.mark.asyncio
async def test_mongo_count(driver):
    await driver.add(TestModel(name="dummy1"), TestModel(name="dummy2")).or_raise()

    result = await TestModel.count().or_raise()
    assert result.value == 2
