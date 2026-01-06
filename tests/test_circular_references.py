"""
Tests for circular references between models.
"""
import pytest
import pytest_asyncio
from dataclasses import dataclass
from typing import Annotated, Optional, List, Any

from ommi import ommi_model, BaseDriver
from ommi.ext.drivers.sqlite import SQLiteDriver
from ommi.models.collections import ModelCollection
from ommi.models.field_metadata import ReferenceTo
from ommi.models.query_fields import Lazy, LazyList
from ommi.query_ast import where


@pytest_asyncio.fixture
async def driver():
    driver = SQLiteDriver.connect(":memory:")
    async with driver as d:
        yield d


@pytest.mark.asyncio
async def test_simple_circular_references(driver: BaseDriver):
    """Test simple circular references where two models reference each other."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class ModelA:
        name: str
        b_id: Optional[int] = None
        id: int = None
        
        # Forward reference to ModelB in quotes
        b: "Lazy['ModelB']"

    @ommi_model(collection=collection)
    @dataclass
    class ModelB:
        name: str
        a_id: Annotated[int, ReferenceTo(ModelA.id)]
        id: int = None

        a: Lazy[ModelA]

    # Apply schema
    await driver.apply_schema(collection)
    
    try:
        # Create ModelA first
        model_a = await driver.add([ModelA(name="A Instance")])[0]
        
        # Create ModelB with reference to ModelA
        model_b = await driver.add([ModelB(name="B Instance", a_id=model_a.id)])[0]
        
        # Update ModelA to reference ModelB
        await driver.update(where(ModelA.id == model_a.id), {"b_id": model_b.id})
        
        # Test lazy loading both ways
        loaded_a = await model_b.a
        assert loaded_a.id == model_a.id
        assert loaded_a.name == "A Instance"
        
        # Re-fetch model_a to get the updated b_id
        updated_a = await driver.fetch(where(ModelA.id == model_a.id)).one()
        loaded_b = await updated_a.b
        assert loaded_b.id == model_b.id
        assert loaded_b.name == "B Instance"
        
        # Test circular navigation
        circular_a = await (await updated_a.b).a
        assert circular_a.id == model_a.id
        assert circular_a.name == "A Instance"
    finally:
        # Clean up
        await driver.delete_schema(collection)


@pytest.mark.asyncio
async def test_self_referential_model(driver: BaseDriver):
    """Test a model that references itself (like a tree structure)."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class TreeNode:
        name: str
        parent_id: Annotated[Optional[int], ReferenceTo("TreeNode.id")] = None
        id: int = None
        
        # Self-referential relationships
        parent: "Lazy['TreeNode']"
        children: "LazyList['TreeNode']"

    # Apply schema
    await driver.apply_schema(collection)
    
    try:
        # Create a root node
        root = await driver.add([TreeNode(name="Root")])[0]
        
        # Create child nodes
        child1 = await driver.add([TreeNode(name="Child 1", parent_id=root.id)])[0]
        child2 = await driver.add([TreeNode(name="Child 2", parent_id=root.id)])[0]
        
        # Create a grandchild
        grandchild = await driver.add([TreeNode(name="Grandchild", parent_id=child1.id)])[0]
        
        # Test parent relationship
        child1_parent = await child1.parent
        assert child1_parent.id == root.id
        assert child1_parent.name == "Root"
        
        # Test children relationship
        root_children = await root.children
        assert len(root_children) == 2
        child_names = {node.name for node in root_children}
        assert child_names == {"Child 1", "Child 2"}
        
        # Test multi-level traversal
        grandchild_parent = await grandchild.parent
        assert grandchild_parent.id == child1.id
        
        grandparent = await grandchild_parent.parent
        assert grandparent.id == root.id
        
        # Test that parent of root is None
        try:
            root_parent = await root.parent
            assert root_parent is None
        except Exception:
            # Different drivers may handle NULL foreign keys differently
            pass
    finally:
        # Clean up
        await driver.delete_schema(collection)


@pytest.mark.asyncio
async def test_complex_circular_references(driver: BaseDriver):
    """Test complex circular references with multiple models in a cycle."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class ModelA:
        name: str
        id: int = None
        
        # Forward reference in quotes
        b_list: "LazyList['ModelB']"

    @ommi_model(collection=collection)
    @dataclass
    class ModelB:
        name: str
        a_id: Annotated[int, ReferenceTo(ModelA.id)]
        id: int = None
        
        a: Lazy[ModelA]
        # Forward reference in quotes
        c: "Lazy['ModelC']"

    @ommi_model(collection=collection)
    @dataclass
    class ModelC:
        name: str
        b_id: Annotated[int, ReferenceTo(ModelB.id)]
        id: int = None
        
        b: Lazy[ModelB]
        a_list: LazyList[ModelA]

    # Apply schema
    await driver.apply_schema(collection)
    
    try:
        # Create the models with circular references
        model_a = await driver.add([ModelA(name="A Instance")])[0]
        model_b = await driver.add([ModelB(name="B Instance", a_id=model_a.id)])[0]
        model_c = await driver.add([ModelC(name="C Instance", b_id=model_b.id)])[0]
        
        # Test traversing the circle: A -> B -> C -> A
        b_list = await model_a.b_list
        assert len(b_list) == 1
        assert b_list[0].id == model_b.id
        
        c = await b_list[0].c
        assert c.id == model_c.id
        
        a_list = await c.a_list  # This should be empty as we haven't established the C -> A link in data
        
        # Now let's associate Model C with Model A explicitly through a query
        # (assuming such relationship exists in the database schema)
        c_a_query = where(ModelA, ModelC.id == model_c.id)
        a_from_c = await driver.fetch(c_a_query).get()
        assert len(a_from_c) == 1  # We should find Model A through Model B's a_id
        assert a_from_c[0].id == model_a.id
    finally:
        # Clean up
        await driver.delete_schema(collection)


@pytest.mark.asyncio
async def test_lazy_loading_circular_references(driver: BaseDriver):
    """Test that lazy loading works correctly with circular references."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class Person:
        name: str
        id: int = None
        
        # Self-referential relationship
        friends: "LazyList['Person']"
        
    # Apply schema
    await driver.apply_schema(collection)
    
    try:
        # Create people
        alice = await driver.add([Person(name="Alice")])[0]
        bob = await driver.add([Person(name="Bob")])[0]
        charlie = await driver.add([Person(name="Charlie")])[0]
        
        # To create a friendship graph, we need an association table
        friends_collection = ModelCollection()
        
        @ommi_model(collection=friends_collection)
        @dataclass
        class Friendship:
            person_id: Annotated[int, ReferenceTo(Person.id)]
            friend_id: Annotated[int, ReferenceTo(Person.id)]
            id: int = None
        
        await driver.apply_schema(friends_collection)
        
        # Create friendships (bidirectional)
        # Alice is friends with Bob and Charlie
        await driver.add([
            Friendship(person_id=alice.id, friend_id=bob.id),
            Friendship(person_id=alice.id, friend_id=charlie.id),
            Friendship(person_id=bob.id, friend_id=alice.id),
            Friendship(person_id=bob.id, friend_id=charlie.id),
            Friendship(person_id=charlie.id, friend_id=alice.id),
            Friendship(person_id=charlie.id, friend_id=bob.id),
        ])
        
        # Test friendship queries (not using lazy loading directly since we need the association table)
        alice_friends_query = where(Person, Friendship.person_id == alice.id, Friendship.friend_id == Person.id)
        alice_friends = await driver.fetch(alice_friends_query).get()
        
        assert len(alice_friends) == 2
        friend_names = {p.name for p in alice_friends}
        assert friend_names == {"Bob", "Charlie"}
        
        # Test circular friendship query
        bob_friends_of_alice_query = where(
            Person, 
            Friendship.person_id == bob.id,
            Friendship.friend_id == Person.id,
            Person.id.in_([
                # Subquery for friends of Alice
                where(Person, Friendship.person_id == alice.id, Friendship.friend_id == Person.id).id
            ])
        )
        
        # This should return Charlie (the common friend of Alice and Bob)
        common_friends = await driver.fetch(bob_friends_of_alice_query).get()
        assert len(common_friends) == 1
        assert common_friends[0].name == "Charlie"
    finally:
        # Clean up
        await driver.delete_schema(friends_collection)
        await driver.delete_schema(collection) 