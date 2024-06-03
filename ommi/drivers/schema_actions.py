from typing import Generic, Iterable, Type
from abc import ABC, abstractmethod

from ommi.drivers.database_results import AsyncResultWrapper
from ommi.drivers.driver_types import TConn, TModel
from ommi.models.collections import ModelCollection


class SchemaAction(Generic[TConn, TModel], ABC):
    def __init__(self, connection: TConn, model_collection: ModelCollection[Type[TModel]] | None):
        self._connection = connection
        self._model_collection = model_collection

    @abstractmethod
    def create_models(self) -> AsyncResultWrapper[Iterable[Type[TModel]]]:
        ...

    @abstractmethod
    def delete_models(self) -> AsyncResultWrapper[None]:
        ...
