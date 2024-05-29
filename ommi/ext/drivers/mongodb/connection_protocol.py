from typing import Protocol, runtime_checkable


@runtime_checkable
class MongoDBConnection(Protocol):
    def get_database(self, database_name: str):
        ...

    def close(self):
        ...
