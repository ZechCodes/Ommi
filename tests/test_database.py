from dataclasses import dataclass

import pytest

from ommi import OmmiDatabase, ommi_model
from ommi.database import OmmiTransaction
from ommi.database.actions import OmmiAction, OmmiActionQuery, OmmiUpdateAction, OmmiUpdateActionQuery
from ommi.models.collections import ModelCollection
from ommi.utils.awaitable_results import AwaitableResult

test_collection = ModelCollection()


@ommi_model(collection=test_collection)
@dataclass
class TestModel:
    string: str
    integer: int


class DummyTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None

    async def add(self, *items):
        return None

    async def delete(self, query):
        return None

    async def fetch(self, query):
        return []

    async def sync_schema(self, model_collection):
        return None

    async def update(self, query, **kwargs):
        return None


class DummyDriver:
    def transaction(self):
        return DummyTransaction()

    async def add(self, transaction, *items):
        return None

    async def delete(self, transaction, query):
        return None

    async def fetch(self, transaction, query):
        return None

    async def update(self, transaction, query, **kwargs):
        return None

    async def sync_schema(self, model_collection):
        return None


@pytest.fixture
def dummy_db():
    return OmmiDatabase(DummyDriver())


@pytest.mark.asyncio
async def test_add_action(dummy_db):
    action = dummy_db.add(TestModel("test", 1))
    assert isinstance(action, AwaitableResult)

    assert await action.raise_on_errors() is None


@pytest.mark.asyncio
async def test_delete_action(dummy_db):
    action = dummy_db.delete[TestModel]
    assert isinstance(action, OmmiAction)

    action = action.matching(TestModel.string == "test")
    assert isinstance(action, OmmiActionQuery)

    assert await action.result.raise_on_errors() is None


@pytest.mark.asyncio
async def test_fetch_action(dummy_db):
    action = dummy_db.fetch[TestModel]
    assert isinstance(action, OmmiAction)

    action = action.matching(TestModel.string == "test")
    assert isinstance(action, OmmiActionQuery)

    assert await action.result.raise_on_errors() == []


@pytest.mark.asyncio
async def test_sync_schema_action(dummy_db):
    action = dummy_db.sync_schema(test_collection)
    assert isinstance(action, AwaitableResult)

    assert await action.raise_on_errors() is None


@pytest.mark.asyncio
async def test_update_action(dummy_db):
    action = dummy_db.update[TestModel]
    assert isinstance(action, OmmiUpdateAction)

    action = action.matching(TestModel.string == "test")
    assert isinstance(action, OmmiUpdateActionQuery)

    assert await action.set(integer=2).raise_on_errors() is None


def test_transaction_type(dummy_db):
    transaction = dummy_db.transaction()
    assert isinstance(transaction, OmmiTransaction)