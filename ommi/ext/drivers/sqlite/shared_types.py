import sqlite3
from typing import Any, Protocol, Sequence

type SQLStatement = str
type SQLParams = Sequence[Any, ...]
type SQLQuery = tuple[SQLStatement, SQLParams]


class Cursor(Protocol):
    @property
    def connection(self) -> sqlite3.Connection:
        ...

    def close(self) -> None:
        ...

    def execute(self, sql: SQLStatement, params: SQLParams) -> "Cursor":
        ...

    def fetchone(self) -> tuple[Any, ...]:
        ...

    def fetchall(self) -> list[tuple[Any, ...]]:
