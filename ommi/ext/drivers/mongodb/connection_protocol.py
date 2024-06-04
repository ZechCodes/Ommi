from typing import Protocol, runtime_checkable
from pymongo.client_session import ClientSession


@runtime_checkable
class MongoDBConnection(Protocol):
    def get_database(self, database_name: str):
        ...

    def close(self):
        ...

    async def start_session(self) -> ClientSession:
        ...
