"""
Tests for schema management operations to validate consistent behavior across all drivers.
"""
from dataclasses import dataclass
from typing import Annotated, Dict, List, Optional

import pytest
from ommi import BaseDriver, ommi_model, StoreAs
from ommi.models.collections import ModelCollection
from ommi.models.field_metadata import ReferenceTo, Key
from ommi.query_ast import when

from conftest import WithModels


@pytest.mark.asyncio
async def test_basic_schema_creation(driver: BaseDriver):
    """Test basic schema creation and deletion."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class BasicModel:
        name: str
        value: int
        active: bool = True
        id: int = None

    # Apply schema
    await driver.apply_schema(collection)
    
    # Test schema by adding a record
    await driver.add([BasicModel(name="Test Item", value=123)])
    
    # Verify record exists
    result = await driver.fetch(when(BasicModel.name == "Test Item")).one()
    assert result.name == "Test Item"
    assert result.value == 123
    assert result.active == True
    
    # Delete schema
    await driver.delete_schema(collection)
    
    # Verify schema is gone - this should fail with an appropriate exception
    with pytest.raises(Exception):
        await driver.fetch(when(BasicModel)).get()


@pytest.mark.asyncio
async def test_schema_with_custom_column_names(driver: BaseDriver):
    """Test schema creation with custom column names using StoreAs."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class RenamedModel:
        user_name: Annotated[str, StoreAs("username")]
        email_address: Annotated[str, StoreAs("email")]
        created_timestamp: Annotated[str, StoreAs("created_at")]
        id: int = None

    async with WithModels(driver, collection):
        # Add a record
        model = RenamedModel(
            user_name="test_user",
            email_address="test@example.com",
            created_timestamp="2023-01-01"
        )
        await driver.add([model])
        
        # Fetch and verify
        result = await driver.fetch(when(RenamedModel.user_name == "test_user")).one()
        assert result.user_name == "test_user"
        assert result.email_address == "test@example.com"
        assert result.created_timestamp == "2023-01-01"


@pytest.mark.asyncio
async def test_schema_with_composite_keys(driver: BaseDriver):
    """Test schema creation with composite keys."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class CompositeKeyModel:
        region_code: Annotated[str, Key]
        item_code: Annotated[str, Key]
        description: str

    async with WithModels(driver, collection):
        # Add records with the same region_code but different item_code
        await driver.add([
            CompositeKeyModel(region_code="US", item_code="ITEM1", description="US Item 1"),
            CompositeKeyModel(region_code="US", item_code="ITEM2", description="US Item 2"),
            CompositeKeyModel(region_code="EU", item_code="ITEM1", description="EU Item 1"),
        ])
        
        # Verify we can fetch by composite key
        result = await driver.fetch(
            when(CompositeKeyModel.region_code == "US", CompositeKeyModel.item_code == "ITEM1")
        ).one()
        
        assert result.description == "US Item 1"
        
        # Make sure all records were added correctly
        result = await driver.count(when(CompositeKeyModel))
        assert result == 3


@pytest.mark.asyncio
async def test_schema_with_relationships(driver: BaseDriver):
    """Test schema creation with relationship constraints."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class Department:
        name: str
        id: int = None

    @ommi_model(collection=collection)
    @dataclass
    class Employee:
        name: str
        department_id: Annotated[int, ReferenceTo(Department.id)]
        id: int = None

    async with WithModels(driver, collection):
        # Add a department
        dept = (await driver.add([Department(name="Engineering")]))[0]
        
        # Add employees referencing the department
        employees = await driver.add([
            Employee(name="Employee 1", department_id=dept.id),
            Employee(name="Employee 2", department_id=dept.id),
        ])
        
        # Verify relationship
        result = await driver.fetch(when(Employee, Department.name == "Engineering")).get()
        assert len(result) == 2
        assert {e.name for e in result} == {"Employee 1", "Employee 2"}


@pytest.mark.asyncio
async def test_schema_with_all_field_types(driver: BaseDriver):
    """Test schema creation with all supported field types."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class AllTypesModel:
        string_field: str
        int_field: int
        float_field: float
        bool_field: bool
        optional_string: Optional[str] = None
        optional_int: Optional[int] = None
        optional_float: Optional[float] = None
        optional_bool: Optional[bool] = None
        id: int = None

    async with WithModels(driver, collection):
        # Add a record with all fields populated
        full_model = AllTypesModel(
            string_field="test",
            int_field=123,
            float_field=45.67,
            bool_field=True,
            optional_string="optional",
            optional_int=456,
            optional_float=78.9,
            optional_bool=False
        )
        
        # Add a record with only required fields
        minimal_model = AllTypesModel(
            string_field="minimal",
            int_field=999,
            float_field=0.1,
            bool_field=False
        )
        
        await driver.add([full_model, minimal_model])
        
        # Verify full model
        result = await driver.fetch(when(AllTypesModel.string_field == "test")).one()
        assert result.string_field == "test"
        assert result.int_field == 123
        assert result.float_field == 45.67
        assert result.bool_field == True
        assert result.optional_string == "optional"
        assert result.optional_int == 456
        assert result.optional_float == 78.9
        assert result.optional_bool == False
        
        # Verify minimal model
        result = await driver.fetch(when(AllTypesModel.string_field == "minimal")).one()
        assert result.string_field == "minimal"
        assert result.int_field == 999
        assert result.float_field == 0.1
        assert result.bool_field == False
        assert result.optional_string is None
        assert result.optional_int is None
        assert result.optional_float is None
        assert result.optional_bool is None


@pytest.mark.asyncio
async def test_multiple_model_schema(driver: BaseDriver):
    """Test schema creation with multiple related models at once."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class Customer:
        name: str
        id: int = None

    @ommi_model(collection=collection)
    @dataclass
    class Order:
        total: float
        customer_id: Annotated[int, ReferenceTo(Customer.id)]
        id: int = None

    @ommi_model(collection=collection)
    @dataclass
    class OrderItem:
        description: str
        price: float
        order_id: Annotated[int, ReferenceTo(Order.id)]
        id: int = None

    async with WithModels(driver, collection):
        # Create a customer
        customer = (await driver.add([Customer(name="Test Customer")]))[0]
        
        # Create an order for the customer
        order = (await driver.add([Order(total=125.99, customer_id=customer.id)]))[0]
        
        # Create order items
        await driver.add([
            OrderItem(description="Item 1", price=25.99, order_id=order.id),
            OrderItem(description="Item 2", price=100.00, order_id=order.id),
        ])
        
        # Query across all three models
        results = await driver.fetch(
            when(OrderItem, Order.customer_id == customer.id)
        ).get()
        
        assert len(results) == 2
        assert {item.description for item in results} == {"Item 1", "Item 2"}


@pytest.mark.asyncio
async def test_duplicate_field_validation(driver: BaseDriver):
    """Test that models cannot have fields with duplicate normalized names/store_as values."""
    collection = ModelCollection()
    
    # This should be detected as an error when the model is created
    with pytest.raises(ValueError, match="Duplicate StoreAs value"):
        @ommi_model(collection=collection)
        @dataclass 
        class DuplicateFieldModel:
            name: str
            name_duplicate: Annotated[str, StoreAs("name")]  # Same store_as as normalized 'name'
            id: int = None
