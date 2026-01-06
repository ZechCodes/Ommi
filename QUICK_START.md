# Ommi Quick Start Guide

Ommi is a modern, asynchronous Object-Relational Mapper (ORM) for Python designed for ease of use, type safety, and high performance. This guide covers the essential components to get you started.

## Core Components

### The Ommi Class

The `Ommi` class is your main entry point for database operations. It wraps a database driver and provides high-level methods for CRUD operations.

```python
from ommi import Ommi
from ommi.ext.drivers.sqlite import SQLiteDriver

# Create a database connection
db = Ommi(SQLiteDriver.connect())

# Use with async context manager for automatic cleanup
async with Ommi(SQLiteDriver.connect()) as db:
    # Your database operations here
    pass
```

### Creating a Driver

Ommi supports multiple database backends through its driver system. Here's how to create drivers for different databases:

#### SQLite Driver

```python
from ommi.ext.drivers.sqlite import SQLiteDriver

# In-memory database (default)
driver = SQLiteDriver.connect()

# File-based database
driver = SQLiteDriver.connect({
    "database": "myapp.db",
    "isolation_level": "DEFERRED"
})
```

#### PostgreSQL Driver

```python
from ommi.ext.drivers.postgresql import PostgreSQLDriver

driver = PostgreSQLDriver.connect({
    "host": "localhost",
    "port": 5432,
    "database": "myapp",
    "user": "username",
    "password": "password"
})
```

#### MongoDB Driver

```python
from ommi.ext.drivers.mongodb import MongoDBDriver

driver = MongoDBDriver.connect({
    "connection_string": "mongodb://localhost:27017",
    "database": "myapp"
})
```

## Defining Models

Use the `@ommi_model` decorator to transform Python classes into database models:

```python
from dataclasses import dataclass
from typing import Annotated
from ommi import ommi_model, Key, ReferenceTo, Lazy, LazyList

@ommi_model
@dataclass
class User:
    name: str
    age: int
    id: Annotated[int, Key] = None  # Primary key field

@ommi_model
@dataclass
class Post:
    title: str
    content: str
    author_id: Annotated[int, ReferenceTo(User.id)]
    author: Lazy[User]  # One-to-one relationship
    id: Annotated[int, Key] = None
```

### Field Types

Ommi supports basic Python types for model fields:

- `str` - Text/varchar fields
- `int` - Integer fields  
- `float` - Floating point numbers
- `bool` - Boolean fields
- `bytes` - Binary data
- `datetime` - Date and time values

**Important**: Fields can only be basic types. Complex types like `dict`, `list`, or `tuple` are not supported.

### Field Metadata

Use field metadata to configure how fields are handled:

```python
from typing import Annotated
from ommi import Key, StoreAs, Auto, ReferenceTo

@ommi_model
@dataclass
class User:
    # Primary key with auto-increment
    id: Annotated[int, Key | Auto] = None
    
    # Store with different column name
    full_name: Annotated[str, StoreAs("user_full_name")]
    
    # Foreign key reference
    department_id: Annotated[int, ReferenceTo(Department.id)]
```

Available metadata:
- `Key` - Marks field as primary key
- `Auto` - Auto-incrementing field
- `StoreAs(column_name)` - Custom database column name
- `ReferenceTo(field)` - Foreign key reference

## Lazy Fields

Lazy fields enable relationships between models without immediate database queries:

### Lazy (One-to-One)

```python
@ommi_model
@dataclass
class Post:
    author_id: Annotated[int, ReferenceTo(User.id)]
    author: Lazy[User]  # Loads single related model

# Usage
post = await db.find(Post.id == 1).one()
author = await post.author  # Queries database when accessed
```

### LazyList (One-to-Many)

```python
@ommi_model
@dataclass
class User:
    id: Annotated[int, Key]
    posts: LazyList[Post]  # Loads multiple related models

# Usage
user = await db.find(User.id == 1).one()
posts = await user.posts  # Returns list of Post objects
```

### Association Tables (Many-to-Many)

```python
from ommi.models.query_fields import AssociateUsing

@ommi_model
@dataclass
class UserPermission:
    user_id: Annotated[int, ReferenceTo(User.id)]
    permission_id: Annotated[int, ReferenceTo(Permission.id)]

@ommi_model
@dataclass
class User:
    id: Annotated[int, Key]
    permissions: LazyList[Annotated[Permission, AssociateUsing(UserPermission)]]
```

## Transactions

Use `OmmiTransaction` for atomic database operations:

```python
async with db.transaction() as t:
    # Add a user
    user = User(name="Alice", age=30)
    await t.add(user)
    
    # Add related post
    post = Post(title="My Post", content="Hello!", author_id=user.id)
    await t.add(post)
    
    # Both operations commit together
    # If any operation fails, all changes are rolled back
```

### Manual Transaction Control

```python
async with db.transaction() as t:
    await t.add(User(name="Bob", age=25))
    
    if some_condition_fails:
        await t.rollback()  # Explicit rollback
        return
        
    # Transaction commits automatically when exiting context
    # Or call await t.commit() for explicit commit
```

## Basic CRUD Operations

### Creating Records

```python
from ommi.database.results import DBResult

# Single record with match/case
user = User(name="Alice", age=30)
result = await db.add(user)
match result:
    case DBResult.DBSuccess(saved_user):
        print(f"User saved with ID: {saved_user.id}")
    case DBResult.DBFailure(exception):
        print(f"Failed to add user: {exception}")

# Or use or_raise() for direct exception handling
user = User(name="Bob", age=25)
saved_user = await db.add(user).or_raise()
print(f"User saved with ID: {saved_user.id}")
```

### Reading Records

```python
from ommi.database.query_results import DBQueryResult
from ommi.database.results import DBStatusNoResultException

# Find by ID with match/case
result = await db.find(User.id == 1).one()
match result:
    case DBQueryResult.DBQuerySuccess(user):
        print(f"Found: {user.name}")
    case DBQueryResult.DBQueryFailure(DBStatusNoResultException()):
        print("No user found")
    case DBQueryResult.DBQueryFailure(exception):
        print(f"Error: {exception}")

# Or use or_use() for simpler handling
user = await db.find(User.id == 1).one.or_use(None)
if user:
    print(f"Found: {user.name}")

# Find multiple records
adult_users = await db.find(User.age >= 18).or_raise()
async for user in adult_users:
    print(f"Adult user: {user.name}")

# Count records
count = await db.find(User.age > 30).count.or_use(0)
print(f"Users over 30: {count}")
```

### Updating Records

```python
# Update through query
await db.find(User.name == "Alice").update(age=31)

# Update specific record
user = await db.find(User.id == 1).one.or_use(None)
if user:
    user.age = 32
    await user.save()
```

### Deleting Records

```python
# Delete through query
await db.find(User.age < 18).delete()

# Delete specific record  
user = await db.find(User.id == 1).one.or_use(None)
if user:
    await user.delete()
```

## Schema Management

```python
from ommi.models.collections import ModelCollection

# Create a model collection
collection = ModelCollection()

# Register models with collection
@ommi_model(collection=collection)
@dataclass
class User:
    # ... field definitions

# Apply schema to database
await db.sync_models(collection)

# Remove schema from database
await db.drop_models(collection)
```

## Error Handling

Ommi uses a result-based error handling system:

```python
from ommi.database.results import DBResult
from ommi.database.query_results import DBQueryResult

# Pattern matching for explicit success/failure handling
result = await db.add(user)
match result:
    case DBResult.DBSuccess(saved_user):
        print(f"Success: {saved_user}")
    case DBResult.DBFailure(exception):
        print(f"Error: {exception}")

# Use or_raise() for exception-based handling
user = await db.find(User.id == 1).one.or_raise()

# Use or_use() for default values
user = await db.find(User.id == 999).one.or_use(None)
```

## Complete Example

```python
import asyncio
from dataclasses import dataclass
from typing import Annotated
from ommi import Ommi, ommi_model, Key, ReferenceTo, Lazy
from ommi.ext.drivers.sqlite import SQLiteDriver
from ommi.models.collections import ModelCollection

# Create model collection
collection = ModelCollection()

@ommi_model(collection=collection)
@dataclass
class User:
    name: str
    age: int
    id: Annotated[int, Key] = None

@ommi_model(collection=collection)
@dataclass
class Post:
    title: str
    content: str
    author_id: Annotated[int, ReferenceTo(User.id)]
    author: Lazy[User]
    id: Annotated[int, Key] = None

async def main():
    # Create database connection
    async with Ommi(SQLiteDriver.connect()) as db:
        # Set up schema
        await db.sync_models(collection)

        # Create user
        user = User(name="Alice", age=30)
        await db.add(user)

        # Create post
        post = Post(
            title="My First Post",
            content="Hello, Ommi!",
            author_id=user.id
        )
        await db.add(post)

        # Query with relationships
        post = await db.find(Post.title == "My First Post").one.or_use(None)
        if post:
            author = await post.author
            print(f"Post '{post.title}' by {author.name}")

if __name__ == "__main__":
    asyncio.run(main())
```

This guide covers the essential components of Ommi. For more advanced features and detailed API documentation, refer to the full documentation.