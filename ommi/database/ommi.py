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
    ) -> "Awaitable[ommi.database.query_results.DBQueryResult[ommi.shared_types.DBModel]]":
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
        """Create a new transaction.

        Returns:
            An OmmiTransaction that can be used to perform operations within a transaction.

        Example:
            ```python
            async with db.transaction() as transaction:
                await transaction.add(model)
                # If an exception occurs here, the transaction will be rolled back
            # Transaction is committed here if no exception occurred
            ```
        """
        return OmmiTransaction(self.driver.transaction())

    async def __aenter__(self):
        await self._driver.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self._driver.__aexit__(exc_type, exc_val, exc_tb)
