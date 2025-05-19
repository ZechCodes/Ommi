"""
Lazy Reference Builder for Ommi Models

This module handles the lazy evaluation of type annotations to avoid circular
imports in the Ommi framework. It provides a mechanism for defining and
resolving references between models only when they are needed, ensuring
dependencies are managed without early binding.

When models reference each other in a circular manner, standard Python imports
can cause problems. This module allows for lazy resolution of references, where
the actual model types are resolved only when needed.

Example:
    ```python
    # In model definition
    from typing import Annotated
    from ommi import ommi_model, ReferenceTo
    
    @ommi_model
    class User:
        id: int
        
    @ommi_model
    class Post:
        # Reference is resolved lazily to avoid circular imports
        author_id: Annotated[int, ReferenceTo(User.id)]
    ```
"""


from collections import defaultdict
from dataclasses import dataclass
from enum import auto, Enum
from typing import Type, Any

from ommi import query_ast
from ommi.models.field_metadata import ReferenceTo, FieldMetadata
import ommi.models


class LazyReferencesState(Enum):
    """
    Enum representing the possible states of a LazyReferenceBuilder.
    
    This tracks whether references have been generated yet, allowing for
    demand-driven resolution.
    
    Attributes:
        ReferencesNotYetGenerated: References have not been built/resolved yet
        ReferencesHaveBeenGenerated: References have been built and are available
    """
    ReferencesNotYetGenerated = auto()
    ReferencesHaveBeenGenerated = auto()


@dataclass
class FieldReference:
    """
    Represents a reference from one model field to another.
    
    This dataclass stores the complete information about a reference between
    two model fields, capturing both the source and target of the relationship.
    
    Attributes:
        from_model: The model class containing the reference
        from_field: The field metadata from the referring model
        to_model: The model class being referenced
        to_field: The field metadata being referenced in the target model
    """
    from_model: "Type[ommi.models.OmmiModel]"
    from_field: FieldMetadata
    to_model: "Type[ommi.models.OmmiModel]"
    to_field: FieldMetadata


class LazyReferenceBuilder:
    """
    Builds and manages references between models on-demand.
    
    This class is responsible for lazily resolving references between models,
    only computing them when they are actually needed. This avoids circular
    import problems and improves startup performance.
    
    The reference resolution happens automatically when references are accessed,
    and the results are cached for future use.
    """
    
    def __init__(
        self,
        fields: dict[str, FieldMetadata],
        model: "Type[ommi.models.OmmiModel]",
        namespace: dict[str, Any],
    ):
        """
        Args:
            fields: Dictionary mapping field names to their metadata
            model: The model class that owns these fields
            namespace: The namespace where models can be found for string references
        """
        self._references_state = LazyReferencesState.ReferencesNotYetGenerated
        self._fields = fields
        self._model = model
        self._namespace = namespace
        self._references: dict[
            Type[ommi.models.OmmiModel], list[FieldReference]
        ] = defaultdict(list)

    def __contains__(self, model: "Type[ommi.models.OmmiModel]") -> bool:
        """
        Check if there are any references to the given model.
        
        This will trigger reference generation if it hasn't happened yet.
        
        Args:
            model: The model class to check for references to
            
        Returns:
            True if there are references to the model, False otherwise
        """
        if self._references_state == LazyReferencesState.ReferencesNotYetGenerated:
            self._build_references()

        return model in self._references

    def __getitem__(self, model: "Type[ommi.models.OmmiModel]") -> list[FieldReference]:
        """
        Get all references to the given model.
        
        This will trigger reference generation if it hasn't happened yet.
        
        Args:
            model: The model class to get references for
            
        Returns:
            A list of FieldReference objects for the model
            
        Raises:
            KeyError: If there are no references to the model
        """
        if self._references_state == LazyReferencesState.ReferencesNotYetGenerated:
            self._build_references()

        return self._references[model]

    def __repr__(self):
        if self._references_state == LazyReferencesState.ReferencesHaveBeenGenerated:
            content = repr(dict(self._references))
        else:
            content = f"{type(self._references_state).__name__}.{self._references_state.name}"

        return f"<{type(self).__name__}: {content}>"

    def get(
        self,
        model: "Type[ommi.models.OmmiModel]",
        default: list[FieldReference] | None = None,
    ) -> list[FieldReference]:
        """
        Get references to a model with a default value if none exist.
        
        This will trigger reference generation if it hasn't happened yet.
        
        Args:
            model: The model class to get references for
            default: Value to return if no references exist (defaults to None)
            
        Returns:
            A list of FieldReference objects or the default value
        """
        if self._references_state == LazyReferencesState.ReferencesNotYetGenerated:
            self._build_references()

        return self._references.get(model, default)

    def _build_references(self) -> None:
        for name, metadata in self._fields.items():
            if metadata.matches(ReferenceTo):
                match metadata.get("reference_to"):
                    case query_ast.ASTReferenceNode(to_field, to_model):
                        self._references[to_model].append(
                            FieldReference(
                                from_model=self._model,
                                from_field=metadata,
                                to_model=to_model,
                                to_field=to_field.metadata,
                            )
                        )

                    case str() as ref:
                        reference: query_ast.ASTReferenceNode = eval(
                            ref, vars(self._namespace)
                        )
                        self._references[reference.model].append(
                            FieldReference(
                                from_model=self._model,
                                from_field=metadata,
                                to_model=reference.model,
                                to_field=reference.field.metadata,
                            )
                        )

                    case unexpected_value:
                        raise TypeError(
                            f"Unexpected value for reference: {unexpected_value}"
                        )

        self._references_state = LazyReferencesState.ReferencesHaveBeenGenerated
