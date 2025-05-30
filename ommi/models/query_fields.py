"""
Lazy Evaluation of Query Fields for Ommi Models

This module implements lazy loading of query fields from the database, using
different strategies for associating models. It supports various approaches for
deferring query execution until needed, thus managing model relationships and
avoiding issues like circular imports efficiently.
"""


from abc import ABC, abstractmethod
from functools import partial
from typing import Annotated, Callable, get_args, get_origin, Protocol, TypeVar, Any, Type

from tramp.annotations import ForwardRef

import ommi
import ommi.drivers.drivers
import ommi.query_ast
from ommi.database.results import DBResult

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


class LazyQueryField[T](ABC):
    def __init__(
        self,
        query_factory: "Callable[[], ommi.query_ast.ASTGroupNode]",
        driver: "ommi.drivers.drivers.AbstractDatabaseDriver | None" = None,
    ):
        self._query_factory = query_factory
        self._driver = driver

        self._cache = DBResult.DBFailure(ValueError("Not cached yet"))

    @property
    def _query(self) -> "ommi.query_ast.ASTGroupNode"   :
        return self._query_factory()

    def __await__(self):
        return self._value.__await__()

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
    async def or_use[D](self, default: D) -> T | D:
        ...

    async def refresh(self) -> None:
        try:
            result = DBResult.DBSuccess(await self._fetch())
        except Exception as e:
            result = DBResult.DBFailure(e)

        self._cache = result

    async def refresh_if_needed(self) -> None:
        match self._cache:
            case DBResult.DBFailure():
                await self.refresh()

    @abstractmethod
    async def get_result(self) -> DBResult[T]:
        ...

    @property
    @abstractmethod
    async def _value(self):
        ...

    @abstractmethod
    async def _fetch(self):
        ...

    async def _get_result(self):
        match self._cache:
            case DBResult.DBSuccess() as result:
                return result

            case DBResult.DBFailure():
                self._cache = await self._fetch()
                return self._cache

            case _:
                raise ValueError("Invalid cache state")

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


class LazyLoadTheRelated[T](LazyQueryField):
    async def or_use[D](self, default: D) -> T | D:
        return (await self.get_result()).result_or(default)

    async def get_result(self) -> DBResult[T]:
        return await self._get_result()

    @property
    async def _value(self) -> T:
        return (await self.get_result()).result

    async def _fetch(self):
        try:
            result = DBResult.DBSuccess(await self._get_driver().fetch(self._query.limit(1)).one())
        except Exception as e:
            result = DBResult.DBFailure(e)

        return result


class LazyLoadEveryRelated[T](LazyQueryField):
    async def or_use[D](self, default: list[D]) -> list[T] | list[D]:
        return (await self.get_result()).result_or(default)

    async def get_result(self) -> DBResult[list[T]]:
        return await self._get_result()

    @property
    async def _value(self) -> list[T]:
        return (await self.get_result()).result

    async def _fetch(self):
        try:
            result = DBResult.DBSuccess(await self._get_driver().fetch(self._query).get())
        except Exception as e:
            result = DBResult.DBFailure(e)

        return result
