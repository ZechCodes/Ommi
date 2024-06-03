from dataclasses import dataclass
from typing import Annotated

import pytest

from ommi import StoreAs
from ommi.ext.drivers.sqlite import SQLiteDriver, SQLiteConfig
from ommi.models.collections import ModelCollection
from ommi.models import ommi_model
from ommi.models.field_metadata import ReferenceTo
from ommi.models.query_fields import LazyLoadTheRelated

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
    driver = await SQLiteDriver.from_config(SQLiteConfig(filename=":memory:"))
    schema = driver.schema(test_models)
    await schema.delete_models().raise_on_errors()
    await schema.create_models().raise_on_errors()
    return driver


@DriverFactory
async def mongo():
    config = MongoDBConfig(
        host="127.0.0.1", port=27017, database_name="tests", timeout=100
    )
    try:
        driver = await MongoDBDriver.from_config(config)
        await driver.schema(test_models).delete_models().raise_on_errors()
    except pymongo.errors.ServerSelectionTimeoutError as exc:
        raise RuntimeError(
            f"Could not connect to MongoDB. Is it running? {config}"
        ) from exc
    else:
        await driver.schema(test_models).create_models().raise_on_errors()
        return driver


@DriverFactory
async def postgresql():
    config = PostgreSQLConfig(
        host="127.0.0.1",
        port=5432,
        database_name="postgres",
        username="postgres",
        password="password",
    )
    try:
        driver = await PostgreSQLDriver.from_config(config)
        schema = driver.schema(test_models)
        await schema.delete_models().raise_on_errors()
    except psycopg.OperationalError as exc:
        raise RuntimeError(
            f"Could not connect to PostgreSQL. Is it running? {config}"
        ) from exc
    else:
        await schema.create_models().raise_on_errors()
        return driver


def id_factory(param):
    return param.name


def parametrize_drivers():
    return pytest.mark.parametrize("driver", connections, ids=id_factory)


connections = [
    sqlite,
]

try:
    from ommi.ext.drivers.mongodb import MongoDBDriver, MongoDBConfig
    import pymongo.errors
except ImportError:
    MongoDBDriver = MongoDBConfig = pymongo = None
else:
    connections.append(mongo)

try:
    from ommi.ext.drivers.postgresql import PostgreSQLConfig, PostgreSQLDriver
    import psycopg
except ImportError:
    PostgreSQLConfig = PostgreSQLDriver = psycopg = None
else:
    connections.append(postgresql)


@pytest.mark.asyncio
@parametrize_drivers()
async def test_insert_and_fetch(driver):
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class InnerTestModel:
        id: int
        name: str
        toggle: bool
        decimal: float

    async with driver as connection:
        await connection.schema(collection).create_models().raise_on_errors()

        await connection.add(model := InnerTestModel(10, "testing", True, 1.23)).raise_on_errors()
        assert model.id == 10
        assert model.name == "testing"
        assert model.toggle == True
        assert model.decimal == 1.23

        result = await connection.find(InnerTestModel.id == 10).fetch.one()
        assert result.id == model.id
        assert result.name == model.name
        assert result.toggle == model.toggle
        assert result.decimal == model.decimal


@pytest.mark.asyncio
@parametrize_drivers()
async def test_driver(driver):
    async with driver as connection:
        await connection.add(model := TestModel(name="dummy")).raise_on_errors()

        result = await connection.find(TestModel.name == "dummy").fetch.one()
        assert result.name == model.name

        model.name = "Dummy"
        await model.save()
        result = await connection.find(TestModel.name == "Dummy").fetch.one()
        assert result.name == model.name

        await model.delete().raise_on_errors()
        result = await connection.find(TestModel.name == "Dummy").fetch.all()
        assert len(result) == 0


@pytest.mark.asyncio
@parametrize_drivers()
async def test_fetch(driver):
    async with driver as connection:
        await connection.add(model := TestModel(name="dummy")).raise_on_errors()

        result = await connection.find(TestModel.name == "dummy").fetch.one()
        assert result.name == model.name


@pytest.mark.asyncio
@parametrize_drivers()
async def test_update(driver):
    async with driver as connection:
        await connection.add(model := TestModel(name="dummy")).raise_on_errors()

        model.name = "Dummy"
        await model.save().raise_on_errors()

        result = await connection.find(TestModel.name == "Dummy").fetch.one()
        assert result.name == model.name


@pytest.mark.asyncio
@parametrize_drivers()
async def test_delete(driver):
    async with driver as connection:
        await connection.add(model := TestModel(name="dummy")).raise_on_errors()

        await model.delete().raise_on_errors()
        result = await connection.find(TestModel).fetch()
        assert len(result.value) == 0


@pytest.mark.asyncio
@parametrize_drivers()
async def test_count(driver):
    async with driver as connection:
        await connection.add(
            TestModel(name="dummy1"), TestModel(name="dummy2")
        ).raise_on_errors()

        result = await TestModel.count().value
        assert result == 2


@pytest.mark.asyncio
@parametrize_drivers()
async def test_sync_schema(driver):
    async with driver as connection:
        await connection.schema(test_models).create_models().raise_on_errors()

        await connection.add(
            a := TestModel(name="dummy1"),
            b := TestModel(name="dummy2"),
        ).raise_on_errors()

        assert isinstance(a.id, int)
        assert isinstance(b.id, int)
        assert a.id != b.id


@pytest.mark.asyncio
@parametrize_drivers()
async def test_detached_model_sync(driver):
    async with driver as connection:
        await connection.add(a := TestModel(name="dummy")).raise_on_errors()

        b = TestModel(name="Dummy", id=a.id)
        await b.save().raise_on_errors()

        r = await connection.find(TestModel).fetch.one()
        assert r.name == "Dummy"


@pytest.mark.asyncio
@parametrize_drivers()
async def test_detached_model_delete(driver):
    async with driver as connection:
        await connection.add(a := TestModel(name="dummy")).raise_on_errors()

        b = TestModel(name="Dummy", id=a.id)
        await b.delete().raise_on_errors()

        r = await connection.find(TestModel).fetch()
        assert len(r.value) == 0


@pytest.mark.asyncio
@parametrize_drivers()
async def test_driver_delete_query(driver):
    async with driver as connection:
        await connection.add(
            TestModel(name="dummy1"),
            TestModel(name="dummy2"),
        ).raise_on_errors()

        await connection.find(TestModel.name == "dummy1").delete().raise_on_errors()

        r = await connection.find(TestModel).fetch.all()
        assert len(r) == 1
        assert r[0].name == "dummy2"


@pytest.mark.asyncio
@parametrize_drivers()
async def test_driver_update_query(driver):
    async with driver as connection:
        await connection.add(
            TestModel(name="dummy1"),
            TestModel(name="dummy2"),
            TestModel(name="dummy3"),
            TestModel(name="dummy4"),
        ).raise_on_errors()

        ignore_id, new_name = 2, "dummy"
        await connection.find(TestModel.id != ignore_id).set(name=new_name).raise_on_errors()
        result = await connection.find(TestModel.name == new_name).fetch.all()
        assert len(result) > 1
        assert all(m.name == new_name for m in result)
        assert all(m.id != ignore_id for m in result)

        ignore_id, new_name = 1, "DUMMY"
        await connection.find(
            (TestModel.id != ignore_id).And(TestModel.name == "dummy")
        ).set(name=new_name).raise_on_errors()
        result = await connection.find(TestModel.name == new_name).fetch.all()
        assert len(result) > 1
        assert all(m.name == new_name for m in result)
        assert all(m.id != ignore_id for m in result)


@pytest.mark.asyncio
@parametrize_drivers()
async def test_load_changes(driver):
    async with driver as connection:
        await connection.add(m := TestModel(name="dummy")).raise_on_errors()

        await connection.find(TestModel.name == "dummy").set(name="Dummy").raise_on_errors()
        assert m.name == "dummy"

        await m.reload().raise_on_errors()
        assert m.name == "Dummy"


@pytest.mark.asyncio
async def test_async_with_connection():
    async with SQLiteDriver.from_config(
        SQLiteConfig(filename=":memory:")
    ) as connection:
        assert isinstance(connection, SQLiteDriver)


lazy_load_field_collection = ModelCollection()


@ommi_model(collection=lazy_load_field_collection)
@dataclass
class LazyLoadFieldA:
    id: int
    name: str


@ommi_model(collection=lazy_load_field_collection)
@dataclass
class LazyLoadFieldB:
    id: int
    a_id: Annotated[str, ReferenceTo(LazyLoadFieldA.id)]

    a: LazyLoadTheRelated[LazyLoadFieldA] = None


@pytest.mark.asyncio
@parametrize_drivers()
async def test_lazy_load_field(driver):
    async with driver as connection:
        schema = connection.schema(lazy_load_field_collection)
        await schema.delete_models().raise_on_errors()
        await schema.create_models().raise_on_errors()

        await connection.add(a := LazyLoadFieldA(10, "testing")).raise_on_errors()
        await connection.add(b := LazyLoadFieldB(10, a_id=a.id)).raise_on_errors()

        b_a = await b.a
        assert b_a.id == a.id
