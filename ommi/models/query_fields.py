"""
Query Fields for Ommi Models

This module enables dynamic relationships between models by defining fields that
are populated through database queries. These fields can represent one-to-many,
many-to-one, and many-to-many relationships between models.

The module provides:
- QueryStrategy: Protocol defining how to generate queries for related models
- AssociateOnReference: Strategy for querying based on foreign key references
- QueryField: Base class for fields that are populated via queries
- Related: Type annotation for defining query fields on models

Example:
    ```python
    from ommi import OmmiModel, Lazy, LazyList, ReferenceTo

    class User(OmmiModel):
        id: int
        posts: "LazyList[Post]"

    class Post(OmmiModel):
        author_id: Annotated[int, ReferenceTo(User.id)]
        author: Lazy[User]
    ```
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
    """
    Protocol defining how to generate queries for related models.
    
    Query strategies determine how to build query AST nodes for fetching related models 
    from the database. Different strategies can be used for different relationship types
    (one-to-one, one-to-many, many-to-many through association tables, etc.).
    """
    
    def generate_query(
        self, model: "ommi.models.OmmiModel", contains: "Type[ommi.models.OmmiModel]"
    ) -> "ommi.query_ast.ASTGroupNode":
        """
        Generate a query AST node for fetching related models.
        
        Args:
            model: The source model instance that owns the relationship
            contains: The target model type that is being related to
            
        Returns:
            An AST node representing the query to fetch related models
            
        Raises:
            RuntimeError: If no relationship can be established between the models
        """
        ...

    def generate_query_factory(
        self, model: "ommi.models.OmmiModel", contains: "Type[ommi.models.OmmiModel]"
    ) -> "Callable[[], ommi.query_ast.ASTGroupNode]":
        """
        Create a factory function that generates queries for related models.
        
        This creates a partial function that can be called later to generate
        the actual query. This allows deferring query generation until needed.
        
        Args:
            model: The source model instance that owns the relationship
            contains: The target model type that is being related to
            
        Returns:
            A callable that will generate an AST query node when invoked
        """
        return partial(self.generate_query, model, contains)


class AssociateOnReference(QueryStrategy):
    """
    Strategy for querying related models based on direct foreign key references.
    
    This strategy examines model references to determine how to join models together.
    It supports both forward references (parent -> child) and backward references
    (child -> parent).

    It is typically the default strategy used when no specific association
    strategy is specified.
    """
    
    def generate_query(
        self, model: "ommi.models.OmmiModel", contains: "Type[ommi.models.OmmiModel]"
    ) -> "ommi.query_ast.ASTGroupNode":
        """
        Generate a query for related models based on foreign key references.
        
        This looks up reference metadata between the models and constructs
        appropriate conditions to join them in a query.
        
        Args:
            model: The source model instance that owns the relationship
            contains: The target model type that is being related to
            
        Returns:
            An AST query node for fetching the related models
            
        Raises:
            RuntimeError: If no reference can be found between the models
        """
        if refs := model.__ommi__.references.get(contains):
            return ommi.query_ast.where(
                *(
                    getattr(r.to_model, r.to_field.get("field_name"))
                    == getattr(model, r.from_field.get("field_name"))
                    for r in refs
                )
            )

        if refs := contains.__ommi__.references.get(type(model)):
            return ommi.query_ast.where(
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
    """
    Strategy for querying models using an association model (many-to-many relationships).
    
    This strategy enables many-to-many relationships by using a third model (association
    table) that connects the two related models. This is particularly useful when additional
    data needs to be stored about the relationship itself.
    
    Example:
        ```python
        @ommi_model
        class User:
            id: int
            permissions: "LazyList[Annotated[Permission, AssociateUsing(UserPermission)]]"
        
        @ommi_model
        class Permission:
            id: int
            
        @ommi_model
        class UserPermission:
            user_id: Annotated[int, ReferenceTo(User.id)]
            permission_id: Annotated[int, ReferenceTo(Permission.id)]
        ```
    """
    
    def __init__(self, association_model: Type[T]):
        """
        Args:
            association_model: The model class that links the two related models
        """
        self._association_model = association_model

    @property
    def association_model(self) -> Type[T]:
        """
        Get the association model, evaluating forward references if needed.
        
        Returns:
            The resolved association model class
        """
        if isinstance(self._association_model, ForwardRef):
            return self._association_model.evaluate()

        return self._association_model

    def generate_query(
        self, model: "ommi.models.OmmiModel", contains: "Type[ommi.models.OmmiModel]"
    ) -> "ommi.query_ast.ASTGroupNode":
        """
        Generate a query for related models using the association model.
        
        Args:
            model: The source model instance that owns the relationship
            contains: The target model type that is being related to
            
        Returns:
            An AST query node for fetching the related models through the association
            
        Raises:
            RuntimeError: If the association model doesn't properly link the two models
        """
        contains_model = get_args(contains)[0]
        refs = self.association_model.__ommi__.references.get(type(model))
        return ommi.query_ast.where(
            contains_model,
            *(
                getattr(r.from_model, r.from_field.get("field_name"))
                == getattr(model, r.to_field.get("field_name"))
                for r in refs
            )
        )


class LazyQueryField[T](ABC):
    """
    Base class for fields that are populated via database queries.
    
    LazyQueryField provides the foundation for lazy-loaded relationship fields.
    Instead of loading related data when the model is fetched, these fields
    defer loading until the relationship is actually accessed, improving
    performance.
    
    Key features:
    - Caching of query results
    - Ability to refresh data from database
    - Handling of query errors
    - Support for default values
    """
    
    def __init__(
        self,
        query_factory: "Callable[[], ommi.query_ast.ASTGroupNode]",
        driver: "ommi.drivers.drivers.AbstractDatabaseDriver | None" = None,
    ):
        """
        Args:
            query_factory: Factory function that produces query AST nodes
            driver: Optional specific driver to use for queries (defaults to active driver)
        """
        self._query_factory = query_factory
        self._driver = driver

        self._cache = DBResult.DBFailure(ValueError("Not cached yet"))

    @property
    def _query(self) -> "ommi.query_ast.ASTGroupNode":
        return self._query_factory()

    def __await__(self):
        """
        Make the field awaitable to fetch the related data.
        
        This allows using the field directly with await:
        ```python
        related_models = await model.related_field
        ```
        
        Returns:
            An awaitable that resolves to the related model(s)
        """
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
        """
        Get the related model(s) or use a default value if fetching fails.
        
        Args:
            default: The value to return if fetching fails
            
        Returns:
            The related model(s) or the default value
        """
        ...

    async def refresh(self) -> None:
        """
        Refresh the cached data by fetching from the database again.
        
        This forces a new database query regardless of existing cache state.
        Any errors during fetching will be stored in the cache.
        """
        try:
            result = DBResult.DBSuccess(await self._fetch())
        except Exception as e:
            result = DBResult.DBFailure(e)

        self._cache = result

    async def refresh_if_needed(self) -> None:
        """
        Refresh the cached data only if it hasn't been fetched yet or previously failed.
        
        This is more efficient than unconditional refresh when the data may already
        be cached.
        """
        match self._cache:
            case DBResult.DBFailure():
                await self.refresh()

    @abstractmethod
    async def get_result(self) -> DBResult[T]:
        """
        Get the DBResult containing either the related model(s) or an error.
        
        Returns:
            A DBResult containing either the successful result or failure information
        """
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
        """
        Create a LazyQueryField instance from a model and type annotation.
        
        This factory method creates the appropriate LazyQueryField instance
        based on the model and annotation arguments.
        
        Args:
            model: The model instance that owns the relationship
            annotation_args: Type annotation arguments for the relationship
            query_strategy: Optional explicit query strategy to use
            
        Returns:
            A configured LazyQueryField instance
        """
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


class Lazy[T](LazyQueryField):
    """
    A lazy-loaded field for one-to-one relationships.

    This field represents a relationship where the current model is related to
    a single instance of another model. The related model is loaded from the
    database only when accessed.

    Example:
        ```python
        @ommi_model
        class Post:
            author_id: Annotated[int, ReferenceTo(User.id)]
            author: Lazy[User]
        ```
    """
    
    async def or_use[D](self, default: D) -> T | D:
        """
        Get the related model or use a default value if fetching fails.
        
        Args:
            default: The value to return if fetching fails
            
        Returns:
            The related model or the default value
        """
        return (await self.get_result()).result_or(default)

    async def get_result(self) -> DBResult[T]:
        """
        Get the DBResult containing either the related model or an error.
        
        Returns:
            A DBResult containing either the successful result or failure information
        """
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


class LazyList[T](LazyQueryField):
    """
    A lazy-loaded field for one-to-many relationships.

    This field represents a relationship where the current model is related to
    multiple instances of another model. The related models are loaded from the
    database only when accessed.

    Example:
        ```python
        @ommi_model
        class User:
            id: int
            posts: LazyList[Post]
        ```
    """
    
    async def or_use[D](self, default: list[D]) -> list[T] | list[D]:
        """
        Get the related models or use a default value if fetching fails.
        
        Args:
            default: The value to return if fetching fails
            
        Returns:
            A list of related models or the default value
        """
        return (await self.get_result()).result_or(default)

    async def get_result(self) -> DBResult[list[T]]:
        """
        Get the DBResult containing either the related models or an error.
        
        Returns:
            A DBResult containing either the successful result list or failure information
        """
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
