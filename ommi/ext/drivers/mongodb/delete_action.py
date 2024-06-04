from typing import Sequence, Type, Any
from tramp.optionals import Optional

from ommi.drivers.database_results import async_result
from ommi.drivers.delete_actions import DeleteAction
from ommi.ext.drivers.mongodb.connection_protocol import MongoDBConnection
from ommi.ext.drivers.mongodb.utils import build_pipeline, process_ast, Query
from ommi.models import OmmiModel
from ommi.query_ast import when, ASTGroupNode

Predicate = ASTGroupNode | type(OmmiModel) | bool


class MongoDBDeleteAction(DeleteAction[MongoDBConnection, OmmiModel]):
    def __init__(
        self, connection: MongoDBConnection, predicates: Sequence[Predicate], database
    ):
        super().__init__(connection, predicates)
        self._db = database
        self._is_replica_set_result: Optional[bool] = Optional.Nothing

    @property
    async def _is_replica_set(self) -> bool:
        match self._is_replica_set_result:
            case Optional.Nothing:
                result = await self._connection.local.system.replset.find().to_list(1)
                self._is_replica_set_result = Optional.Some(len(result) != 0)

            case Optional.Some(result):
                return result

    @async_result
    async def delete(self) -> bool:
        query = process_ast(when(*self._predicates))
        if query.collections:
            return await self._join_delete(query)

        return await self._delete(query.collection, query.match)

    async def _delete(
        self, model: Type[OmmiModel], match: list[dict[str, Any]]
    ) -> bool:
        await self._db[model.__ommi__.model_name].delete_many(
            {"$and": match} if match else {},
        )
        return True

    async def _join_delete(self, query: Query) -> bool:
        async with await self._connection.start_session() as session:
            if await self._is_replica_set:
                return await self._transaction_delete(query, session)

            return await self._do_join_delete(query, session)

    async def _do_join_delete(self, query: Query, session=None) -> bool:
        pipeline, model = build_pipeline(query)
        documents_to_delete = self._db[model.__ommi__.model_name].aggregate(
            pipeline, session=session
        )
        await self._db[model.__ommi__.model_name].delete_many(
            {"_id": {"$in": [doc["_id"] async for doc in documents_to_delete]}},
            session=session,
        )
        return True

    async def _transaction_delete(self, query: Query, session) -> bool:
        async with session.start_transaction():
            return await self._do_join_delete(query, session)
