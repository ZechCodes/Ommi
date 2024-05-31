from abc import ABC, abstractmethod
from functools import wraps
from typing import TypeAlias, Type, Any, Generic, get_args, TypeVar, Callable, Awaitable

import ommi
import ommi.drivers.add_actions as add_action
import ommi.drivers.find_actions as find_action
import ommi.drivers.schema_actions as schema_action

from ommi.drivers.database_results import AsyncResultWrapper
from ommi.drivers.driver_configs import DriverConfig
from ommi.drivers.driver_types import TConn, TModel
from ommi.models.collections import ModelCollection
from ommi.query_ast import ASTGroupNode

DriverName: TypeAlias = str
DriverNiceName: TypeAlias = str
Predicate: TypeAlias = ASTGroupNode | Type[TModel] | bool
ConnectionProtocol = TypeVar("ConnectionProtocol")


class AbstractDatabaseDriver(Generic[TConn, TModel], ABC):
    __drivers__: "dict[DriverName, Type[AbstractDatabaseDriver]]"
    driver_name: DriverName

    # ---------------------------- #
    # Connection Management        #
    # ---------------------------- #

    @property
    @abstractmethod
    def connection(self) -> Any: ...

    @property
    @abstractmethod
    def connected(self) -> bool: ...

    @abstractmethod
    def disconnect(self) -> AsyncResultWrapper[bool]: ...

    # ---------------------------- #
    # Actions                      #
    # ---------------------------- #

    @property
    @abstractmethod
    def add(self, *items: TModel) -> "add_action.AddAction[TConn, TModel]": ...

    @abstractmethod
    def find(self, *predicates: Predicate) -> "find_action.FindAction[TConn, TModel]": ...

    @abstractmethod
    def schema(
        self, model_collection: ModelCollection[Type[TModel]] | None = None
    ) -> "schema_action.SchemaAction[TConn, TModel]": ...

    # ---------------------------- #
    # Driver Collection Management #
    # ---------------------------- #

    @classmethod
    @abstractmethod
    def add_driver(cls, driver: "Type[AbstractDatabaseDriver]"): ...

    @classmethod
    @abstractmethod
    def disable_driver(cls, name: DriverName): ...

    # ---------------------------- #
    # Configuration                #
    # ---------------------------- #

    @classmethod
    @abstractmethod
    async def from_config(cls, config: DriverConfig) -> "AbstractDatabaseDriver": ...


class DatabaseDriver(AbstractDatabaseDriver[TConn, TModel], ABC):
    __drivers__ = {}

    def __init_subclass__(cls, **kwargs):
        cls.driver_name = kwargs.pop(
            "driver_name", getattr(cls, "driver_name", cls.__name__)
        )
        cls.nice_name = kwargs.pop("nice_name", getattr(cls, "nice_name", cls.__name__))

        super().__init_subclass__(**kwargs)
        cls.add_driver(cls)

    def __init__(self, connection: TConn):
        self._connection = connection
        self._connected = True

    def __enter__(self):
        if hasattr(self, "_driver_context"):
            return self

        self._driver_context = ommi.driver_context.UseDriver(self)
        return self._driver_context.__enter__()

    def __exit__(self, *args):
        if not hasattr(self, "_driver_context"):
            return

        context = self._driver_context
        del self._driver_context
        try:
            return context.__exit__(*args)
        except ValueError:
            return True

    async def __aenter__(self):
        self.__enter__()
        return self

    async def __aexit__(self, *args):
        await self.disconnect().raise_on_errors()
        self.__exit__(*args)
        return

    @property
    def connection(self) -> TConn:
        return self._connection

    @property
    def connected(self) -> bool:
        return self._connected

    @classmethod
    def add_driver(cls, driver: "Type[AbstractDatabaseDriver]"):
        cls.__drivers__[driver.driver_name] = driver

    @classmethod
    def disable_driver(cls, name: DriverName):
        cls.__drivers__.pop(name, None)


class ConnectionFromConfigContextManager:
    def __init__(self, awaitable: Awaitable[AbstractDatabaseDriver]):
        self.awaitable = awaitable
        self.connection = None

    def __await__(self):
        return self.awaitable.__await__()

    async def __aenter__(self):
        self.connection = await self.awaitable
        await self.connection.__aenter__()
        return self.connection

    async def __aexit__(self, *args):
        return await self.connection.__aexit__(*args)


def connection_context_manager(
    func: Callable[[DriverConfig], Awaitable[AbstractDatabaseDriver]]
):
    @wraps(func)
    def wrapper(cls, config: DriverConfig) -> ConnectionFromConfigContextManager:
        return ConnectionFromConfigContextManager(func(cls, config))

    return wrapper

def enforce_connection_protocol(driver: Type[AbstractDatabaseDriver]):
    init = driver.__init__
    connection_protocol = get_args(driver.__orig_bases__[0])[0]
    if connection_protocol is ConnectionProtocol:
        raise TypeError(
            f"Expected a connection protocol to be defined on the driver class {driver.__qualname__}."
        )

    @wraps(driver.__init__)
    def __init__(self, connection, *args, **kwargs):
        if connection_protocol and not isinstance(connection, connection_protocol):
            raise TypeError(
                f"Expected connection implementing the {connection_protocol.__qualname__} protocol, {type(connection)} does not."
            )

        init(self, connection, *args, **kwargs)

    driver.__init__ = __init__
    return driver

