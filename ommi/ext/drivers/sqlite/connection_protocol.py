import sqlite3
from typing import Protocol, runtime_checkable


@runtime_checkable
class SQLiteConnection(Protocol):
    def close(self) -> None: ...

    def cursor(self) -> sqlite3.Cursor: ...

    def rollback(self) -> None: ...