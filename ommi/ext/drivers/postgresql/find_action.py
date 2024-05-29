from ommi.drivers.find_actions import FindAction
from ommi.ext.drivers.postgresql.connection_protocol import PostgreSQLConnection
from ommi.ext.drivers.postgresql.count_action import PostgreSQLCountAction
from ommi.ext.drivers.postgresql.delete_action import PostgreSQLDeleteAction
from ommi.ext.drivers.postgresql.fetch_action import PostgreSQLFetchAction
from ommi.ext.drivers.postgresql.set_fields_action import PostgreSQLSetFieldsAction
from ommi.models import OmmiModel


class PostgreSQLFindAction(FindAction[PostgreSQLConnection, OmmiModel]):
    _count_action = PostgreSQLCountAction
    _delete_action = PostgreSQLDeleteAction
    _fetch_action = PostgreSQLFetchAction
    _set_fields_action = PostgreSQLSetFieldsAction
