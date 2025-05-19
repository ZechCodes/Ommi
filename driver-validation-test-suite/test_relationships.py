"""
Tests for model relationships and lazy loading to validate consistent behavior across all drivers.
"""
from dataclasses import dataclass
from typing import Any, Annotated, List

import pytest
import attrs
import pydantic
from ommi import BaseDriver, ommi_model
from ommi.models.collections import ModelCollection
from ommi.models.field_metadata import ReferenceTo, Key
from ommi.models.query_fields import (
    LazyLoadTheRelated,
    LazyLoadEveryRelated,
    AssociateUsing,
)
from ommi.query_ast import when

from conftest import WithModels


@pytest.mark.asyncio
async def test_direct_reference_relationship(driver: BaseDriver):
    """Test a simple one-to-many relationship using direct references."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class Author:
        name: str
        id: int = None

    @ommi_model(collection=collection)
    @dataclass
    class Book:
        title: str
        author_id: Annotated[int, ReferenceTo(Author.id)]
        id: int = None

    async with WithModels(driver, collection):
        # Create authors
        authors = await driver.add([
            Author(name="Author 1"),
            Author(name="Author 2"),
        ])
        
        # Create books with references to authors
        books = await driver.add([
            Book(title="Book 1 by Author 1", author_id=authors[0].id),
            Book(title="Book 2 by Author 1", author_id=authors[0].id),
            Book(title="Book 1 by Author 2", author_id=authors[1].id),
        ])
        
        # Query books by author
        author1_books = await driver.fetch(
            when(Book, Author.id == authors[0].id)
        ).get()
        
        assert len(author1_books) == 2
        assert all(book.author_id == authors[0].id for book in author1_books)
        
        # Query authors by book
        book_author = await driver.fetch(
            when(Author, Book.id == books[0].id)
        ).one()
        
        assert book_author.id == authors[0].id


@pytest.mark.asyncio
async def test_lazy_load_one_to_one(driver: BaseDriver):
    """Test lazy loading for one-to-one relationships."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class Profile:
        bio: str
        id: int = None

    @ommi_model(collection=collection)
    @dataclass
    class User:
        username: str
        profile_id: Annotated[int, ReferenceTo(Profile.id)]
        # One-to-one relationship
        profile: LazyLoadTheRelated[Profile]
        id: int = None
        
    async with WithModels(driver, collection):
        # Create a profile
        profiles = await driver.add([
            Profile(bio="Test bio for user")
        ])
        
        # Create a user with reference to profile
        users = await driver.add([
            User(username="testuser", profile_id=profiles[0].id)
        ])
        
        # Lazy load the profile
        user_profile = await users[0].profile
        
        # Verify the relationship
        assert user_profile.id == profiles[0].id
        assert user_profile.bio == "Test bio for user"


@pytest.mark.asyncio
async def test_lazy_load_one_to_many(driver: BaseDriver):
    """Test lazy loading for one-to-many relationships."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class Department:
        name: str
        id: int = None
        
        # One-to-many relationship with forward reference
        employees: "LazyLoadEveryRelated['Employee']"

    @ommi_model(collection=collection)
    @dataclass
    class Employee:
        name: str
        department_id: Annotated[int, ReferenceTo(Department.id)]
        id: int = None
        
        # Many-to-one relationship
        department: LazyLoadTheRelated[Department]

    async with WithModels(driver, collection):
        # Create departments
        departments = await driver.add([
            Department(name="Engineering"),
            Department(name="Marketing"),
        ])
        
        # Create employees with references to departments
        employees = await driver.add([
            Employee(name="Employee 1", department_id=departments[0].id),
            Employee(name="Employee 2", department_id=departments[0].id),
            Employee(name="Employee 3", department_id=departments[1].id),
        ])
        
        # Test many-to-one: employee -> department
        emp_dept = await employees[0].department
        assert emp_dept.id == departments[0].id
        assert emp_dept.name == "Engineering"
        
        # Test one-to-many: department -> employees
        dept_employees = await departments[0].employees
        assert len(dept_employees) == 2
        assert {emp.name for emp in dept_employees} == {"Employee 1", "Employee 2"}


@pytest.mark.asyncio
async def test_circular_references(driver: BaseDriver):
    """Test circular references between models."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class Person:
        name: str
        best_friend_id: Annotated[int, ReferenceTo("Person.id")] = None
        id: int = None
        
        # Self-referential relationship
        best_friend: "LazyLoadTheRelated['Person']"
        friends: "LazyLoadEveryRelated['Person']"

    async with WithModels(driver, collection):
        # Create people without relationships first
        people = await driver.add([
            Person(name="Alice"),
            Person(name="Bob"),
            Person(name="Charlie"),
        ])
        
        # Update with relationships
        alice, bob, charlie = people
        
        # Alice's best friend is Bob
        await driver.update(when(Person.id == alice.id), {"best_friend_id": bob.id})
        
        # Bob's best friend is Charlie
        await driver.update(when(Person.id == bob.id), {"best_friend_id": charlie.id})
        
        # Charlie's best friend is Alice (circular)
        await driver.update(when(Person.id == charlie.id), {"best_friend_id": alice.id})
        
        # Test the circular references
        alice_friend = await alice.best_friend
        assert alice_friend.id == bob.id
        assert alice_friend.name == "Bob"
        
        bob_friend = await alice_friend.best_friend
        assert bob_friend.id == charlie.id
        assert bob_friend.name == "Charlie"
        
        charlie_friend = await bob_friend.best_friend
        assert charlie_friend.id == alice.id
        assert charlie_friend.name == "Alice"
        
        # Test that the circle is complete
        full_circle = await (await (await alice.best_friend).best_friend).best_friend
        assert full_circle.id == alice.id


@pytest.mark.asyncio
async def test_composite_key_references(driver: BaseDriver):
    """Test relationships using composite keys."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class OrderItem:
        order_id: Annotated[int, Key]
        item_id: Annotated[int, Key]
        quantity: int

    @ommi_model(collection=collection)
    @dataclass
    class ItemDetail:
        order_id: Annotated[int, ReferenceTo(OrderItem.order_id)]
        item_id: Annotated[int, ReferenceTo(OrderItem.item_id)]
        description: str
        id: int = None

    async with WithModels(driver, collection):
        # Create order items
        await driver.add([
            OrderItem(order_id=1, item_id=101, quantity=2),
            OrderItem(order_id=1, item_id=102, quantity=1),
            OrderItem(order_id=2, item_id=101, quantity=3),
        ])
        
        # Create item details
        await driver.add([
            ItemDetail(order_id=1, item_id=101, description="Order 1, Item 101"),
            ItemDetail(order_id=1, item_id=102, description="Order 1, Item 102"),
            ItemDetail(order_id=2, item_id=101, description="Order 2, Item 101"),
        ])
        
        # Query using composite key conditions
        result = await driver.fetch(
            when(ItemDetail, OrderItem.order_id == 1, OrderItem.item_id == 101)
        ).one()
        
        assert result.description == "Order 1, Item 101"
        
        # Update based on composite key relationship
        await driver.update(
            when(OrderItem, ItemDetail.description == "Order 1, Item 102"),
            {"quantity": 5}
        )
        
        updated_item = await driver.fetch(
            when(OrderItem.order_id == 1, OrderItem.item_id == 102)
        ).one()
        
        assert updated_item.quantity == 5


@pytest.mark.asyncio
async def test_many_to_many_with_association_table(driver: BaseDriver):
    """Test many-to-many relationships using an association table."""
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclass
    class Student:
        name: str
        id: int = None

    @ommi_model(collection=collection)
    @dataclass
    class Course:
        title: str
        id: int = None

    @ommi_model(collection=collection)
    @dataclass
    class StudentCourse:
        student_id: Annotated[int, Key | ReferenceTo(Student.id)]
        course_id: Annotated[int, Key | ReferenceTo(Course.id)]
        enrollment_date: str = None

    # Define the models again with proper relationships defined at class creation time
    @ommi_model(collection=collection)
    @dataclass
    class Student:
        name: str
        id: int = None
        
        # Many-to-many relationship with explicit association table
        courses: "LazyLoadEveryRelated[Annotated[Course, AssociateUsing(StudentCourse)]]"

    @ommi_model(collection=collection)
    @dataclass
    class Course:
        title: str
        id: int = None
        
        # Many-to-many relationship with explicit association table
        students: "LazyLoadEveryRelated[Annotated[Student, AssociateUsing(StudentCourse)]]"

    async with WithModels(driver, collection):
        # Create students
        students = await driver.add([
            Student(name="Student 1"),
            Student(name="Student 2"),
            Student(name="Student 3"),
        ])
        
        # Create courses
        courses = await driver.add([
            Course(title="Course A"),
            Course(title="Course B"),
            Course(title="Course C"),
        ])
        
        # Create associations
        await driver.add([
            # Student 1 takes Course A and B
            StudentCourse(student_id=students[0].id, course_id=courses[0].id, enrollment_date="2023-01-01"),
            StudentCourse(student_id=students[0].id, course_id=courses[1].id, enrollment_date="2023-01-02"),
            
            # Student 2 takes Course B and C
            StudentCourse(student_id=students[1].id, course_id=courses[1].id, enrollment_date="2023-01-03"),
            StudentCourse(student_id=students[1].id, course_id=courses[2].id, enrollment_date="2023-01-04"),
            
            # Student 3 takes Course A and C
            StudentCourse(student_id=students[2].id, course_id=courses[0].id, enrollment_date="2023-01-05"),
            StudentCourse(student_id=students[2].id, course_id=courses[2].id, enrollment_date="2023-01-06"),
        ])
        
        # Test student -> courses relationship
        student1_courses = await students[0].courses
        assert len(student1_courses) == 2
        course_titles = {course.title for course in student1_courses}
        assert course_titles == {"Course A", "Course B"}
        
        # Test course -> students relationship
        course_b_students = await courses[1].students
        assert len(course_b_students) == 2
        student_names = {student.name for student in course_b_students}
        assert student_names == {"Student 1", "Student 2"}
        
        # Test queries across the association
        course_a_students = await driver.fetch(
            when(Student, Course.title == "Course A")
        ).get()
        
        assert len(course_a_students) == 2
        assert {s.name for s in course_a_students} == {"Student 1", "Student 3"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model_style",
    [
        "dataclass",
        "attrs",
        "pydantic",
    ],
)
async def test_lazy_load_across_model_styles(driver: BaseDriver, model_style: str):
    """Test lazy loading relationships across different model definition styles."""
    collection = ModelCollection()
    
    if model_style == "dataclass":
        @ommi_model(collection=collection)
        @dataclass
        class Parent:
            name: str
            id: int = None
            
            # Forward reference in quotes
            children: "LazyLoadEveryRelated['Child']"
            
        @ommi_model(collection=collection)
        @dataclass
        class Child:
            name: str
            parent_id: Annotated[int, ReferenceTo(Parent.id)]
            id: int = None
            
            parent: LazyLoadTheRelated[Parent]
            
    elif model_style == "attrs":
        @ommi_model(collection=collection)
        @attrs.define
        class Parent:
            name: str
            id: int = None
            
            # Forward reference in quotes
            children: "LazyLoadEveryRelated['Child']"
            
        @ommi_model(collection=collection)
        @attrs.define
        class Child:
            name: str
            parent_id: Annotated[int, ReferenceTo(Parent.id)]
            id: int = None
            
            parent: LazyLoadTheRelated[Parent]
            
    elif model_style == "pydantic":
        @ommi_model(collection=collection)
        class Parent(pydantic.BaseModel):
            name: str
            id: int = None
            
            # Forward reference in quotes
            children: "LazyLoadEveryRelated['Child']"
            
        @ommi_model(collection=collection)
        class Child(pydantic.BaseModel):
            name: str
            parent_id: Annotated[int, ReferenceTo(Parent.id)]
            id: int = None
            
            parent: LazyLoadTheRelated[Parent]
    
    async with WithModels(driver, collection):
        # Create parent
        parents = await driver.add([
            Parent(name=f"Parent ({model_style})"),
        ])
        
        # Create children
        children = await driver.add([
            Child(name=f"Child 1 ({model_style})", parent_id=parents[0].id),
            Child(name=f"Child 2 ({model_style})", parent_id=parents[0].id),
        ])
        
        # Test parent -> children
        parent_children = await parents[0].children
        assert len(parent_children) == 2
        assert {child.name for child in parent_children} == {
            f"Child 1 ({model_style})", 
            f"Child 2 ({model_style})"
        }
        
        # Test child -> parent
        child_parent = await children[0].parent
        assert child_parent.id == parents[0].id
        assert child_parent.name == f"Parent ({model_style})" 