import contextlib
from dataclasses import dataclass
from typing import Annotated

import pymongo.errors
import pytest
import pytest_asyncio

from ommi import StoreAs
from ommi.ext.drivers.sqlite import SQLiteDriver, SQLiteConfig
from ommi.model_collections import ModelCollection
from ommi.models import ommi_model


test_models = ModelCollection()


@ommi_model(collection=test_models)
@dataclass
class TestModel:
    name: Annotated[str, StoreAs("username")]
    id: int = None


class DriverFactory:
    def __init__(self, factory):
        self.factory = factory
        self.driver = None

    @property
    def name(self):
        return self.factory.__name__

    async def __aenter__(self):
        self.driver = await self.factory()
        return await self.driver.__aenter__()

    async def __aexit__(self, *args):
        return await self.driver.__aexit__(*args)


@DriverFactory
async def sqlite():
    driver = SQLiteDriver(SQLiteConfig(filename=":memory:"))
    await driver.connect().or_raise()
    await driver.sync_schema(test_models).or_raise()
    return driver


@DriverFactory
async def mongo():
    driver = MongoDBDriver(MongoDBConfig(host="127.0.0.1", port=27017, database_name="tests", timeout=100))
    try:
        await driver.connect().or_raise()
        await driver._db.drop_collection("TestModel")
    except pymongo.errors.ServerSelectionTimeoutError as exc:
        raise RuntimeError(f"Could not connect to MongoDB. Is it running? {driver.config}") from exc
    else:
        await driver.sync_schema(test_models).or_raise()
        return driver


def id_factory(param):
    return param.name


def parametrize_drivers():
    return pytest.mark.parametrize("driver", connections, ids=id_factory)


connections = [sqlite,]

try:
    from ommi.ext.drivers.mongodb import MongoDBDriver, MongoDBConfig
except ImportError:
    MongoDBDriver = MongoDBConfig = None
else:
    connections.append(mongo)


@pytest.mark.asyncio
@parametrize_drivers()
async def test_driver(driver):
    async with driver as connection:
        model = TestModel(name="dummy")
        await model.add().or_raise()

        result = await connection.fetch(TestModel.name == "dummy").or_raise()
        assert result.value[0].name == model.name

        model.name = "Dummy"
        await model.sync().or_raise()
        result = await connection.fetch(TestModel.name == "Dummy").or_raise()
        assert result.value[0].name == model.name

        await model.delete().or_raise()
        result = await connection.fetch(TestModel.name == "Dummy").or_raise()
        assert len(result.value) == 0


@pytest.mark.asyncio
@parametrize_drivers()
async def test_fetch(driver):
    async with driver as connection:
        model = TestModel(name="dummy")
        await model.add().or_raise()

        result = await connection.fetch(TestModel.name == "dummy").or_raise()
        assert result.value[0].name == model.name


@pytest.mark.asyncio
@parametrize_drivers()
async def test_update(driver):
    async with driver as connection:
        model = TestModel(name="dummy")
        await model.add().or_raise()

        model.name = "Dummy"
        await model.sync().or_raise()

        result = await connection.fetch(TestModel.name == "Dummy").or_raise()
        assert result.value[0].name == model.name


@pytest.mark.asyncio
@parametrize_drivers()
async def test_delete(driver):
    async with driver as connection:
        model = TestModel(name="dummy")
        await model.add().or_raise()

        await model.delete().or_raise()
        result = await connection.fetch(TestModel).or_raise()
        assert len(result.value) == 0


@pytest.mark.asyncio
@parametrize_drivers()
async def test_count(driver):
    async with driver as connection:
        await connection.add(TestModel(name="dummy1"), TestModel(name="dummy2")).or_raise()

        result = await TestModel.count().or_raise()
        assert result.value == 2
