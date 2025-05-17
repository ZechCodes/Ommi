from dataclasses import dataclass
from typing import Annotated

import pytest
import pytest_asyncio
from tramp.results import Result

from ommi import ommi_model
from ommi.ext.drivers.sqlite import SQLiteDriver
from ommi.models.collections import ModelCollection
from ommi.models.field_metadata import ReferenceTo
from ommi.models.query_fields import AssociateUsing, LazyLoadTheRelated, LazyLoadEveryRelated
from ommi.query_ast import when

collection = ModelCollection()


@ommi_model(collection=collection)
@dataclass
class ModelA:
    id: int


@ommi_model(collection=collection)
@dataclass
class ModelB:
    id: int
    a_id: Annotated[int, ReferenceTo(ModelA)]


@ommi_model(collection=collection)
@dataclass
class ModelC:
    id: int

    a: "LazyLoadEveryRelated[Annotated[ModelA, AssociateUsing(AssociationTable)]]"


@ommi_model(collection=collection)
@dataclass
class AssociationTable:
    a_id: Annotated[int, ReferenceTo(ModelA.id)]
    c_id: Annotated[int, ReferenceTo(ModelC.id)]


a = ModelA(id=1)
b = ModelB(id=2, a_id=a.id)


@pytest_asyncio.fixture
async def driver():
    driver = SQLiteDriver.connect()
    await driver.apply_schema(collection)
    await driver.add((a, b))
    yield driver
    await driver.disconnect()


@pytest.mark.asyncio
async def test_lazy_load_the_related(driver):
    relation = LazyLoadTheRelated(lambda:when(ModelB.a_id == a.id), driver=driver)
    result = await relation.result

    assert isinstance(result, Result.Value)

    await relation.value
    assert await relation.value == b


@pytest.mark.asyncio
async def test_load_relation(driver):
    relation = LazyLoadEveryRelated(lambda:when(ModelB.a_id == a.id), driver=driver)
    result = await relation.result

    assert isinstance(result, Result.Value)

    await relation.value
    assert await relation.value == [b]


@pytest.mark.asyncio
async def test_associate_using_strategy(driver):
    async with driver:
        # Add test data to the database
        c = ModelC(id=3)
        a2 = ModelA(id=4)
        association_a = AssociationTable(a_id=a.id, c_id=c.id)
        association_b = AssociationTable(a_id=a2.id, c_id=c.id)
        await driver.add((c, a2, association_a, association_b))

        # Get the result
        result = await c.a.result
        assert isinstance(result, Result.Value)
        assert result.value == [a, a2]
