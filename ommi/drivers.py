from abc import ABC, abstractmethod
from typing import Type, TypeAlias, TypeVar, Callable

from ommi.models import OmmiModel
from ommi.query_ast import ASTGroupNode
from ommi.statuses import DatabaseStatus


DriverName: TypeAlias = str
DriverNiceName: TypeAlias = str
M = TypeVar("M")
T = TypeVar("T")


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
    async def sync_schema(self, models: set[Type[OmmiModel]]) -> DatabaseStatus:
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
