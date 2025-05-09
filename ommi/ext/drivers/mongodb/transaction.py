from typing import Any, Iterable, TYPE_CHECKING

from motor.motor_asyncio import AsyncIOMotorClientSession, AsyncIOMotorClient, AsyncIOMotorDatabase

from ommi.drivers import BaseDriverTransaction
from ommi.drivers.exceptions import TransactionError, DriverOperationError

# Import the new helper modules
import ommi.ext.drivers.mongodb.mongodb_add as mongodb_add
import ommi.ext.drivers.mongodb.mongodb_fetch as mongodb_fetch
import ommi.ext.drivers.mongodb.mongodb_delete as mongodb_delete
import ommi.ext.drivers.mongodb.mongodb_update as mongodb_update
import ommi.ext.drivers.mongodb.mongodb_schema as mongodb_schema

if TYPE_CHECKING:
    from ommi.models.collections import ModelCollection
    from ommi.query_ast import ASTGroupNode
    from ommi.shared_types import DBModel
    from tramp.async_batch_iterator import AsyncBatchIterator


class MongoDBTransaction(BaseDriverTransaction):
    def __init__(self, client: AsyncIOMotorClient, db: AsyncIOMotorDatabase):
        self.client = client
        self.db = db
        self.session: AsyncIOMotorClientSession | None = None
        self._is_open = False # To track if open() has been successfully called

    async def open(self):
        if self._is_open and self.session:
            # Idempotent: if already open and session exists, do nothing or raise
            # For now, let's be strict to catch potential misuse
            raise TransactionError("Transaction is already open.")
        try:
            self.session = await self.client.start_session()
            self.session.start_transaction()
            if not self.session.in_transaction:
                # This should not happen if start_transaction() is successful
                # and client/server support transactions.
                self.session = None # Clean up session object
                self._is_open = False
                raise TransactionError("MongoDB session.start_transaction() did not result in an active transaction.")
            self._is_open = True
        except Exception as e:
            self.session = None # Ensure session is None if start_session fails
            self._is_open = False
            raise TransactionError(f"Failed to open MongoDB transaction: {e}") from e

    async def close(self):
        """Ensures the session is ended. Called by commit/rollback or explicitly."""
        if self.session:
            try:
                # If transaction is active, it should be aborted before closing session if not committed/rolled back prior.
                if self.session.in_transaction:
                    await self.session.abort_transaction()
            except Exception as e:
                # Log or handle error during abort if necessary, but proceed to end session
                # print(f"Error aborting transaction during close: {e}") # Or use proper logging
                pass # Swallow error here as main goal is to end session
            finally:
                await self.session.end_session()
                self.session = None
        self._is_open = False

    async def commit(self):
        if not self._is_open: # Check if transaction was already closed (e.g., by rollback)
            return

        if not self.session or not self.session.in_transaction:
            raise TransactionError("No active transaction to commit.")
        try:
            await self.session.commit_transaction()
        except Exception as e:
            # As per Motor docs, abort transaction if commit fails and transaction is still active.
            if self.session and self.session.in_transaction:
                try:
                    await self.session.abort_transaction()
                except Exception as abort_exc:
                    # Log abort error, but raise original commit error
                    # print(f"Failed to abort transaction after commit error: {abort_exc}")
                    pass 
            raise TransactionError(f"Failed to commit transaction: {e}") from e
        finally:
            await self.close() # Ensures session is closed

    async def rollback(self):
        if not self._is_open: # Check if transaction was already closed (e.g., by commit or another rollback)
            return

        if not self.session: # No session, nothing to rollback
            self._is_open = False # Ensure state is consistent
            return
        
        if not self.session.in_transaction:
            await self.close() # Just close the session
            return

        try:
            await self.session.abort_transaction()
        except Exception as e:
            raise TransactionError(f"Failed to rollback transaction: {e}") from e
        finally:
            await self.close() # Ensures session is closed

    def _ensure_session_active(self):
        if not self.session or not self._is_open:
            raise TransactionError(
                "Transaction is not open or session is not active. Call open() first."
            )
        if not self.session.in_transaction:
             raise TransactionError("The transaction in this session is no longer active (committed or aborted). Start a new transaction.")

    async def add(self, models: "Iterable[DBModel]") -> "Iterable[DBModel]":
        self._ensure_session_active()
        return await mongodb_add.add_models(self.db, models, session=self.session)

    async def count(self, predicate: "ASTGroupNode") -> int:
        self._ensure_session_active()
        return await mongodb_fetch.count_models(self.db, predicate, session=self.session)

    async def delete(self, predicate: "ASTGroupNode") -> int:
        self._ensure_session_active()
        return await mongodb_delete.delete_models(self.db, predicate, session=self.session)

    def fetch(self, predicate: "ASTGroupNode") -> "AsyncBatchIterator[DBModel]":
        self._ensure_session_active()
        return mongodb_fetch.fetch_models(self.db, predicate, session=self.session)

    async def update(self, predicate: "ASTGroupNode", values: dict[str, Any]) -> int:
        self._ensure_session_active()
        return await mongodb_update.update_models(self.db, predicate, values, session=self.session)

    async def apply_schema(self, model_collection: "ModelCollection"):
        self._ensure_session_active()
        # As noted before, schema ops in MongoDB are generally not transactional with data ops.
        # Running them with a session might link them to the server session but not make them atomic with other data ops.
        # Some commands might not support sessions or behave differently.
        # For now, pass the session, but be aware of MongoDB's behavior.
        # Consider raising NotImplementedError if strict transactional DDL is expected by Ommi for MongoDB.
        # For now, let's allow it but with caveats.
        try:
            await mongodb_schema.apply_schema(self.db, model_collection, session=self.session) # Pass session
        except Exception as e:
            # More specific error handling for schema operations within a transaction might be needed.
            raise DriverOperationError(f"Error applying schema within transaction: {e}. Schema operations may not be fully transactional in MongoDB.") from e


    async def delete_schema(self, model_collection: "ModelCollection"):
        self._ensure_session_active()
        # Similar caveats as apply_schema regarding transactions.
        try:
            await mongodb_schema.delete_schema(self.db, model_collection, session=self.session) # Pass session
        except Exception as e:
            raise DriverOperationError(f"Error deleting schema within transaction: {e}. Schema operations may not be fully transactional in MongoDB.") from e 