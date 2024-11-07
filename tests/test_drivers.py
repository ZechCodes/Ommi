from dataclasses import dataclass
from typing import Annotated

import pytest
import attrs
import pydantic

from ommi import StoreAs
from ommi.ext.drivers.sqlite import SQLiteDriver, SQLiteConfig
from ommi.models.collections import ModelCollection
from ommi.models import ommi_model
from ommi.models.field_metadata import ReferenceTo, Key
from ommi.models.query_fields import (
    LazyLoadTheRelated,
    LazyLoadEveryRelated,
    AssociateUsing,
)

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


connections = [sqlite]

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
        await connection.schema(collection).delete_models().raise_on_errors()
        await connection.schema(collection).create_models().raise_on_errors()

        await connection.add(
            model := InnerTestModel(10, "testing", True, 1.23)
        ).raise_on_errors()
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
        await model.save().raise_on_errors()
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
        await connection.find(TestModel.id != ignore_id).set(
            name=new_name
        ).raise_on_errors()
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

        await connection.find(TestModel.name == "dummy").set(
            name="Dummy"
        ).raise_on_errors()
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
class LazyLoadFieldADataclass:
    id: int
    name: str

    b: "LazyLoadEveryRelated[LazyLoadFieldBDataclass]"


@ommi_model(collection=lazy_load_field_collection)
@dataclass
class LazyLoadFieldBDataclass:
    id: int
    a_id: Annotated[int, ReferenceTo(LazyLoadFieldADataclass.id)]

    a: LazyLoadTheRelated[LazyLoadFieldADataclass]


@ommi_model(collection=lazy_load_field_collection)
@attrs.define
class LazyLoadFieldAAttrs:
    id: int
    name: str

    b: "LazyLoadEveryRelated[LazyLoadFieldBAttrs]"


@ommi_model(collection=lazy_load_field_collection)
@attrs.define
class LazyLoadFieldBAttrs:
    id: int
    a_id: Annotated[int, ReferenceTo(LazyLoadFieldAAttrs.id)]

    a: LazyLoadTheRelated[LazyLoadFieldAAttrs]


@ommi_model(collection=lazy_load_field_collection)
class LazyLoadFieldAPydantic(pydantic.BaseModel):
    id: int
    name: str

    b: "LazyLoadEveryRelated[LazyLoadFieldBPydantic]"


@ommi_model(collection=lazy_load_field_collection)
class LazyLoadFieldBPydantic(pydantic.BaseModel):
    id: int
    a_id: Annotated[int, ReferenceTo(LazyLoadFieldAPydantic.id)]

    a: LazyLoadTheRelated[LazyLoadFieldAPydantic]


@pytest.mark.asyncio
@parametrize_drivers()
@pytest.mark.parametrize(
    "models",
    [
        *zip(
            (LazyLoadFieldADataclass, LazyLoadFieldAAttrs, LazyLoadFieldAPydantic),
            (LazyLoadFieldBDataclass, LazyLoadFieldBAttrs, LazyLoadFieldBPydantic),
            ("Dataclasses", "Attrs", "Pydantic"),
        )
    ],
    ids=lambda params: params[~0],
)
async def test_lazy_load_field(driver, models):
    model_a, model_b, _ = models
    async with driver as connection:
        schema = connection.schema(lazy_load_field_collection)
        await schema.delete_models().raise_on_errors()
        await schema.create_models().raise_on_errors()

        await connection.add(a := model_a(id=10, name="testing")).raise_on_errors()
        await connection.add(b := model_b(id=10, a_id=a.id)).raise_on_errors()
        await connection.add(c := model_b(id=11, a_id=a.id)).raise_on_errors()

        b_a = await b.a
        assert b_a.id == a.id

        a_b = await a.b
        assert {b.id, c.id} == {m.id for m in a_b}


@pytest.mark.asyncio
@parametrize_drivers()
async def test_join_queries(driver):
    join_collection = ModelCollection()

    @ommi_model(collection=join_collection)
    @dataclass
    class JoinModelA:
        id: int
        name: str

    @ommi_model(collection=join_collection)
    @dataclass
    class JoinModelB:
        id: int
        a_id: Annotated[int, ReferenceTo(JoinModelA.id)]

    async with driver as connection:
        schema = connection.schema(join_collection)
        await schema.delete_models().raise_on_errors()
        await schema.create_models().raise_on_errors()

        await connection.add(
            JoinModelA(id=10, name="testing"),
            JoinModelB(id=10, a_id=10),
            JoinModelB(id=11, a_id=10),
        ).raise_on_errors()

        await connection.add(
            JoinModelA(id=11, name="foobar"), JoinModelB(id=12, a_id=11)
        ).raise_on_errors()

        result = await connection.find(
            JoinModelB, JoinModelA.name == "testing"
        ).fetch.all()
        assert {10, 11} == {m.id for m in result}


@pytest.mark.asyncio
@parametrize_drivers()
async def test_join_deletes(driver):
    join_collection = ModelCollection()

    @ommi_model(collection=join_collection)
    @dataclass
    class JoinModelA:
        id: int
        name: str

    @ommi_model(collection=join_collection)
    @dataclass
    class JoinModelB:
        id: int
        a_id: Annotated[int, ReferenceTo(JoinModelA.id)]

    async with driver as connection:
        schema = connection.schema(join_collection)
        await schema.delete_models().raise_on_errors()
        await schema.create_models().raise_on_errors()

        await connection.add(
            JoinModelA(id=10, name="testing"),
            JoinModelB(id=10, a_id=10),
            JoinModelB(id=11, a_id=10),
        ).raise_on_errors()

        await connection.add(
            JoinModelA(id=11, name="foobar"), JoinModelB(id=12, a_id=11)
        ).raise_on_errors()

        await connection.find(
            JoinModelB, JoinModelA.name == "testing"
        ).delete().raise_on_errors()
        result = await connection.find(JoinModelB).fetch.all()
        assert {m.id for m in result} == {12}


@pytest.mark.asyncio
@parametrize_drivers()
async def test_join_updates(driver):
    join_collection = ModelCollection()

    @ommi_model(collection=join_collection)
    @dataclass
    class JoinModelA:
        id: int
        name: str

    @ommi_model(collection=join_collection)
    @dataclass
    class JoinModelB:
        id: int
        value: str

        a_id: Annotated[int, ReferenceTo(JoinModelA.id)]

    async with driver as connection:
        schema = connection.schema(join_collection)
        await schema.delete_models().raise_on_errors()
        await schema.create_models().raise_on_errors()

        await connection.add(
            JoinModelA(id=10, name="testing"),
            JoinModelB(id=10, value="foo", a_id=10),
            JoinModelB(id=11, value="bar", a_id=10),
        ).raise_on_errors()

        await connection.add(
            JoinModelA(id=11, name="foobar"), JoinModelB(id=12, value="foo", a_id=11)
        ).raise_on_errors()

        await connection.find(JoinModelB, JoinModelA.name == "testing").set(
            value="foobar"
        ).raise_on_errors()
        result = await connection.find(JoinModelB.value == "foobar").fetch.all()
        assert {m.id for m in result} == {10, 11}


@pytest.mark.asyncio
@parametrize_drivers()
async def test_join_counts(driver):
    join_collection = ModelCollection()

    @ommi_model(collection=join_collection)
    @dataclass
    class JoinModelA:
        id: int
        name: str

    @ommi_model(collection=join_collection)
    @dataclass
    class JoinModelB:
        id: int
        a_id: Annotated[int, ReferenceTo(JoinModelA.id)]

    async with driver as connection:
        schema = connection.schema(join_collection)
        await schema.delete_models().raise_on_errors()
        await schema.create_models().raise_on_errors()

        await connection.add(
            JoinModelA(id=10, name="testing"),
            JoinModelB(id=10, a_id=10),
            JoinModelB(id=11, a_id=10),
        ).raise_on_errors()

        await connection.add(
            JoinModelA(id=11, name="foobar"), JoinModelB(id=12, a_id=11)
        ).raise_on_errors()

        result = (
            await connection.find(JoinModelB, JoinModelA.name == "testing")
            .count()
            .value
        )
        assert result == 2


@pytest.mark.asyncio
@parametrize_drivers()
async def test_composite_keys(driver):
    composite_collection = ModelCollection()

    @ommi_model(collection=composite_collection)
    @dataclass
    class CompositeModelA:
        id1: Annotated[int, Key]
        id2: Annotated[int, Key]
        value: str

    @ommi_model(collection=composite_collection)
    @dataclass
    class CompositeModelB:
        id: int
        id1: Annotated[int, ReferenceTo(CompositeModelA.id1)]
        id2: Annotated[int, ReferenceTo(CompositeModelA.id2)]

    async with driver as connection:
        schema = connection.schema(composite_collection)
        await schema.delete_models().raise_on_errors()
        await schema.create_models().raise_on_errors()

        await connection.add(
            CompositeModelA(id1=10, id2=20, value="foo"),
            CompositeModelA(id1=10, id2=21, value="bar"),
            CompositeModelB(id=1, id1=10, id2=20),
            CompositeModelB(id=2, id1=10, id2=21),
        ).raise_on_errors()

        result = await connection.find(
            CompositeModelB, CompositeModelA.value == "foo"
        ).fetch.all()
        assert len(result) == 1
        assert result[0].id == 1

        result = (
            await connection.find(CompositeModelA, CompositeModelB.id == 1)
            .count()
            .value
        )
        assert result == 1

        await connection.find(CompositeModelA, CompositeModelB.id == 1).set(
            value="FOOBAR"
        ).raise_on_errors()
        result = await connection.find(CompositeModelA.value == "FOOBAR").fetch.all()
        assert len(result) == 1
        assert result[0].id1 == 10
        assert result[0].id2 == 20

        await connection.find(
            CompositeModelA, CompositeModelB.id == 1
        ).delete().raise_on_errors()
        result = await connection.find(CompositeModelA).fetch.all()
        assert len(result) == 1


@pytest.mark.asyncio
@parametrize_drivers()
async def test_composite_key_lazy_loads(driver):
    composite_collection = ModelCollection()

    @ommi_model(collection=composite_collection)
    @dataclass
    class CompositeModelA:
        id1: Annotated[int, Key]
        id2: Annotated[int, Key]
        value: str

    @ommi_model(collection=composite_collection)
    @dataclass
    class CompositeModelB:
        id: int
        id1: Annotated[int, ReferenceTo(CompositeModelA.id1)]
        id2: Annotated[int, ReferenceTo(CompositeModelA.id2)]

        a: LazyLoadEveryRelated[CompositeModelA]

    async with driver as connection:
        schema = connection.schema(composite_collection)
        await schema.delete_models().raise_on_errors()
        await schema.create_models().raise_on_errors()

        await connection.add(
            CompositeModelA(id1=10, id2=20, value="foo"),
            CompositeModelA(id1=10, id2=21, value="bar"),
            CompositeModelB(
                id=1,
                id1=10,
                id2=20,
            ),
        ).raise_on_errors()

        result = await connection.find(CompositeModelB).fetch.one()
        a = await result.a
        assert result.id == 1
        assert len(a) == 1
        assert a[0].value == "foo"


association_collection = ModelCollection()

@ommi_model(collection=association_collection)
@dataclass
class AssociationModelA:
    id: Annotated[int, Key]

    b: "LazyLoadEveryRelated[Annotated[AssociationModelB, AssociateUsing(AssociationTable)]]"


@ommi_model(collection=association_collection)
@dataclass
class AssociationModelB:
    id: Annotated[int, Key]


@ommi_model(collection=association_collection)
@dataclass
class AssociationTable:
    id_a: Annotated[int, Key | ReferenceTo(AssociationModelA.id)]
    id_b: Annotated[int, Key | ReferenceTo(AssociationModelB.id)]


@pytest.mark.asyncio
@parametrize_drivers()
async def test_association_tables(driver):
    async with driver as connection:
        schema = connection.schema(association_collection)
        await schema.delete_models().raise_on_errors()
        await schema.create_models().raise_on_errors()

        await connection.add(
            # A Models
            AssociationModelA(id=10),
            AssociationModelA(id=11),
            # B Models
            AssociationModelB(id=20),
            AssociationModelB(id=21),
            AssociationModelB(id=22),
            # Association Table
            AssociationTable(id_a=10, id_b=20),
            AssociationTable(id_a=10, id_b=21),
            AssociationTable(id_a=11, id_b=22),
        ).raise_on_errors()

        result = await connection.find(AssociationModelA.id == 10).fetch.one()
        b = await result.b
        assert result.id == 10
        assert len(b) == 2
        assert {m.id for m in b} == {20, 21}


@pytest.mark.asyncio
@parametrize_drivers()
async def test_transaction_commit(driver):
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class InnerTestModel:
        id: int

    async with driver as connection:
        await connection.schema(collection).delete_models().raise_on_errors()
        await connection.schema(collection).create_models().raise_on_errors()

        async with connection.transaction() as transaction:
            await transaction.add(
                InnerTestModel(10)
            ).raise_on_errors()

        result = await connection.find(InnerTestModel.id == 10).fetch.one()
        assert result.id == 10


@pytest.mark.asyncio
@parametrize_drivers()
async def test_transaction_rollback(driver):
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class InnerTestModel:
        id: int

    async with driver as connection:
        await connection.schema(collection).delete_models().raise_on_errors()
        await connection.schema(collection).create_models().raise_on_errors()

        async with connection.transaction() as transaction:
            await transaction.add(
                InnerTestModel(10)
            ).raise_on_errors()
            await transaction.rollback()

        result = await connection.find(InnerTestModel).fetch()
        assert len(result.value) == 0


@pytest.mark.asyncio
@parametrize_drivers()
async def test_transaction_exception(driver):
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class InnerTestModel:
        id: int

    class TestException(Exception): ...

    async with driver as connection:
        await connection.schema(collection).delete_models().raise_on_errors()
        await connection.schema(collection).create_models().raise_on_errors()

        with pytest.raises(TestException):
            async with connection.transaction() as transaction:
                await transaction.add(
                    InnerTestModel(10)
                ).raise_on_errors()

                raise TestException()

        result = await connection.find(InnerTestModel).fetch()
        assert len(result.value) == 0