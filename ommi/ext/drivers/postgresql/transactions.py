from ommi.drivers.transactions import Transaction
from psycopg import Rollback


class PostgreSQLTransaction(Transaction):
    def __init__(self, driver):
        self._transaction = driver.connection.transaction()

        super().__init__(driver, [self._transaction])

    async def _commit(self):
        await self.driver.connection.commit()

    async def _rollback(self):
        raise Rollback()