import asyncio
from typing import Iterable, Type, TYPE_CHECKING

from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorClientSession
from pymongo.errors import BulkWriteError
from pymongo import ReturnDocument

from ommi.drivers.exceptions import ModelInsertError, DriverOperationError
from ommi.ext.drivers.mongodb.mongodb_utils import (
    get_collection_name, 
    model_to_document, 
    get_model_pk_db_name,
    get_model_pk_name
)
from ommi.models import OmmiModel

if TYPE_CHECKING:
    from ommi.shared_types import DBModel


async def add_models(
    db: AsyncIOMotorDatabase,
    models: Iterable["DBModel"],
    session: AsyncIOMotorClientSession | None = None,
) -> Iterable["DBModel"]:
    if not models:
        return []

    # Group models by type to perform batch operations per collection
    models_by_type: dict[Type[OmmiModel], list[OmmiModel]] = {}
    for model_instance in models:
        models_by_type.setdefault(type(model_instance), []).append(model_instance)

    processed_models = []
    collection_name = "<unknown>" # Default for error message if needed before assignment
    try:
        for model_type, instances in models_by_type.items():
            if not instances:
                continue

            if not hasattr(model_type, '__ommi__') or not hasattr(model_type.__ommi__, 'fields'):
                # This model type hasn't been fully processed by Ommi (e.g. @ommi_model decorator)
                # Skip or raise, depending on strictness.
                processed_models.extend(instances) # Or handle as error if this state is unexpected
                continue

            collection_name = get_collection_name(model_type)
            collection = db[collection_name]
            
            # Prepare documents and handle PKs for insertion
            documents_for_insert_operation = []
            original_instances_for_id_update = [] # Keep track of original instances for ID update phase

            pk_attr_name = get_model_pk_name(model_type)
            pk_db_field_name = get_model_pk_db_name(model_type) 

            pk_attr_is_int = False
            if hasattr(model_type, '__ommi__') and hasattr(model_type.__ommi__, 'fields'):
                pk_field_meta = model_type.__ommi__.fields.get(pk_attr_name)
                if pk_field_meta and pk_field_meta.get("field_type") is int:
                    pk_attr_is_int = True

            # Store generated int IDs to set back on instances later
            generated_int_ids_map: dict[int, int] = {} # instance_index -> int_id

            # Track indices of original instances for which MongoDB is expected to generate an _id
            mongo_should_generate_id_for_original_indices = []

            for i, instance in enumerate(instances):
                doc = model_to_document(instance)
                instance_id_value = getattr(instance, pk_attr_name, None)

                if pk_db_field_name == "_id":
                    if pk_attr_is_int and instance_id_value is None:
                        # Simulate auto-increment for int PK attribute that maps to _id
                        counter_collection_name = "ommi_counters"
                        counter_doc_id = f"{get_collection_name(model_type)}__{pk_attr_name}"
                        
                        updated_counter_doc = await db[counter_collection_name].find_one_and_update(
                            {"_id": counter_doc_id},
                            {"$inc": {"seq": 1}},
                            upsert=True,
                            return_document=ReturnDocument.AFTER,
                            session=session
                        )
                        if not updated_counter_doc or "seq" not in updated_counter_doc:
                            # This should ideally not happen with upsert=True and ReturnDocument.AFTER
                            raise DriverOperationError(f"Failed to generate sequence ID for {model_type.__name__}")
                        
                        generated_int_id = updated_counter_doc["seq"]
                        doc["_id"] = generated_int_id
                        generated_int_ids_map[i] = generated_int_id
                    
                    elif not pk_attr_is_int and instance_id_value is None:
                        # PK is _id, not an int we are simulating, and user provided no ID value.
                        # MongoDB will generate an ObjectId. Mark this index.
                        if "_id" in doc: del doc["_id"] # Ensure _id is not None, let Mongo generate
                        mongo_should_generate_id_for_original_indices.append(i)
                    # Else, _id was provided by user (either for int PK, or as ObjectId/custom for non-int PK)
                    # or it's an int PK that we just generated. In these cases, doc["_id"] is already set.
                    # If pk_attr_is_int is True but instance_id_value was provided, doc["_id"] has that int value.
                
                else: # PK is a custom field name (not _id)
                    if doc.get(pk_db_field_name) is None:
                        raise ModelInsertError(
                            f"Primary key '{pk_db_field_name}' (attribute '{pk_attr_name}') for model "
                            f"'{model_type.__name__}' must be provided."
                        )
                
                documents_for_insert_operation.append(doc)
                original_instances_for_id_update.append(instance)

            if not documents_for_insert_operation:
                processed_models.extend(instances)
                continue

            insert_result = await collection.insert_many(
                documents_for_insert_operation, ordered=False, session=session
            )

            # Update instances with generated IDs
            mongo_generated_ids_iterator = iter(insert_result.inserted_ids)

            for i, instance_to_update in enumerate(original_instances_for_id_update):
                if i in generated_int_ids_map:
                    # This instance had an int PK generated by our counter logic
                    setattr(instance_to_update, pk_attr_name, generated_int_ids_map[i])
                elif i in mongo_should_generate_id_for_original_indices:
                    # This instance's ID was expected to be generated by MongoDB
                    try:
                        generated_id_from_mongo = next(mongo_generated_ids_iterator)
                        setattr(instance_to_update, pk_attr_name, generated_id_from_mongo)
                    except StopIteration:
                        # This indicates a mismatch between our tracking and mongo's result.
                        # Log or raise, as this implies a logic error. For now, we assume consistency.
                        pass
                # Else: ID was pre-set by user, or it's a custom PK (not _id) that was pre-set. No update needed from result.
                
                processed_models.append(instance_to_update)
                
    except BulkWriteError as e:
        # Handle bulk write errors, e.g., duplicate keys
        # e.details["writeErrors"] gives info on individual errors
        # For simplicity, wrap the first error or a general message
        first_error = e.details["writeErrors"][0] if e.details and e.details["writeErrors"] else {}
        err_msg = first_error.get("errmsg", "Bulk insert failed.")
        code = first_error.get("code")
        # TODO: map MongoDB error codes to Ommi specific exceptions if possible
        raise ModelInsertError(f"Failed to add one or more models to collection '{collection_name}': {err_msg} (Code: {code})") from e
    except Exception as e:
        # Catch any other unexpected errors during the add operation
        raise DriverOperationError(f"An unexpected error occurred during model insertion into '{collection_name}': {e}") from e

    return processed_models 