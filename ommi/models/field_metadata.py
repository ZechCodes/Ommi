"""
Field Metadata Types for Setting Properties of Model Fields

This module defines the types that are used to store metadata about model fields. The metadata is intended to be stored
as a typing.Annotated type annotation. Helper methods are provided for creating custom field metadata types.

Field metadata is used throughout Ommi to provide additional information about model fields to the ORM system. This
includes information about:

- Primary keys and auto-incrementing fields
- Foreign key references and relationships
- Custom field types and storage names

Example:
    ```python
    from typing import Annotated
    from ommi import ommi_model, Key, ReferenceTo
    from dataclasses import dataclass

    @ommi_model
    @dataclass
    class User:
        name: str
        id: Annotated[int, Key] = None  # Primary key field
        
    @ommi_model
    @dataclass
    class Post:
        title: str
        content: str
        author_id: Annotated[int, ReferenceTo(User.id)]  # Foreign key reference
        id: Annotated[int, Key] = None
    ```
"""


from collections import ChainMap
from typing import Any, TypeVar, Type, cast, MutableMapping
from tramp.optionals import Optional, Some, Nothing
from itertools import zip_longest


T = TypeVar("T")


class FieldMetadata:
    """
    Base type for all field metadata types.
    
    Field metadata instances carry information about how a field on a
    model should be handled by Ommi and the database driver. The union 
    operator (`|`) can be used to combine multiple metadata types.
    
    This provides a flexible way to annotate model fields with multiple 
    behaviors or attributes without complex inheritance hierarchies.
    
    Attributes:
        metadata: A mapping containing the metadata key-value pairs
    """

    metadata: MutableMapping[str, Any]

    def __contains__(self, key: str) -> bool:
        return key in self.metadata

    def __eq__(self, other: "FieldMetadata | Any") -> bool:
        if not isinstance(other, FieldMetadata):
            raise NotImplementedError

        return self.metadata == other.metadata

    def __hash__(self):
        return hash(tuple(self.metadata.items()))

    def __or__(self, other: "FieldMetadata") -> "FieldMetadata":
        if not isinstance(other, FieldMetadata):
            raise NotImplementedError

        return AggregateMetadata(self, other)

    def __repr__(self):
        return f"{type(self).__name__}({', '.join(f'{k}={v}' for k, v in self.metadata.items())})"

    def get(self, key: str, default: T = None) -> T:
        """
        Retrieve a value from the metadata.
        
        Args:
            key: The metadata key to retrieve
            default: Value to return if the key doesn't exist
            
        Returns:
            The value associated with the key, or the default if not found
        """
        return self.metadata.get(key, default)

    def matches(self, check_for: "FieldMetadata | Type[FieldMetadata]") -> bool:
        """
        Check if this metadata matches a specific type or instance.
        
        Args:
            check_for: A FieldMetadata instance or class to check against
            
        Returns:
            True if this metadata matches the check_for criteria, False otherwise
        """
        match check_for:
            case type() as metadata_type if issubclass(metadata_type, FieldMetadata):
                return isinstance(self, metadata_type)

            case FieldMetadata() as metadata:
                return self == metadata

            case _:
                return False


class AggregateMetadata(FieldMetadata):
    """
    Combines multiple field metadata instances into one.
    
    This allows a field to have multiple kinds of metadata applied by 
    aggregating them into a single object. The union operator (`|`) is 
    typically used to create these aggregates.
    
    Example:
        ```python
        # Combine Key and Auto metadata
        field_metadata = Key | Auto
        ```
    
    Attributes:
        metadata: A ChainMap containing all aggregated metadata dictionaries
        _fields: The list of original metadata instances that were aggregated
    """

    metadata: ChainMap[str, Any]

    def __init__(self, *fields: "FieldMetadata") -> None:
        """
        Args:
            *fields: The metadata instances to aggregate
        """
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

    def __hash__(self):
        return hash(tuple(self.metadata.items()))

    def _add_field(self, field: "FieldMetadata") -> None:
        """Adds field metadata to the aggregate metadata. This is done in a non-destructive way so as to prevent changes
        made to the aggregate metadata mapping from propagating to the the aggregated field metadata instances.
        """
        self._fields.append(field)
        self.metadata.maps.append(field.metadata)

    def matches(self, metadata: "FieldMetadata | Type[FieldMetadata]") -> bool:
        """
        Check if any of the aggregated metadata instances match a type or instance.
        
        Args:
            metadata: A FieldMetadata instance or class to check against
            
        Returns:
            True if any of the aggregated metadata match, False otherwise
        """
        return any(f.matches(metadata) for f in self._fields)


class MetadataFlag(FieldMetadata):
    """
    A field metadata type that acts as a flag.
    
    Flags indicate that a field has a certain property. They contain
    a single boolean True value and should be treated as singletons
    for identity checks.
    
    Examples include the `Key` flag for primary keys and the `Auto` flag
    for auto-incrementing fields.
    """


class FieldType(FieldMetadata):
    """
    Field metadata type for setting the field's data type.
    
    This metadata specifies how the field should be stored in the database,
    which may differ from its Python type.
    
    Attributes:
        field_type: The database type for the field
    """

    def __init__(self, field_type: Any):
        """
        Args:
            field_type: The database type specification for the field
        """
        self.metadata = {"field_type": field_type}


class ReferenceTo(FieldMetadata):
    """
    Field metadata type for setting the model field that this field references.
    
    This is used to define foreign key relationships between models.
    
    Example:
        ```python
        @ommi_model
        @dataclass
        class Post:
            # Reference to User.id field
            author_id: Annotated[int, ReferenceTo(User.id)] 
        ```
        
    Attributes:
        reference_to: The field or field reference being referenced
    """

    def __init__(self, reference_to: "query_ast.ASTReferenceNode | str | Any"):
        """
        Args:
            reference_to: The field being referenced, which can be:
                - A direct field reference (User.id)
                - A string path ("User.id")
                - An AST reference node
        """
        self.metadata = {"reference_to": reference_to}


class StoreAs(FieldMetadata):
    """
    Field metadata type for setting a custom storage name.
    
    This allows using a different field name in the database than in the model.
    
    Example:
        ```python
        @ommi_model
        @dataclass
        class User:
            # Will be stored as "user_name" in the database
            name: Annotated[str, StoreAs("user_name")]
        ```
        
    Attributes:
        store_as: The name to use in the database
    """

    def __init__(self, store_as: str):
        """
        Args:
            store_as: The name to use when storing the field in the database
        """
        self.metadata = {"store_as": store_as}


def create_metadata_type(
    name: str, metadata_type: "Optional[Type[FieldMetadata]]" = Nothing(), /, **kwargs
) -> Type[FieldMetadata]:
    """
    Helper function for creating a simple field metadata type.
    
    This creates a new metadata class with preloaded default values,
    useful for creating field types that don't need values set at creation.
    
    Args:
        name: The name for the new metadata type
        metadata_type: Optional base class for the new type
        **kwargs: Default metadata values to include in the type
        
    Returns:
        A new FieldMetadata subclass with the specified properties
    """
    return cast(
        Type[FieldMetadata],
        type(name, (metadata_type.value_or(FieldMetadata),), {"metadata": kwargs}),
    )


def create_metadata_flag(name: str) -> FieldMetadata:
    """
    Helper function for creating field metadata flag instances.
    
    These flags indicate that a field has a certain property and contain
    a single boolean True value. They should be treated as singletons.
    
    Args:
        name: The name for the flag
        
    Returns:
        A singleton instance of the created flag metadata
    """
    return create_metadata_type(name, Some(MetadataFlag), **{f"__flag_{name}": True})()


# Pre-defined metadata flags
Auto = create_metadata_flag("Auto")  # Indicates an auto-incrementing field
"""
Indicates an auto-incrementing field.

Example:
    ```python
    @ommi_model
    @dataclass
    class User:
        id: Annotated[int, Key | Auto]  # Auto-incrementing primary key
    ```
"""
Key = create_metadata_flag("Key")
"""
Indicates a primary key field.

Example:
    ```python
    @ommi_model
    @dataclass
    class User:
        id: Annotated[int, Key]  # Primary key field
    ```
"""
