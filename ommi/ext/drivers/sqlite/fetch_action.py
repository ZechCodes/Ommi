import sqlite3
from datetime import datetime, date
from typing import Type, Any, Generator, TypeVar, Callable, get_origin

from ommi.drivers.database_results import async_result
from ommi.drivers.fetch_actions import FetchAction
from ommi.ext.drivers.sqlite.connection_protocol import SQLiteConnection
from ommi.ext.drivers.sqlite.utils import build_query, SelectQuery, generate_joins
from ommi.models import OmmiModel
from ommi.query_ast import when, ASTGroupNode, ResultOrdering


T = TypeVar("T")


class Iteratable:
    pass


class SQLiteFetchAction(FetchAction[SQLiteConnection, OmmiModel]):
    type_validators = {
        datetime: lambda value: value,  # No-op to avoid type conflict with date
        date: lambda value: value.split()[0],
    }

    @async_result
    async def fetch(self) -> list[OmmiModel]:
        ast = when(*self._predicates)
        session = self._connection.cursor()
        result = self._select(ast, session)
        return result

    async def one(self) -> OmmiModel:
        return (await self.all())[0]

    def _select(self, predicates: ASTGroupNode, session: sqlite3.Cursor):
        query = build_query(predicates)
        query_str = self._build_select_query(query)
        session.execute(query_str, query.values)
        result = session.fetchall()
        return [
            query.model(**dict(self._validate_row_values(query.model, row)))
            for row in result
        ]

    def _build_select_query(self, query: SelectQuery):
        query_builder = [f"SELECT * FROM {query.model.__ommi__.model_name}"]
        if query.models:
            query_builder.extend(generate_joins(query.model, query.models))

        if query.where:
            query_builder.append(f"WHERE {query.where}")

        if query.limit > 0:
            query_builder.append(f"LIMIT {query.limit}")

            if query.offset > 0:
                query_builder.append(f"OFFSET {query.offset}")

        if query.order_by:
            ordering = ", ".join(
                f"{column} {'ASC' if ordering is ResultOrdering.ASCENDING else 'DESC'}"
                for column, ordering in query.order_by.items()
            )
            query_builder.append("ORDER BY")
            query_builder.append(ordering)

        return " ".join(query_builder) + ";"

    def _validate_row_values(
        self, model: Type[OmmiModel], row: tuple[Any]
    ) -> Generator[tuple[str, Any], None, None]:
        for field, value in zip(model.__ommi__.fields.values(), row):
            name = field.get("field_name")
            if validator := self._find_type_validator(field.get("field_type", value)):
                yield name, validator(value)
            else:
                yield name, value

    def _find_type_validator(self, type_hint: Type[T]) -> Callable[[Any], T] | None:
        hint = get_origin(type_hint) or type_hint
        for validator_type, validator in self.type_validators.items():
            if issubclass(hint, validator_type):
                return validator

        return None
