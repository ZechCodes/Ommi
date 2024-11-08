from typing import TypeVar, Generic

from ommi.drivers.transactions import Transaction
from ommi.models import OmmiModel
from ommi.utils.awaitable_results import awaitable_result

TModel = TypeVar("TModel", bound=OmmiModel)


class OmmiTransaction(Generic[TModel]):
    def __init__(self, transaction: Transaction):
        self.transaction = transaction

    async def __aenter__(self):
        await self.transaction.__aenter__()
        return OmmiMultiTransaction(self.transaction)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self.transaction.__aexit__(exc_type, exc_val, exc_tb)

    @awaitable_result
    async def add(self, *items: TModel):
        async with self.transaction as transaction:
            return await transaction.add(*items)

    @awaitable_result
    async def delete(self, query):
        async with self.transaction as transaction:
            return await transaction.delete(query)

    @awaitable_result
    async def fetch(self, query) -> list[TModel]:
        async with self.transaction as transaction:
            return await transaction.fetch(query)

    @awaitable_result
    async def sync_schema(self, model_collection):
        async with self.transaction as transaction:
            return await transaction.sync_schema(model_collection)

    @awaitable_result
    async def update(self, query, **kwargs):
        async with self.transaction as transaction:
            return await transaction.update(query, **kwargs)


class OmmiMultiTransaction(Generic[TModel]):
    def __init__(self, transaction: Transaction):
        self.transaction = transaction

    @awaitable_result
    async def add(self, *items: TModel):
        return self.transaction.add(*items)

    @awaitable_result
    async def delete(self, query):
        return self.transaction.delete(query)

    @awaitable_result
    async def fetch(self, query) -> list[TModel]:
        return self.transaction.fetch(query)

    @awaitable_result
    async def sync_schema(self, model_collection):
        return self.transaction.sync_schema(model_collection)

    @awaitable_result
    async def update(self, query, **kwargs):
        return await self. transaction.update(query, **kwargs)