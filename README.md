# Ommi

> [!CAUTION]
> Ommi is under construction and much of the functionality is undergoing frequent revision. There is no guarantee future
> versions will be backwards compatible.

Have you ever needed to use a database for a simple project but didn't want to worry about which database you were going
to use? Or maybe you wanted to create a package that needed to store data but didn't want to force your users to use a
specific database? Meet Ommi, a simple object model mapper that allows you to use whatever models you want to interface
with whatever database you like.

Ommi doesn't provide its own model types, it allows you to use whatever models you are already using. Compatibility with
the most popular model implementations are ensured through unit tests.

### Compatible Model Implementations

Ommi's test suite checks for compatibility with the following model implementations:

- [Dataclasses](https://docs.python.org/3/library/dataclasses.html)
- [Attrs](https://www.attrs.org/en/stable/)
- [Pydantic](https://docs.pydantic.dev/latest/)

### Included Database Support

#### SQLite3

- Table creation from models
- Select, Insert, Update, Delete

## Usage

### Defining Models

All models that support Ommi database drivers need to use the `ommi_model` class decorator.

```python
from ommi import ommi_model, Key
from dataclasses import dataclass
from typing import Annotated

@ommi_model
@dataclass
class User:
    name: str
    age: int
    id: Annotated[int, Key] = None  # Optional primary key
```

Models can be assigned to model collections. Any model not assigned a collection will be assigned to a global
collection which can be accessed by calling `ommi.models.get_global_collection()`.

```python
from ommi.model_collections import ModelCollection

collection = ModelCollection()

@ommi_model(collection=collection)
@dataclass
class User:
    name: str
    age: int
```

### Connecting

```python
from ommi.ext.drivers.sqlite import SQLiteDriver, SQLiteConfig


async def example():
    async with SQLiteDriver(SQLiteConfig(filename=":memory:")) as db:
        ...
```

### Database Actions

The database drivers provide `add`, `count`, delete`, `fetch`, `sync_schema`, and `update` methods. These methods should
be wrapped in an `ommi.drivers.DatabaseAction`. The database action will capture the return and wrap it in a
`DatabaseStatus` result that is either a `Success` or `Exception`. The database action provides an `or_raise` method
that will force the exception to be raised immediately or return a `Success` result. The `DatabaseStatus` types are
sub-types of `tramp.results.Result` types.

#### Add

Add takes any number of model instances and adds them to the database.

```python
user = User(name="Alice", age=25)
await db.add(user).or_raise()
```

#### Count

Count takes any number of predicates and returns the number of models that match the predicates. The predicates will be
ANDed together.

```python
count = await db.count(User.name == "Alice").or_raise()
```

#### Delete

Delete takes any number of model instances and deletes them from the database.

```python
await db.delete(user).or_raise()
```

#### Fetch

Fetch takes any number of predicates and returns a result of matching models. The predicates will be ANDed together.

```python
users = await db.fetch(User.name == "Alice").or_raise()
```

#### Sync Schema

Sync schema takes a model collection and makes updates the database to match. If no model collection is provided, a
global collection is used.

```python
await db.sync_schema().or_raise()
```

#### Update

Update takes any number of model instances and syncs their changes to the database.

```python
user.name = "Bob"
await db.update(user).or_raise()
```