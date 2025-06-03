# Getting Started with Ommi

This comprehensive guide will walk you through using Ommi's general interface, including driver configuration, database operations, result handling, and error management.

## Installation

Ommi is available on PyPI and can be installed using Poetry (or pip):

```bash
poetry add ommi
```

You'll also need a driver for your target database. Ommi includes built-in drivers for popular databases:

```bash
# For SQLite (great for getting started)
poetry add ommi[sqlite]

# For PostgreSQL
poetry add ommi[postgresql]

# For MongoDB
poetry add ommi[mongodb]
```

## Core Concepts

Ommi's architecture centers around three main components:

1. **Models**: Your data structures decorated with `@ommi_model()`
2. **Drivers**: Database-specific adapters that handle the actual database communication
3. **Ommi Instance**: The main interface that orchestrates all database operations

## Defining Models

All models must use the `@ommi_model` decorator to be compatible with Ommi. Ommi supports multiple model implementations including **dataclasses**, **Pydantic**, and **attrs**:

### Using Dataclasses (Standard Library)

```python
from dataclasses import dataclass
from typing import Annotated
from ommi import ommi_model, Key

@ommi_model
@dataclass
class User:
    name: str
    email: str
    age: int
    id: Annotated[int, Key] = None  # Optional auto-generated primary key
```

### Using Pydantic

```python
from pydantic import BaseModel
from typing import Annotated
from ommi import ommi_model, Key

@ommi_model
class User(BaseModel):
    name: str
    email: str
    age: int
    id: Annotated[int, Key] = None
```

### Using Attrs

```python
import attrs
from typing import Annotated
from ommi import ommi_model, Key

@ommi_model
@attrs.define
class User:
    name: str
    email: str
    age: int
    id: Annotated[int, Key] = None
```

All three approaches work identically with Ommi's database operations. Choose the one that best fits your project's needs and existing patterns.

## Driver Configuration

Each database driver has its own configuration options. Here's how to configure the most common drivers:

### SQLite Driver

```python
from ommi.ext.drivers.sqlite import SQLiteDriver, SQLiteSettings

# In-memory database (perfect for testing)
driver = SQLiteDriver.connect()

# File-based database
driver = SQLiteDriver.connect(SQLiteSettings(
    database="./my_app.db",
    isolation_level="IMMEDIATE"
))
```

### PostgreSQL Driver

```python
from ommi.ext.drivers.postgresql import PostgreSQLDriver, PostgreSQLSettings

driver = PostgreSQLDriver.connect(PostgreSQLSettings(
    host="localhost",
    port=5432,
    database="my_database",
    user="username",
    password="password"
))
```

### MongoDB Driver

```python
from ommi.ext.drivers.mongodb import MongoDBDriver, MongoDBSettings

# Basic connection (uses defaults: localhost:27017, database="ommi")
driver = MongoDBDriver.connect()

# Custom configuration
driver = MongoDBDriver.connect(MongoDBSettings(
    host="localhost",
    port=27017,
    database_name="my_database",
    username="myuser",
    password="mypassword",
    authSource="admin",
    timeout=20000,
    connection_options={"retryWrites": True}
))
```

## The Ommi Interface

The `Ommi` class is your primary interface for all database operations:

```python
import asyncio
from ommi import Ommi

async def main():
    # Create driver instance
    driver = SQLiteDriver.connect()
    
    # Initialize Ommi with the driver
    async with Ommi(driver) as db:
        # All database operations go through 'db'
        pass

if __name__ == "__main__":
    asyncio.run(main())
```

### Model Collections

Ommi organizes models into **collections**, which are logical groups that get managed together in the database. There are two approaches:

#### Global Collection (Default)

When you don't specify a collection, models are automatically added to a global collection:

```python
from dataclasses import dataclass
from ommi import ommi_model

# These models are automatically added to the global collection
@ommi_model
@dataclass
class User:
    name: str
    email: str
    age: int
    id: Annotated[int, Key] = None

@ommi_model
@dataclass
class Post:
    title: str
    content: str
    author_id: int
    id: Annotated[int, Key] = None

# Global collection models are set up automatically on first use
async with Ommi(driver) as db:
    # Schema is created automatically for both User and Post
    await db.add(User(name="Alice", email="alice@example.com", age=30)).or_raise()
```

#### Custom Collections (Explicit Control)

For larger applications, you can create your own collections to organize related models:

```python
from ommi.models.collections import ModelCollection

# Create separate collections for different domains
user_collection = ModelCollection()
blog_collection = ModelCollection()

@ommi_model(collection=user_collection)
@dataclass
class User:
    name: str
    email: str
    age: int
    id: Annotated[int, Key] = None

@ommi_model(collection=user_collection)
@dataclass  
class UserProfile:
    user_id: int
    bio: str
    id: Annotated[int, Key] = None

@ommi_model(collection=blog_collection)
@dataclass
class Post:
    title: str
    content: str
    author_id: int
    id: Annotated[int, Key] = None

# Explicitly control which models are set up and when
async with Ommi(driver, allow_imlicit_model_setup=False) as db:
    # Set up only user-related models first
    await db.use_models(user_collection)
    
    # Later, set up blog models when needed
    await db.use_models(blog_collection)
    
    # Now you can use models from both collections
    await db.add(User(name="Alice", email="alice@example.com", age=30)).or_raise()
```

**Benefits of Custom Collections:**
- **Modular setup**: Set up only the models you need for specific operations
- **Better organization**: Group related models together logically  
- **Migration control**: Manage schema changes for different parts of your application independently
- **Testing**: Easily set up subsets of your models for focused tests

## Database Operations

### Adding Records

```python
# Add a single record
user = User(name="Alice", email="alice@example.com", age=30)
result = await db.add(user)

# Add multiple records
users = [
    User(name="Bob", email="bob@example.com", age=25),
    User(name="Charlie", email="charlie@example.com", age=35)
]
result = await db.add(*users)
```

### Finding Records

The `find()` method returns a query builder that supports various operations:

```python
# Find all users and iterate over results
all_users_builder = db.find(User)
users_result = await all_users_builder.all()

# Using or_raise() for direct iteration over AsyncBatchIterator
async for user in await db.find(User.age >= 18).all().or_raise():
    print(f"Adult user: {user.name}, age: {user.age}")

# Using match/case for error handling with AsyncBatchIterator
match await db.find(User).all():
    case DBQueryResult.DBQuerySuccess(user_iterator):
        async for user in user_iterator:
            print(f"User: {user.name}")
    case DBQueryResult.DBQueryFailure(exception):
        print(f"Failed to fetch users: {exception}")

# Find a single user
user_builder = db.find(User.email == "alice@example.com")
user = await user_builder.one()

# Count records
count_builder = db.find(User.age > 30)
count = await count_builder.count()

# Convert AsyncBatchIterator to list (for small datasets)
users_list = await (await db.find(User.age < 25).all().or_raise()).to_list()
print(f"Found {len(users_list)} young users")
```

### Updating Records

```python
# Update using the query builder
await db.find(User.name == "Alice").update(age=31)

# Update with a dictionary
await db.find(User.age < 18).update({"status": "minor"})
```

### Deleting Records

```python
# Delete matching records
await db.find(User.age < 13).delete()
```

## Result Types and Error Handling

Ommi provides a comprehensive result system that wraps all database operations in result types, making error handling explicit and predictable.

### DBResult vs DBQueryResult

Ommi uses two main result types:

- **`DBResult[T]`**: For operations that add/modify single records (like `add()`)
- **`DBQueryResult[T]`**: For query operations that fetch data (like `find().all()`)

### Result Pattern Matching

The recommended way to handle results is using Python's `match/case` syntax:

```python
from ommi.database.results import DBResult
from ommi.database.query_results import DBQueryResult, DBStatusNoResultException

# Handling add operations
user = User(name="Alice", email="alice@example.com", age=30)
match await db.add(user):
    case DBResult.DBSuccess(added_users):
        print(f"Successfully added {len(added_users)} users")
        first_user = added_users[0]
        print(f"User ID: {first_user.id}")
    case DBResult.DBFailure(exception):
        print(f"Failed to add user: {exception}")

# Handling query operations  
match await db.find(User.email == "alice@example.com").one():
    case DBQueryResult.DBQuerySuccess(user):
        print(f"Found user: {user.name}")
    case DBQueryResult.DBQueryFailure(DBStatusNoResultException()):
        print("No user found with that email")
    case DBQueryResult.DBQueryFailure(exception):
        print(f"Database error: {exception}")
```

### Convenience Methods

For simpler error handling, Ommi provides convenience methods:

```python
# or_raise(): Execute operation and raise exceptions directly
try:
    user = await db.find(User.email == "alice@example.com").one().or_raise()
    print(f"Found user: {user.name}")
except DBStatusNoResultException:
    print("User not found")
except Exception as e:
    print(f"Database error: {e}")

# or_use(): Provide a default value on failure
users = await db.find(User.age > 100).all().or_use([])
print(f"Found {len(users)} centenarians")

# result_or(): Access result with default fallback
count = (await db.find(User).count()).result_or(0)
print(f"Total users: {count}")
```

### Working with AsyncBatchIterator

Query results that return multiple records use `AsyncBatchIterator`, which provides efficient, lazy loading:

```python
# Method 1: Using or_raise() for direct iteration
async for user in await db.find(User.age >= 18).all().or_raise():
    print(f"Adult user: {user.name}")

# Method 2: Using match/case for error handling
match await db.find(User).all():
    case DBQueryResult.DBQuerySuccess(user_iterator):
        async for user in user_iterator:
            print(f"User: {user.name}")
    case DBQueryResult.DBQueryFailure(exception):
        print(f"Failed to fetch users: {exception}")

# Method 3: Convert to list (for small datasets)
users_list = await (await db.find(User).all().or_raise()).to_list()
print(f"Loaded {len(users_list)} users into memory")
```

## Transactions

Ommi provides built-in transaction support for maintaining data consistency:

```python
# Basic transaction usage
async with db.transaction() as tx:
    # All operations within this block are part of one transaction
    await tx.add(User(name="Alice", email="alice@example.com", age=30)).or_raise()
    await tx.add(Post(title="Hello World", content="My first post", author_id=1)).or_raise()
    
    # Transaction automatically commits on successful exit
    # or rolls back if an exception occurs

# Manual transaction control
async with db.transaction() as tx:
    try:
        await tx.add(User(name="Bob", email="bob@example.com", age=25)).or_raise()
        
        # Some business logic that might fail
        if some_validation_fails():
            await tx.rollback()  # Explicit rollback
            return
            
        await tx.commit()  # Explicit commit (optional)
    except Exception as e:
        # Transaction automatically rolls back on exception
        print(f"Transaction failed: {e}")
```

## Complex Query Examples

### Combining Multiple Conditions

```python
from ommi.query_ast import when

# Using method chaining for AND conditions
active_adults = db.find(User.age >= 18, User.status == "active")

# Using when() for complex OR logic
complex_query = db.find(
    when(User.age < 18).Or(
        when(User.status == "premium").And(User.age >= 65)
    )
)
```

### Working with Results

```python
# Count and then fetch if needed
user_count = await db.find(User.age >= 18).count().or_raise()
if user_count > 0:
    adult_users = await db.find(User.age >= 18).all().or_raise()
    async for user in adult_users:
        print(f"Adult user: {user.name}")

# Fetch one user, handle not found gracefully
newest_user = await db.find(User).one().or_use(None)
if newest_user:
    print(f"Newest user: {newest_user.name}")
else:
    print("No users in database")
```

## Error Handling Best Practices

1. **Use match/case for comprehensive error handling**:
```python
match await db.find(User.id == user_id).one():
    case DBQueryResult.DBQuerySuccess(user):
        # Handle success
        pass
    case DBQueryResult.DBQueryFailure(DBStatusNoResultException()):
        # Handle not found
        pass  
    case DBQueryResult.DBQueryFailure(exception):
        # Handle other errors
        pass
```

2. **Use or_raise() when you want exceptions**:
```python
try:
    user = await db.find(User.id == user_id).one().or_raise()
    # Work with user
except DBStatusNoResultException:
    # Handle not found
    pass
```

3. **Use or_use() for defaults**:
```python
# Safe defaults for counts and lists
user_count = (await db.find(User).count()).result_or(0)
users = await db.find(User).all().or_use([])
```

## Next Steps

Now that you understand Ommi's core interface and result handling, explore these advanced topics:

- **[Models](usage/models.md)**: Learn about field types, validation, and model relationships
- **[Lazy Fields](usage/lazy-fields.md)**: Understand lazy loading for efficient relationship traversal
- **[Model Collections](usage/model-collections.md)**: Organize models into logical groups for larger applications
- **[Association Tables](usage/association-tables.md)**: Handle many-to-many relationships 