import psycopg
from dataclasses import dataclass, field as dc_field
from datetime import datetime, date
from typing import Type, Any, TypeVar, Callable, get_origin, Generator, Sequence, Protocol, runtime_checkable

from tramp.results import Result

from ommi.drivers import DatabaseDriver, DriverConfig, database_action, enforce_connection_protocol, connection_context_manager
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
class PostgreSQLConfig(DriverConfig):
    host: str
    port: int
    database_name: str
    username: str
    password: str

    def to_uri(self) -> str:
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database_name}"


@runtime_checkable
class PostgreSQLConnection(Protocol):
    def cursor(self) -> psycopg.AsyncCursor:
        ...

    def close(self) -> None:
        ...

    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...


@enforce_connection_protocol
class PostgreSQLDriver(DatabaseDriver[PostgreSQLConnection], driver_name="postgresql", nice_name="PostgreSQL"):
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

    def __init__(self, connection: PostgreSQLConnection):
        super().__init__(connection)

    @database_action
    async def disconnect(self) -> "PostgreSQLDriver":
        await self.connection.close()
        self._connected = False
        return self

    @database_action
    async def add(self, *items: OmmiModel) -> "PostgreSQLDriver":
        session = self._connection.cursor()
        try:
            await self._insert(items, session, type(items[0]))

        except:
            await self._connection.rollback()
            raise

        else:
            return self

        finally:
            await session.close()

    @database_action
    async def count(self, *predicates: ASTGroupNode | Type[OmmiModel]) -> int:
        ast = when(*predicates)
        session = self._connection.cursor()
        return await self._count(ast, session)

    @database_action
    async def delete(self, *items: OmmiModel) -> "PostgreSQLDriver":
        models = {}
        for item in items:
            models.setdefault(type(item), []).append(item)

        session = self._connection.cursor()
        try:
            for model, items in models.items():
                await self._delete_rows(model, items, session)

        except:
            await self._connection.rollback()
            raise

        else:
            return self

        finally:
            await session.close()

    @database_action
    async def fetch(
        self, *predicates: ASTGroupNode | Type[OmmiModel]
    ) -> list[OmmiModel]:
        ast = when(*predicates)
        session = self._connection.cursor()
        result = await self._select(ast, session)
        return result

    @database_action
    async def sync_schema(
        self, collection: ModelCollection | None = None
    ) -> "PostgreSQLDriver":
        session = self._connection.cursor()
        models = get_collection(
            Result.Value(collection) if collection else Result.Nothing
        ).models
        try:
            for model in models:
                await self._create_table(model, session)

        except:
            await self._connection.rollback()
            raise

        else:
            return self

        finally:
            await session.close()

    @database_action
    async def update(self, *items: OmmiModel) -> "PostgreSQLDriver":
        models = {}
        for item in items:
            models.setdefault(type(item), []).append(item)

        session = self._connection.cursor()
        try:
            for model, items in models.items():
                await self._update_rows(model, items, session)

        except:
            await self._connection.rollback()
            raise

        else:
            return self

        finally:
            await session.close()

    @classmethod
    @connection_context_manager
    async def from_config(cls, config: PostgreSQLConfig) -> "PostgreSQLDriver":
        connection = await psycopg.AsyncConnection.connect(config.to_uri())
        return cls(connection)

    def _build_column(self, field: OmmiField, pk: bool) -> str:
        column = [
            field.get("store_as"),
            self._get_postgresql_type(field.get("field_type"), pk),
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
                    where.append("%s")
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

    async def _create_table(self, model: Type[OmmiModel], session: psycopg.AsyncCursor):
        pk = model.get_primary_key_field()
        columns = ", ".join(
            self._build_column(field, field == pk)
            for field in model.__ommi_metadata__.fields.values()
        )
        await session.execute(
            f"CREATE TABLE IF NOT EXISTS {model.__ommi_metadata__.model_name} ({columns});"
        )

    async def _insert(self, items: Sequence[OmmiModel], session: psycopg.AsyncCursor, model: Type[OmmiModel]):
        query = [f"INSERT INTO {model.__ommi_metadata__.model_name}"]

        fields = list(model.__ommi_metadata__.fields.values())
        pk = model.get_primary_key_field()
        columns = [field.get("store_as") for field in fields if field != pk]
        query.append(f"({','.join(columns)})")

        values = []
        inserts = []
        for item in items:
            qs = ",".join(["%s"] * len(columns))
            inserts.append(f"({qs})")
            values.extend(getattr(item, field.get("field_name")) for field in fields if field != pk)

        query.append(f"VALUES {','.join(inserts)}")
        query.append(f"RETURNING {pk.get('store_as')};")

        result = await session.execute(" ".join(query).encode(), values)

        # Update the primary key field of the models that were inserted if the primary key is an auto-incrementing field
        item_stack = iter(items)
        async for record in result:
            item = next(item_stack)
            setattr(item, pk.get("field_name"), record[0])

    async def _update_rows(
        self,
        model: Type[OmmiModel],
        items: list[OmmiModel],
        session: psycopg.AsyncCursor,
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
                f"{field.get('store_as')} = %s"
                for field in fields
                if field.get("store_as") != pk
            )
            await session.execute(
                f"UPDATE {model.__ommi_metadata__.model_name} SET {assignments} WHERE {pk} = %s;",
                (*values, getattr(item, pk)),
            )

    async def _delete_rows(
        self,
        model: Type[OmmiModel],
        items: list[OmmiModel],
        session: psycopg.AsyncCursor,
    ):
        pk = model.get_primary_key_field().get("store_as")
        keys = [getattr(item, pk) for item in items]
        qs = ", ".join(["%s"] * len(items))
        await session.execute(
            f"DELETE FROM {model.__ommi_metadata__.model_name} WHERE {pk} IN ({qs});",
            keys,
        )

    async def _select(self, predicates: ASTGroupNode, session: psycopg.AsyncCursor):
        query = self._process_ast(predicates)
        query_str = self._build_select_query(query)
        result = await session.execute(query_str.encode(), query.values)
        return [
            query.model(*self._validate_row_values(query.model, row)) async for row in result
        ]

    async def _count(self, predicates: ASTGroupNode, session: psycopg.AsyncCursor):
        query = self._process_ast(predicates)
        query_str = self._build_count_query(query)
        result = await (await session.execute(query_str.encode(), query.values)).fetchone()
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

    def _get_postgresql_type(self, type_: Type, pk: bool) -> str:
        if pk and isinstance(type_, type) and issubclass(type_, int):
            return "SERIAL"

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
