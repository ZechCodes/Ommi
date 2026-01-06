"""
Tests for driver context switching functionality.
"""
import pytest
import asyncio
from dataclasses import dataclass

from ommi import BaseDriver, ommi_model
from ommi.driver_context import UseDriver, get_current_driver
from ommi.ext.drivers.sqlite import SQLiteDriver
from ommi.models.collections import ModelCollection
from ommi.query_ast import where


@dataclass
class MockDriver(BaseDriver):
    """Mock driver for testing context switching."""
    name: str = "mock"
    
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, *args):
        pass
    
    async def apply_schema(self, models):
        pass
        
    async def delete_schema(self, models):
        pass
    
    # Implement required abstract methods with stub behavior
    async def add(self, models):
        return models
        
    async def update(self, query, values):
        pass
        
    async def delete(self, query):
        pass
        
    async def fetch(self, query):
        pass
        
    async def count(self, query):
        return 0

    async def use_models(self, models):
        pass
        
    def transaction(self):
        return self

    async def disconnect(self):
        pass

    async def connect(self):
        pass


@pytest.fixture
def mock_driver_a():
    return MockDriver(name="driver_a")


@pytest.fixture
def mock_driver_b():
    return MockDriver(name="driver_b")


def test_get_current_driver_no_context():
    """Test that getting current driver outside a context raises an error."""
    with pytest.raises(RuntimeError):
        get_current_driver()


def test_use_driver_context_manager():
    """Test that UseDriver context manager properly sets and clears the driver."""
    driver = MockDriver(name="test_driver")
    
    # Outside context, should raise error
    with pytest.raises(RuntimeError):
        get_current_driver()
    
    # Inside context, should return the driver
    with UseDriver(driver):
        assert get_current_driver() is driver
        assert get_current_driver().name == "test_driver"
    
    # After context, should raise error again
    with pytest.raises(RuntimeError):
        get_current_driver()


def test_nested_driver_contexts():
    """Test nested UseDriver contexts behave correctly."""
    driver_a = MockDriver(name="driver_a")
    driver_b = MockDriver(name="driver_b")
    
    with UseDriver(driver_a):
        assert get_current_driver() is driver_a
        
        # Nested context should override
        with UseDriver(driver_b):
            assert get_current_driver() is driver_b
            assert get_current_driver().name == "driver_b"
        
        # Back to outer context
        assert get_current_driver() is driver_a
        assert get_current_driver().name == "driver_a"


def test_driver_context_exception_safety():
    """Test that driver context is restored even when exceptions occur."""
    driver_a = MockDriver(name="driver_a")
    driver_b = MockDriver(name="driver_b")
    
    with UseDriver(driver_a):
        assert get_current_driver() is driver_a
        
        # Even with an exception, context should be restored
        try:
            with UseDriver(driver_b):
                assert get_current_driver() is driver_b
                raise ValueError("Test exception")
        except ValueError:
            pass
        
        # Back to outer context
        assert get_current_driver() is driver_a


@pytest.mark.asyncio
async def test_driver_context_in_async_functions():
    """Test that driver context works correctly in async functions."""
    driver_a = MockDriver(name="driver_a")
    driver_b = MockDriver(name="driver_b")
    
    async def async_function_a():
        assert get_current_driver() is driver_a
        return "a"
    
    async def async_function_b():
        assert get_current_driver() is driver_b
        return "b"
    
    with UseDriver(driver_a):
        result_a = await async_function_a()
        assert result_a == "a"
        
        with UseDriver(driver_b):
            result_b = await async_function_b()
            assert result_b == "b"
        
        # Back to driver_a
        result_a2 = await async_function_a()
        assert result_a2 == "a"


@pytest.mark.asyncio
async def test_driver_context_in_parallel_async_tasks():
    """Test that driver context is maintained correctly in parallel async tasks."""
    driver_a = MockDriver(name="driver_a")
    driver_b = MockDriver(name="driver_b")
    
    async def task_a():
        with UseDriver(driver_a):
            assert get_current_driver() is driver_a
            # Simulate some work
            await asyncio.sleep(0.1)
            assert get_current_driver() is driver_a
            return "a"
    
    async def task_b():
        with UseDriver(driver_b):
            assert get_current_driver() is driver_b
            # Simulate some work
            await asyncio.sleep(0.1)
            assert get_current_driver() is driver_b
            return "b"
    
    # Run tasks in parallel
    results = await asyncio.gather(task_a(), task_b())
    assert results == ["a", "b"]


@pytest.mark.asyncio
async def test_real_driver_with_context():
    """Test that a real driver works correctly with context switching."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class TestModel:
        name: str
        id: int = None

    # Create two SQLite drivers
    driver_a = SQLiteDriver.connect()
    driver_b = SQLiteDriver.connect()
    
    async with driver_a as a, driver_b as b:
        # Set up schema in both drivers
        await a.apply_schema(collection)
        await b.apply_schema(collection)
        
        # Use driver_a to add a model
        with UseDriver(a):
            await a.add([TestModel(name="Model in A")])
            result_a = await a.fetch(where(TestModel.name == "Model in A")).one()
            assert result_a.name == "Model in A"
            
            # No data in driver_b yet
            with UseDriver(b):
                count_b = await b.count(where(TestModel))
                assert count_b == 0
                
                # Add a model to driver_b
                await b.add([TestModel(name="Model in B")])
            
            # Back to driver_a, verify data
            result_a_again = await a.fetch(where(TestModel.name == "Model in A")).one()
            assert result_a_again.name == "Model in A"
            
            # Model in B should not exist in driver_a
            count_a_b = await a.count(where(TestModel.name == "Model in B"))
            assert count_a_b == 0
        
        # Clean up
        await a.delete_schema(collection)
        await b.delete_schema(collection) 