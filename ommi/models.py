from dataclasses import dataclass, field as dc_field
from inspect import get_annotations
from typing import Callable, overload, Type, TypeVar, Any, Generator, get_origin, Annotated, get_args, Awaitable
from tramp.results import Result

import ommi.drivers as drivers
import ommi.query_ast as query_ast
from ommi.field_metadata import FieldMetadata, AggregateMetadata, FieldType, StoreAs, create_metadata_type
from ommi.statuses import DatabaseStatus
from ommi.contextual_method import contextual_method
from ommi.driver_context import active_driver
import ommi.model_collections


T = TypeVar("T", bound=Type)

DRIVER_DUNDER_NAME = "__ommi_driver__"
MODEL_NAME_DUNDER_NAME = "__ommi_model_name__"
MODEL_NAME_CLASS_PARAM = "name"
METADATA_DUNDER_NAME = "__ommi_metadata__"


_global_collection = None


def get_global_collection() -> "ommi.model_collections.ModelCollection":
    global _global_collection
    if not _global_collection:
        _global_collection = ommi.model_collections.ModelCollection()

    return _global_collection


class QueryableFieldDescriptor:
    def __init__(self, name, field):
        self.field = field
        self.name = name

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
    collection: "ommi.model_collections.ModelCollection" = dc_field(
        default_factory=get_global_collection
    )

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

    @contextual_method
    def get_driver(
        self, driver: "drivers.DatabaseDrivers | None" = None
    ) -> "drivers.DatabaseDriver | None":
        return driver or type(self).get_driver()

    @get_driver.classmethod
    def get_driver(cls, driver: "drivers.DatabaseDrivers | None" = None) -> "drivers.DatabaseDriver | None":
        return driver or active_driver.get(None)

    def add(self) -> "drivers.DatabaseAction[DatabaseStatus[OmmiModel]] | Awaitable[DatabaseStatus[OmmiModel]]":
        return self.get_driver().add(self)

    @contextual_method
    def delete(
        self, driver: "drivers.DatabaseDriver | None" = None
    ) -> "drivers.DatabaseAction[DatabaseStatus[drivers.DatabaseDriver]] | Awaitable[DatabaseStatus[drivers.DatabaseDriver]]":
        return self.get_driver(driver).delete(self)

    @delete.classmethod
    def delete(
        cls, *items: "OmmiModel", driver: "drivers.DatabaseDriver | None" = None
    ) -> "drivers.DatabaseAction[DatabaseStatus[drivers.DatabaseDriver]] | Awaitable[DatabaseStatus[drivers.DatabaseDriver]]":
        return cls.get_driver(driver).delete(*items)

    @classmethod
    def count(
        cls,
        *predicates: "ASTGroupNode | DatabaseModel | bool",
        columns: Any | None = None,
        driver: "drivers.DatabaseDriver | None" = None,
    ) -> "drivers.DatabaseAction[DatabaseStatus[int]] | Awaitable[DatabaseStatus[int]]":
        return cls.get_driver(driver).count(
            cls, *predicates, *cls._build_column_predicates(columns)
        )

    @classmethod
    def fetch(
        cls,
        *predicates: "ASTGroupNode | DatabaseModel | bool",
        driver: "drivers.DatabaseDriver | None" = None,
        **columns: Any,
    ) -> "drivers.DatabaseAction[DatabaseStatus[list[OmmiModel]]] | Awaitable[DatabaseStatus[list[OmmiModel]]]":
        return cls.get_driver(driver).fetch(cls, *predicates, *cls._build_column_predicates(columns))

    def sync(
        self, driver: "drivers.DatabaseDriver | None" = None
    ) -> "drivers.DatabaseAction[DatabaseStatus[drivers.DatabaseDriver]] | Awaitable[DatabaseStatus[drivers.DatabaseDriver]]":
        return self.get_driver(driver).update(self)

    @classmethod
    def _build_column_predicates(
        cls, columns: dict[str, Any]
    ) -> "Generator[query_ast.ASTComparisonNode | bool, None, None]":
        if not columns:
            return

        for name, value in columns.items():
            if name not in cls.__fields__:
                raise ValueError(f"Invalid column {name!r} for model {cls.__name__}")

            yield getattr(cls, name) == value


@overload
def ommi_model(
    cls: None = None, *, collection: "ommi.model_collections.ModelCollection | None" = None
) -> Callable[[T], T | Type[OmmiModel]]:
    ...


@overload
def ommi_model(cls: T) -> T | Type[OmmiModel]:
    ...


def ommi_model(
    cls: T | None = None, /, **kwargs
) -> T | Type[OmmiModel] | Callable[[T], T | Type[OmmiModel]]:
    def wrap_model(c: T) -> T | Type[OmmiModel]:
        model = _create_model(c, **kwargs)
        _register_model(model, Result.Value(kwargs["collection"]) if "collection" in kwargs else Result.Nothing)
        return model

    return wrap_model if cls is None else wrap_model(cls)


def _create_model(c: T, **kwargs) -> T | Type[OmmiModel]:
    metadata_factory = (
        c.__ommi_metadata__.clone
        if hasattr(c, METADATA_DUNDER_NAME)
        else OmmiMetadata
    )

    fields = _get_fields(get_annotations(c))
    return type.__new__(
        type(c),
        f"OmmiModel_{c.__name__}",
        (c, OmmiModel),
        {
            name: QueryableFieldDescriptor(fields[name].get("store_as"), getattr(c, name, None))
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
                ),
                fields=fields,
            )
        },
    )


def _register_model(model: Type[OmmiModel], collection: "Result[ommi.model_collections.ModelCollection]"):
    get_collection(collection, model).add(model)


def get_collection(
        collection: "Result[ommi.model_collections.ModelCollection]",
        model: Type[OmmiModel] | None = None,
) -> "ommi.model_collections.ModelCollection":
    return collection.value_or(getattr(model, METADATA_DUNDER_NAME).collection if model else get_global_collection())


def _get_fields(fields: dict[str, Any]) -> dict[str, FieldMetadata]:
    ommi_fields = {}
    for name, hint in fields.items():
        ommi_fields[name] = AggregateMetadata()
        if get_origin(hint) == Annotated:
            field_type, *annotations = get_args(hint)
            _annotations = []
            for annotation in annotations:
                match annotation:
                    case FieldMetadata():
                        ommi_fields[name] |= annotation

                    case _:
                        _annotations.append(annotation)

            if _annotations:
                field_type = Annotated.__class_getitem__(field_type, *_annotations)  # Hack to support 3.10

        else:
            field_type = hint

        ommi_fields[name] |= FieldType(field_type)
        if not ommi_fields[name].matches(StoreAs):
            ommi_fields[name] |= StoreAs(name)

        ommi_fields[name] |= create_metadata_type("FieldMetadata", field_name=name, field_type=field_type)()

    return ommi_fields
