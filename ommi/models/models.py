from typing import (
    Callable,
    overload,
    Type,
    TypeVar,
    Any,
    Generator,
)

import ommi.query_ast as query_ast
from ommi.drivers.database_results import async_result, AsyncResultWrapper
from ommi.models.field_metadata import FieldMetadata
from ommi.models.metadata import OmmiMetadata
from ommi.contextual_method import contextual_method
import ommi.models.collections

import ommi.drivers.delete_actions as delete_actions
import ommi.drivers.fetch_actions as fetch_actions

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
        return driver or active_driver.get(None)

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
        query = query_ast.when()
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
            .find(query_ast.when(pk_reference == getattr(self, pk_name)))
            .fetch
            .first()
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
                Result.Value(kwargs["collection"])
                if "collection" in kwargs
                else Result.Nothing
            ),
        )
        return model

    return wrap_model if cls is None else wrap_model(cls)


def _create_model(c: T, **kwargs) -> T | Type[OmmiModel]:
    metadata_factory = (
        c.__ommi_metadata__.clone if hasattr(c, METADATA_DUNDER_NAME) else OmmiMetadata
    )

    fields = _get_fields(get_annotations(c))
    model_type = type.__new__(
        type(c),
        f"OmmiModel_{c.__name__}",
        (c, OmmiModel),
        {
            name: QueryableFieldDescriptor(
                getattr(c, name, None), fields[name]
            )
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
                references=LazyReferenceBuilder(fields, c, sys.modules[c.__module__]),
            )
        },
    )
    getattr(model_type, METADATA_DUNDER_NAME).references._model = model_type
    return model_type


def _register_model(
    model: Type[OmmiModel], collection: "Result[ommi.models.collections.ModelCollection]"
):
    get_collection(collection, model).add(model)


def get_collection(
    collection: "Result[ommi.models.collections.ModelCollection]",
    model: Type[OmmiModel] | None = None,
) -> "ommi.models.collections.ModelCollection":
    return collection.value_or(
        getattr(model, METADATA_DUNDER_NAME).collection
        if model
        else ommi.models.collections.get_global_collection()
    )


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
                field_type = Annotated.__class_getitem__(
                    field_type, *_annotations
                )  # Hack to support 3.10

        else:
            field_type = hint

        ommi_fields[name] |= FieldType(field_type)
        if not ommi_fields[name].matches(StoreAs):
            ommi_fields[name] |= StoreAs(name)

        ommi_fields[name] |= create_metadata_type(
            "FieldMetadata", field_name=name, field_type=field_type
        )()

    return ommi_fields
import sys
from inspect import get_annotations
from typing import (
    Callable,
    overload,
    Type,
    TypeVar,
    Any,
    Generator,
    get_origin,
    Annotated,
    get_args,
)
from tramp.optionals import Optional

import ommi.query_ast as query_ast
from ommi.drivers.database_results import async_result, AsyncResultWrapper
from ommi.models.field_metadata import (
    FieldMetadata,
    AggregateMetadata,
    FieldType,
    StoreAs,
    create_metadata_type,
    Key,
)
from ommi.models.metadata import OmmiMetadata
from ommi.models.queryable_descriptors import QueryableFieldDescriptor
from ommi.models.references import LazyReferenceBuilder
from ommi.utils.get_first import first
from ommi.contextual_method import contextual_method
from ommi.driver_context import active_driver
import ommi.models.collections

import ommi.drivers.delete_actions as delete_actions
import ommi.drivers.fetch_actions as fetch_actions

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
        return driver or active_driver.get(None)

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
        query = query_ast.when()
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
            .find(query_ast.when(pk_reference == getattr(self, pk_name)))
            .fetch
            .first()
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
                Optional.Value(kwargs["collection"])
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

    fields = _get_fields(get_annotations(c))
    model_type = type.__new__(
        type(c),
        f"OmmiModel_{c.__name__}",
        (c, OmmiModel),
        {
            name: QueryableFieldDescriptor(
                getattr(c, name, None), fields[name]
            )
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
                field_type = Annotated.__class_getitem__(
                    field_type, *_annotations
                )  # Hack to support 3.10

        else:
            field_type = hint

        ommi_fields[name] |= FieldType(field_type)
        if not ommi_fields[name].matches(StoreAs):
            ommi_fields[name] |= StoreAs(name)

        ommi_fields[name] |= create_metadata_type(
            "FieldMetadata", field_name=name, field_type=field_type
        )()

    return ommi_fields