import sys
from dataclasses import dataclass
from inspect import get_annotations
from typing import (
    Callable,
    overload,
    Type,
    TypeVar,
    Any,
    Generator,
    Annotated,
    get_origin,
    get_args,
)
from tramp.annotations import Annotation
from tramp.optionals import Optional

import ommi.query_ast as query_ast
import ommi
from ommi.drivers.database_results import async_result, AsyncResultWrapper
from ommi.models.field_metadata import FieldMetadata, FieldType, StoreAs, create_metadata_type, AggregateMetadata, Key
from ommi.models.metadata import OmmiMetadata
from ommi.contextual_method import contextual_method
import ommi.models.collections

import ommi.drivers.delete_actions as delete_actions
import ommi.drivers.fetch_actions as fetch_actions
import ommi.models.query_fields
from ommi.models.queryable_descriptors import QueryableFieldDescriptor
from ommi.models.references import LazyReferenceBuilder
from ommi.utils.get_first import first

try:
    from typing import Self
except ImportError:
    Self = Any

T = TypeVar("T", bound=Type)

DRIVER_DUNDER_NAME = "__ommi_driver__"
MODEL_NAME_DUNDER_NAME = "__ommi_model_name__"
MODEL_NAME_CLASS_PARAM = "name"
METADATA_DUNDER_NAME = "__ommi_metadata__"


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
    __ommi_metadata__: OmmiMetadata

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

    @contextual_method
    def delete(
        self, driver: "drivers.DatabaseDriver | None" = None
    ) -> "delete_actions.DeleteAction":
        driver = self.get_driver(driver)
        pk_name = self.get_primary_key_field().get("field_name")
        return driver.find(getattr(type(self), pk_name) == getattr(self, pk_name)).delete()

    @delete.classmethod
    def delete(
        cls, *items: "OmmiModel", driver: "drivers.DatabaseDriver | None" = None
    ) -> AsyncResultWrapper[bool]:
        driver = cls.get_driver(driver)
        query = query_ast.search()
        for item in items:
            pk_name = item.get_primary_key_field().get("field_name")
            query = query.Or(getattr(cls, pk_name) == getattr(item, pk_name))

        return driver.find(query).delete

    @classmethod
    def count(
        cls,
        *predicates: "ASTGroupNode | DatabaseModel | bool",
        columns: Any | None = None,
        driver: "drivers.DatabaseDriver | None" = None,
    ) -> AsyncResultWrapper[int]:
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

    @async_result
    async def reload(
        self, driver: "drivers.DatabaseDriver | None" = None
    ) -> Self:
        pk_name = self.get_primary_key_field().get("field_name")
        pk_reference = getattr(type(self), pk_name)

        result = await (
            self.get_driver(driver)
            .find(query_ast.search(pk_reference == getattr(self, pk_name)))
            .fetch
            .one()
        )
        for name in self.__ommi_metadata__.fields.keys():
            setattr(self, name, getattr(result, name))

        return self

    @async_result
    async def save(
        self, driver: "drivers.DatabaseDriver | None" = None
    ) -> bool:
        pk_name = self.get_primary_key_field().get("field_name")
        driver = self.get_driver(driver)
        await (
            driver
            .find(getattr(type(self), pk_name) == getattr(self, pk_name))
            .set(
                **{
                    name: getattr(self, name)
                    for name in self.__ommi_metadata__.fields.keys()
                    if name != pk_name
                }
            )
        )
        return True

    @classmethod
    def get_primary_key_field(cls) -> FieldMetadata:
        fields = cls.__ommi_metadata__.fields
        if not fields:
            raise Exception(f"No fields defined on {cls}")

        def find_field_where(predicate):
            return first(f for f in fields.values() if predicate(f))

        if field := find_field_where(lambda f: f.matches(Key)):
            return field

        if field := find_field_where(lambda f: f.get("store_as") in {"id", "_id"}):
            return field

        if field := find_field_where(lambda f: issubclass(f.get("field_type"), int)):
            return field

        return first(fields.values())

    @classmethod
    def _build_column_predicates(
        cls, columns: dict[str, Any]
    ) -> "Generator[query_ast.ASTComparisonNode | bool, None, None]":
        if not columns:
            return

        for name, value in columns.items():
            if name not in cls.__ommi_metadata__.fields:
                raise ValueError(f"Invalid column {name!r} for model {cls.__name__}")

            yield getattr(cls, name) == value


@overload
def ommi_model(
    cls: None = None,
    *,
    collection: "ommi.model_collections.ModelCollection | None" = None,
) -> Callable[[T], T | Type[OmmiModel]]: ...


@overload
def ommi_model(cls: T) -> T | Type[OmmiModel]: ...


def ommi_model(
    cls: T | None = None, /, **kwargs
) -> T | Type[OmmiModel] | Callable[[T], T | Type[OmmiModel]]:
    def wrap_model(c: T) -> T | Type[OmmiModel]:
        model = _create_model(c, **kwargs)
        _register_model(
            model,
            (
                Optional.Some(kwargs["collection"])
                if "collection" in kwargs
                else Optional.Nothing
            ),
        )
        return model

    return wrap_model if cls is None else wrap_model(cls)


def _create_model(c: T, **kwargs) -> T | Type[OmmiModel]:
    metadata_factory = (
        c.__ommi_metadata__.clone if hasattr(c, METADATA_DUNDER_NAME) else OmmiMetadata
    )

    annotations = {
        name: Annotation(hint, Optional.Some(vars(sys.modules[c.__module__])))
        for name, hint in get_annotations(c).items()
    }
    fields = _get_fields(annotations, vars(sys.modules[c.__module__]))
    query_fields = _get_query_fields(annotations)

    def init(self, *args, **kwargs):
        unset_query_fields = {
            name: None
            for name in query_fields
            if name not in kwargs
        }
        super(model_type, self).__init__(*args, **kwargs | unset_query_fields)

        for name, annotation in query_fields.items():
            if name in unset_query_fields:
                setattr(self, name, annotation.origin.create(self, annotation.args))

    model_type = type.__new__(
        type(c),
        f"OmmiModel_{c.__name__}",
        (c, OmmiModel),
        {
            name: QueryableFieldDescriptor(
                getattr(c, name, None), fields[name]
            )
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
            )
        },
    )
    getattr(model_type, METADATA_DUNDER_NAME).references._model = model_type
    return model_type


def _register_model(
    model: Type[OmmiModel], collection: "Optional[ommi.models.collections.ModelCollection]"
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


def _get_fields(fields: dict[str, Annotation], namespace: dict[str, Any]) -> dict[str, FieldMetadata]:
    some_namespace = Optional.Some(namespace)
    ommi_fields = {}
    for name, annotation in fields.items():
        metadata = AggregateMetadata()

        if annotation.origin == Annotated:
            for arg in annotation.args:
                match arg:
                    case FieldMetadata():
                        metadata |= arg

        if not issubclass(annotation.type, ommi.models.query_fields.LazyQueryField):
            ommi_fields[name] = metadata | FieldType(annotation.type)
            if not ommi_fields[name].matches(StoreAs):
                ommi_fields[name] |= StoreAs(name)

            ommi_fields[name] |= create_metadata_type(
                "FieldMetadata", field_name=name, field_type=annotation.type
            )()

    return ommi_fields


def _get_query_fields(fields: dict[str, Annotation]) -> dict[str, Annotation]:
    return {
        name: annotation
        for name, annotation in fields.items()
        if annotation.is_generic() and issubclass(annotation.type, ommi.models.query_fields.LazyQueryField)
    }
