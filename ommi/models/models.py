"""
Model Definition and Management for Ommi

This module provides a comprehensive framework for defining, managing, and interacting with database models in the Ommi ORM. It offers a powerful and flexible approach to working with database entities, combining the simplicity of Python classes with advanced ORM features.

Key Components:

**1. OmmiModel:**

- Base class for all Ommi model types
- Provides core functionality for database operations (e.g., save, delete, reload)
- Implements query methods for fetching and filtering data
- Supports lazy-loading of related models

**2. ommi_model Decorator:**

- Transforms regular Python classes into fully-featured Ommi models
- Automatically generates metadata and query fields
- Enables the use of type annotations for defining model structure

**3. Metadata Management:**

- OmmiMetadata class for storing and managing model-specific metadata
- FieldMetadata for detailed information about individual fields
- Support for custom field types and behaviors

**4. Query Fields and Lazy Loading:**

- LazyQueryField for deferred loading of related models
- Support for one-to-one, one-to-many, and many-to-many relationships
- Efficient querying of related data

**5. Database Driver Integration:**

- Abstract interface for database operations
- Support for multiple database backends
- Context-aware driver selection

**6. Advanced Querying Capabilities:**

- Expressive query syntax using Python operators
- Support for complex filters, sorting, and aggregations
- Asynchronous query execution

**7. Model Collections:**

- Management of model instances across the application
- Global and scoped collections for flexible data access

**8. Type Annotations and Metadata:**

- Extensive use of type hints for better IDE support and type checking
- Custom metadata types (e.g., Key, StoreAs) for fine-grained control over field behavior

**9. Utility Functions:**

- Helper methods for common tasks like metadata extraction and field type inference
- Support for dataclass integration and custom field descriptors

Example Usage:
    ```python
    from dataclasses import dataclass
    from typing import Annotated
    from ommi import ommi_model, Key, Lazy, ReferenceTo

    @ommi_model
    @dataclass
    class User:
        name: str
        age: int
        id: Annotated[int, Key] = None

    @ommi_model
    @dataclass
    class Post:
        title: str
        content: str
        author_id: Annotated[int, ReferenceTo(User.id)]
        author: Lazy[User]
        id: Annotated[int, Key] = None

    # Create and save a user
    user = User(name="Alice", age=30)
    await user.save()

    # Create a post with a reference to the user
    post = Post(title="My First Post", content="Hello, World!", author_id=user.id)
    await post.save()

    # Query users
    adult_users = await User.fetch(User.age >= 18).all()

    # Lazy-load related data
    post_author = await post.author
    print(f"Post '{post.title}' was written by {post_author.name}")

    # Complex querying
    recent_posts = await Post.fetch(
        (Post.author.age > 25) & (Post.title.contains("Python"))
    ).order_by(Post.id.desc()).limit(10).all()
    ```

This module forms the core of the Ommi ORM, providing a robust foundation for building database-driven
applications with clean, Pythonic code. It combines the simplicity of dataclasses (or your modeling
library of choice) with the power of advanced ORM features, making it suitable for both simple CRUD
 operations and complex data modeling scenarios.
"""

__all__ = ['OmmiModel', 'ommi_model', 'QueryFieldMetadata', '_get_fields', '_get_query_fields']

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
    """
    Metadata for a lazy-loaded query field.
    
    This stores information about a field that will be populated via
    a database query, such as a relationship field.
    
    Attributes:
        name: The name of the field
        type: The type of lazy query field (e.g., Lazy)
        args: Type arguments for the query field
    """
    name: str
    type: "Type[ommi.models.query_fields.LazyQueryField]"
    args: tuple[Any, ...]


class OmmiModel:
    """
    Base class for all Ommi models, applied dynamically by the @ommi_model decorator.

    When a class is decorated with @ommi_model, the following changes occur:

    **1. The class inherits from OmmiModel, gaining database operation methods like:**

       - fetch() - Query instances from the database
       - save() - Persist changes to the database 
       - delete() - Remove from the database
       - reload() - Refresh data from the database
       - count() - Count matching instances

    **2. Type annotations are processed to create queryable fields:**

       - Basic types (str, int, etc) become regular database columns
       - Annotated types can specify special behaviors like Keys or References
       - Forward references are supported for circular dependencies
       - Fields can be used on the class type to build queries (e.g. User.age >= 18)

    **3. Relationship fields are transformed into lazy-loading descriptors:**

       - Lazy[Model] for one-to-one relationships
       - LazyList[Model] for one-to-many relationships
       - Relationships are loaded from the database only when accessed
       - Results are cached after first access

    **4. Model metadata is created and stored in `__ommi__`:**

       - Field definitions and types
       - Foreign key references
       - Collection registration
       - Model name and configuration

    Attributes:
        __ommi__: Metadata about the model's fields, references and configuration

    Example: Basic Model Definition
        Define a simple User model with an id, name, and age.
        ```python
        @ommi_model
        @dataclass
        class User:
            id: Annotated[int, Key]
            name: str
            age: int
        ```

    Example: Relationships
        Define models with one-to-one and one-to-many relationships.
        ```python
        @ommi_model
        @dataclass
        class Post:
            id: Annotated[int, Key]
            title: str
            content: str
            author_id: Annotated[int, ReferenceTo(User.id)]
            author: Lazy[User]

        @ommi_model
        @dataclass
        class User:
            id: Annotated[int, Key]
            name: str
            posts: LazyList[Post]
        ```

    Example: Query Building
        Use class fields to construct complex queries.
        ```python
        adult_users = await User.fetch(User.age >= 18)
        recent_posts = await Post.fetch(when(Post.author.name == "Alice").And(Post.created_at > datetime(2023, 1, 1)))
        ```

    Example: CRUD Operations
        Perform create, read, update, and delete operations.
        ```python
        # Create
        new_user = User(name="Bob", age=30)
        await new_user.save()

        # Read
        user = await User.fetch(User.id == 1).one()

        # Update
        user.age = 31
        await user.save()

        # Delete
        await user.delete()
        ```

    Example: Lazy Loading
        ```python
        user = await User.fetch(User.id == 1).one()
        # Posts are not loaded yet
        posts = await user.posts
        # Now posts are loaded and cached
        ```
    """
    __ommi__: OmmiMetadata

    @contextual_method
    def get_driver(
        self, driver: "drivers.DatabaseDrivers | None" = None
    ) -> "drivers.DatabaseDriver | None":
        """
        Get the database driver for this model instance.
        
        This method can be called on model instances to get the appropriate
        database driver, using the provided driver or falling back to the
        model's default driver or the active driver.
        
        Args:
            driver: Optional specific driver to use
            
        Returns:
            The appropriate database driver, or None if no driver is available
        """
        return driver or type(self).get_driver()

    @get_driver.classmethod
    def get_driver(
        cls, driver: "drivers.DatabaseDrivers | None" = None
    ) -> "drivers.DatabaseDriver | None":
        """
        Get the database driver for this model class.
        
        This classmethod version can be called on the model class to get
        the appropriate database driver.
        
        Args:
            driver: Optional specific driver to use
            
        Returns:
            The appropriate database driver, or None if no driver is available
        """
        return driver or ommi.active_driver.get(None)

    def delete(
        self, driver: "drivers.DatabaseDriver | None" = None
    ) -> "delete_actions.DeleteAction":
        """
        Delete this model instance from the database.
        
        This creates a delete action for the current model instance,
        which can be executed to remove it from the database.
        
        Args:
            driver: Optional specific driver to use
            
        Returns:
            A DeleteAction that can be executed to perform the deletion
            
        Example:
            ```python
            # Delete a user
            user = await User.fetch(User.name == "Alice").one()
            await user.delete().raise_on_errors()
            ```
        """
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
        """
        Count the number of model instances matching the given predicates.
        
        This creates a query to count models matching the specified conditions.
        
        Args:
            *predicates: Query conditions to filter the results
            columns: Optional column values to filter by
            driver: Optional specific driver to use
            
        Returns:
            An AsyncResultWrapper containing the count of matching models
            
        Example:
            ```python
            # Count users older than 30
            count = await User.count(User.age > 30).value
            ```
        """
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
        """
        Fetch model instances matching the given predicates.
        
        This creates a query to retrieve models matching the specified conditions.
        
        Args:
            *predicates: Query conditions to filter the results
            driver: Optional specific driver to use
            **columns: Column values to filter by (as keyword arguments)
            
        Returns:
            A FetchAction that can be executed to retrieve the matching models
            
        Example:
            ```python
            # Fetch all users named "Alice"
            users = await User.fetch(User.name == "Alice").all()
            
            # Alternative syntax with column values
            users = await User.fetch(name="Alice").all()
            ```
        """
        driver = cls.get_driver(driver)
        return driver.find(*predicates, *cls._build_column_predicates(columns)).fetch

    async def reload(self, driver: "drivers.DatabaseDriver | None" = None) -> Self:
        """
        Reload this model instance from the database.
        
        This refreshes the current instance with the latest data from the database,
        overwriting any local changes that haven't been saved.
        
        Args:
            driver: Optional specific driver to use
            
        Returns:
            The updated model instance (self)
            
        Example:
            ```python
            # Reload a user to get the latest data
            await user.reload()
            ```
        """
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
        """
        Save changes to this model instance to the database.
        
        This updates the database record for this model with any changes
        made to the instance's fields.
        
        Args:
            driver: Optional specific driver to use
            
        Returns:
            True if the save was successful
            
        Example:
            ```python
            # Update a user's age and save
            user.age = 31
            await user.save()
            ```
        """
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
        """
        Get the primary key fields for this model.
        
        This determines which fields should be used as the primary key
        for database operations.
        
        Returns:
            A tuple of FieldMetadata objects representing the primary key fields
            
        Raises:
            Exception: If no fields are defined on the model
            
        Note:
            If no fields are explicitly marked as keys with the Key metadata,
            this will try to find fields named 'id' or '_id', then integer fields,
            and finally fall back to the first field.
        """
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
        """
        Build query predicates from column values.
        
        This converts keyword arguments into query predicates for filtering.
        
        Args:
            columns: Dictionary of column names and values to filter by
            
        Yields:
            AST comparison nodes for each column filter
            
        Raises:
            ValueError: If an invalid column name is provided
        """
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
    """
    Decorator that transforms a class into an Ommi model for database operations.
    
    This decorator analyzes a class's type annotations and field metadata, setting up
    the necessary infrastructure to use the class with Ommi database operations.
    It handles:
    
    1. Processing field annotations and metadata
    2. Setting up relationships between models
    3. Creating queryable descriptors for each field
    4. Registering the model with a model collection
    
    The decorated class inherits from OmmiModel, gaining access to methods like
    fetch(), count(), save(), reload(), and delete().
    
    Args:
        model_type: The class to transform into an Ommi model
        collection: Optional model collection to register the model with
                   (defaults to the global collection)
    
    Returns:
        The transformed model class or a decorator function if model_type is None
    
    Example:
        ```python
        from dataclasses import dataclass
        from typing import Annotated
        from ommi import ommi_model, Key
        
        @ommi_model
        @dataclass
        class User:
            name: str
            age: int
            id: Annotated[int, Key] = None
        ```
    """

    def wrap_model(c: Type[T]) -> Type[T]:
        """
        Internal function that performs the model transformation.
        
        Args:
            c: The class to transform
            
        Returns:
            The transformed model class
        """
        model = _create_model(c, collection=collection)
        _register_model(
            model,
            Optional.Some(collection) if collection else Optional.Nothing(),
        )
        return model

    return wrap_model if model_type is None else wrap_model(model_type)


def _create_model(c, **kwargs) -> Type[OmmiModel]:
    """
    Create an Ommi model from a class.
    
    This function creates a new class that inherits from both the original class
    and OmmiModel, adding all the necessary attributes and methods for Ommi
    database operations.
    
    Args:
        c: The class to transform
        **kwargs: Additional arguments to pass to the metadata factory
        
    Returns:
        The new model class
    """
    metadata_factory = (
        c.__ommi__.clone if hasattr(c, METADATA_DUNDER_NAME) else OmmiMetadata
    )

    # Get annotations and field metadata
    annotations = tramp.annotations.get_annotations(c, tramp.annotations.Format.FORWARDREF)
    fields = _get_fields(annotations)
    
    # Validate field names for case insensitivity
    _validate_case_insensitive_fields(fields)

    def init(self, *init_args, **init_kwargs):
        """
        Custom __init__ method for the model.
        
        This initializes the base class and sets up lazy query fields.
        
        Args:
            *init_args: Positional arguments to pass to the base class __init__
            **init_kwargs: Keyword arguments to pass to the base class __init__
        """
        annotations = tramp.annotations.get_annotations(c, tramp.annotations.Format.FORWARDREF)
        query_fields = _get_query_fields(annotations)

        unset_query_fields = {name: None for name in query_fields if name not in init_kwargs}
        super(model_type, self).__init__(*init_args, **init_kwargs | unset_query_fields)

        for name, annotation in query_fields.items():
            if name in unset_query_fields:
                setattr(self, name, get_origin(annotation).create(self, get_args(annotation)))

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


def _validate_case_insensitive_fields(fields: dict[str, FieldMetadata]) -> None:
    """
    Validate that field names are case-insensitive and raise an error if duplicates are found.
    
    This checks for field names that differ only by case, which is not allowed.
    However, it makes an exception for fields that use StoreAs with different column names.
    
    Args:
        fields: Dictionary of field names to their FieldMetadata
        
    Raises:
        ValueError: If duplicate field names (case-insensitive) are found without different StoreAs values
    """
    # Create a mapping of lowercase field names to their original names and StoreAs values
    lowercase_fields = {}
    
    for field_name, metadata in fields.items():
        # Get the StoreAs value if it exists
        store_as_value = None
        if metadata.matches(StoreAs):
            store_as_value = metadata.get("store_as")
            
        # Check for case-insensitive duplicates
        lowercase_name = field_name.lower()
        
        if lowercase_name in lowercase_fields:
            original_name, original_store_as = lowercase_fields[lowercase_name]
            
            # Allow duplicates only if both have different StoreAs values
            if store_as_value is None or original_store_as is None or store_as_value.lower() == original_store_as.lower():
                raise ValueError(
                    f"Duplicate field name found: '{field_name}' and '{original_name}'. "
                    f"Field names must be case-insensitive unique unless they use different StoreAs values."
                )
        
        lowercase_fields[lowercase_name] = (field_name, store_as_value)
        
    # Now check for duplicate StoreAs values
    store_as_map = {}
    
    for field_name, metadata in fields.items():
        if metadata.matches(StoreAs):
            store_as_value = metadata.get("store_as")
            if store_as_value:
                lowercase_store_as = store_as_value.lower()
                
                if lowercase_store_as in store_as_map:
                    raise ValueError(
                        f"Duplicate StoreAs value found: '{store_as_value}' used by fields "
                        f"'{field_name}' and '{store_as_map[lowercase_store_as]}'. "
                        f"StoreAs values must be case-insensitive unique."
                    )
                
                store_as_map[lowercase_store_as] = field_name


def _register_model(
    model: Type[OmmiModel],
    collection: "Optional[ommi.models.collections.ModelCollection]",
):
    """
    Register a model with a model collection.
    
    This adds the model to the specified collection or to the global
    collection if none is specified.
    
    Args:
        model: The model class to register
        collection: Optional collection to register the model with
    """
    get_collection(collection, model).add(model)


def get_collection(
    collection: "Optional[ommi.models.collections.ModelCollection]",
    model: Type[OmmiModel] | None = None,
) -> "ommi.models.collections.ModelCollection":
    """
    Get the appropriate model collection based on inputs.
    
    This determines which collection to use based on the provided collection,
    the model's collection, or falling back to the global collection.
    
    Args:
        collection: Optional explicit collection to use
        model: Optional model to get the collection from
        
    Returns:
        The appropriate ModelCollection
    """
    return collection.value_or(
        getattr(model, METADATA_DUNDER_NAME).collection
        if model
        else ommi.models.collections.get_global_collection()
    )


def _get_fields(fields: dict[str, Any]) -> dict[str, FieldMetadata]:
    """
    Extract field metadata from class annotations.
    
    This analyzes class annotations to build field metadata for each field,
    extracting type information and any explicit metadata provided through
    Annotated.
    
    Args:
        fields: Dictionary of field names to their annotations
        
    Returns:
        Dictionary of field names to their FieldMetadata
    """
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
    """
    Extract lazy query fields from class annotations.
    
    This identifies fields that are lazy query fields (like Lazy)
    that need special handling during model initialization.
    
    Args:
        fields: Dictionary of field names to their annotations
        
    Returns:
        Dictionary of query field names to their annotations
    """
    return {
        name: annotation
        for name, annotation in fields.items()
        if _is_lazy_query_field(annotation)
    }

def _is_lazy_query_field(annotation: Any) -> bool:
    """
    Check if an annotation is a lazy query field.
    
    This determines if the annotation refers to a LazyQueryField subclass,
    such as Lazy or LazyList.
    
    Args:
        annotation: The annotation to check
        
    Returns:
        True if the annotation is a lazy query field, False otherwise
    """
    origin = get_origin(annotation)
    return (
        isinstance(origin, type)
        and issubclass(origin, ommi.models.query_fields.LazyQueryField)
    )
