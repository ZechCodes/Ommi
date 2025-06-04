"""
Tests for complex query construction and execution to validate consistent behavior across all drivers.
"""
from dataclasses import dataclass
import datetime
from typing import Annotated, List, Optional

import pytest
from ommi import BaseDriver, ommi_model
from ommi.models.collections import ModelCollection
from ommi.models.field_metadata import ReferenceTo
from ommi.query_ast import when
from ommi.models.query_fields import LazyLoadTheRelated, LazyLoadEveryRelated

from conftest import WithModels


@pytest.mark.asyncio
async def test_complex_and_or_conditions(driver: BaseDriver):
    """Test complex AND/OR query conditions."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class Product:
        name: str
        category: str
        price: float
        in_stock: bool
        id: int = None

    async with WithModels(driver, collection):
        # Create test data
        await driver.add([
            Product(name="Product A", category="Electronics", price=99.99, in_stock=True),
            Product(name="Product B", category="Electronics", price=149.99, in_stock=False),
            Product(name="Product C", category="Books", price=19.99, in_stock=True),
            Product(name="Product D", category="Books", price=29.99, in_stock=True),
            Product(name="Product E", category="Clothing", price=49.99, in_stock=True),
            Product(name="Product F", category="Clothing", price=79.99, in_stock=False),
        ])
        
        # Complex query: (category == "Electronics" OR price < 25) AND in_stock == True
        query = when(
            (Product.category == "Electronics").Or(Product.price < 25)
        ).And(Product.in_stock == True)
        
        results = await driver.fetch(query).get()
        
        # Should match: 
        # - Product A (Electronics, in_stock=True)
        # - Product C (Books, price=19.99, in_stock=True)
        assert len(results) == 2
        assert {p.name for p in results} == {"Product A", "Product C"}
        
        # Complex query with nested conditions
        # ((category == "Books" AND price > 25) OR (category == "Clothing" AND price < 60)) AND in_stock == True
        query = when(
            (
                (Product.category == "Books").And(Product.price > 25)
            ).Or(
                (Product.category == "Clothing").And(Product.price < 60)
            )
        ).And(Product.in_stock == True)
        
        results = await driver.fetch(query).get()
        
        # Should match:
        # - Product D (Books, price=29.99, in_stock=True)
        # - Product E (Clothing, price=49.99, in_stock=True)
        assert len(results) == 2
        assert {p.name for p in results} == {"Product D", "Product E"}







@pytest.mark.asyncio
async def test_order_by_operations(driver: BaseDriver):
    """Test ORDER BY operations (sort, asc, desc)."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class SortableItem:
        name: str
        priority: int
        created_at: str  # Using string for date for simplicity
        id: int = None

    async with WithModels(driver, collection):
        # Create test data with different ordering characteristics
        await driver.add([
            SortableItem(name="Item C", priority=3, created_at="2023-03-01"),
            SortableItem(name="Item A", priority=1, created_at="2023-01-01"),
            SortableItem(name="Item E", priority=5, created_at="2023-05-01"),
            SortableItem(name="Item B", priority=2, created_at="2023-02-01"),
            SortableItem(name="Item D", priority=4, created_at="2023-04-01"),
        ])
        
        # Test single field ascending sort
        query = when(SortableItem).sort(SortableItem.name.asc)
        results = await driver.fetch(query).get()
        
        # Verify order: A, B, C, D, E
        assert [item.name for item in results] == ["Item A", "Item B", "Item C", "Item D", "Item E"]
        
        # Test single field descending sort
        query = when(SortableItem).sort(SortableItem.priority.desc)
        results = await driver.fetch(query).get()
        
        # Verify order: E, D, C, B, A
        assert [item.name for item in results] == ["Item E", "Item D", "Item C", "Item B", "Item A"]
        
        # Test multi-field sort (same direction)
        # First create items with same priority but different names
        await driver.add([
            SortableItem(name="Item X", priority=3, created_at="2023-06-01"),
            SortableItem(name="Item Y", priority=3, created_at="2023-07-01"),
        ])
        
        query = when(SortableItem).sort(SortableItem.priority.asc, SortableItem.name.asc)
        results = await driver.fetch(query).get()
        
        # Items with priority 3 should be sorted by name: C, X, Y
        priority_3_items = [item for item in results if item.priority == 3]
        assert [item.name for item in priority_3_items] == ["Item C", "Item X", "Item Y"]
        
        # Test multi-field sort (different directions)
        query = when(SortableItem).sort(SortableItem.priority.asc, SortableItem.name.desc)
        results = await driver.fetch(query).get()
        
        # Items with priority 3 should be sorted by name in descending order: Y, X, C
        priority_3_items = [item for item in results if item.priority == 3]
        assert [item.name for item in priority_3_items] == ["Item Y", "Item X", "Item C"]


@pytest.mark.asyncio
async def test_join_with_complex_conditions(driver: BaseDriver):
    """Test complex conditions across joined tables."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class Category:
        name: str
        active: bool
        id: int = None

    @ommi_model(collection=collection)
    @dataclass
    class Product:
        name: str
        price: float
        featured: bool
        category_id: Annotated[int, ReferenceTo(Category.id)]
        id: int = None

    async with WithModels(driver, collection):
        # Create categories
        categories = await driver.add([
            Category(name="Electronics", active=True),
            Category(name="Books", active=True),
            Category(name="Clothing", active=False),  # Inactive category
        ])
        
        # Create products
        await driver.add([
            # Electronics products
            Product(name="Laptop", price=999.99, featured=True, category_id=categories[0].id),
            Product(name="Phone", price=599.99, featured=True, category_id=categories[0].id),
            Product(name="Headphones", price=99.99, featured=False, category_id=categories[0].id),
            
            # Books products
            Product(name="Fiction Book", price=19.99, featured=False, category_id=categories[1].id),
            Product(name="Non-fiction Book", price=29.99, featured=True, category_id=categories[1].id),
            
            # Clothing products (inactive category)
            Product(name="T-shirt", price=24.99, featured=False, category_id=categories[2].id),
            Product(name="Jeans", price=49.99, featured=True, category_id=categories[2].id),
        ])
        
        # Complex join query: 
        # Get featured products from active categories where price > 50
        query = when(
            Product,
            Product.featured == True,
            Category.active == True,
            Product.price > 50
        )
        
        results = await driver.fetch(query).get()
        
        # Should match: Laptop, Phone (Non-fiction Book fails price > 50 condition)
        assert len(results) == 2
        assert {p.name for p in results} == {"Laptop", "Phone"}
        
        # More complex query: 
        # Get products where:
        # (category is Electronics AND price > 500) OR (category is Books AND featured == True)
        query = when(
            Product,
            (
                (Category.name == "Electronics").And(Product.price > 500)
            ).Or(
                (Category.name == "Books").And(Product.featured == True)
            )
        )
        
        results = await driver.fetch(query).get()
        
        # Should match: Laptop, Phone, Non-fiction Book
        assert len(results) == 3
        assert {p.name for p in results} == {"Laptop", "Phone", "Non-fiction Book"}


@pytest.mark.asyncio
async def test_batch_execution_with_limits(driver: BaseDriver):
    """Test batch execution with limits and pagination."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class BatchItem:
        name: str
        value: int
        id: int = None

    async with WithModels(driver, collection):
        # Create a large batch of test data
        batch_size = 100
        await driver.add([
            BatchItem(name=f"Item {i}", value=i)
            for i in range(batch_size)
        ])
        
        # Test fetch with limit
        limit = 10
        query = when(BatchItem).limit(limit)
        results = await driver.fetch(query).get()
        
        assert len(results) == limit
        
        # Test fetch with limit and offset (pagination)
        page_size = 20
        total_pages = batch_size // page_size
        
        # Collect all items across all pages
        all_fetched_items = []
        
        for page in range(total_pages):
            offset = page * page_size
            query = when(BatchItem).limit(page_size, offset)
            page_results = await driver.fetch(query).get()
            
            assert len(page_results) == page_size, f"Page {page} should have {page_size} items"
            all_fetched_items.extend(page_results)
        
        # Verify we fetched all items without duplicates
        assert len(all_fetched_items) == batch_size
        assert len({item.id for item in all_fetched_items}) == batch_size


@pytest.mark.asyncio
async def test_async_batch_iterator(driver: BaseDriver):
    """Test the AsyncBatchIterator behavior."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class StreamItem:
        index: int
        id: int = None

    async with WithModels(driver, collection):
        # Create a large batch of test data
        item_count = 200
        await driver.add([
            StreamItem(index=i)
            for i in range(item_count)
        ])
        
        # Create a query and get an AsyncBatchIterator
        query = when(StreamItem).sort(StreamItem.index.asc)
        result = driver.fetch(query)
        
        # Count manually by iterating
        count = 0
        indexes = []
        
        async for item in result:
            count += 1
            indexes.append(item.index)
        
        # Verify all items were fetched and in the correct order
        assert count == item_count
        assert indexes == list(range(item_count))
        
        # Test AsyncBatchIterator slicing
        result = driver.fetch(query)
        slice_result = await result[10:20].get()
        
        assert len(slice_result) == 10
        assert [item.index for item in slice_result] == list(range(10, 20))


@pytest.mark.asyncio
async def test_null_value_handling(driver: BaseDriver):
    """Test handling of NULL/None values in queries."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class OptionalFieldModel:
        name: str
        description: Optional[str] = None
        value: Optional[int] = None
        id: int = None

    async with WithModels(driver, collection):
        # Create test data with various null/None values
        await driver.add([
            OptionalFieldModel(name="Item 1", description="Description 1", value=10),
            OptionalFieldModel(name="Item 2", description="Description 2", value=None),
            OptionalFieldModel(name="Item 3", description=None, value=30),
            OptionalFieldModel(name="Item 4", description=None, value=None),
        ])
        
        # Test IS NULL condition
        query = when(OptionalFieldModel.description == None)
        results = await driver.fetch(query).get()
        
        assert len(results) == 2
        assert {r.name for r in results} == {"Item 3", "Item 4"}
        
        # Test IS NOT NULL condition
        query = when(OptionalFieldModel.description != None)
        results = await driver.fetch(query).get()
        
        assert len(results) == 2
        assert {r.name for r in results} == {"Item 1", "Item 2"}
        
        # Test combined null conditions
        query = when(OptionalFieldModel.description == None, OptionalFieldModel.value != None)
        results = await driver.fetch(query).get()
        
        assert len(results) == 1
        assert results[0].name == "Item 3"
        
        # Test OR with null
        query = when((OptionalFieldModel.description == None).Or(OptionalFieldModel.value == None))
        results = await driver.fetch(query).get()
        
        assert len(results) == 3
        assert {r.name for r in results} == {"Item 2", "Item 3", "Item 4"} 