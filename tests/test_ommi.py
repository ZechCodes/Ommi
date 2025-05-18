import sqlite3
from contextlib import suppress
from dataclasses import dataclass

import pytest
import pytest_asyncio
from _pytest.python_api import raises

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
        await self.db.use_models(self.collection)
        return self.db

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.db.remove_models(self.collection)


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


@pytest.mark.asyncio
async def test_ommi_use_and_remove_models(db):
    new_collection = ModelCollection()

    @ommi_model(collection=new_collection)
    @dataclass
    class NewModel:
        id: int
        value: str

    # Test use_models
    await db.use_models(new_collection)

    # Add a model to verify the schema was created
    await db.add(NewModel(1, "test")).or_raise()
    result = await db.find(NewModel.id == 1).one.or_raise()
    assert result.id == 1
    assert result.value == "test"

    # Test remove_models
    await db.remove_models(new_collection)

    # Try to use the model again to verify schema was removed
    # This should fail, but we'll catch the exception
    with raises(sqlite3.OperationalError):
        await db.add(NewModel(2, "test2")).or_raise()


@pytest.mark.asyncio
async def test_transaction_commit(db):
    # Start a transaction
    async with db.transaction() as transaction:
        # Add a model within the transaction
        await transaction.add(TestModel(1, "test_transaction")).or_raise()
        # Commit happens automatically when exiting the context

    # Verify the model was committed
    result = await db.find(TestModel.id == 1).one.or_raise()
    assert result.id == 1
    assert result.name == "test_transaction"


@pytest.mark.asyncio
async def test_transaction_rollback(db):
    # Start a transaction
    async with db.transaction() as transaction:
        # Add a model within the transaction
        await transaction.add(TestModel(2, "test_rollback")).or_raise()

        # Manually rollback the transaction
        await transaction.rollback()

    # Verify the model was not committed
    result = await db.find(TestModel.id == 2).count.or_raise()
    assert result == 0


@pytest.mark.asyncio
async def test_transaction_exception_rollback(db):
    with suppress(ValueError), raises(ValueError):  # PyCharm doesn't realize that raises suppresses, so hack to make it happy
        async with db.transaction() as transaction:
            # Add a model within the transaction
            await transaction.add(TestModel(3, "test_exception")).or_raise()
            # Raise an exception to trigger rollback
            raise ValueError("Test exception")

    # Verify the model was not committed due to the exception
    result = await db.find(TestModel.id == 3).count.or_raise()
    assert result == 0


@pytest.mark.asyncio
async def test_transaction_explicit_commit(db):
    with suppress(ValueError), raises(ValueError):  # PyCharm doesn't realize that raises suppresses, so hack to make it happy
        async with db.transaction() as transaction:
            await transaction.add(TestModel(4, "test_explicit_commit")).or_raise()
            await transaction.commit()
            raise ValueError("Test exception")

    result = await db.find(TestModel.id == 4).one.or_raise()
    assert result.id == 4
    assert result.name == "test_explicit_commit"
