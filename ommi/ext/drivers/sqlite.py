import sqlite3
from dataclasses import dataclass, field as dc_field
from datetime import datetime, date
from typing import Type, Any, TypeVar, Callable, get_origin, Generator, Protocol, runtime_checkable

from tramp.results import Result

from ommi.drivers import DatabaseDriver, DriverConfig, database_action, enforce_connection_protocol
from ommi.model_collections import ModelCollection
from ommi.models import OmmiField, OmmiModel, get_collection
from ommi.query_ast import (
    ASTGroupNode,
    when,
    ASTReferenceNode,
    ASTLiteralNode,
    ASTLogicalOperatorNode,
    ASTComparisonNode,
    ASTOperatorNode,
    ASTGroupFlagNode,
    ResultOrdering,
)

T = TypeVar("T")


@dataclass
class SelectQuery:
    limit: int = 0
    model: Type[OmmiModel] | None = None
    offset: int = 0
    order_by: dict[str, ResultOrdering] = dc_field(default_factory=dict)
    tables: list[OmmiModel] = dc_field(default_factory=list)
    values: list[Any] = dc_field(default_factory=list)
    where: str = ""


@dataclass
class SQLiteConfig(DriverConfig):
    filename: str


@runtime_checkable
class SQLiteConnection(Protocol):
    def close(self) -> None:
        ...

    def cursor(self) -> sqlite3.Cursor:
        ...

    def rollback(self) -> None:
        ...

@enforce_connection_protocol
class SQLiteDriver(DatabaseDriver[SQLiteConnection], driver_name="sqlite", nice_name="SQLite"):
    logical_operator_mapping = {
        ASTLogicalOperatorNode.AND: "AND",
        ASTLogicalOperatorNode.OR: "OR",
    }

    operator_mapping = {
        ASTOperatorNode.EQUALS: "=",
        ASTOperatorNode.NOT_EQUALS: "!=",
        ASTOperatorNode.GREATER_THAN: ">",
        ASTOperatorNode.GREATER_THAN_OR_EQUAL: ">=",
        ASTOperatorNode.LESS_THAN: "<",
        ASTOperatorNode.LESS_THAN_OR_EQUAL: "<=",
    }

    type_validators = {
        datetime: lambda value: value,  # No-op to avoid type conflict with date
        date: lambda value: value.split()[0],
    }

    type_mapping = {
        int: "INTEGER",
        str: "TEXT",
        float: "REAL",
        bool: "INTEGER",
    }

    @database_action
    async def disconnect(self) -> "SQLiteDriver":
        self._connection.close()
        self._connected = False
        return self

    @database_action
    async def add(self, *items: OmmiModel) -> "SQLiteDriver":
        session = self._connection.cursor()
        try:
            for item in items:
                self._insert(item, session)
                self._sync_with_last_inserted(item, session)

        except:
            self._connection.rollback()
            raise

        else:
            return self

        finally:
            session.close()

    @database_action
    async def count(self, *predicates: ASTGroupNode | Type[OmmiModel]) -> int:
        ast = when(*predicates)
        session = self._connection.cursor()
        return self._count(ast, session)

    @database_action
    async def delete(self, *items: OmmiModel) -> "SQLiteDriver":
        models = {}
        for item in items:
            models.setdefault(type(item), []).append(item)

        session = self._connection.cursor()
        try:
            for model, items in models.items():
                self._delete_rows(model, items, session)

        except:
            self._connection.rollback()
            raise

        else:
            return self

        finally:
            session.close()

    @database_action
    async def fetch(
        self, *predicates: ASTGroupNode | Type[OmmiModel]
    ) -> list[OmmiModel]:
        ast = when(*predicates)
        session = self._connection.cursor()
        result = self._select(ast, session)
        return result

    @database_action
    async def sync_schema(
        self, collection: ModelCollection | None = None
    ) -> "SQLiteDriver":
        session = self._connection.cursor()
        models = get_collection(
            Result.Value(collection) if collection else Result.Nothing
        ).models
        try:
            for model in models:
                self._create_table(model, session)

        except:
            self._connection.rollback()
            raise

        else:
            return self

        finally:
            session.close()

    @database_action
    async def update(self, *items: OmmiModel) -> "SQLiteDriver":
        models = {}
        for item in items:
            models.setdefault(type(item), []).append(item)

        session = self._connection.cursor()
        try:
            for model, items in models.items():
                self._update_rows(model, items, session)

        except:
            self._connection.rollback()
            raise

        else:
            return self

        finally:
            session.close()

    @classmethod
    async def from_config(cls, config: SQLiteConfig) -> "SQLiteDriver":
        return cls(sqlite3.connect(config.filename))

    def _build_column(self, field: OmmiField, pk: bool) -> str:
        column = [
            field.get("store_as"),
            self._get_sqlite_type(field.get("field_type")),
        ]
        if pk:
            column.append("PRIMARY KEY")

        return " ".join(column)

    def _process_ast(self, ast: ASTGroupNode) -> SelectQuery:
        query = SelectQuery(
            limit=ast.max_results,
            offset=ast.results_page * ast.max_results,
            order_by=self._process_ordering(ast.sorting),
        )
        where = []
        node_stack = [iter(ast)]
        while node_stack:
            match next(node_stack[~0], None):
                case ASTGroupNode() as group:
                    node_stack.append(iter(group))

                case ASTReferenceNode(None, model):
                    query.tables.append(model)
                    query.model = query.model or model

                case ASTReferenceNode(field, model):
                    name = f"{model.__ommi_metadata__.model_name}.{field.name}"
                    where.append(name)
                    query.tables.append(model)
                    query.model = query.model or model

                case ASTLiteralNode(value):
                    where.append("?")
                    query.values.append(value)

                case ASTLogicalOperatorNode() as op:
                    where.append(self.logical_operator_mapping[op])

                case ASTOperatorNode() as op:
                    where.append(self.operator_mapping[op])

                case ASTComparisonNode(left, right, op):
                    node_stack.append(iter((left, op, right)))

                case ASTGroupFlagNode.OPEN:
                    if len(node_stack) > 1:
                        where.append("(")

                case ASTGroupFlagNode.CLOSE:
                    if len(node_stack) > 1:
                        where.append(")")

                case None:
                    node_stack.pop()

                case node:
                    raise TypeError(f"Unexpected node type: {node}")

        query.where = " ".join(where)
        return query

    def _process_ordering(
        self, sorting: list[ASTReferenceNode]
    ) -> dict[str, ResultOrdering]:
        return {
            f"{ref.model.__model_name__}.{ref.field.name}": ref.ordering
            for ref in sorting
        }

    def _create_table(self, model: Type[OmmiModel], session: sqlite3.Cursor):
        pk = model.get_primary_key_field().get("store_as")
        columns = ", ".join(
            self._build_column(field, field.get("store_as") == pk)
            for field in model.__ommi_metadata__.fields.values()
        )
        session.execute(
            f"CREATE TABLE IF NOT EXISTS {model.__ommi_metadata__.model_name} ({columns});"
        )

    def _insert(self, item: OmmiModel, session: sqlite3.Cursor):
        fields = list(item.__ommi_metadata__.fields.values())
        data = {
            field.get("store_as"): getattr(item, field.get("field_name"))
            for field in fields
        }
        qs = ", ".join(["?"] * len(data))
        columns = ", ".join(data.keys())
        values = tuple(data.values())
        session.execute(
            f"INSERT INTO {item.__ommi_metadata__.model_name} ({columns}) VALUES ({qs});",
            values,
        )

    def _update_rows(
        self,
        model: Type[OmmiModel],
        items: list[OmmiModel],
        session: sqlite3.Cursor,
    ):
        pk = model.get_primary_key_field().get("store_as")
        fields = list(model.__ommi_metadata__.fields.values())
        for item in items:
            values = (
                getattr(item, field.get("field_name"))
                for field in fields
                if field.get("store_as") != pk
            )
            assignments = ", ".join(
                f"{field.get('store_as')} = ?"
                for field in fields
                if field.get("store_as") != pk
            )
            session.execute(
                f"UPDATE {model.__ommi_metadata__.model_name} SET {assignments} WHERE {pk} = ?;",
                (*values, getattr(item, pk)),
            )

    def _delete_rows(
        self,
        model: Type[OmmiModel],
        items: list[OmmiModel],
        session: sqlite3.Cursor,
    ):
        pk = model.get_primary_key_field().get("store_as")
        keys = [getattr(item, pk) for item in items]
        qs = ", ".join(["?"] * len(items))
        session.execute(
            f"DELETE FROM {model.__ommi_metadata__.model_name} WHERE {pk} IN ({qs});",
            keys,
        )

    def _select(self, predicates: ASTGroupNode, session: sqlite3.Cursor):
        query = self._process_ast(predicates)
        query_str = self._build_select_query(query)
        session.execute(query_str, query.values)
        result = session.fetchall()
        return [
            query.model(*self._validate_row_values(query.model, row)) for row in result
        ]

    def _count(self, predicates: ASTGroupNode, session: sqlite3.Cursor):
        query = self._process_ast(predicates)
        query_str = self._build_count_query(query)
        session.execute(query_str, query.values)
        result = session.fetchone()
        return result[0]

    def _validate_row_values(
        self, model: Type[OmmiModel], row: tuple[Any]
    ) -> Generator[Any, None, None]:
        for field, value in zip(model.__ommi_metadata__.fields.values(), row):
            if validator := self._find_type_validator(field.get("field_type", value)):
                yield validator(value)
            else:
                yield value

    def _find_type_validator(self, type_hint: Type[T]) -> Callable[[Any], T] | None:
        hint = get_origin(type_hint) or type_hint
        for validator_type, validator in self.type_validators.items():
            if issubclass(hint, validator_type):
                return validator

        return None

    def _get_sqlite_type(self, type_: Type) -> str:
        return self.type_mapping.get(type_, "TEXT")

    def _build_select_query(self, query: SelectQuery):
        query_builder = [f"SELECT * FROM {query.model.__ommi_metadata__.model_name}"]
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

    def _build_count_query(self, query: SelectQuery):
        query_builder = [
            f"SELECT Count(*) FROM {query.model.__ommi_metadata__.model_name}"
        ]
        if query.where:
            query_builder.append(f"WHERE {query.where}")

        if query.limit > 0:
            query_builder.append(f"LIMIT {query.limit}")

            if query.offset > 0:
                query_builder.append(f"OFFSET {query.offset}")

        return " ".join(query_builder) + ";"

    def _sync_with_last_inserted(self, item: OmmiModel, session: sqlite3.Cursor):
        pk = item.get_primary_key_field().get("store_as")
        result = session.execute("SELECT last_insert_rowid();").fetchone()
        setattr(item, pk, result[0])
