# Handling Database Operation Results

Ommi provides robust result types like `DBResult[T]` and `DBQueryResult[T]` that allow you to explicitly handle the outcome of database operations, such as success or failure, without immediately resorting to `try/except` blocks or methods like `.or_raise()`.

This approach, often used with Python's `match/case` statement, promotes clear and type-safe result handling.

## Understanding `DBResult` and `DBQueryResult`

Most Ommi operations that interact with the database (e.g., adding a record, finding one or more records) don't return the raw data or raise an exception directly. Instead, they typically return an awaitable object that, when awaited, resolves to either a `DBResult` or a `DBQueryResult` instance.

These result types are wrappers around the actual outcome and have two main variants:

*   **`DBSuccess[T]`** (or `DBQuerySuccess[T]`): Indicates the operation was successful and contains the result of type `T`.
    *   For example, `T` could be your model instance for `db.find(...).one()`, a list or iterator of models for `db.find(...).all()`, an integer for `db.find(...).count()`, or the added model for `db.add(...)`.
*   **`DBFailure[T]`** (or `DBQueryFailure[T]`): Indicates the operation failed and contains the `Exception` that occurred.

Both `DBResult` and `DBQueryResult` (and their success/failure variants) support the `result_or(default_value)` method and can be used effectively with `match/case`.

## Using `match/case` for Result Handling

Python's structural pattern matching (`match/case`) is a powerful way to handle these result types.

### Example: Fetching a Single Record with `db.find(...).one`

When you use `db.find(...).one`, the operation might succeed (record found) or fail (record not found, or other database error).

```python
import asyncio
from dataclasses import dataclass
from typing import Optional, Annotated

from ommi import Ommi, ommi_model
from ommi.models.field_metadata import Key
from ommi.ext.drivers.sqlite import SQLiteDriver
from ommi.database import DBResult # For type hinting, DBSuccess/DBFailure are accessed via DBResult
# from ommi.database import DBQueryResult # If specifically handling find results

@ommi_model()
@dataclass
class User:
    id: Annotated[int, Key]
    name: str

async def get_user_by_id(db: Ommi, user_id: int) -> Optional[User]:
    # The .one itself returns an awaitable that resolves to DBResult or DBQueryResult
    # For clarity, we can await it to get the actual result object.
    query_operation = db.find(User.id == user_id).one
    result_status: DBResult[User] = await query_operation # Await the operation to get the status object

    match result_status:
        case DBResult.DBSuccess(user_instance): # Matches if successful, extracts the User instance
            print(f"Successfully fetched user: {user_instance.name}")
            return user_instance
        case DBResult.DBFailure(exception):
            # DBStatusNoResultException is common if .one finds nothing
            if isinstance(exception, DBResult.DBStatusNoResultException): # Assuming this specific exception type
                print(f"User with ID {user_id} not found.")
            else:
                print(f"Error fetching user {user_id}: {type(exception).__name__} - {exception}")
            return None
        case _:
            print("Unhandled result status.") # Should not happen with DBResult
            return None

async def main():
    driver = SQLiteDriver.connect()
    async with Ommi(driver) as db:
        await db.add(User(id=1, name="Alice")).or_raise()

        user = await get_user_by_id(db, 1)
        if user:
            print(f"Main found: {user.name}")

        user_not_found = await get_user_by_id(db, 2)
        if not user_not_found:
            print("Main confirmed: User 2 not found.")

if __name__ == "__main__":
    asyncio.run(main())
```

**Explanation:**

*   `query_operation = db.find(User.id == user_id).one` creates the awaitable query part.
*   `result_status: DBResult[User] = await query_operation` executes the query and gives you the `DBResult` object (which could be `DBSuccess` or `DBFailure`).
*   `case DBResult.DBSuccess(user_instance)`: If the query was successful and a user was found, this case matches. The `user_instance` variable is automatically assigned the `User` object from `DBSuccess.result`.
*   `case DBResult.DBFailure(exception)`: If any error occurred (including not finding a record with `.one`), this case matches. The `exception` variable holds the exception instance. You can then inspect the type of exception.
    *   Note: The exact exception type for "not found" by `.one()` would be `ommi.database.results.DBStatusNoResultException` (or similar, based on the imports in your `query_results.py`).

### Example: Adding a Record with `db.add`

The `db.add()` operation also returns a `DBResult`.

```python
# (Assuming User model and imports from previous example)

async def add_new_user(db: Ommi, user_id: int, name: str):
    new_user = User(id=user_id, name=name)
    add_operation = db.add(new_user) # add() returns an awaitable
    result_status: DBResult[User] = await add_operation

    match result_status:
        case DBResult.DBSuccess(added_user): # Contains the model instance that was added
            print(f"Successfully added user: {added_user.name} (ID: {added_user.id})")
            return added_user
        case DBResult.DBFailure(exception):
            print(f"Error adding user {name}: {type(exception).__name__} - {exception}")
            # e.g., could be a constraint violation if ID already exists and is a PK
            return None

async def main_add():
    driver = SQLiteDriver.connect()
    async with Ommi(driver) as db:
        user_bob = await add_new_user(db, 2, "Bob")
        if user_bob:
            # Attempt to add again, which might cause a PK constraint error
            await add_new_user(db, 2, "Bobby") # This will likely print an error

# if __name__ == "__main__":
#     asyncio.run(main_add())
```

## Using `result_or(default_value)`

If you simply want to get the result or a default value if the operation fails (or, in some cases, if no result is found), the `result_or(default)` method is very convenient.

```python
# (Assuming User model and imports from previous example)

async def get_user_or_default(db: Ommi, user_id: int) -> User:
    default_user = User(id=-1, name="Default User")
    query_operation = db.find(User.id == user_id).one
    user_instance_or_default = (await query_operation).result_or(default_user)

    # Note: If .one() fails due to a non-DBStatusNoResultException (e.g., DB connection issue),
    # result_or() would still return the default if the overall result is a DBFailure.
    # If the operation yields DBSuccess but with an empty result (not typical for .one but for .all), behavior depends on T.

    if user_instance_or_default.id == -1:
        print(f"User {user_id} not found, using default.")
    else:
        print(f"Found user {user_id}: {user_instance_or_default.name}")
    return user_instance_or_default

async def main_result_or():
    driver = SQLiteDriver.connect()
    async with Ommi(driver) as db:
        await db.add(User(id=3, name="Charlie")).or_raise()
        await get_user_or_default(db, 3)
        await get_user_or_default(db, 4) # Will use default

# if __name__ == "__main__":
#     asyncio.run(main_result_or())
```
**When `result_or` is useful:**
*   When you have a sensible default to fall back to.
*   When you want to avoid `match/case` for simpler scenarios where you don't need detailed error inspection.

**Important Note on `.one.result_or(default)`:**
If `db.find(...).one` fails to find a record, it results in a `DBFailure` containing a `DBStatusNoResultException`. In this case, `(await query_operation).result_or(default)` will correctly return your `default`.

## Comparison with `.or_raise()` and `.or_else()`

*   **`.or_raise()`**: Awaits the operation and if it's a failure (any `DBFailure` or `DBQueryFailure`), it raises the contained exception. This is concise if you want exceptions to propagate and be handled by a higher-level `try/except`.

*   **`.or_else(default_value)` (or similar, e.g. `.or_use(default_value)` seen in `WrapInResult`)**: This is a common alternative name for functionality similar to `result_or`. Ommi provides `result_or(default)` directly on the `DBResult`/`DBQueryResult` objects *after* they have been awaited.
    The `LazyQueryField` in `ommi.models.query_fields` shows an `async def or_use[D](self, default: D)` method, which internally calls `(await self.get_result()).result_or(default)`. This provides a convenient shortcut on the lazy field itself.

*   **`match/case`**: Offers the most explicit control. You can distinguish between different types of failures, log specific errors, or take different actions based on the success or failure details.

*   **`(await operation).result_or(default)`**: Good for providing a fallback value without detailed error handling logic.

Choose the method that best fits the clarity and error handling requirements of your specific situation.

## Results of `.all()` operations

When you use an operation like `db.find(...).all()`, the `DBQuerySuccess` variant will typically contain an iterable (like `AsyncBatchIterator[YourModel]`) as its result. You can then iterate over this.

```python
# (Assuming User model and imports)
async def get_all_users(db: Ommi):
    find_all_op = db.find(User).all() # This builder itself is awaitable or has awaitable methods
    result_status: DBQueryResult[AsyncBatchIterator[User]] = await find_all_op # Await the .all() builder

    match result_status:
        case DBQueryResult.DBQuerySuccess(users_iterator):
            print("Successfully fetched users:")
            users_found = False
            async for user in users_iterator:
                users_found = True
                print(f"- {user.name}")
            if not users_found:
                print("(No users found in the database)")
        case DBQueryResult.DBQueryFailure(exception):
            print(f"Error fetching all users: {exception}")

# ... (main function to test this)
```

By understanding and utilizing `DBResult`, `DBQueryResult`, `match/case`, and `result_or`, you can write more resilient and expressive database interaction code with Ommi. 