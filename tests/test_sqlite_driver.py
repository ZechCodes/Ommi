from dataclasses import dataclass
from typing import Annotated

import pytest
import pytest_asyncio

from ommi import StoreAs
from ommi.ext.drivers.sqlite import SQLiteConfig, SQLiteDriver
from ommi.model_collections import ModelCollection
from ommi.models import ommi_model


test_models = ModelCollection()


@ommi_model(collection=test_models)
@dataclass
class TestModel:
    name: Annotated[str, StoreAs("username")]
    id: int = None


@pytest.fixture
def sqlite_driver() -> SQLiteDriver:
    """Need to use a pytest fixture so that the contextvar exists in the same context as the test. pytest-asyncio seems
    to create its own event loop which causes the contextvar to create an entirely new context.

    There may be a more elegan"""
    with SQLiteDriver(SQLiteConfig(filename=":memory:")) as driver:
        yield driver


@pytest_asyncio.fixture
async def driver(sqlite_driver):
    async with sqlite_driver as driver:
        await driver.sync_schema(test_models).or_raise()
        yield driver


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


@pytest.mark.asyncio
async def test_sqlite_count(driver):
    await driver.add(TestModel(name="dummy1"), TestModel(name="dummy2")).or_raise()

    result = await TestModel.count().or_raise()
    assert result.value == 2
