from abc import ABC, abstractmethod
from functools import wraps
from typing import (
    Any,
    Awaitable,
    Callable,
    Generator,
    Generic,
    get_args,
    ParamSpec,
    Type,
    TypeAlias,
    TypeVar,
)

import ommi.driver_context
import ommi.model_collections
from ommi.models import OmmiModel
from ommi.query_ast import ASTGroupNode
from ommi.statuses import DatabaseStatus


DriverName: TypeAlias = str
DriverNiceName: TypeAlias = str
M = TypeVar("M")
T = TypeVar("T")
P = ParamSpec("P")
ConnectionProtocol = TypeVar("ConnectionProtocol")


class DatabaseAction(Generic[T]):
    """A coroutine wrapper that wraps the coroutine's return in a DatabaseStatus result. To force exceptions to be
    raised there is an or_raise coroutine that can be awaited.

        result = await driver.fetch(predicate)  # Can be a DatabaseStatus.Success or a DatabaseStatus.Exception
        ...
        result = await driver.fetch(predicate).or_raise()  # DatabaseStatus.Success or raises the exception
    """

    def __init__(self, awaitable: Awaitable[T]):
        self._awaitable = awaitable

    def __await__(self) -> Generator[Any, None, DatabaseStatus[T]]:
        return self._run().__await__()

    async def or_raise(self) -> DatabaseStatus[T]:
        return DatabaseStatus.Success(await self._awaitable)

    async def _run(self) -> DatabaseStatus[T]:
        try:
            result = await self._awaitable

        except Exception as error:
            return DatabaseStatus.Exception(error)

        else:
            return DatabaseStatus.Success(result)


def database_action(func: Callable[P, T]) -> Callable[P, DatabaseAction[T]]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> DatabaseAction[T]:
        return DatabaseAction[T](func(*args, **kwargs))

    return wrapper


class DriverConfig:
    pass


class AbstractDatabaseDriver(ABC):
    __drivers__: "dict[DriverName, Type[AbstractDatabaseDriver]]"
    driver_name: DriverName

    @classmethod
    @abstractmethod
    def add_driver(cls, driver: "Type[AbstractDatabaseDriver]"):
        ...

    @classmethod
    @abstractmethod
    def disable_driver(cls, name: DriverName):
        ...

    @property
    @abstractmethod
    def connection(self) -> Any:
        ...

    @property
    @abstractmethod
    def connected(self) -> bool:
        ...

    @abstractmethod
    async def add(self, *items: M) -> DatabaseStatus[M]:
        ...

    @abstractmethod
    async def count(self, *predicates: ASTGroupNode | Type[M]) -> DatabaseStatus[int]:
        ...

    @abstractmethod
    async def delete(self, *items: OmmiModel) -> DatabaseStatus:
        ...

    @abstractmethod
    async def disconnect(self) -> DatabaseStatus:
        ...

    @abstractmethod
    async def fetch(
        self, *predicates: ASTGroupNode | Type[OmmiModel]
    ) -> DatabaseStatus:
        ...

    @abstractmethod
    async def sync_schema(
        self, models: "ommi.model_collections.ModelCollection | None"
    ) -> DatabaseStatus:
        ...

    @abstractmethod
    async def update(self, *items: OmmiModel) -> DatabaseStatus:
        ...

    @classmethod
    @abstractmethod
    async def from_config(cls, config: DriverConfig) -> "AbstractDatabaseDriver":
        ...


class DatabaseDriver(Generic[ConnectionProtocol], AbstractDatabaseDriver, ABC):
    __drivers__ = {}
    driver_name: DriverName
    nice_name: DriverNiceName
    auto_value_factories: dict[Type[T], Callable[[OmmiModel], T]] = {}

    def __init_subclass__(cls, **kwargs):
        cls.driver_name = kwargs.pop(
            "driver_name", getattr(cls, "driver_name", cls.__name__)
        )
        cls.nice_name = kwargs.pop("nice_name", getattr(cls, "nice_name", cls.__name__))

        super().__init_subclass__(**kwargs)
        cls.add_driver(cls)

    def __init__(self, connection: ConnectionProtocol):
        super().__init__()
        self._connection = connection
        self._connected = True


    @property
    def connection(self) -> Any:
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
        await self.disconnect().or_raise()
        self.__exit__(*args)
        return


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


def connection_context_manager(func: Callable[[DriverConfig], Awaitable[AbstractDatabaseDriver]]):
    @wraps(func)
    def wrapper(cls, config: DriverConfig) -> ConnectionFromConfigContextManager:
        return ConnectionFromConfigContextManager(func(cls, config))

    return wrapper


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