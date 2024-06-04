import psycopg

from ommi.drivers.database_results import async_result
from ommi.drivers.delete_actions import DeleteAction
from ommi.ext.drivers.postgresql.connection_protocol import PostgreSQLConnection
from ommi.ext.drivers.postgresql.utils import build_query
from ommi.models import OmmiModel
from ommi.query_ast import when, ASTGroupNode


class PostgreSQLDeleteAction(DeleteAction[PostgreSQLConnection, OmmiModel]):
    @async_result
    async def delete(self) -> bool:
        ast = when(*self._predicates)
        session = self._connection.cursor()
        await self._delete(ast, session)
        return self

    async def _delete(
        self,
        ast: ASTGroupNode,
        session: psycopg.AsyncCursor,
    ):
        query = build_query(ast)
        query_builder = ["DELETE FROM", query.model.__ommi_metadata__.model_name]
        where = [query.where]
        if query.models:
            query_builder.append("USING")
            query_builder.append(", ".join(model.__ommi_metadata__.model_name for model in query.models))
            using_join = [" AND ".join(self._create_using_predicate(model, query.model) for model in query.models)]

            where = []
            if query.where:
                where.append(f"({query.where}) AND")

            where.extend(using_join)

        query_builder.append("WHERE")
        query_builder.extend(where)
        print(f"{' '.join(query_builder)};")
        await session.execute(f"{' '.join(query_builder)};", query.values)

    def _create_using_predicate(self, model: OmmiModel, target_model: OmmiModel) -> str:
        if target_model in model.__ommi_metadata__.references:
            reference = model.__ommi_metadata__.references[target_model][0]
            to_column = f"{reference.to_model.__ommi_metadata__.model_name}.{reference.to_field.get('store_as')}"
            from_column = f"{reference.from_model.__ommi_metadata.model_name}.{reference.from_field.get('store_as')}"

        else:
            reference = target_model.__ommi_metadata__.references[model][0]
            from_column = f"{reference.to_model.__ommi_metadata__.model_name}.{reference.to_field.get('store_as')}"
            to_column = f"{reference.from_model.__ommi_metadata__.model_name}.{reference.from_field.get('store_as')}"

        return f"{to_column} = {from_column}"