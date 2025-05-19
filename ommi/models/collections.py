"""
Model Collection Management

This module provides a model collection type for grouping models. It also provides a function for getting a global
model collection that is the default collection.
"""


from typing import Type, TYPE_CHECKING

if TYPE_CHECKING:
    from ommi.models import OmmiModel


_global_collection = None


class ModelCollection:
    """A collection for grouping Ommi models.

    Model collections are used to manage sets of related database models.
    This can be useful for organizing models by feature, domain, or any other
    logical grouping. When applying or deleting schemas with `Ommi.use_models()`
    or `Ommi.remove_models()`, you typically pass a `ModelCollection` instance.

    A global default collection is available via `get_global_collection()`,
    which is often used implicitly if no specific collection is provided.

    Attributes:
        models (set[Type[OmmiModel]]): A set of `OmmiModel` class types that belong
                                       to this collection.
    """
    def __init__(self):
        self.models = set()

    def add(self, model: "Type[OmmiModel]"):
        """Adds a model class to this collection.

        If the model is already in the collection, this operation has no effect.

        Args:
            model: The `OmmiModel` class (not an instance) to add.
        """
        self.models.add(model)

    def __repr__(self):
        return f"<{type(self).__name__}: contains {len(self.models)} model{'' if len(self.models) == 1 else 's'}>"


def get_global_collection() -> ModelCollection:
    """Retrieves the global default `ModelCollection`.

    This function provides a singleton instance of `ModelCollection` that is used
    by Ommi as the default collection if models are defined without being explicitly
    added to a user-created collection, and if implicit model setup is enabled
    in the `Ommi` instance.

    The global collection is created on its first call.

    Returns:
        The global `ModelCollection` instance.
    """
    global _global_collection
    if not _global_collection:
        _global_collection = ModelCollection()

    return _global_collection
