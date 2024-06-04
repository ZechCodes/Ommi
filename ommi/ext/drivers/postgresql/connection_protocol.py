from typing import Protocol, runtime_checkable
import psycopg


@runtime_checkable
class PostgreSQLConnection(Protocol):
    def cursor(self) -> psycopg.AsyncCursor:
        ...

    async def close(self) -> None:
        ...

    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...
