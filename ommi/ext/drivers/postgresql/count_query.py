from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg import AsyncCursor # Or the appropriate async cursor type
    from ommi.query_ast import ASTGroupNode

async def count_models(cursor: "AsyncCursor", predicate: "ASTGroupNode") -> int:
    raise NotImplementedError("count_models for PostgreSQL is not yet implemented") 