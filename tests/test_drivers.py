from dataclasses import dataclass
from typing import Annotated, Generator

import pytest
import pytest_asyncio
import attrs
import pydantic
from ommi import BaseDriver

from ommi import StoreAs
from ommi.driver_context import UseDriver
from ommi.ext.drivers.sqlite import SQLiteDriver
from ommi.models.collections import ModelCollection
from ommi.models import ommi_model
from ommi.models.field_metadata import ReferenceTo, Key
from ommi.models.query_fields import (
    LazyLoadTheRelated,
    LazyLoadEveryRelated,
    AssociateUsing,
)
from ommi.query_ast import when

test_models = ModelCollection()


class WithModels:
    def __init__(self, driver, models):
        self.driver = driver
        self.models = models

    async def __aenter__(self):
        await self.driver.apply_schema(self.models)
        return

    async def __aexit__(self, *_):
        await self.driver.delete_schema(self.models)


@pytest.fixture(autouse=True)
def use_driver(driver):
    with UseDriver(driver):
        yield


@ommi_model(collection=test_models)
@dataclass
class TestModel:
    name: Annotated[str, StoreAs("username")]
    id: int = None


@pytest_asyncio.fixture(params=[SQLiteDriver], scope="function")
async def driver(request) -> Generator[BaseDriver, None, None]:
    async with request.param.connect() as driver:
        async with WithModels(driver, test_models):
            yield driver


@pytest.mark.asyncio()
async def test_async_batch_iterator_offset(driver):
    await driver.add([TestModel(name=f"dummy_{i}") for i in range(10)])
    result = await driver.fetch(when(TestModel).limit(5, 1)).get()
    assert result[0].name == "dummy_5"


@pytest.mark.asyncio()
async def test_insert_and_fetch(driver):
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class InnerTestModel:
        id: int
        name: str
        toggle: bool
        decimal: float

    async with WithModels(driver, collection):
        await driver.add(
            (model := InnerTestModel(10, "testing", True, 1.23),)
        )
        assert model.id == 10
        assert model.name == "testing"
        assert model.toggle == True
        assert model.decimal == 1.23

        result = await driver.fetch(when(InnerTestModel.id == 10)).one()
        assert result.id == model.id
        assert result.name == model.name
        assert result.toggle == model.toggle
        assert result.decimal == model.decimal


@pytest.mark.asyncio()
async def test_driver(driver):
    await driver.add([model := TestModel(name="dummy")])

    result = await driver.fetch(when(TestModel.name == "dummy")).one()
    assert result.name == model.name

    await driver.update(when(TestModel.id == result.id), {"name": "Dummy"})
    result = await driver.fetch(when(TestModel.id == result.id)).one()
    assert result.name == "Dummy"

    await driver.delete(when(TestModel.name == "Dummy"))
    result = await driver.fetch(when(TestModel.name == "Dummy")).get()
    assert len(result) == 0


@pytest.mark.asyncio()
async def test_fetch(driver):
    await driver.add([model := TestModel(name="dummy")])

    result = await driver.fetch(when(TestModel.name == "dummy")).one()
    assert result.name == model.name


@pytest.mark.asyncio()
async def test_update(driver):
    await driver.add([model := TestModel(name="dummy")])

    model.name = "Dummy"
    await driver.update(when(TestModel.name == "dummy"), {"name": "Dummy"})

    result = await driver.fetch(when(TestModel.name == "Dummy")).one()
    assert result.name == model.name


@pytest.mark.asyncio()
async def test_delete(driver):
    await driver.add([model := TestModel(name="dummy")])

    await driver.delete(when(TestModel.id == model.id))
    result = await driver.fetch(when(TestModel)).get()
    assert len(result) == 0


@pytest.mark.asyncio()
async def test_count(driver):
    await driver.add(
        [TestModel(name="dummy1"), TestModel(name="dummy2")]
    )

    result = await driver.count(when(TestModel))
    assert result == 2


@pytest.mark.asyncio()
async def test_sync_schema(driver):
    a, b = await driver.add(
        [
            TestModel(name="dummy1"),
            TestModel(name="dummy2"),
        ],
    )

    assert isinstance(a.id, int)
    assert isinstance(b.id, int)
    assert a.id != b.id


@pytest.mark.asyncio()
async def test_driver_delete_query(driver):
    await driver.add(
        [
            TestModel(name="dummy1"),
            TestModel(name="dummy2"),
        ],
    )

    await driver.delete(when(TestModel.name == "dummy1"))

    r = await driver.fetch(when(TestModel)).get()
    assert len(r) == 1
    assert r[0].name == "dummy2"


@pytest.mark.asyncio()
async def test_driver_update_query(driver):
    await driver.add(
        [
            TestModel(name="dummy1"),
            TestModel(name="dummy2"),
            TestModel(name="dummy3"),
            TestModel(name="dummy4"),
        ],
    )

    ignore_id, new_name = 2, "dummy"
    await driver.update(when(TestModel.id != ignore_id), {"name": new_name})
    result = await driver.fetch(when(TestModel.name == new_name)).get()
    assert len(result) > 1
    assert all(m.name == new_name for m in result)
    assert all(m.id != ignore_id for m in result)

    ignore_id, new_name = 1, "DUMMY"
    await driver.update(
        when(TestModel.id != ignore_id).And(TestModel.name == "dummy"),
        {"name": new_name},
    )
    result = await driver.fetch(when(TestModel.name == new_name)).get()
    assert len(result) > 1
    assert all(m.name == new_name for m in result)
    assert all(m.id != ignore_id for m in result)


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


@pytest.mark.asyncio()
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
    async with WithModels(driver, lazy_load_field_collection):
        model_a, model_b, _ = models

        await driver.add([a := model_a(id=10, name="testing")])
        await driver.add([b := model_b(id=10, a_id=a.id)])
        await driver.add([c := model_b(id=11, a_id=a.id)])

        b_a = await b.a
        assert b_a.id == a.id

        a_b = await a.b
        assert {b.id, c.id} == {m.id for m in a_b}


@pytest.mark.asyncio()
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

    async with WithModels(driver, join_collection):
        await driver.add(
            [
                JoinModelA(id=10, name="testing"),
                JoinModelB(id=10, a_id=10),
                JoinModelB(id=11, a_id=10),
            ],
        )

        await driver.add(
            [JoinModelA(id=11, name="foobar"), JoinModelB(id=12, a_id=11)],
        )

        result = await driver.fetch(
            when(JoinModelB, JoinModelA.name == "testing")
        ).get()
        assert {10, 11} == {m.id for m in result}


@pytest.mark.asyncio()
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

    async with WithModels(driver, join_collection):
        await driver.add(
            [
                JoinModelA(id=10, name="testing"),
                JoinModelB(id=10, a_id=10),
                JoinModelB(id=11, a_id=10),
            ],
        )

        await driver.add(
            [JoinModelA(id=11, name="foobar"), JoinModelB(id=12, a_id=11)],
        )

        await driver.delete(
            when(JoinModelB, JoinModelA.name == "testing")
        )
        result = await driver.fetch(when(JoinModelB)).get()
        assert {m.id for m in result} == {12}


@pytest.mark.asyncio()
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

    async with WithModels(driver, join_collection):
        await driver.add(
            [
                JoinModelA(id=10, name="testing"),
                JoinModelB(id=10, value="foo", a_id=10),
                JoinModelB(id=11, value="bar", a_id=10),
            ],
        )

        await driver.add(
            [JoinModelA(id=11, name="foobar"), JoinModelB(id=12, value="foo", a_id=11)],
        )

        await driver.update(when(JoinModelB, JoinModelA.name == "testing"), {"value": "foobar"})
        result = await driver.fetch(when(JoinModelB.value == "foobar")).get()
        assert {m.id for m in result} == {10, 11}


@pytest.mark.asyncio()
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

    async with WithModels(driver, join_collection):
        await driver.add(
            [
                JoinModelA(id=10, name="testing"),
                JoinModelB(id=10, a_id=10),
                JoinModelB(id=11, a_id=10),
            ],
        )

        await driver.add(
            [JoinModelA(id=11, name="foobar"), JoinModelB(id=12, a_id=11),]
        )

        result = await driver.count(when(JoinModelB, JoinModelA.name == "testing"))
        assert result == 2


@pytest.mark.asyncio()
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

    async with WithModels(driver, composite_collection):
        await driver.add(
            [
                CompositeModelA(id1=10, id2=20, value="foo"),
                CompositeModelA(id1=10, id2=21, value="bar"),
                CompositeModelB(id=1, id1=10, id2=20),
                CompositeModelB(id=2, id1=10, id2=21),
            ],
        )

        result = await driver.fetch(
            when(CompositeModelB, CompositeModelA.value == "foo")
        ).get()
        assert len(result) == 1
        assert result[0].id == 1

        result = await driver.count(when(CompositeModelA, CompositeModelB.id == 1))
        assert result == 1

        await driver.update(when(CompositeModelA, CompositeModelB.id == 1), {"value": "FOOBAR"})
        result = await driver.fetch(when(CompositeModelA.value == "FOOBAR")).get()
        assert len(result) == 1
        assert result[0].id1 == 10
        assert result[0].id2 == 20

        await driver.delete(
            when(CompositeModelA, CompositeModelB.id == 1)
        )
        result = await driver.fetch(when(CompositeModelA)).get()
        assert len(result) == 1


@pytest.mark.asyncio()
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

    async with WithModels(driver, composite_collection):
        await driver.add(
            [
                CompositeModelA(id1=10, id2=20, value="foo"),
                CompositeModelA(id1=10, id2=21, value="bar"),
                CompositeModelB(
                    id=1,
                    id1=10,
                    id2=20,
                ),
            ],
        )

        result = await driver.fetch(when(CompositeModelB)).one()
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


@pytest.mark.asyncio()
async def test_association_tables(driver):
    async with WithModels(driver, association_collection):
        await driver.add(
            [
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
            ],
        )

        result = await driver.fetch(when(AssociationModelA.id == 10)).one()
        b = await result.b
        assert result.id == 10
        assert len(b) == 2
        assert {m.id for m in b} == {20, 21}


@pytest.mark.asyncio()
async def test_transaction_commit(driver):
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class InnerTestModel:
        id: int

    async with WithModels(driver, collection):
        async with driver.transaction() as transaction:
            await transaction.add(
                [InnerTestModel(10)],
            )

        result = await driver.fetch(when(InnerTestModel.id == 10)).one()
        assert result.id == 10


@pytest.mark.asyncio()
async def test_transaction_rollback(driver):
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class InnerTestModel:
        id: int

    async with WithModels(driver, collection):
        async with driver.transaction() as transaction:
            await transaction.add(
                [InnerTestModel(10)],
            )
            await transaction.rollback()

        result = await driver.count(when(InnerTestModel))
        assert result == 0


@pytest.mark.asyncio()
async def test_transaction_exception(driver):
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class InnerTestModel:
        id: int

    class TestException(Exception): ...

    async with WithModels(driver, collection):
        with pytest.raises(TestException):
            async with driver.transaction() as transaction:
                await transaction.add(
                    [InnerTestModel(10)],
                )

                raise TestException()

        result = await driver.fetch(when(InnerTestModel)).get()
        assert len(result) == 0
