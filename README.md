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
- Select, Insert, Update, Delete, Count
- No relationships or joins

#### PostgreSQL

- Table creation from models
- Select, Insert, Update, Delete, Count
- No relationships or joins

#### MongoDB

- Collection creation from models
- Fetch, Insert, Update, Delete, Count
- No relationships or nested documents

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
from ommi.models.collections import ModelCollection

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
    async with SQLiteDriver.from_config(SQLiteConfig(filename=":memory:")) as db:
        ...
```

### Database Actions

The database drivers provide `add`, `count`, `delete`, `fetch`, `sync_schema`, and `update` methods. These methods should
be wrapped in an `ommi.drivers.DatabaseAction`. The database action will capture the return and wrap it in a
`DatabaseStatus` result that is either a `Success` or `Exception`. The database action provides an `or_raise` method
that will force the exception to be raised immediately or return a `Success` result. The `DatabaseStatus` types are
sub-types of `tramp.results.Result` types.

#### Add

Add takes any number of model instances and adds them to the database.

```python
user_1 = User(name="Alice", age=25)
user_2 = User(name="Alice", age=25)
await db.add(user_1, user_2).raise_on_errors()
```

#### Find

Find returns a `FindAction`. This action is used to count, delete, fetch, or set fields on models in the database. It
takes any number of predicates that are AND'd together. It doesn't return any models or make any changes to the database
on its own.

#### Count

Count is an action of `find` that returns the number of models that match the predicates passed to `find`. It returns an
`AsyncResultWrapper` which allows you to access the returned `int` value through chaining, you can read more about it
below.

```python
count = await db.find(User.name == "Alice").count().value
```

#### Delete

Delete is an action of `find` that deletes all models that match the predicates passed to `find`. It also returns
an `AsyncResultWrapper`.

```python
await db.find(User.id == user.id).delete().raise_on_errors()
```

#### Fetch

Fetch is an action of `find` that returns all models that match the predicates passed to `find`. It provides `all` and
`one` helper methods to help with value unpacking, they both raise on errors. Calling `fetch` directly will  return an
`AsyncResultWrapper` that contains the list of models.

```python
users = await db.find(User.name == "Alice").fetch().value
```

```python
users = await db.find(User.name == "Alice").fetch.all()
```

```python
user = await db.find(User.name == "Alice").fetch.one()
```

Models provide a `reload` method that will pull the latest data from the database. It returns an `AsyncResultWrapper`.

```python
await user.reload().raise_on_errors()
```

#### Set

Set is an action of `find` that updates all models that match the predicates passed to `find`. It takes a any number of
keyword arguments that are used to update the models fields. It returns an `AsyncResultWrapper`.

```python
await db.find(name="bob").set(name = "Bob").raise_on_errors()
```

Models provide a `save` method that will push changed fields to the database. It returns an
`AsyncResultWrapper`.

```python
user.name = "Bob"
await user.save().raise_on_errors()
```

#### Schema

Schema is an action object that provides methods to manipulate the database itself. It can optionally be passed an
optional `ModelCollection` or nothing to default to the global collection.

Its `create_models` action returns an `AsyncResultWrapper` that contains a list of the models that were created.

```python
await db.schema().create_models().raise_on_errors()
```

```python
await db.schema(some_model_collection).create_models().raise_on_errors()
```

It also provides a `delete_models` action that deletes all models in the collection from the database.

```python
await db.schema(some_model_collection).delete_models().raise_on_errors()
```

### AsyncResultWrapper

`AsyncResultWrapper` is a wrapper around the result of an async database action. It provides various awaitable
properties and methods that allow you to access the result of the action. Awaiting the `AsyncResultWrapper` itself will
return a `DatabaseResult.Success` object if the action succeeded or a `DatabaseResult.Failure` object if there was an
exception.

```python
match await db.find(User.name == "Alice").count():
    case DatabaseResult.Success(value):
        print(value)

    case DatabaseResult.Failure(error):
        print(error)
```

#### Value

Value is an awaitable property that returns the value of the action. It will raise an exception if the action failed.

```python
await db.find(User.name == "Alice").count().value
```

#### Value Or

Value or is a method that takes a default value and returns the value of the action or the default value if the action
failed.

```python
count = await db.find(User.name == "Alice").count().value_or(0)
```

#### Raise on Errors

Raise on errors is a method that will raise an exception if the action failed. If the action succeeds it'll return
nothing. It's a convenience method that allows you to raise errors and discard the result on success.

```python
await db.find(User.name == "Alice").delete().raise_on_errors()
```

### Database Results

`DatabaseResult` is a result type that is used to wrap the values of database actions. It provides a `Success` and
`Failure` type that can be used to match on the result of an action.

```python
match await db.find(User.name == "Alice").count():
    case DatabaseResult.Success(value):
        print(value)

    case DatabaseResult.Failure(error):
        print(error)
```

#### Value and Value Or

`DatabaseResult` objects provide a `value` property that returns the value of the action or raises an exception if the
action failed. It also provides a `value_or` that takes a default value that is returned if the action failed.

Unlike `AsyncResultWrapper`, `DatabaseResult` objects do not need to be awaited.

```python
result = await db.find(User.name == "Alice").count()
print(result.value)  # Raises an exception if the action failed
```

```python
result = await db.find(User.name == "Alice").count()
print(result.value_or(0))  # Prints 0 if the action failed
```

#### Error

`DatabaseResult` objects provide an `error` property that returns the exception that caused the action to fail or `None`
if the action succeeded.

```python
result = await db.find(User.name == "Alice").count()
print(result.error)  # Prints None if the action succeeded
```

### Lazy Loaded Relationships

Ommi provides support for lazy loading relationships between models. It fully supports forward references as string
annotations. There are two supported relationship types using the `ommi.query_fields.LazyLoadTheRelated` and
`ommi.query_fields.LazyLoadEveryRelated` generic types as annotations. It relies on models using the
`ommi.field_metadata.ReferenceTo` annotation to define which field references which field on another model.

```python
@ommi_model
@dataclass
class User:
    id: int

    posts: LazyLoadEveryRelated["Post"]

class Post:
    id: int
    author_id: Annotated[int, ReferenceTo(User)]

    author: LazyLoadTheRelated[User]
```

`LazyLoadTheRelated` and `LazyLoadEveryRelated` are awaitable to fetch the related models. They also provide an
awaitable `value` property that returns the same value as well as a `get` method that takes a default value in case of a
failure. `LazyLoadTheRelated` will return a single model while `LazyLoadEveryRelated` will return a `list` of models.

```python
user = User(id=1)
posts = await user.posts
```

Lazy fields will only fetch once and then cache the result.

#### Get

'LazyQueryFields` provide a `get` method that takes a default value and returns the value of the relationship or the
default value if there is an error.

```python
user = User(id=1)
posts = await user.posts.get([])
```

### Value

`LazyQueryFields` provide a `value` property that returns the value of the relationship or raises an exception if there
is an error.

```python
user = User(id=1)
posts = await user.posts.value
```

### Refresh

`LazyQueryFields` provide a `refresh` method that will fetch the related models again and update the cache.

```python
user = User(id=1)
await user.posts.refresh()
```

### Refresh if needed

The `refresh_if_needed` method will only fetch the related models if they haven't been fetched yet.

```python
user = User(id=1)
await user.posts.refresh_if_needed()
```

### Result

`LazyQueryFields` provide a `result` property that returns the `tramp.results.Result` object directly. This can be
helpful for handling errors more explicitly.

```python
user = User(id=1)
match await user.posts.result:
    case Value(posts):
        ...

    case Error(error):
        ...
```