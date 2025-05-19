"""
Tests for basic CRUD operations to validate consistent behavior across all drivers.
"""
from dataclasses import dataclass
from typing import Any, Annotated

import pytest
from ommi import ommi_model, StoreAs
from ommi.models.collections import ModelCollection
from ommi.query_ast import when
from ommi import BaseDriver

from conftest import WithModels


# Basic model for testing simple CRUD operations
@dataclass
class BasicModel:
    name: Annotated[str, StoreAs("username")]
    id: int = None


@pytest.mark.asyncio
async def test_insert_and_fetch(driver: BaseDriver):
    """Test that a model can be inserted and then fetched correctly."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class TestModel:
        id: int
        name: str
        toggle: bool
        decimal: float

    async with WithModels(driver, collection):
        # Add a model
        await driver.add((model := TestModel(10, "testing", True, 1.23),))
        
        # Verify the model was added with correct values
        assert model.id == 10
        assert model.name == "testing"
        assert model.toggle is True
        assert model.decimal == 1.23

        # Fetch the model and verify it matches
        result = await driver.fetch(when(TestModel.id == 10)).one()
        assert result.id == model.id
        assert result.name == model.name
        assert result.toggle == model.toggle
        assert result.decimal == model.decimal


@pytest.mark.asyncio
async def test_basic_crud_operations(driver: BaseDriver):
    """Test the full CRUD lifecycle (create, read, update, delete)."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class TestModel:
        name: str
        id: int = None

    async with WithModels(driver, collection):
        # Create
        await driver.add([model := TestModel(name="test_item")])
        assert model.id is not None, "ID should be assigned after add"

        # Read
        result = await driver.fetch(when(TestModel.name == "test_item")).one()
        assert result.name == model.name
        assert result.id == model.id

        # Update
        await driver.update(when(TestModel.id == result.id), {"name": "updated_item"})
        updated = await driver.fetch(when(TestModel.id == result.id)).one()
        assert updated.name == "updated_item"

        # Delete
        await driver.delete(when(TestModel.id == result.id))
        count = await driver.count(when(TestModel))
        assert count == 0


@pytest.mark.asyncio
async def test_batch_insert(driver: BaseDriver):
    """Test inserting multiple models in a batch."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class TestModel:
        name: str
        id: int = None

    async with WithModels(driver, collection):
        # Add multiple models at once
        models = [TestModel(name=f"item_{i}") for i in range(10)]
        added_models = await driver.add(models)
        
        # Check all models were added with unique IDs
        ids = {model.id for model in added_models}
        assert len(ids) == 10, "Each model should have a unique ID"
        
        # Verify we can fetch all models
        all_models = await driver.fetch(when(TestModel)).get()
        assert len(all_models) == 10


@pytest.mark.asyncio
async def test_count_operation(driver: BaseDriver):
    """Test counting records with various conditions."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class TestModel:
        name: str
        category: str
        id: int = None

    async with WithModels(driver, collection):
        # Add mixed models
        await driver.add([
            TestModel(name="item1", category="A"),
            TestModel(name="item2", category="A"),
            TestModel(name="item3", category="B"),
            TestModel(name="item4", category="B"),
            TestModel(name="item5", category="C"),
        ])
        
        # Count all
        count_all = await driver.count(when(TestModel))
        assert count_all == 5
        
        # Count with condition
        count_a = await driver.count(when(TestModel.category == "A"))
        assert count_a == 2
        
        count_not_a = await driver.count(when(TestModel.category != "A"))
        assert count_not_a == 3
        
        # Complex condition
        count_a_or_b = await driver.count(
            when(TestModel.category == "A").Or(TestModel.category == "B")
        )
        assert count_a_or_b == 4


@pytest.mark.asyncio
async def test_complex_update(driver: BaseDriver):
    """Test updating records with complex conditions."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class TestModel:
        name: str
        status: str
        value: int
        id: int = None

    async with WithModels(driver, collection):
        # Add test data
        await driver.add([
            TestModel(name="item1", status="active", value=10),
            TestModel(name="item2", status="active", value=20),
            TestModel(name="item3", status="inactive", value=30),
            TestModel(name="item4", status="active", value=40),
            TestModel(name="item5", status="inactive", value=50),
        ])
        
        # Update active items with value > 15
        await driver.update(
            when(TestModel.status == "active").And(TestModel.value > 15),
            {"status": "premium"}
        )
        
        # Verify correct items were updated
        premium_items = await driver.fetch(when(TestModel.status == "premium")).get()
        assert len(premium_items) == 2
        premium_names = {item.name for item in premium_items}
        assert premium_names == {"item2", "item4"}
        
        # Verify other items weren't changed
        active_items = await driver.fetch(when(TestModel.status == "active")).get()
        assert len(active_items) == 1
        assert active_items[0].name == "item1"


@pytest.mark.asyncio
async def test_batch_delete(driver: BaseDriver):
    """Test deleting multiple records with a single operation."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class TestModel:
        name: str
        category: str
        id: int = None

    async with WithModels(driver, collection):
        # Add test data
        await driver.add([
            TestModel(name="item1", category="delete"),
            TestModel(name="item2", category="delete"),
            TestModel(name="item3", category="keep"),
            TestModel(name="item4", category="delete"),
            TestModel(name="item5", category="keep"),
        ])
        
        # Delete all items in "delete" category
        await driver.delete(when(TestModel.category == "delete"))
        
        # Verify only the correct items were deleted
        remaining = await driver.fetch(when(TestModel)).get()
        assert len(remaining) == 2
        categories = {item.category for item in remaining}
        assert categories == {"keep"}


@pytest.mark.asyncio
async def test_read_with_limit_and_offset(driver: BaseDriver):
    """Test fetching records with limit and offset for pagination."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class TestModel:
        name: str
        id: int = None

    async with WithModels(driver, collection):
        # Add 20 items
        await driver.add([TestModel(name=f"item_{i}") for i in range(20)])
        
        # Fetch with limit
        page1 = await driver.fetch(when(TestModel).limit(5)).get()
        assert len(page1) == 5
        
        # Fetch with limit and offset
        page2 = await driver.fetch(when(TestModel).limit(5, 5)).get()
        assert len(page2) == 5
        assert page1[0].id != page2[0].id
        
        # Verify no overlap between pages
        page1_ids = {item.id for item in page1}
        page2_ids = {item.id for item in page2}
        assert not page1_ids.intersection(page2_ids)


@pytest.mark.asyncio
async def test_unicode_handling(driver: BaseDriver):
    """Test that drivers properly handle Unicode text."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class UnicodeModel:
        text: str
        id: int = None

    async with WithModels(driver, collection):
        # Add models with various Unicode characters
        test_strings = [
            "English text",
            "中文测试文本",  # Chinese
            "Русский текст",  # Russian
            "日本語テスト",   # Japanese
            "🚀 Emoji test 🔥",  # Emojis
            "Mixed: ñáéíóú 你好 こんにちは",  # Mixed scripts
        ]
        
        for text in test_strings:
            await driver.add([UnicodeModel(text=text)])
            
        # Fetch and verify each string
        for text in test_strings:
            result = await driver.fetch(when(UnicodeModel.text == text)).one()
            assert result.text == text, f"Unicode text '{text}' was not preserved" 