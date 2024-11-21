"""
This module defines functionality for creating and managing database models
using the Ommi framework. It includes the base `OmmiModel` class, which
provides methods for database operations, as well as a decorator for defining
models with Ommi metadata and query fields. It also includes helper functions
and classes for managing model metadata, query fields, and database drivers.
"""


import sys
from dataclasses import dataclass
from typing import (
    Annotated,
    Any,
    Callable,
    Generator,
    get_args,
    get_origin,
    overload,
    Type,
    TypeVar,
)

import tramp.annotations
from tramp.optionals import Optional

import ommi.query_ast as query_ast
import ommi
from ommi.models.field_metadata import (
    AggregateMetadata,
    create_metadata_type,
    FieldMetadata,
    FieldType,
    Key,
    StoreAs,
)
from ommi.models.metadata import OmmiMetadata
from ommi.contextual_method import contextual_method
import ommi.models.collections

import ommi.models.query_fields
from ommi.models.queryable_descriptors import QueryableFieldDescriptor
from ommi.models.references import LazyReferenceBuilder
from ommi.utils.get_first import first

try:
    from typing import Self
except ImportError:
    Self = Any

DRIVER_DUNDER_NAME = "__ommi_driver__"
MODEL_NAME_DUNDER_NAME = "__ommi_model_name__"
MODEL_NAME_CLASS_PARAM = "name"
METADATA_DUNDER_NAME = "__ommi__"


def _get_value(
    class_params: dict[str, Any],
    param_name: str,
    cls: Type[Any],
    dunder_name: str,
    default: Any,
) -> Any:
    return class_params.pop(param_name, getattr(cls, dunder_name, default))


@dataclass
class QueryFieldMetadata:
    name: str
    type: "Type[ommi.models.query_fields.LazyQueryField]"
    args: tuple[Any, ...]


class OmmiModel:
    __ommi__: OmmiMetadata

    @contextual_method
    def get_driver(
        self, driver: "drivers.DatabaseDrivers | None" = None
    ) -> "drivers.DatabaseDriver | None":
        return driver or type(self).get_driver()

    @get_driver.classmethod
    def get_driver(
        cls, driver: "drivers.DatabaseDrivers | None" = None
    ) -> "drivers.DatabaseDriver | None":
        return driver or ommi.active_driver.get(None)

    def delete(
        self, driver: "drivers.DatabaseDriver | None" = None
    ) -> "delete_actions.DeleteAction":
        return (
            self.get_driver(driver)
            .find(
                query_ast.when(
                    *(
                        getattr(type(self), pk.get("field_name"))
                        == getattr(self, pk.get("field_name"))
                        for pk in self.get_primary_key_fields()
                    )
                )
            )
            .delete()
        )

    @classmethod
    def count(
        cls,
        *predicates: "ASTGroupNode | DatabaseModel | bool",
        columns: Any | None = None,
        driver: "drivers.DatabaseDriver | None" = None,
    ) -> "AsyncResultWrapper[int]":
        driver = cls.get_driver(driver)
        if not predicates and not columns:
            predicates = (cls,)

        return driver.find(*predicates, *cls._build_column_predicates(columns)).count()

    @classmethod
    def fetch(
        cls,
        *predicates: "ASTGroupNode | DatabaseModel | bool",
        driver: "drivers.DatabaseDriver | None" = None,
        **columns: Any,
    ) -> "fetch_actions.FetchAction[OmmiModel]":
        driver = cls.get_driver(driver)
        return driver.find(*predicates, *cls._build_column_predicates(columns)).fetch

    async def reload(self, driver: "drivers.DatabaseDriver | None" = None) -> Self:
        result = await (
            self.get_driver(driver)
            .find(
                query_ast.when(
                    *(
                        getattr(type(self), pk.get("field_name"))
                        == getattr(self, pk.get("field_name"))
                        for pk in self.get_primary_key_fields()
                    )
                )
            )
            .fetch.one()
        )
        for name in self.__ommi__.fields.keys():
            setattr(self, name, getattr(result, name))

        return self

    async def save(self, driver: "drivers.DatabaseDriver | None" = None) -> bool:
        pks = self.get_primary_key_fields()
        driver = self.get_driver(driver)
        await driver.find(
            query_ast.when(
                *(
                    getattr(type(self), pk.get("field_name"))
                    == getattr(self, pk.get("field_name"))
                    for pk in pks
                )
            )
        ).set(
            **{
                field.get("field_name"): getattr(self, field.get("field_name"))
                for field in self.__ommi__.fields.values()
                if field not in pks
                and getattr(self, field.get("field_name")) is not None
            }
        )
        return True

    @classmethod
    def get_primary_key_fields(cls) -> tuple[FieldMetadata, ...]:
        fields = cls.__ommi__.fields
        if not fields:
            raise Exception(f"No fields defined on {cls}")

        def find_fields_where(predicate):
            return tuple(f for f in fields.values() if predicate(f))

        def find_field_where(predicate):
            return first(find_fields_where(predicate))

        if matches := find_fields_where(lambda f: f.matches(Key)):
            return matches

        if field := find_field_where(lambda f: f.get("store_as") in {"id", "_id"}):
            return (field,)

        if field := find_field_where(lambda f: issubclass(f.get("field_type"), int)):
            return (field,)

        return (first(fields.values()),)

    @classmethod
    def _build_column_predicates(
        cls, columns: dict[str, Any]
    ) -> "Generator[query_ast.ASTComparisonNode | bool, None, None]":
        if not columns:
            return

        for name, value in columns.items():
            if name not in cls.__ommi__.fields:
                raise ValueError(f"Invalid column {name!r} for model {cls.__name__}")

            yield getattr(cls, name) == value


@overload
def ommi_model[T](
    *, collection: "ommi.models.collections.ModelCollection",
) -> Callable[[Type[T]], Type[T] | Type[OmmiModel]]:
    ...


@overload
def ommi_model[T](model_type: Type[T]) -> Type[T] | Type[OmmiModel]:
    ...


def ommi_model[T](
    model_type: Type[T] | None = None,
    *,
    collection: "ommi.models.collections.ModelCollection | None" = None
) -> Type[T] | Callable[[Type[T]], Type[T]]:
    def wrap_model(c: Type[T]) -> Type[T]:
        model = _create_model(c, collection=collection)
        _register_model(
            model,
            Optional.Some(collection) if collection else Optional.Nothing(),
        )
        return model

    return wrap_model if model_type is None else wrap_model(model_type)


def _create_model(c, **kwargs) -> Type[OmmiModel]:
    metadata_factory = (
        c.__ommi__.clone if hasattr(c, METADATA_DUNDER_NAME) else OmmiMetadata
    )

    def init(self, *init_args, **init_kwargs):
        annotations = tramp.annotations.get_annotations(c, tramp.annotations.Format.FORWARDREF)
        query_fields = _get_query_fields(annotations)

        unset_query_fields = {name: None for name in query_fields if name not in init_kwargs}
        super(model_type, self).__init__(*init_args, **init_kwargs | unset_query_fields)

        for name, annotation in query_fields.items():
            if name in unset_query_fields:
                setattr(self, name, get_origin(annotation).create(self, get_args(annotation)))

    fields = _get_fields(
        tramp.annotations.get_annotations(c, tramp.annotations.Format.FORWARDREF)
    )

    model_type = type.__new__(
        type(c),
        f"OmmiModel_{c.__name__}",
        (c, OmmiModel),
        {
            name: QueryableFieldDescriptor(getattr(c, name, None), fields[name])
            for name in fields
        }
        | {
            "__init__": init,
            METADATA_DUNDER_NAME: metadata_factory(
                model_name=_get_value(
                    kwargs,
                    MODEL_NAME_CLASS_PARAM,
                    c,
                    MODEL_NAME_DUNDER_NAME,
                    c.__name__,
                ),
                fields=fields,
                references=LazyReferenceBuilder(fields, c, sys.modules[c.__module__]),
            ),
        },
    )
    getattr(model_type, METADATA_DUNDER_NAME).references._model = model_type
    return model_type


def _register_model(
    model: Type[OmmiModel],
    collection: "Optional[ommi.models.collections.ModelCollection]",
):
    get_collection(collection, model).add(model)


def get_collection(
    collection: "Optional[ommi.models.collections.ModelCollection]",
    model: Type[OmmiModel] | None = None,
) -> "ommi.models.collections.ModelCollection":
    return collection.value_or(
        getattr(model, METADATA_DUNDER_NAME).collection
        if model
        else ommi.models.collections.get_global_collection()
    )


def _get_fields(fields: dict[str, Any]) -> dict[str, FieldMetadata]:
    ommi_fields = {}
    for name, annotation in fields.items():
        metadata = AggregateMetadata()

        if isinstance(annotation, tramp.annotations.ForwardRef):
            annotation = annotation.evaluate()

        origin = get_origin(annotation)
        annotation_type = annotation
        if origin == Annotated:
            annotation_type, *args = get_args(annotation)
            for arg in args:
                match arg:
                    case FieldMetadata():
                        metadata |= arg

        if not isinstance(origin, type) or not issubclass(origin, ommi.models.query_fields.LazyQueryField):
            ommi_fields[name] = metadata | FieldType(annotation_type)
            if not ommi_fields[name].matches(StoreAs):
                ommi_fields[name] |= StoreAs(name)

            ommi_fields[name] |= create_metadata_type(
                "FieldMetadata", field_name=name, field_type=annotation_type
            )()

    return ommi_fields


def _get_query_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        name: annotation
        for name, annotation in fields.items()
        if _is_lazy_query_field(annotation)
    }

def _is_lazy_query_field(annotation: Any) -> bool:
    origin = get_origin(annotation)
    return (
        isinstance(origin, type)
        and issubclass(origin, ommi.models.query_fields.LazyQueryField)
    )
