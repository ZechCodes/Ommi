from typing import Type, Any, TYPE_CHECKING

from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorClientSession
from pymongo.results import DeleteResult

from ommi.drivers.exceptions import DriverOperationError
from ommi.query_ast import ASTGroupNode, ASTReferenceNode
from ommi.ext.drivers.mongodb.mongodb_query_builder import build_query_parts, MongoDBQueryParts
from ommi.ext.drivers.mongodb.mongodb_utils import get_collection_name, get_model_pk_db_name

if TYPE_CHECKING:
    from ommi.models import OmmiModel


async def delete_models(
    db: AsyncIOMotorDatabase,
    predicate: ASTGroupNode,
    session: AsyncIOMotorClientSession | None = None,
) -> int: # Return count of deleted documents
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
        raise ValueError("Could not determine model_type from predicate for delete operations.")

    query_parts = build_query_parts(predicate)
    collection_name = query_parts.target_collection_name or get_collection_name(model_type)
    
    try:
        collection = db[collection_name]

        if query_parts.pipeline:
            # Deleting based on an aggregation pipeline is more complex.
            # 1. Run aggregation to find _ids of documents to delete.
            #    - Pipeline should end before any $sort, $skip, $limit meant for fetching data.
            #    - Add $project to get only _id.
            # 2. Use delete_many with $in operator on the fetched _ids.
            
            id_pipeline = [
                stage for stage in query_parts.pipeline 
                if not (isinstance(stage, dict) and ("$sort" in stage or "$skip" in stage or "$limit" in stage))
            ]
            # Assuming the primary key is _id for all models for simplicity here.
            # If not, this needs to use the actual pk_db_name from mongodb_utils.
            # This also assumes that after joins, the main model's _id is still available at top level.
            id_pipeline.append({"$project": {"_id": 1}})

            ids_to_delete = []
            async for doc in collection.aggregate(id_pipeline, session=session):
                ids_to_delete.append(doc["_id"])
            
            if not ids_to_delete:
                return 0
            
            delete_result = await collection.delete_many({"_id": {"$in": ids_to_delete}}, session=session)
            return delete_result.deleted_count
            
        else:
            # Simple delete_many query
            # MongoDB's delete_many filter should not include sort, skip, or limit.
            # Those are for find operations.
            if not query_parts.filter:
                 # Deleting all documents if filter is empty. This can be dangerous.
                 # Depending on Ommi's philosophy, this might require a specific confirmation
                 # or be disallowed for safety. For now, assume it's allowed.
                 # An empty filter {} means all documents in the collection.
                 pass # Allow empty filter

            delete_result = await collection.delete_many(query_parts.filter, session=session)
            return delete_result.deleted_count
            
    except Exception as e:
        raise DriverOperationError(f"Error deleting models in MongoDB: {e}") from e 