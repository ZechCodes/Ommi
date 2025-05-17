from typing import Awaitable

import ommi
from ommi.query_ast import when


class Ommi[TDriver: "ommi.BaseDriver"]:
    def __init__(self, driver: TDriver):
        self._driver = driver

    @property
    def driver(self) -> TDriver:
        return self._driver

    def add(
        self, *models: "ommi.shared_types.DBModel"
    ) -> "Awaitable[ommi.database.DBResult[ommi.shared_types.DBModel]]":
        return ommi.database.DBResult.build(self.driver.add, models)

    def find(
        self, *predicates: "ommi.query_ast.ASTGroupNode | ommi.shared_types.DBModel | bool"
    ) -> "Awaitable[ommi.database.DBQueryResult[ommi.shared_types.DBModel]]":
        return ommi.database.DBQueryResult.build(self.driver, when(*predicates))

    async def __aenter__(self):
        await self._driver.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self._driver.__aexit__(exc_type, exc_val, exc_tb)
