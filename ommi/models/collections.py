"""
Model Collection Management

This module provides a model collection type for grouping models. It also provides a function for getting a global
model collection that is the default collection.
"""


from typing import Type, TYPE_CHECKING

if TYPE_CHECKING:
    import ommi
    from ommi.models import OmmiModel


_global_collection = None


class ModelCollection:
    def __init__(self):
        self.models = set()

    def add(self, model: "Type[OmmiModel]"):
        self.models.add(model)

    async def setup_on(self, db: "ommi.Ommi"):
        await db.driver.delete_schema(self)
        await db.driver.apply_schema(self)

    async def remove_from(self, db: "ommi.Ommi"):
        await db.driver.delete_schema(self)

    def __repr__(self):
        return f"<{type(self).__name__}: contains {len(self.models)} model{'' if len(self.models) == 1 else 's'}>"


def get_global_collection() -> ModelCollection:
    global _global_collection
    if not _global_collection:
        _global_collection = ModelCollection()

    return _global_collection
