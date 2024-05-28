from ommi.drivers.find_actions import FindAction
from ommi.ext.drivers.sqlite.connection_protocol import SQLiteConnection
from ommi.ext.drivers.sqlite.count_action import SQLiteCountAction
from ommi.ext.drivers.sqlite.delete_action import SQLiteDeleteAction
from ommi.ext.drivers.sqlite.fetch_action import SQLiteFetchAction
from ommi.ext.drivers.sqlite.set_fields_action import SQLiteSetFieldsAction
from ommi.models import OmmiModel


class SQLiteFindAction(FindAction[SQLiteConnection, OmmiModel]):
    _count_action = SQLiteCountAction
    _delete_action = SQLiteDeleteAction
    _fetch_action = SQLiteFetchAction
    _set_fields_action = SQLiteSetFieldsAction
