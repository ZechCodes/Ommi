"""Provides the main `Ommi` class for database interaction.

This module defines the `Ommi` class, which serves as the primary entry point
for all database operations within the Ommi ORM. It encapsulates a database
driver and provides high-level methods for common tasks such as adding records,
finding records, managing model schemas, and handling transactions.

The `Ommi` class is designed to be initialized with a specific database driver
(e.g., for SQLite, PostgreSQL) and then used to interact with the database
associated with that driver.

Key functionalities include:

-   Adding new model instances to the database (`add` method).
-   Finding existing model instances based on various criteria (`find` method),
    which returns a builder for flexible query execution (all, one, count, update, delete).
-   Managing database schemas for model collections (`use_models`, `remove_models`).
-   Providing an asynchronous context manager for database transactions (`transaction` method).
-   Implicitly setting up models from a global collection if `allow_implicit_model_setup` is true.

Usage Example:
    ```python
    from ommi import Ommi, ommi_model
    from ommi.ext.drivers.sqlite import SQLiteDriver # Example driver
    from ommi.models.collections import ModelCollection

    collection = ModelCollection()

    @ommi_model(collection=collection)
    class User:
        id: int
        name: str

    # Initialize with a driver (e.g., in-memory SQLite for this example)
    db = Ommi(SQLiteDriver.connect())

    async def main():
        # Ensure models are known to the database
        await db.use_models(collection)

        # Add a user
        add_result = await db.add(User(name="Alice"))
        if add_result.result_or(False):
            print(f"Added: {add_status.result}")

        # Find the user
        user = await db.find(User.name == "Alice").one()
        if user.result_or(False):
            print(f"Found: {user_status.value}")

        # Perform operations in a transaction
        async with db.transaction() as t:
            await t.add(User(name="Bob"))
            # ... other operations ...
            # Transaction commits on successful exit, rolls back on exception.
    ```
"""
from typing import Awaitable, TYPE_CHECKING

import ommi
from ommi.query_ast import when
from ommi.database.transaction import OmmiTransaction

if TYPE_CHECKING:
    from ommi.drivers import BaseDriver
    from ommi.models.collections import ModelCollection
    from ommi.shared_types import DBModel


class Ommi[TDriver: "ommi.BaseDriver"]:
    """Main class for interacting with a database through a specified driver.

    The `Ommi` class provides a high-level API for database operations, including
    adding, finding, updating, and deleting records, as well as managing database
    schemas and transactions. It is initialized with a database driver instance,
    which dictates how it communicates with the underlying database.

    Attributes:
        driver (TDriver): The database driver instance used for all operations.

    Example: Example Usage
        ```python
        from ommi import Ommi, ommi_model
        from ommi.ext.drivers.sqlite import SQLiteDriver # Example driver
        from ommi.models.collections import ModelCollection

        collection = ModelCollection()

        @ommi_model(collection=collection)
        class User:
            id: int
            name: str

        async def main():
            driver = SQLiteDriver.connect()
            async with Ommi(driver) as db:
                await db.use_models(collection)
                await db.add(User(name="Alice")).or_raise()
                user = await db.find(User.name == "Alice").one.or_raise()
                print(f"Found: {user.name}")
        ```
    """
    def __init__(self, driver: TDriver, *, allow_imlicit_model_setup: bool = True):
        """Initializes the Ommi database interaction layer.

        Args:
            driver: The database driver instance (e.g., `SQLiteDriver`, `PostgreSQLDriver`)
                that Ommi will use to communicate with the database.
            allow_imlicit_model_setup: If `True` (the default), Ommi will attempt to
                automatically set up models from `ommi.models.collections.get_global_collection()`
                before the first operation if no models have been explicitly registered via
                `use_models()`. This can be convenient for simpler setups but might be
                undesirable in complex applications where explicit schema management is preferred.
                Set to `False` to disable this behavior and require explicit calls to `use_models()`.
        """
        self._driver = driver
        self._known_model_collections: set["ModelCollection"] = set()
        self._allow_implicit_model_setup = allow_imlicit_model_setup

    @property
    def driver(self) -> TDriver:
        return self._driver

    def _ensure_model_setup(self) -> "Awaitable[None] | None":
        """Ensures that models are set up if implicit model setup is allowed.

        If `_allow_implicit_model_setup` is true and no model collections are currently
        known, this method will attempt to apply the schema of the global model collection
        obtained via `ommi.models.collections.get_global_collection()`.

        This is an internal method primarily called before operations like `add()` or `find()`
        to ensure the database schema is ready.

        Returns:
            An awaitable if models need to be set up (i.e., `self.use_models()` is called),
            otherwise `None`.
        """
        if not self._known_model_collections and self._allow_implicit_model_setup:
            return self.use_models(ommi.models.collections.get_global_collection())
        return None

    def add(
        self, *models: "ommi.shared_types.DBModel"
    ) -> "Awaitable[ommi.database.results.DBResult[ommi.shared_types.DBModel]]":
        """Persists one or more model instances to the database.

        This method takes new model instances and attempts to save them as new records.
        If implicit model setup is enabled and no models have been explicitly registered
        via `use_models()`, this method will trigger the setup of the global model collection.

        The result of the operation is wrapped in a `ommi.database.results.DBResult` type.
        This allows for explicit handling of the operation's success or failure:
        -   If successful, `DBResult.is_success` will be `True`, and `DBResult.value`
            will contain the added model instance(s) (potentially updated with database-generated
            values like primary keys).
        -   If an error occurs, `DBResult.is_failure` will be `True`, and
            `DBResult.exception` will hold the specific exception.

        Args:
            *models: A variable number of `DBModel` instances to be added to the
                     database. These should be new instances not yet persisted.

        Returns:
            An awaitable that resolves to a `DBResult`. The `DBResult` wraps the added
            model(s) on success or the exception on failure.

        Example: Adding a single user
            ```python
            from ommi.database.results import DBResult # For match/case

            user = User(name="Alice")
            result_one = await db.add(user)
            if result_one.is_success:
                added_user = result_one.value
                print(f"Added user: {added_user.name}")
            else:
                print(f"Failed to add user: {result_one.exception}")
            ```

        Example: Adding multiple users
            ```python
            user1 = User(name="Alice")
            user2 = User(name="Bob")
            result_many = await db.add(user1, user2)
            if result_many.is_success:
                added_items = result_many.value
                print(f"Successfully added {len(added_items)} users.")
            else:
                print(f"Failed to add multiple users: {result_many.exception}")
            ```
        """
        setup_awaitable = self._ensure_model_setup()
        if setup_awaitable is not None:
            # We need to wrap the add operation in a function that awaits the setup first
            async def _add_with_setup():
                await setup_awaitable
                return await self.driver.add(models)
            return ommi.database.results.DBResult.build(_add_with_setup)

        return ommi.database.results.DBResult.build(self.driver.add, models)

    def find(
        self, *predicates: "ommi.query_ast.ASTGroupNode | ommi.shared_types.DBModel | bool"
    ) -> "Awaitable[ommi.database.query_results.DBQueryResultBuilder[ommi.shared_types.DBModel]]":
        """Initiates a query to retrieve models from the database based on specified criteria.

        This method provides a flexible way to define conditions for your search. It returns
        an `ommi.database.query_results.DBQueryResultBuilder` instance immediately.
        This builder object is central to fetching data and does not execute the query
        until one of its data retrieval or modification methods is called and awaited.

        If implicit model setup is enabled and no models have been explicitly registered
        via `use_models()`, this method will trigger the setup of the global model collection.

        Available `DBQueryResultBuilder` methods:
        -   `.all()`: Asynchronously fetches all matching records. On success, returns an
            `AsyncBatchIterator` via `DBQueryResult.value`.
        -   `.one()`: Fetches a single record. On success, returns the record via `DBQueryResult.value`.
            Raises `DBStatusNoResultException` (accessible via `DBQueryResult.exception`)
            if no record is found.
        -   `.count()`: Returns the total number of matching records as an integer via
            `DBQueryResult.value`.
        -   `.delete()`: Deletes all records matching the predicates. Returns a `DBResult`
            indicating success or failure.
        -   `.update(**values)` or `.update(values_dict)`: Updates fields of matching records.
            Returns a `DBResult` indicating success or failure.

        Each of these execution methods (`.all()`, `.one()`, etc.) returns an awaitable.
        When this awaitable is resolved, it yields an `ommi.database.query_results.DBQueryResult`
        (for `.all()`, `.one()`, `.count()`) or an `ommi.database.results.DBResult`
        (for `.delete()`, `.update()`), allowing robust outcome handling.
        The `DBQueryResultBuilder` itself can also be directly awaited, defaulting to `.all()`.

        > **Note on Predicates:**
        > Predicates define the search criteria. You can use:
        > - Pythonic comparison expressions: `User.age > 18`
        > - `ommi.query_ast.when()` for complex AND/OR logic: `when(User.name == "A").Or(User.age < 20)`
        > - Model classes (e.g., `User`) to target all instances or provide context.

        Args:
            *predicates: Variable number of conditions that define the query. These are
                typically combined with AND logic by default (internally passed to
                `ommi.query_ast.when(*predicates)`).

        Returns:
            An awaitable that resolves to a `DBQueryResultBuilder`. This builder can then be
            used to execute the query and retrieve results in various forms.

        Example: Find user by ID
            ```python
            from ommi.query_ast import when
            from ommi.database.query_results import DBQueryResult
            from ommi.database.results import DBResult, DBStatusNoResultException

            user_id_to_find = 1
            query_by_id = db.find(User.id == user_id_to_find)
            result_status = await query_by_id.one()

            if result_status.is_success:
                user = result_status.value
                print(f"Found user by ID: {user.name}")
            elif result_status.exception_is(DBStatusNoResultException):
                print(f"User with ID {user_id_to_find} not found.")
            else:
                print(f"Error finding user by ID: {result_status.exception}")
            ```

        Example: Find users older than 18 and count them
            ```python
            older_users_query = db.find(User.age > 18, User.is_active == True)
            count_status = await older_users_query.count()
            if count_status.is_success:
                number_of_users = count_status.value
                print(f"Number of active users older than 18: {number_of_users}")
            else:
                print(f"Error counting users: {count_status.exception}")
            ```
        """
        setup_awaitable = self._ensure_model_setup()
        if setup_awaitable is not None:
            # We need to wrap the find operation in a function that awaits the setup first
            async def _find_with_setup():
                await setup_awaitable
                return ommi.database.query_results.DBQueryResult.build(self.driver, when(*predicates))
            return _find_with_setup()

        return ommi.database.query_results.DBQueryResult.build(self.driver, when(*predicates))

    async def use_models(self, model_collection: "ModelCollection") -> None:
        """Explicitly applies the schema for a given model collection to the database.

        This involves first attempting to delete any existing schema for the collection
        and then applying the new schema. This ensures that the database tables and
        indexes match the model definitions in the provided collection.

        This method should be called if `allow_implicit_model_setup` is `False` or if
        you need to manage different sets of models explicitly.

        Args:
            model_collection: The `ModelCollection` instance whose schema (tables, indexes)
                              needs to be created or updated in the database.
        """
        await self.driver.delete_schema(model_collection)
        await self.driver.apply_schema(model_collection)
        self._known_model_collections.add(model_collection)

    async def remove_models(self, model_collection: "ModelCollection") -> None:
        """Removes the schema for the given model collection from the database.

        This typically involves dropping tables associated with the models in the collection.
        The collection is also removed from Ommi's set of known model collections.

        Args:
            model_collection: The `ModelCollection` whose schema should be removed
                              from the database.
        """
        await self.driver.delete_schema(model_collection)
        self._known_model_collections.discard(model_collection)

    def transaction(self) -> OmmiTransaction:
        """Creates an asynchronous context manager for database transactions.

        Operations performed on the `OmmiTransaction` object within the `async with`
        block will be part of a single atomic transaction. The transaction is
        automatically committed if the block exits successfully, or rolled back
        if an unhandled exception occurs within the block.

        Returns:
            An `OmmiTransaction` instance that can be used with `async with`.

        Example: Basic transaction usage
            ```python
            async with db.transaction() as t:
                await t.add(User(name="Charlie"))
                # If an error occurs here, changes are rolled back.
                # If all operations succeed, changes are committed.
            ```

        Example: Manual rollback within a transaction
            ```python
            try:
                async with db.transaction() as tx:
                    await tx.add(User(name="Dave"))
                    if some_condition_fails:
                        await tx.rollback() # Explicitly roll back
                    else:
                        await tx.commit() # Explicitly commit (optional if auto-commit on exit is desired)
            except Exception as e:
                print(f"Transaction failed: {e}")
            ```
        """
        return OmmiTransaction(self.driver.transaction())

    async def __aenter__(self):
        """This context manager ensures that the database connection is open
        when entering the `async with` block. Using a context manager ensures that
        exceptions are properly handled and resources are cleaned up automatically.

        Returns:
            The `Ommi` instance itself.
        """
        return self

    async def __aexit__(self, *_):
        """Exits the asynchronous context, closing the driver connection.

        Ensures that the database connection managed by the driver is properly closed
        when the `async with` block finishes, regardless of whether it completed
        successfully or an exception occurred.
        """
        await self.driver.disconnect()
