from typing import Type, Any, TYPE_CHECKING

from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorClientSession
from pymongo.results import UpdateResult
from pymongo.errors import BulkWriteError

from ommi.drivers.exceptions import DriverOperationError, ModelUpdateError
from ommi.query_ast import ASTGroupNode, ASTReferenceNode
from ommi.ext.drivers.mongodb.mongodb_query_builder import build_query_parts, MongoDBQueryParts
from ommi.ext.drivers.mongodb.mongodb_utils import get_model_field_name, get_collection_name, get_model_pk_db_name

if TYPE_CHECKING:
    from ommi.models import OmmiModel


async def update_models(
    db: AsyncIOMotorDatabase,
    predicate: ASTGroupNode,
    values: dict[str, Any],
    session: AsyncIOMotorClientSession | None = None,
) -> int: # Return count of updated documents
    model_type: Type["OmmiModel"] | None = None
    if predicate and predicate.items:
        for item in predicate.items:
            if isinstance(item, ASTReferenceNode):
                model_type = item.model
                break
            elif hasattr(item, 'left') and isinstance(item.left, ASTReferenceNode):
                model_type = item.left.model
                break
            elif hasattr(item, 'right') and isinstance(item.right, ASTReferenceNode):
                model_type = item.right.model
                break
    
    if not model_type:
        raise ValueError("Could not determine model_type from predicate for update operations.")

    query_parts = build_query_parts(predicate)
    collection_name = query_parts.target_collection_name or get_collection_name(model_type)
    
    if not values:
        return 0 # Nothing to update

    # Transform attribute names in `values` to their `StoreAs` database names if applicable.
    # This must be done in the context of the predicate's model type, as updates apply to this model.
    update_doc = {}
    for attr_name, value in values.items():
        db_field_name = get_model_field_name(model_type, attr_name)
        update_doc[db_field_name] = value
    
    # The update operation itself in MongoDB uses a specific update document structure, e.g., {"$set": update_doc}
    # We should not allow updating the primary key (_id).
    # Check if _id or its model attribute equivalent is in update_doc.
    # This check is a bit simplistic, as get_model_field_name would map 'id' to '_id' if that's the PK.
    # More robustly: iterate update_doc keys, and for each, check if it corresponds to a PK field.
    # For now, simple check for "_id" as MongoDB PK.
    if "_id" in update_doc:
        raise DriverOperationError("Updating the primary key ('_id') is not allowed.")

    update_payload = {"$set": update_doc}

    try:
        collection = db[collection_name]

        if query_parts.pipeline:
            # Updating based on an aggregation pipeline is complex like delete.
            # 1. Run aggregation to find _ids of documents to update.
            #    - Pipeline should end before any $sort, $skip, $limit meant for fetching data.
            #    - Add $project to get only _id.
            # 2. Use update_many with $in operator on the fetched _ids and the $set payload.
            
            id_pipeline = [
                stage for stage in query_parts.pipeline 
                if not (isinstance(stage, dict) and ("$sort" in stage or "$skip" in stage or "$limit" in stage))
            ]
            id_pipeline.append({"$project": {"_id": 1}})

            ids_to_update = []
            async for doc in collection.aggregate(id_pipeline, session=session):
                ids_to_update.append(doc["_id"])
            
            if not ids_to_update:
                return 0
            
            final_filter = {"_id": {"$in": ids_to_update}}
            update_result = await collection.update_many(final_filter, update_payload, session=session)
            return update_result.modified_count
            
        else:
            # Simple update_many query
            if not query_parts.filter:
                 # Updating all documents if filter is empty. This can be dangerous.
                 # Consider Ommi's policy on this.
                 pass # Allow empty filter

            update_result = await collection.update_many(query_parts.filter, update_payload, session=session)
            return update_result.modified_count
            
    except Exception as e:
        raise DriverOperationError(f"Error updating models in MongoDB: {e}") from e 