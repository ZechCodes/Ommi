"""
Common test fixtures and utilities for the Ommi driver validation test suite.
"""
import asyncio
from dataclasses import dataclass
from typing import Generator

import pytest
import pytest_asyncio
from ommi import BaseDriver
from ommi.driver_context import UseDriver
from ommi.ext.drivers.mongodb.driver import MongoDBDriver
from ommi.ext.drivers.postgresql.driver import PostgreSQLDriver
from ommi.ext.drivers.sqlite import SQLiteDriver
from ommi.models.collections import ModelCollection


class WithModels:
    """Context manager for applying/deleting model schema in tests."""
    
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
    """Fixture to set the active driver for the test using the driver context."""
    with UseDriver(driver):
        yield


@pytest_asyncio.fixture(
    params=[SQLiteDriver, PostgreSQLDriver, MongoDBDriver], 
    scope="function",
    ids=["sqlite", "postgresql", "mongodb"]
)
async def driver(request) -> Generator[BaseDriver, None, None]:
    """Fixture that provides a connected driver instance for testing.
    
    This fixture is parameterized to run tests with all supported driver types.
    Each test using this fixture will run multiple times, once for each driver.
    """
    connect_val = request.param.connect()
    driver_obj = await connect_val if asyncio.iscoroutine(connect_val) else connect_val
    async with driver_obj as d:
        yield d


@pytest.fixture
def test_collection() -> ModelCollection:
    """Fixture providing a fresh ModelCollection for test models."""
    return ModelCollection()


@dataclass
class DriverTestConfig:
    """Configuration options for driver tests."""
    collection: ModelCollection
    driver: BaseDriver
    

@pytest_asyncio.fixture
async def driver_test_config(driver, test_collection) -> Generator[DriverTestConfig, None, None]:
    """Fixture providing a combined configuration for driver tests."""
    async with WithModels(driver, test_collection):
        yield DriverTestConfig(
            collection=test_collection,
            driver=driver,
        ) 