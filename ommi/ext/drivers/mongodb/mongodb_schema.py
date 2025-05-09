from typing import Type, TYPE_CHECKING
import asyncio

from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorClientSession
from pymongo.errors import CollectionInvalid, OperationFailure
from pymongo import IndexModel

from ommi.drivers.exceptions import SchemaError, DriverOperationError
from ommi.ext.drivers.mongodb.mongodb_utils import get_collection_name, get_model_field_name
from ommi.models import OmmiModel
from ommi.models.field_metadata import FieldMetadata, ReferenceTo, Key

if TYPE_CHECKING:
    from ommi.models.collections import ModelCollection

async def apply_schema(
    db: AsyncIOMotorDatabase,
    model_collection: "ModelCollection",
    session: AsyncIOMotorClientSession | None = None,
):
    """Creates collections and applies indexes for the given models."""
    try:
        for model_type in model_collection.models:
            if not hasattr(model_type, '__ommi__') or not hasattr(model_type.__ommi__, 'fields'):
                continue

            collection_name = get_collection_name(model_type)
            
            try:
                await db.create_collection(collection_name, session=session)
            except CollectionInvalid: 
                pass
            except OperationFailure as e:
                if "transaction" in str(e).lower():
                    try:
                        await db.create_collection(collection_name)
                    except CollectionInvalid:
                        pass
                    except Exception as fallback_e:
                         raise SchemaError(f"Failed to create collection '{collection_name}' (fallback after transaction error): {fallback_e}") from fallback_e
                else:
                    raise SchemaError(f"Failed to create collection '{collection_name}': {e}") from e

            collection = db[collection_name]
            indexes_to_create = []
            
            # Store parts of potential composite key
            key_db_field_names_for_index: list[tuple[str, int]] = [] 

            for field_name, meta in model_type.__ommi__.fields.items():
                if not meta: continue

                db_field_name = get_model_field_name(model_type, field_name)

                if meta.matches(Key) and db_field_name != "_id":
                    key_db_field_names_for_index.append((db_field_name, 1))
                
                ref_to_info = meta.get("reference_to")
                if isinstance(ref_to_info, ReferenceTo):
                    # FK indexes are typically not unique by default, but can be.
                    # For now, creating non-unique FK indexes.
                    indexes_to_create.append(
                        IndexModel([(db_field_name, 1)], name=f"idx_{collection_name}_{db_field_name}_fk")
                    )

            # After iterating all fields, create PK index(es)
            if key_db_field_names_for_index:
                if len(key_db_field_names_for_index) == 1:
                    # Single field primary key
                    single_pk_field_name = key_db_field_names_for_index[0][0]
                    indexes_to_create.append(
                        IndexModel(key_db_field_names_for_index, 
                                   name=f"idx_{collection_name}_{single_pk_field_name}_pk", 
                                   unique=True)
                    )
                else:
                    # Composite primary key
                    compound_key_name_parts = "_".join([field_tuple[0] for field_tuple in key_db_field_names_for_index])
                    indexes_to_create.append(
                        IndexModel(key_db_field_names_for_index, 
                                   name=f"idx_{collection_name}_{compound_key_name_parts}_cpk", 
                                   unique=True)
                    )

            if indexes_to_create:
                try:
                    await collection.create_indexes(indexes_to_create)
                except OperationFailure as e:
                    if e.code in [85, 86]: # Index already exists errors
                        pass 
                    elif "transaction" in str(e).lower():
                        try:
                            await db[collection_name].create_indexes(indexes_to_create)
                        except OperationFailure as fallback_e:
                            if fallback_e.code in [85, 86]:
                                pass
                            else:
                                raise SchemaError(f"Failed to create indexes for collection '{collection_name}' (fallback after transaction error): {fallback_e}") from fallback_e
                    else:
                        raise SchemaError(f"Failed to create indexes for collection '{collection_name}': {e}") from e
                        
    except Exception as e:
        raise DriverOperationError(f"An error occurred during schema application: {e}") from e


async def delete_schema(
    db: AsyncIOMotorDatabase,
    model_collection: "ModelCollection",
    session: AsyncIOMotorClientSession | None = None, 
):
    """Drops collections for the given models."""
    try:
        for model_type in model_collection.models:
            if not hasattr(model_type, '__ommi__'): continue
            collection_name = get_collection_name(model_type)
            try:
                await db.drop_collection(collection_name)
            except OperationFailure as e:
                if "transaction" in str(e).lower():
                    try:
                        await db.drop_collection(collection_name)
                    except Exception as fallback_e:
                        raise SchemaError(f"Failed to drop collection '{collection_name}' (fallback after transaction error): {fallback_e}") from fallback_e
                else:
                    pass 

    except Exception as e:
        raise DriverOperationError(f"An error occurred during schema deletion: {e}") from e 