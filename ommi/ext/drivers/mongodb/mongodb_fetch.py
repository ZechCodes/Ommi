from typing import Any, AsyncIterator, Type, TYPE_CHECKING, Callable, Awaitable, Iterable

from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorClientSession, AsyncIOMotorCursor
from tramp.async_batch_iterator import AsyncBatchIterator

from ommi.drivers.exceptions import DriverOperationError
from ommi.query_ast import ASTGroupNode, ASTReferenceNode, ASTNode, ASTComparisonNode
from ommi.ext.drivers.mongodb.mongodb_query_builder import build_query_parts, MongoDBQueryParts
from ommi.ext.drivers.mongodb.mongodb_utils import get_collection_name, document_to_model
from ommi.models import OmmiModel

if TYPE_CHECKING:
    from ommi.shared_types import DBModel


DEFAULT_BATCH_SIZE = 100


def _determine_model_type_from_predicate_items(items: list[ASTNode]) -> Type[OmmiModel] | None:
    for item in items:
        if isinstance(item, ASTReferenceNode): # Covers direct model ref like when(Model) or field ref like Model.field
            return item.model
        elif isinstance(item, ASTComparisonNode): # Covers comparison like Model.field == value
            if isinstance(item.left, ASTReferenceNode):
                return item.left.model
        elif isinstance(item, ASTGroupNode):
            model_from_group = _determine_model_type_from_predicate_items(item.items)
            if model_from_group:
                return model_from_group
    return None


def _create_mongodb_batcher(
    db: AsyncIOMotorDatabase,
    predicate: ASTGroupNode,
    session: AsyncIOMotorClientSession | None = None,
) -> Callable[[int], Awaitable[Iterable["DBModel"]]]:
    
    target_model_type: Type[OmmiModel] | None = None
    if predicate and predicate.items:
        target_model_type = _determine_model_type_from_predicate_items(predicate.items)
    
    if not target_model_type:
        raise ValueError("Could not determine model_type from predicate in _create_mongodb_batcher.")

    # Build initial query parts once. We will adjust skip/limit for each batch.
    # Note: If predicate itself has skip/limit, this batching logic might interact unexpectedly.
    # The base query_parts from build_query_parts should ideally not have skip/limit if used with this batcher.
    # For now, assume predicate.limit_val and predicate.offset_val are for overall query, 
    # and this batcher paginates within that if they are None, or respects them if present.
    # This needs careful thought: if predicate has its own limit, batching should respect that overall limit.

    original_query_parts: MongoDBQueryParts = build_query_parts(predicate) # this already includes limit/offset from predicate
    if not original_query_parts.target_collection_name:
        original_query_parts.target_collection_name = get_collection_name(target_model_type)

    async def fetch_batch(batch_index: int) -> Iterable["DBModel"]:
        # Overall window defined by user
        user_offset = original_query_parts.skip or 0
        user_limit = original_query_parts.limit # This is the max number of items the user wants

        # Skip and limit for the *current batch* request from AsyncBatchIterator
        # (how many items AsyncBatchIterator would skip if there were no user_offset/user_limit)
        batch_internal_skip = batch_index * DEFAULT_BATCH_SIZE
        batch_internal_limit = DEFAULT_BATCH_SIZE

        # Actual skip for the DB query:
        # Start at user_offset, then add the batch's own internal skip.
        db_query_skip = user_offset + batch_internal_skip

        # Actual limit for the DB query, initially set to what the batch would normally fetch.
        db_query_limit = batch_internal_limit

        if user_limit is not None:
            # If this batch (considering its starting point db_query_skip relative to user_offset)
            # starts at or after the end of the user's total desired data window, it should fetch nothing.
            # The user's window ends after `user_limit` items have been fetched *starting from user_offset*.
            # So, if the current batch_internal_skip alone is already >= user_limit, it means
            # all desired items by the user would have been covered by previous batches.
            if batch_internal_skip >= user_limit:
                return []

            # The number of items this batch can contribute is capped by
            # how many items are left in the user's requested limit.
            # (user_limit - batch_internal_skip) gives remaining items for user from this point.
            db_query_limit = min(batch_internal_limit, user_limit - batch_internal_skip)

        if db_query_limit <= 0: # Ensure limit is positive, or if no items are left to fetch
            return []

        # Create query parts for this specific batch
        batch_query_parts = MongoDBQueryParts(
            filter=original_query_parts.filter,
            sort=original_query_parts.sort,
            skip=db_query_skip,
            limit=db_query_limit,
            pipeline=None, # Will be reconstructed if needed
            target_collection_name=original_query_parts.target_collection_name
        )

        models_in_batch = []
        try:
            collection = db[batch_query_parts.target_collection_name]
            cursor: AsyncIOMotorCursor

            if original_query_parts.pipeline: # If original query used pipeline (e.g. for joins)
                # We need to inject skip/limit into the pipeline carefully.
                # Remove existing $skip, $limit, $sort from original pipeline, then add batch-specific ones.
                # Sort should ideally be part of the original pipeline structure for correctness with joins.
                # If original_query_parts.sort exists, it should be part of its pipeline already.
                # Let's assume build_query_parts places sort correctly in the pipeline if specified.
                # The challenge is that original_query_parts.pipeline *is* the final pipeline (including sort/skip/limit from predicate).
                # So, we need to rebuild it or modify it.
                
                # Rebuild pipeline for batch, preserving structure, just changing skip/limit.
                # This is tricky. A simpler approach for pipeline + batching might be needed in query builder.
                # For now, if original had a pipeline, we will apply batch skip/limit *after* the full pipeline runs.
                # This is NOT efficient for large datasets. Correct batching with aggregation needs $skip/$limit stages within the pipeline.
                # This is a temporary simplification and likely performance bottleneck for pipeline queries.
                
                # A better way: modify the original pipeline array
                batch_pipeline = list(original_query_parts.pipeline) # Make a copy
                # Remove any pre-existing $skip, $limit. $sort should be kept if it was there.
                batch_pipeline = [s for s in batch_pipeline if not ("$skip" in s or "$limit" in s)]
                
                if batch_query_parts.skip is not None and batch_query_parts.skip > 0:
                    batch_pipeline.append({"$skip": batch_query_parts.skip})
                if batch_query_parts.limit is not None and batch_query_parts.limit > 0:
                    batch_pipeline.append({"$limit": batch_query_parts.limit})
                
                cursor = collection.aggregate(batch_pipeline, session=session)

            else: # Simple find query
                cursor = collection.find(batch_query_parts.filter, session=session)
                if batch_query_parts.sort:
                    cursor = cursor.sort(batch_query_parts.sort)
                if batch_query_parts.skip is not None and batch_query_parts.skip > 0:
                    cursor = cursor.skip(batch_query_parts.skip)
                if batch_query_parts.limit is not None and batch_query_parts.limit > 0:
                    cursor = cursor.limit(batch_query_parts.limit)
            
            async for doc in cursor:
                models_in_batch.append(document_to_model(target_model_type, doc))
            
        except Exception as e:
            raise DriverOperationError(f"Error fetching batch from MongoDB: {e}") from e
        return models_in_batch

    return fetch_batch


def fetch_models(
    db: AsyncIOMotorDatabase,
    predicate: ASTGroupNode,
    session: AsyncIOMotorClientSession | None = None,
) -> "AsyncBatchIterator[DBModel]":
    model_type: Type[OmmiModel] | None = None
    if predicate and predicate.items:
        model_type = _determine_model_type_from_predicate_items(predicate.items)
    
    if not model_type: 
        raise ValueError("Could not determine model_type from the predicate.")

    # query_parts = build_query_parts(predicate) # Pass only predicate - This line is problematic for model_type determination if model_type is needed before this.
    # collection_name = query_parts.target_collection_name or get_collection_name(model_type)
    # For now, model_type is determined above. build_query_parts might also determine it for its own needs.

    batcher_callable = _create_mongodb_batcher(db, predicate, session) # _create_mongodb_batcher now uses the robust determination
    return AsyncBatchIterator(batcher_callable)


async def count_models(
    db: AsyncIOMotorDatabase,
    predicate: ASTGroupNode,
    session: AsyncIOMotorClientSession | None = None,
) -> int:
    # Determine model_type from the predicate for count operations.
    # This is needed to find the correct collection if not explicitly in query_parts.pipeline.
    model_type: Type[OmmiModel] | None = None
    if predicate and predicate.items:
        # Simplified search for model type in predicate items.
        # AST for count might be like when(Model) or when(Model, Model.field == val).
        for item in predicate.items:
            if isinstance(item, ASTReferenceNode):
                model_type = item.model
                break
            elif hasattr(item, 'left') and isinstance(item.left, ASTReferenceNode):
                model_type = item.left.model
                break
            # Check right side of comparison if it could be a model field (less common for typical query structure)
            elif hasattr(item, 'right') and isinstance(item.right, ASTReferenceNode):
                model_type = item.right.model
                break
    
    if not model_type:
        # Predicates like when() for a specific model usually provide enough info.
        # Complex joins might require target_collection_name to be set by build_query_parts.
        raise ValueError("Could not determine model_type from predicate for count_models. Ensure predicate references a model.")

    query_parts = build_query_parts(predicate) # model_type no longer passed to build_query_parts
    collection_name = query_parts.target_collection_name or get_collection_name(model_type)

    try:
        collection = db[collection_name]

        if query_parts.pipeline:
            count_pipeline = [
                stage for stage in query_parts.pipeline 
                if not ( isinstance(stage, dict) and ("$sort" in stage or "$skip" in stage or "$limit" in stage) )
            ]
            count_pipeline.append({"$count": "total_count"})
            
            result_cursor = collection.aggregate(count_pipeline, session=session)
            # Use await result_cursor.next() if PyMongo >= 4.0, or loop for < 4.0
            count_doc = None
            async for doc_item in result_cursor: # Iterate to get the first (and only) doc
                count_doc = doc_item
                break
            return count_doc["total_count"] if count_doc and "total_count" in count_doc else 0
        else:
            return await collection.count_documents(query_parts.filter or {}, session=session)
            
    except Exception as e:
        raise DriverOperationError(f"Error counting models in MongoDB: {e}") from e 