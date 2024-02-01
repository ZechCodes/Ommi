from abc import ABC, abstractmethod
from functools import wraps
from typing import Type, TypeAlias, TypeVar, Callable, Awaitable, Generator, Any, Generic, ParamSpec

import ommi.model_collections
from ommi.models import OmmiModel
from ommi.query_ast import ASTGroupNode
from ommi.statuses import DatabaseStatus


DriverName: TypeAlias = str
DriverNiceName: TypeAlias = str
M = TypeVar("M")
T = TypeVar("T")
P = ParamSpec("P")


class DatabaseAction(Generic[T]):
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
    def connected(self) -> bool:
        ...

    @abstractmethod
    async def add(self, *items: M) -> DatabaseStatus[M]:
        ...

    @abstractmethod
    async def connect(self, config: DriverConfig) -> DatabaseStatus:
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
    async def sync_schema(self, models: "ommi.model_collections.ModelCollection") -> DatabaseStatus:
        ...

    @abstractmethod
    async def update(self, *items: OmmiModel) -> DatabaseStatus:
        ...


class DatabaseDriver(AbstractDatabaseDriver, ABC):
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

    @classmethod
    def add_driver(cls, driver: "Type[AbstractDatabaseDriver]"):
        cls.__drivers__[driver.driver_name] = driver

    @classmethod
    def disable_driver(cls, name: DriverName):
        cls.__drivers__.pop(name, None)
