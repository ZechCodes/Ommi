"""Defines shared type aliases used across the Ommi package.

This module centralizes common type hints to improve code clarity, maintainability,
and support static type checking, especially for concepts that might have multiple
valid underlying types or to avoid circular dependencies with forward references.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ommi.models import OmmiModel


type DBModel = "Any | OmmiModel"
"""Type alias representing a database model instance.

This alias is used throughout Ommi to refer to instances of models that are managed
by the ORM. It primarily resolves to `ommi.models.OmmiModel` but is defined broadly
to accommodate potential extensions or different model base types in the future.

Using `DBModel` helps in:
-   Providing a consistent type hint for database records.
-   Simplifying refactoring if the base model type changes.
-   Improving readability by clearly indicating that a variable is expected to hold
    a database model object.

During static type checking (when `TYPE_CHECKING` is true), this will be seen as
`OmmiModel`. At runtime, the string literal `"Any | OmmiModel"` is a placeholder
and doesn't enforce runtime type checks beyond what Python's dynamic typing does.
"""
