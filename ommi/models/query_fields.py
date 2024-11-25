"""
Lazy Evaluation of Query Fields for Ommi Models

This module implements lazy loading of query fields from the database, using
different strategies for associating models. It supports various approaches for
deferring query execution until needed, thus managing model relationships and
avoiding issues like circular imports efficiently.
"""


from abc import ABC, abstractmethod
from functools import partial
from typing import Annotated, Callable, get_args, get_origin, Protocol, TypeVar, Generic, Any, Type

from tramp.results import Result
from tramp.annotations import ForwardRef

import ommi
import ommi.drivers.drivers
import ommi.query_ast

T = TypeVar("T")


class QueryStrategy(Protocol):
    def generate_query(
        self, model: "ommi.models.OmmiModel", contains: "Type[ommi.models.OmmiModel]"
    ) -> "ommi.query_ast.ASTGroupNode":
        ...

    def generate_query_factory(
        self, model: "ommi.models.OmmiModel", contains: "Type[ommi.models.OmmiModel]"
    ) -> "Callable[[], ommi.query_ast.ASTGroupNode]":
        return partial(self.generate_query, model, contains)


class AssociateOnReference(QueryStrategy):
    def generate_query(
        self, model: "ommi.models.OmmiModel", contains: "Type[ommi.models.OmmiModel]"
    ) -> "ommi.query_ast.ASTGroupNode":
        if refs := model.__ommi__.references.get(contains):
            return ommi.query_ast.when(
                *(
                    getattr(r.to_model, r.to_field.get("field_name"))
                    == getattr(model, r.from_field.get("field_name"))
                    for r in refs
                )
            )

        if refs := contains.__ommi__.references.get(type(model)):
            return ommi.query_ast.when(
                *(
                    getattr(r.from_model, r.from_field.get("field_name"))
                    == getattr(model, r.to_field.get("field_name"))
                    for r in refs
                )
            )

        raise RuntimeError(
            f"No reference found between models {type(model)} and {contains}"
        )


class AssociateUsing(QueryStrategy):
    def __init__(self, association_model: Type[T]):
        self._association_model = association_model

    @property
    def association_model(self) -> Type[T]:
        if isinstance(self._association_model, ForwardRef):
            return self._association_model.evaluate()

        return self._association_model

    def generate_query(
        self, model: "ommi.models.OmmiModel", contains: "Type[ommi.models.OmmiModel]"
    ) -> "ommi.query_ast.ASTGroupNode":
        contains_model = get_args(contains)[0]
        refs = self.association_model.__ommi__.references.get(type(model))
        return ommi.query_ast.when(
            contains_model,
            *(
                getattr(r.from_model, r.from_field.get("field_name"))
                == getattr(model, r.to_field.get("field_name"))
                for r in refs
            )
        )


class LazyQueryField(ABC):
    def __init__(
        self,
        query_factory: "Callable[[], ommi.query_ast.ASTGroupNode]",
        driver: "ommi.drivers.drivers.AbstractDatabaseDriver | None" = None,
    ):
        self._query_factory = query_factory
        self._driver = driver

        self._cache = Result.Error(ValueError("Not cached yet"))

    @property
    def _query(self) -> "ommi.query_ast.ASTGroupNode"   :
        return self._query_factory()

    def __await__(self):
        return self.value.__await__()

    def __get_pydantic_core_schema__(self, *_):
        import pydantic_core

        return pydantic_core.core_schema.no_info_plain_validator_function(
            function=self.__pydantic_validator
        )

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
    def create(
        cls, model: "ommi.models.OmmiModel", annotation_args: tuple[Any, ...], *, query_strategy: QueryStrategy | None = None
    ) -> "LazyQueryField":
        return cls(cls._get_query_factory(model, annotation_args[0], query_strategy))

    @classmethod
    def _get_query_factory(
        cls,
        model: "ommi.models.OmmiModel",
        contains: "Type[ommi.models.OmmiModel] | Any",
        query_strategy: QueryStrategy | None
    ) -> "Callable[[], ommi.query_ast.ASTGroupNode]":
        strategy = cls._get_query_strategy(contains, query_strategy)
        return strategy.generate_query_factory(model, contains)

    @staticmethod
    def _get_query_strategy(contains: "Type[ommi.models.OmmiModel]", query_strategy: QueryStrategy | None):
        if query_strategy:
            return query_strategy

        if get_origin(contains) is Annotated:
            return get_args(contains)[1]

        return AssociateOnReference()


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
        with Result.build() as result:
            result.value = await self._get_driver().fetch(self._query.limit(1)).one()

        return result


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
        with Result.build() as result:
            result.value = await self._get_driver().fetch(self._query).get()

        return result
