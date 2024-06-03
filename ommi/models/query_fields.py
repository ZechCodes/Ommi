from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Any, Type
from tramp.results import Result

import ommi
import ommi.drivers.drivers
import ommi.query_ast

T = TypeVar("T")


class LazyQueryField(ABC):
    def __init__(self, query: "ommi.query_ast.ASTGroupNode", driver: "ommi.drivers.drivers.AbstractDatabaseDriver | None" = None):
        self._query = query
        self._driver = driver

        self._cache = Result.Error(ValueError("Not cached yet"))

    def __await__(self):
        return self.value.__await__()

    def __get_pydantic_core_schema__(self, *_):
        import pydantic_core
        return pydantic_core.core_schema.no_info_plain_validator_function(function=self.__pydantic_validator)

    @staticmethod
    def __pydantic_validator(value):
        if value is None:
            return value

        if isinstance(value, LazyQueryField):
            return value

        raise TypeError(f"Expected LazyQueryField, got {type(value)}")

    @abstractmethod
    async def get(self, default=None):
        ...

    async def refresh(self) -> None:
        with Result.build() as builder:
            builder.set(await self._fetch())

        self._cache = builder.result

    async def refresh_if_needed(self) -> None:
        match self._cache:
            case Result.Error():
                await self.refresh()

    @property
    @abstractmethod
    async def result(self):
        ...

    @property
    @abstractmethod
    async def value(self):
        ...

    @abstractmethod
    async def _fetch(self):
        ...

    async def _get_result(self):
        match self._cache:
            case Result.Value() as result:
                return result

            case Result.Error():
                self._cache = await self._fetch()
                return self._cache

    def _get_driver(self):
        return self._driver or ommi.active_driver.get()

    @classmethod
    @abstractmethod
    def create(cls, model: "ommi.models.OmmiModel", args: tuple[Any, ...]) -> "LazyQueryField":
        ...


class LazyLoadTheRelated(Generic[T], LazyQueryField):
    async def get(self, default: T | None = None) -> T | None:
        return (await self.result).value_or(default)

    @property
    async def result(self) -> Result[T]:
        return await self._get_result()

    @property
    async def value(self) -> T:
        return (await self.result).value

    async def _fetch(self):
        with Result.build() as builder:
            builder.set(
                await self._get_driver()
                .find(self._query.limit(1))
                .fetch.one()
            )

        return builder.result

    @classmethod
    def create(cls, model: "ommi.models.OmmiModel", args: tuple[Any, ...]) -> "LazyQueryField":
        contains, *_ = args
        return cls(_build_query(model, contains))


class LazyLoadEveryRelated(Generic[T], LazyQueryField):
    async def get(self, default: list[T] | None = None) -> list[T] | None:
        return (await self.result).value_or(default)

    @property
    async def result(self) -> Result[list[T]]:
        return await self._get_result()

    @property
    async def value(self) -> list[T]:
        return (await self.result).value

    async def _fetch(self):
        with Result.build() as builder:
            builder.set(
                await self._get_driver()
                .find(self._query)
                .fetch.all()
            )

        return builder.result

    @classmethod
    def create(cls, model: "ommi.models.OmmiModel", args: tuple[Any, ...]) -> "LazyQueryField":
        contains, *_ = args
        return cls(_build_query(model, contains))


def _build_query(model: "ommi.models.OmmiModel", contains: "Type[ommi.models.OmmiModel]") -> "ommi.query_ast.ASTGroupNode":
    if ref := model.__ommi_metadata__.references.get(contains):
        return ommi.query_ast.search(
            getattr(ref[0].to_model, ref[0].to_field.get("field_name"))
            == getattr(model, ref[0].from_field.get("field_name"))
        )

    if ref := contains.__ommi_metadata__.references.get(type(model)):
        return ommi.query_ast.search(
            getattr(ref[0].from_model, ref[0].from_field.get("field_name"))
            == getattr(model, ref[0].to_field.get("field_name"))
        )

    raise RuntimeError(f"No reference found between models {type(model)} and {contains}")