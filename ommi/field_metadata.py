from collections import ChainMap
from typing import Any, TypeVar, Type, cast, MutableMapping
from tramp.results import Result, Value, Nothing
from itertools import zip_longest

T = TypeVar("T")


class FieldMetadata:
    """Base type for all field metadata types. Field metadata instances carry the information about how a field on a
    model should be handled by Ommi and the database driver. The union operator can be used on field metadata instances
    to aggregate them into a single metadata object."""

    metadata: MutableMapping[str, Any]

    def __contains__(self, key: str) -> bool:
        return key in self.metadata

    def __eq__(self, other: "FieldMetadata | Any") -> bool:
        if not isinstance(other, FieldMetadata):
            raise NotImplementedError

        return self.metadata == other.metadata

    def __or__(self, other: "FieldMetadata") -> "FieldMetadata":
        if not isinstance(other, FieldMetadata):
            raise NotImplementedError

        return AggregateMetadata(self, other)

    def __repr__(self):
        return f"{type(self).__name__}({', '.join(f'{k}={v}' for k, v in self.metadata.items())})"

    def get(self, key: str, default: T = None) -> T:
        return self.metadata.get(key, default)

    def matches(self, check_for: "FieldMetadata | Type[FieldMetadata]") -> bool:
        match check_for:
            case type() as metadata_type if issubclass(metadata_type, FieldMetadata):
                return isinstance(self, metadata_type)

            case FieldMetadata() as metadata:
                return self == metadata

            case _:
                return False


class AggregateMetadata(FieldMetadata):
    """Aggregates field metadata instances (usually using the union operator) so a field can have multiple kinds of
    metadata applied simply."""

    metadata: ChainMap[str, Any]

    def __init__(self, *fields: "FieldMetadata") -> None:
        self._fields = []
        self.metadata = ChainMap({})

        for field in fields:
            self._add_field(field)

    def __eq__(self, other: "AggregateMetadata | Any") -> bool:
        if not isinstance(other, AggregateMetadata):
            raise NotImplementedError

        return all(a == b for a, b in zip_longest(self._fields, other._fields))

    def __or__(self, other: "FieldMetadata") -> "FieldMetadata":
        if not isinstance(other, FieldMetadata):
            raise NotImplementedError

        self._add_field(other)
        return self

    def _add_field(self, field: "FieldMetadata") -> None:
        """Adds field metadata to the aggregate metadata. This is done in a non-destructive way so as to prevent changes
        made to the aggregate metadata mapping from propagating to the the aggregated field metadata instances."""
        self._fields.append(field)
        self.metadata.maps.append(field.metadata)

    def matches(self, metadata: "FieldMetadata | Type[FieldMetadata]") -> bool:
        return any(f.matches(metadata) for f in self._fields)


class MetadataFlag(FieldMetadata):
    def __eq__(self, other: "MetadataFlag | Any") -> bool:
        if not isinstance(other, MetadataFlag):
            raise NotImplementedError

        return self.metadata == other.metadata


class FieldType(FieldMetadata):
    """Field metadata type for setting the field's data type."""

    def __init__(self, field_type: Any):
        self.metadata = {"field_type": field_type}


class StoreAs(FieldMetadata):
    """Field metadata type for setting the name to use when passing the field to the database backend."""

    def __init__(self, store_as: str):
        self.metadata = {"store_as": store_as}


def create_metadata_type(
    name: str, metadata_type: "Result[Type[FieldMetadata]]" = Nothing(), /, **kwargs
) -> Type[FieldMetadata]:
    """Helper function for creating a simple field metadata type that has preloaded default values. Useful for creating
    field types that don't need values set at creation."""
    return cast(
        Type[FieldMetadata],
        type(name, (metadata_type.value_or(FieldMetadata),), {"metadata": kwargs}),
    )


def create_metadata_flag(name: str) -> FieldMetadata:
    """Helper function for creating field metadata flag instances. These flags are field metadata instances that contain
    a singular boolean True value to indicate that they're set. Flags should be treated as singletons for purposes of
    identity checks."""
    return create_metadata_type(name, Value(MetadataFlag), **{f"__flag_{name}": True})()


Auto = create_metadata_flag("Auto")
Key = create_metadata_flag("Key")
