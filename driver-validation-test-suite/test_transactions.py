"""
Tests for transaction behavior to validate consistent handling across all drivers.
"""
import asyncio
from dataclasses import dataclass
from typing import Any, List

import pytest
from ommi import BaseDriver, ommi_model
from ommi.models.collections import ModelCollection
from ommi.query_ast import when

from conftest import WithModels


@pytest.mark.asyncio
async def test_transaction_commit(driver: BaseDriver):
    """Test that committed transactions persist their changes."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class TestModel:
        name: str
        id: int = None

    async with WithModels(driver, collection):
        # Begin transaction, add a model, and commit
        async with driver.transaction() as transaction:
            await transaction.add([TestModel(name="committed_item")])
            # Transaction auto-commits on exit

        # Verify the item persisted outside the transaction
        result = await driver.fetch(when(TestModel.name == "committed_item")).one()
        assert result.name == "committed_item"


@pytest.mark.asyncio
async def test_transaction_rollback(driver: BaseDriver):
    """Test that rolled back transactions discard their changes."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class TestModel:
        name: str
        id: int = None

    async with WithModels(driver, collection):
        # Begin transaction, add a model, but roll back
        async with driver.transaction() as transaction:
            await transaction.add([TestModel(name="rollback_item")])
            await transaction.rollback()

        # Verify the item did not persist
        count = await driver.count(when(TestModel.name == "rollback_item"))
        assert count == 0, "Rolled back model should not be persisted"


@pytest.mark.asyncio
async def test_transaction_exception_rollback(driver: BaseDriver):
    """Test that transactions roll back when an exception occurs."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class TestModel:
        name: str
        id: int = None

    class TestException(Exception):
        pass

    async with WithModels(driver, collection):
        # Begin transaction, add a model, but raise an exception
        with pytest.raises(TestException):
            async with driver.transaction() as transaction:
                await transaction.add([TestModel(name="exception_item")])
                raise TestException("Test exception to trigger rollback")

        # Verify the item did not persist
        count = await driver.count(when(TestModel.name == "exception_item"))
        assert count == 0, "Model from failed transaction should not be persisted"

