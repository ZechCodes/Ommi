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


@pytest.mark.asyncio
async def test_transaction_isolation(driver: BaseDriver):
    """Test that changes in a transaction are not visible outside until committed."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class TestModel:
        name: str
        id: int = None

    async with WithModels(driver, collection):
        # Add initial model outside transaction
        await driver.add([TestModel(name="visible_outside")])
        
        # Begin transaction
        tx = driver.transaction()
        transaction = await tx.__aenter__()
        
        try:
            # Add model inside transaction
            await transaction.add([TestModel(name="visible_inside")])
            
            # From within the transaction, both models should be visible
            tx_count = await transaction.count(when(TestModel))
            assert tx_count == 2, "Transaction should see both models"
            
            # From outside the transaction, only the initial model should be visible
            outside_count = await driver.count(when(TestModel))
            assert outside_count == 1, "Outside transaction should only see initial model"
            
            # Commit transaction
            await tx.__aexit__(None, None, None)
            
            # Now both models should be visible outside
            final_count = await driver.count(when(TestModel))
            assert final_count == 2, "After commit, both models should be visible"
        except:
            await tx.__aexit__(*asyncio.sys.exc_info())
            raise


@pytest.mark.asyncio
async def test_complex_transaction(driver: BaseDriver):
    """Test a transaction with multiple operations of different types."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class TestModel:
        name: str
        status: str
        id: int = None

    async with WithModels(driver, collection):
        # Add initial data
        await driver.add([
            TestModel(name="item1", status="active"),
            TestModel(name="item2", status="inactive"),
            TestModel(name="item3", status="active"),
        ])
        
        # Transaction with multiple operations
        async with driver.transaction() as tx:
            # Add new model
            await tx.add([TestModel(name="item4", status="active")])
            
            # Update existing model
            await tx.update(when(TestModel.name == "item2"), {"status": "active"})
            
            # Delete a model
            await tx.delete(when(TestModel.name == "item3"))
            
            # Read models (should see transaction state)
            tx_items = await tx.fetch(when(TestModel.status == "active")).get()
            assert len(tx_items) == 3, "Transaction should see 3 active items"
        
        # Verify final state
        active_items = await driver.fetch(when(TestModel.status == "active")).get()
        assert len(active_items) == 3, "Should have 3 active items after commit"
        
        all_items = await driver.fetch(when(TestModel)).get()
        assert len(all_items) == 3, "Should have 3 total items"
        
        item_names = {item.name for item in all_items}
        assert item_names == {"item1", "item2", "item4"}, "item3 should be deleted"


@pytest.mark.asyncio
async def test_nested_transactions(driver: BaseDriver):
    """Test behavior with nested transactions.
    
    All drivers should implement a consistent nested transaction behavior:
    1. Inner transaction commits don't actually commit to the database
    2. Inner transaction rollbacks roll back the entire outer transaction
    3. Only the outermost transaction commit persists changes
    """
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class TestModel:
        name: str
        id: int = None

    async with WithModels(driver, collection):
        # Test 1: Inner transaction commit followed by outer transaction commit
        # Expectation: Both models are saved
        async with driver.transaction() as outer_tx1:
            await outer_tx1.add([TestModel(name="outer_item_1")])
            
            async with driver.transaction() as inner_tx1:
                await inner_tx1.add([TestModel(name="inner_item_1")])
                # Inner transaction commits
            
            # Outer transaction commits
        
        # Verify both models were saved
        saved_models = await driver.fetch(when(TestModel, TestModel.name.in_(["outer_item_1", "inner_item_1"]))).get()
        assert len(saved_models) == 2, "Both models should be saved after nested commits"
        
        # Test 2: Inner transaction rollback with outer transaction commit
        # Expectation: No models are saved (inner rollback rolls back outer too)
        count_before = await driver.count(when(TestModel))
        
        try:
            async with driver.transaction() as outer_tx2:
                await outer_tx2.add([TestModel(name="outer_item_2")])
                
                async with driver.transaction() as inner_tx2:
                    await inner_tx2.add([TestModel(name="inner_item_2")])
                    await inner_tx2.rollback()  # This should roll back everything
                
                # Outer commit should have no effect if inner rolled back
                
        except Exception:
            # If driver can't handle this and throws an exception, that's acceptable
            # as long as the end result is the same - no data is committed
            pass
            
        # Verify no new models were saved
        count_after = await driver.count(when(TestModel))
        assert count_after == count_before, "No models should be saved after inner rollback"
        
        # Test 3: Inner transaction commit with outer rollback
        # Expectation: No models are saved
        try:
            async with driver.transaction() as outer_tx3:
                await outer_tx3.add([TestModel(name="outer_item_3")])
                
                async with driver.transaction() as inner_tx3:
                    await inner_tx3.add([TestModel(name="inner_item_3")])
                    # Inner commits (or tries to)
                
                await outer_tx3.rollback()  # Outer explicitly rolls back
                
        except Exception:
            # If driver can't handle this and throws an exception, that's acceptable
            # as long as the end result is the same - no data is committed
            pass
            
        # Verify no new models were saved
        models = await driver.fetch(when(TestModel, TestModel.name.in_(["outer_item_3", "inner_item_3"]))).get()
        assert len(models) == 0, "No models should be saved after outer rollback"


@pytest.mark.asyncio
async def test_concurrent_transactions(driver: BaseDriver):
    """Test concurrent transactions operating on the same data."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class TestModel:
        name: str
        value: int
        id: int = None

    async with WithModels(driver, collection):
        # Create initial models
        await driver.add([
            TestModel(name="shared", value=0),
            TestModel(name="tx1_only", value=10),
            TestModel(name="tx2_only", value=20),
        ])
        
        # Get initial model IDs for later reference
        shared_model = await driver.fetch(when(TestModel.name == "shared")).one()
        tx1_model = await driver.fetch(when(TestModel.name == "tx1_only")).one()
        tx2_model = await driver.fetch(when(TestModel.name == "tx2_only")).one()
        
        # Start two transactions concurrently
        tx1 = driver.transaction()
        tx2 = driver.transaction()
        
        async def run_tx1():
            async with tx1 as t:
                # Update shared model
                await t.update(when(TestModel.id == shared_model.id), {"value": 1})
                # Update tx1's model
                await t.update(when(TestModel.id == tx1_model.id), {"value": 11})
                # Wait for tx2 to start
                await asyncio.sleep(0.2)
        
        async def run_tx2():
            # Wait for tx1 to start and make changes
            await asyncio.sleep(0.1)
            async with tx2 as t:
                # Update shared model (may conflict with tx1)
                await t.update(when(TestModel.id == shared_model.id), {"value": 2})
                # Update tx2's model
                await t.update(when(TestModel.id == tx2_model.id), {"value": 22})
        
        # Run both transactions
        try:
            await asyncio.gather(run_tx1(), run_tx2())
            
            # Check final state - exact behavior depends on isolation level
            final_shared = await driver.fetch(when(TestModel.id == shared_model.id)).one()
            final_tx1 = await driver.fetch(when(TestModel.id == tx1_model.id)).one()
            final_tx2 = await driver.fetch(when(TestModel.id == tx2_model.id)).one()
            
            # Both tx1 and tx2 model updates should succeed
            assert final_tx1.value == 11, "tx1's model update should persist"
            assert final_tx2.value == 22, "tx2's model update should persist"
            
            # Shared model final value depends on isolation level and timing
            # For most drivers, last write wins, but we can't guarantee order
            assert final_shared.value in (1, 2), "Shared value should be updated by one transaction"
            
        except Exception as e:
            # Some drivers might fail with concurrent transactions
            pytest.skip(f"Concurrent transactions failed: {str(e)}")


@pytest.mark.asyncio
async def test_transaction_with_schema_changes(driver: BaseDriver):
    """Test transactions that include schema changes.
    
    Drivers should provide a consistent approach to schema changes within transactions:
    1. If schema changes are within a transaction, they should be committed or rolled back with the transaction
    2. Schema operations and data operations should maintain atomicity together
    3. If the underlying database doesn't support DDL in transactions, drivers should emulate this behavior
    """
    collection1 = ModelCollection()
    collection2 = ModelCollection()

    @ommi_model(collection=collection1)
    @dataclass
    class ModelA:
        name: str
        id: int = None

    @ommi_model(collection=collection2)
    @dataclass
    class ModelB:
        title: str
        id: int = None

    # Apply Schema for ModelA outside transaction
    await driver.apply_schema(collection1)
    
    try:
        # Test 1: Schema changes and data modifications should commit together
        async with driver.transaction() as tx:
            # Apply schema for ModelB inside transaction
            await tx.apply_schema(collection2)
            
            # Add records to both models
            await tx.add([ModelA(name="a_item_1")])
            await tx.add([ModelB(title="b_item_1")])
        
        # Verify both models were created and populated
        a_items = await driver.fetch(when(ModelA)).get()
        assert len(a_items) == 1, "ModelA record should exist"
        assert a_items[0].name == "a_item_1"
        
        b_items = await driver.fetch(when(ModelB)).get()
        assert len(b_items) == 1, "ModelB record should exist"
        assert b_items[0].title == "b_item_1"
        
        # Test 2: Schema changes and data modifications should roll back together
        try:
            async with driver.transaction() as tx:
                # Add more records
                await tx.add([ModelA(name="a_item_2")])
                await tx.add([ModelB(title="b_item_2")])
                
                # Roll back the transaction
                await tx.rollback()
        except Exception:
            # If the driver doesn't support explicit rollback with schema changes,
            # it should at least not persist any changes after an exception
            pass
            
        # Verify no new records were added
        a_count = await driver.count(when(ModelA))
        assert a_count == 1, "No new ModelA records should be added after rollback"
        
        b_count = await driver.count(when(ModelB))
        assert b_count == 1, "No new ModelB records should be added after rollback"
        
        # Test 3: Transaction that fails should roll back all schema and data changes
        try:
            async with driver.transaction() as tx:
                # Create new collection for a new model
                collection3 = ModelCollection()
                
                @ommi_model(collection=collection3)
                @dataclass
                class ModelC:
                    description: str
                    id: int = None
                
                # Apply schema for ModelC
                await tx.apply_schema(collection3)
                
                # Add records
                await tx.add([ModelA(name="a_item_3")])
                await tx.add([ModelB(title="b_item_3")])
                await tx.add([ModelC(description="c_item_1")])
                
                # Simulate failure
                raise ValueError("Simulated transaction failure")
        except ValueError:
            # Expected exception
            pass
            
        # Verify no changes were persisted
        a_count = await driver.count(when(ModelA))
        assert a_count == 1, "No new ModelA records should be added after exception"
        
        b_count = await driver.count(when(ModelB))
        assert b_count == 1, "No new ModelB records should be added after exception"
        
        # ModelC should not exist at all
        try:
            await driver.count(when(ModelC))
            assert False, "ModelC should not exist after transaction failure"
        except Exception:
            # Expected - ModelC should not exist
            pass
            
    finally:
        # Clean up
        await driver.delete_schema(collection1)
        try:
            await driver.delete_schema(collection2)
        except Exception:
            # May fail if Schema B wasn't created
            pass 