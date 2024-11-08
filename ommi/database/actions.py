from typing import Awaitable, Callable, ClassVar, Generic, override, Type, TypeVar

from ommi.models import OmmiModel
from ommi.query_ast import ASTComparisonNode, ASTGroupNode, when
from ommi.utils.awaitable_results import AwaitableResult

TModel = TypeVar("TModel", bound=OmmiModel)
TResult = TypeVar("TResult")
TDefault = TypeVar("TDefault")


class OmmiActionQuery(Generic[TModel, TResult]):
    action_query_type: "ClassVar[Type[OmmiActionQuery]]"

    def __init__(
        self,
        model: Type[TModel],
        action_callback: Callable[[ASTGroupNode], AwaitableResult[TResult]],
        predicate: ASTGroupNode,
    ):
        self.action_callback = action_callback
        self.model_type = model
        self.predicate = predicate

    def __await__(self):
        return self.result.__await__()

    @property
    def result(self) -> AwaitableResult[TResult]:
        return self.action_callback(self.predicate)

    def raise_on_errors(self) -> Awaitable[TResult]:
        return self.result.raise_on_errors()

    def value_or(self, default: TDefault) -> Awaitable[TResult | TDefault]:
        return self.result.value_or(default)

    def _clone_with_updated_predicate(self, predicate: ASTGroupNode):
        return self.action_query_type(self.model_type, self.action_callback, predicate)


OmmiActionQuery.action_query_type = OmmiActionQuery


class OmmiAction(OmmiActionQuery[TModel, TResult]):
    def __init__(
        self,
        model: Type[TModel],
        action_callback: Callable[[ASTGroupNode], AwaitableResult[TResult]]
    ):
        super().__init__(model, action_callback, when(model))

    def matching(self, query: ASTComparisonNode | Type[OmmiModel] | bool):
        return self._clone_with_updated_predicate(self.predicate.And(query))


class OmmiUpdateActionQuery(OmmiActionQuery[TModel, None]):
    @override
    def __init__(
        self,
        model: Type[TModel],
        action_callback: Callable[[ASTGroupNode, ...], AwaitableResult[None]],
        predicate: ASTGroupNode,
    ):
        self.action_callback = action_callback
        self.model_type = model
        self.predicate = predicate

    @property
    def result(self) -> AwaitableResult[None]:
        raise Exception("Update actions must use the set(**kwargs) method.")

    def set(self, **kwargs) -> AwaitableResult[None]:
        return self.action_callback(self.predicate, **kwargs)


OmmiUpdateActionQuery.action_query_type = OmmiUpdateActionQuery


class OmmiUpdateAction(OmmiUpdateActionQuery[TModel]):
    def __init__(
        self,
        model: Type[TModel],
        action_callback: Callable[[ASTGroupNode, ...], AwaitableResult[None]]
    ):
        super().__init__(model, action_callback, when(model))

    def matching(self, query: ASTComparisonNode | Type[OmmiModel] | bool):
        return self._clone_with_updated_predicate(self.predicate.And(query))\


class OmmiActionBuilder(Generic[TModel, TResult]):
    def __init__(
        self,
        action_type: Type[OmmiAction[TModel, TResult]],
        action_callback: Callable[[ASTGroupNode], AwaitableResult[TResult]],
    ):
        self.action_type = action_type
        self.action_callback = action_callback

    def __getitem__(self, model: Type[TModel]) -> OmmiAction[TModel, TResult]:
        return self.action_type(model, self.action_callback)
