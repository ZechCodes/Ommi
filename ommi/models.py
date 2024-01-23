from dataclasses import dataclass, field
from inspect import get_annotations
from typing import Callable, overload, Type, TypeVar, Any, Generator

import ommi.drivers as drivers
import ommi.query_ast as query_ast
from ommi.statuses import DatabaseStatus
from ommi.contextual_method import contextual_method
from ommi.driver_context import active_driver


T = TypeVar("T")

DRIVER_DUNDER_NAME = "__ommi_driver__"
MODEL_NAME_DUNDER_NAME = "__ommi_model_name__"
MODEL_NAME_CLASS_PARAM = "name"
METADATA_DUNDER_NAME = "__ommi_metadata__"


class QueryableFieldDescriptor:
    def __init__(self, field):
        self.field = field

    def __get__(self, instance, owner):
        if instance is None:
            return query_ast.ASTReferenceNode(self, owner)

        return self.field


@dataclass
class OmmiField:
    name: str
    annotation: Any
    default: Any | None = None


@dataclass
class OmmiMetadata:
    model_name: str
    fields: dict[str, OmmiField]

    def clone(self, **kwargs) -> "OmmiMetadata":
        return OmmiMetadata(
            **{name: kwargs.get(name, value) for name, value in vars(self).items()}
        )


def _get_value(
    class_params: dict[str, Any],
    param_name: str,
    cls: Type[Any],
    dunder_name: str,
    default: Any,
) -> Any:
    return class_params.pop(param_name, getattr(cls, dunder_name, default))


class OmmiModel:
    __ommi_metadata__: OmmiMetadata
    __ommi_driver__: "drivers.DatabaseDriver"

    def bind_driver(self, driver: "drivers.DatabaseDriver"):
        """Binds a model instance to a driver."""
        setattr(self, DRIVER_DUNDER_NAME, driver)

    @contextual_method
    def get_driver(
        self, driver: "drivers.DatabaseDrivers | None"
    ) -> "drivers.DatabaseDriver | None":
        if driver:
            return driver

        if _d := getattr(self, DRIVER_DUNDER_NAME, None):
            return _d

        return type(self).get_driver()

    @get_driver.classmethod
    def get_driver(cls) -> "drivers.DatabaseDriver | None":
        return active_driver.get(None)

    @contextual_method
    async def delete(
        self, driver: "drivers.DatabaseDriver | None" = None
    ) -> "DatabaseStatus[drivers.DatabaseDriver]":
        return await self.get_driver(driver).delete(self)

    @delete.classmethod
    async def delete(
        cls, *items: "OmmiModel", driver: "drivers.DatabaseDriver | None" = None
    ) -> "DatabaseStatus[drivers.DatabaseDriver]":
        return await cls.get_driver(driver).delete(*items)

    @classmethod
    async def add(
        cls, *items: "OmmiModel", driver: "drivers.DatabaseDriver | None" = None
    ) -> "DatabaseStatus[drivers.DatabaseDriver]":
        return await cls.get_driver(driver).add(*items)

    @classmethod
    async def count(
        cls,
        *predicates: "ASTGroupNode | DatabaseModel | bool",
        columns: Any | None = None,
        driver: "drivers.DatabaseDriver | None" = None,
    ) -> DatabaseStatus[int]:
        return await cls.get_driver(driver).count(
            cls, *predicates, *cls._build_column_predicates(columns)
        )

    @classmethod
    async def fetch(
        cls,
        *predicates: "ASTGroupNode | DatabaseModel | bool",
        driver: "drivers.DatabaseDriver | None" = None,
        **columns: Any,
    ) -> "DatabaseStatus[list[DatabaseModel]]":
        return await cls.get_driver(driver).fetch(
            cls, *predicates, *cls._build_column_predicates(columns)
        )

    async def sync(
        self, driver: "drivers.DatabaseDriver | None" = None
    ) -> "DatabaseStatus[drivers.DatabaseDriver]":
        return await self.get_driver(driver).update(self)

    @classmethod
    async def update(
        cls, *items: "DatabaseModel", driver: "drivers.DatabaseDriver | None" = None
    ) -> "DatabaseStatus[drivers.DatabaseDriver]":
        return await cls.get_driver(driver).update(*items)

    @classmethod
    def _build_column_predicates(
        cls, columns: dict[str, Any]
    ) -> "Generator[query_ast.ASTComparisonNode | bool, None, None]":
        for name, value in columns.items():
            if name not in cls.__fields__:
                raise ValueError(f"Invalid column {name!r} for model {cls.__name__}")

            yield getattr(cls, name) == value


@overload
def ommi_model(cls: None = None) -> Callable[[T], T | Type[OmmiModel]]:
    ...


@overload
def ommi_model(cls: T) -> T | Type[OmmiModel]:
    ...


def ommi_model(
    cls: T | None = None, /, **kwargs
) -> Callable[[T], T | Type[OmmiModel]] | T | Type[OmmiModel]:
    def wrap_model(c: T) -> T | Type[OmmiModel]:
        metadata_factory = (
            c.__ommi_metadata__.clone
            if hasattr(c, METADATA_DUNDER_NAME)
            else OmmiMetadata
        )

        return type.__new__(
            type(c),
            f"OmmiModel_{c.__name__}",
            (c, OmmiModel),
            {
                name: QueryableFieldDescriptor(getattr(c, name, None))
                for name in get_annotations(c)
                if not name.startswith("_")
            }
            | {
                METADATA_DUNDER_NAME: metadata_factory(
                    model_name=_get_value(
                        kwargs,
                        MODEL_NAME_CLASS_PARAM,
                        c,
                        MODEL_NAME_DUNDER_NAME,
                        c.__name__,
                    )
                )
            },
        )

    return wrap_model if cls is None else wrap_model(cls)
