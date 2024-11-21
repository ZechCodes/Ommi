import sqlite3
from typing import Any, Protocol

type SQLStatement = str
type SQLParams = tuple[Any, ...]
type SQLQuery = tuple[SQLStatement, SQLParams]


class Cursor(Protocol):
    connection: sqlite3.Connection

    def close(self) -> None:
        ...

    def execute(self, sql: SQLStatement, params: SQLParams) -> "Cursor"
        ...

    def fetchone(self) -> tuple[Any, ...]:
        ...
