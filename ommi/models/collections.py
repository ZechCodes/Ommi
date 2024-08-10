"""
Model Collection Management

This module provides a model collection type for grouping models. It also provides a function for getting a global
model collection that is the default collection.
"""


from typing import Type, Generic

from ommi.drivers.driver_types import TModel

_global_collection = None


class ModelCollection(Generic[TModel]):
    def __init__(self):
        self.models = set()

    def add(self, model: "Type[TModel]"):
        self.models.add(model)

    def __repr__(self):
        return f"<{type(self).__name__}: contains {len(self.models)} model{'' if len(self.models) == 1 else 's'}>"


def get_global_collection() -> ModelCollection:
    global _global_collection
    if not _global_collection:
        _global_collection = ModelCollection()

    return _global_collection
