from typing import Awaitable, TYPE_CHECKING

import ommi
from ommi.query_ast import when
from ommi.database.transaction import OmmiTransaction

if TYPE_CHECKING:
    from ommi.drivers import BaseDriver
    from ommi.models.collections import ModelCollection
    from ommi.shared_types import DBModel


class Ommi[TDriver: "ommi.BaseDriver"]:
    def __init__(self, driver: TDriver, *, allow_imlicit_model_setup: bool = True):
        self._driver = driver
        self._known_model_collections: set["ModelCollection"] = set()
        self._allow_implicit_model_setup = allow_imlicit_model_setup

    @property
    def driver(self) -> TDriver:
        return self._driver

    def _ensure_model_setup(self) -> "Awaitable[None] | None":
        """Ensure that models are set up if implicit model setup is allowed.

        Returns:
            An awaitable if models need to be set up, None otherwise.
        """
        if not self._known_model_collections and self._allow_implicit_model_setup:
            return self.use_models(ommi.models.collections.get_global_collection())
        return None

    def add(
        self, *models: "ommi.shared_types.DBModel"
    ) -> "Awaitable[ommi.database.results.DBResult[ommi.shared_types.DBModel]]":
        """Persists one or more model instances to the database.
        This method takes new model instances and attempts to save them as new records.

        It prepares model instances for insertion into the database. When no models are provided
        to Ommi, this implicitly sets up the global model collection when enabled.

        The result of the operation is wrapped in a `DBResult` type (DBSuccess or DBFailure). This
        allows for explicit handling of operation success or failure: if the operation is successful,
        `DBSuccess.result` contains the added model instance(s). If an error occurs during the operation,
        `DBFailure.exception` holds the specific exception.

        Args:
            *models: A variable number of `DBModel` instances to be added to the
                     database. These should be new instances not yet persisted.

        Returns:
            Resolves to a `DBResult` that wraps the result on success and the exception on failure.

        Example: Example: Adding a single user
            ```python
            user = User(name="Alice")
            result_one = await db.add(user)
            match result_one:
                case DBResult.DBSuccess(added_user):
                    print(f"Added user: {added_user.name}")
                case DBResult.DBFailure(e):
                    print(f"Failed to add user: {e}")
            ```

        Example: Example: Adding multiple users
            ```python
            user1 = User(name="Alice")
            user2 = User(name="Bob")
            result_many = await db.add(user1, user2)
            match result_many:
                case DBResult.DBSuccess(added_items):
                    print(f"Successfully added {len(added_items)} users.")
                case DBResult.DBFailure(e):
                    print(f"Failed to add multiple users: {e}")
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
        This method provides a flexible way to define conditions for your search, returning
        an `ommi.database.query_results.DBQueryResultBuilder`. This builder object is central
        to fetching data and does not execute the query immediately. Instead, it provides
        several methods to execute the query and retrieve results in different forms:

        - `.all()`: Asynchronously fetches all matching records, returning an `AsyncBatchIterator`
          within the `DBQuerySuccess.result`.
        - `.one()`: Fetches a single record. If successful, the record is in `DBQuerySuccess.result`.
          It may result in a `DBStatusNoResultException` (within `DBQueryFailure.exception`)
          if no record is found, or other database exceptions for different errors.
        - `.count()`: Returns the total number of matching records as an integer within
          `DBQueryResult.result`.
        - `.delete()`: Deletes all records matching the predicates. The result (success/failure)
          is given in as a `DBResult` (`DBSuccess` or `DBFailure`).
        - `.update(**values)` or `.update(values_dict)`: Updates fields of matching records.
          The result is given in a `DBResult` (`DBSuccess` or `DBFailure`).

        Each of these execution methods (`.all()`, `.one()`, etc.) returns an awaitable.
        When this awaitable is resolved, it yields a `ommi.DBQueryResult` type (for data-retrieval
        methods like `.all()`, `.one()`, `.count()`) or a `ommi.DBResult` (for CRUD methods like
        `.delete()`, `.update()`), allowing you to handle the outcome robustly. The
        `DBQueryResultBuilder` itself can also be directly awaited, defaulting to the `.all()` behavior.

        > # 💬 Helpful information
        > The `find` method allows intuitive predicate definitions, often directly through Pythonic comparison
        expressions (e.g., `User.age > 18`). This approach minimizes boilerplate for common queries. It's
        designed for clarity. This can be made more powerful through the use of `ommi.query_ast.when` which gives
        you access to it's `And` and `Or` methods to build more complex queries, eg.
        > ```python
        > db.find(when(User.name == "Alice").Or(User.name == "Bob"))
        > ```

        Args:
            *predicates: Variable number of conditions that define the query.
                These are typically combined with an AND logic by default (internally,
                these are passed to `ommi.query_ast.when(*predicates)`).
                Common forms include:

                - Boolean expressions involving model fields: e.g., `User.name == "Alice"`,
                  `User.age > 18`. These are the fundamental building blocks.
                - `ommi.query_ast.ASTGroupNode`: For more complex conditions involving
                  explicit AND/OR logic, often constructed using `ommi.query_ast.when()`
                  with `ASTGroupNode.And()` or `ASTGroupNode.Or()`.
                - Model classes (e.g., `User`): If a model class is passed as a predicate,
                  it typically acts as a target for the query, implying operations on
                  all instances of that model, or providing context for other field-based
                  predicates. For instance, `db.find(User, User.name == "Test")`.
                  To query all instances of a model, you might use `db.find(User)`.

        Returns:
            `DBQueryResultBuilder` that resolves to a `DBQueryResult`, alternatively it provides aggregation and exception handling methods.

        Example: Example 1: Find user by ID
            Assuming `User` is an `@ommi_model` with fields like `id`, `name`, `age`, `is_active`
            ```python
            from ommi.query_ast import when # Corrected import
            from ommi.database.query_results import DBQueryResult # For match/case
            from ommi.database.results import DBResult, DBStatusNoResultException # For match/case

            user_id_to_find = 1
            query_by_id = db.find(User.id == user_id_to_find)
            result_status = await query_by_id.one() # Await .one() to get DBQueryResult
            match result_status:
                case DBQueryResult.DBSuccess(user):
                    print(f"Found user by ID: {user.name}")
                case DBQueryResult.DBFailure(DBStatusNoResultException()):
                    print(f"User with ID {user_id_to_find} not found.")
                case DBQueryResult.DBFailure(e):
                    print(f"Error finding user by ID: {e}")
            ```

        Example: Example 2: Find users older than 18 and count them
            Predicates are ANDed by default when passed directly to `find()` or `when()`
            ```python
            older_users_query = db.find(User.age > 18, User.is_active == True)
            count_status = await older_users_query.count() # Await .count()
            match count_status:
                case DBQueryResult.DBSuccess(number_of_users):
                    print(f"Number of active users older than 18: {number_of_users}")
                case DBQueryResult.DBFailure(e):
                    print(f"Error counting users: {e}")
            ```

        Example: Example 3: Find users named Alice OR Bob, and iterate
            Use `when()` and the `.Or()` method on the resulting `ASTGroupNode` for explicit `OR` conditions.
            ```python
            named_users_query = db.find(when(User.name == "Alice").Or(User.name == "Bob"))

            all_results_status = await named_users_query.all()
            match all_results_status:
                case DBQueryResult.DBSuccess(user_iterator):
                    print("Users named Alice or Bob:")
                    async for user in user_iterator:
                        print(f"- {user.name}")
                case DBQueryResult.DBFailure(e):
                    print(f"Error finding named users: {e}")
            ```

        Example: Example 4: Updating records
            ```python
            update_query = db.find(User.name == "Old Name")
            update_status = await update_query.update(name="New Name", is_active=False) # Await .update()

            match update_status:
                case DBResult.DBSuccess(): # Update might not return data in .result
                    print("Successfully updated records.")
                case DBResult.DBFailure(e):
                    print(f"Error updating records: {e}")
            ```

        Example: Example 5: Deleting records
            ```python
            delete_query = db.find(User.is_active == False)
            delete_status = await delete_query.delete() # Await .delete()

            match delete_status:
                case DBResult.DBSuccess(): # Delete might not return data
                    print("Successfully deleted inactive users.")
                case DBResult.DBFailure(e):
                    print(f"Error deleting users: {e}")
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
        """Apply the schema for the given model collection to the database.

        Args:
            model_collection: The model collection to apply the schema for.
        """
        await self.driver.delete_schema(model_collection)
        await self.driver.apply_schema(model_collection)
        self._known_model_collections.add(model_collection)

    async def remove_models(self, model_collection: "ModelCollection") -> None:
        """Remove the schema for the given model collection from the database.

        Args:
            model_collection: The model collection to remove the schema for.
        """
        await self.driver.delete_schema(model_collection)
        self._known_model_collections.discard(model_collection)

    def transaction(self) -> OmmiTransaction:
        """Creates an async context manager that can be used to perform database operations within a transaction.

        Returns:
            An `OmmiTransaction` that can be used to perform operations within a transaction.

        Example: Example: Basic transaction usage
            ```python
            async with db.transaction() as transaction:
                await transaction.add(model)
                # If an exception occurs here, the transaction will be rolled back
            ```
        """
        return OmmiTransaction(self.driver.transaction())

    async def __aenter__(self):
        await self._driver.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self._driver.__aexit__(exc_type, exc_val, exc_tb)
