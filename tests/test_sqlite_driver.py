from dataclasses import dataclass

import pytest
import pytest_asyncio

from ommi.driver_context import use_driver
from ommi.ext.drivers.sqlite import SQLiteConfig, SQLiteDriver
from ommi.model_collections import ModelCollection
from ommi.models import ommi_model
from ommi.statuses import DatabaseStatus


test_models = ModelCollection()


@ommi_model(collection=test_models)
@dataclass
class TestModel:
    name: str
    id: int = None


@pytest.fixture
def sqlite_driver() -> SQLiteDriver:
    """Need to use a pytest fixture so that the contextvar exists in the same context as the test."""
    with use_driver(SQLiteDriver()) as driver:
        yield driver


@pytest_asyncio.fixture
async def driver(sqlite_driver):
    await sqlite_driver.connect(SQLiteConfig(filename=":memory:")).or_raise()
    await sqlite_driver.sync_schema(test_models).or_raise()

    yield sqlite_driver


@pytest.mark.asyncio
async def test_sqlite_driver(driver):
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


@pytest.mark.asyncio
async def test_sqlite_fetch(driver):
    model = TestModel(name="dummy")
    await model.add().or_raise()

    result = await driver.fetch(TestModel.name == "dummy").or_raise()
    assert result.value[0].name == model.name

@pytest.mark.asyncio
async def test_sqlite_update(driver):
    model = TestModel(name="dummy")
    await model.add().or_raise()

    model.name = "Dummy"
    await model.sync().or_raise()

    result = await driver.fetch(TestModel.name == "Dummy").or_raise()
    assert result.value[0].name == model.name

@pytest.mark.asyncio
async def test_sqlite_delete(driver):
    model = TestModel(name="dummy")
    await model.add().or_raise()

    await model.delete().or_raise()
    result = await driver.fetch(TestModel).or_raise()
    assert len(result.value) == 0
