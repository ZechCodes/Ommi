"""
AST (Abstract Syntax Tree) Implementation for Ommi Query System

This module provides a set of classes for constructing and managing an abstract
syntax tree (AST) for query operations within the Ommi framework. The classes
defined here allow for the creation of logical operators, comparison nodes,
and groupings of these nodes to form complex queries.
"""


from enum import auto, Enum
from itertools import zip_longest
from typing import Any

try:
    from typing import Self
except ImportError:
    Self = Any

import ommi.models as models


class ResultOrdering(Enum):
    ASCENDING = auto()
    DESCENDING = auto()


class ASTNode:
    pass


class ASTLogicalOperatorNode(ASTNode, Enum):
    AND = auto()
    OR = auto()


class ASTOperatorNode(ASTNode, Enum):
    EQUALS = auto()
    NOT_EQUALS = auto()
    GREATER_THAN = auto()
    GREATER_THAN_OR_EQUAL = auto()
    LESS_THAN = auto()
    LESS_THAN_OR_EQUAL = auto()


class ASTGroupFlagNode(ASTNode, Enum):
    OPEN = auto()
    CLOSE = auto()


class ASTGroupNode(ASTNode):
    def __init__(
        self, items: "list[ASTComparableNode | ASTLogicalOperatorNode] | None" = None
    ):
        self.items: list[ASTComparableNode | ASTLogicalOperatorNode] = (
            [] if items is None else items
        )
        self.frozen = False
        self.max_results = -1
        self.results_page = 0
        self.sorting: list[ASTReferenceNode] = []

    def __iter__(self):
        self.frozen = True
        if len(self.items) > 1:
            yield ASTGroupFlagNode.OPEN

        try:
            yield from iter(self.items)
        finally:
            self.frozen = False

        if len(self.items) > 1:
            yield ASTGroupFlagNode.CLOSE

    def add(self, item, logical_type=ASTLogicalOperatorNode.AND):
        if self.frozen:
            return

        if isinstance(item, type) and issubclass(item, models.OmmiModel):
            item = ASTReferenceNode(None, item)

        elif len(self.items) > 0 and getattr(self.items[~0], "field", True) is not None:
            self.items.append(logical_type)

        self.items.append(item)

    def limit(self, limit: int, page: int = 0) -> Self:
        self.max_results = limit
        self.results_page = page
        return self

    def sort(self, *on_fields: "ASTReferenceNode") -> Self:
        # Gotta jump through some hoops to compare ASTReferenceNodes and maintain ordering
        unique = set(on_fields) | set(self.sorting)
        for field in on_fields:
            if field in unique:
                self.sorting.append(field)
                unique.remove(field)

        return self

    def __eq__(self, other):
        if not isinstance(other, ASTGroupNode):
            return NotImplemented

        return self._compare_items(other)

    def _compare_items(self, other):
        # Use zip_longest to ensure there aren't additional items in either group
        for items in zip_longest(self, other):
            match items:
                case (ASTLiteralNode(a), ASTLiteralNode(b)) if a == b:
                    continue

                case (
                    ASTReferenceNode(af, am),
                    ASTReferenceNode(bf, bm),
                ) if af == bf and am == bm:
                    continue

                case (
                    ASTComparisonNode(al, ar, ao),
                    ASTComparisonNode(bl, br, bo),
                ) if al._eq(bl) and ar._eq(br) and ao == bo:
                    continue

                case (ASTGroupNode() as a, ASTGroupNode() as b) if a == b:
                    continue

                case (
                    ASTLogicalOperatorNode() as a,
                    ASTLogicalOperatorNode() as b,
                ) if a == b:
                    continue

                case (ASTGroupFlagNode() as a, ASTGroupFlagNode() as b) if a == b:
                    continue

                case _:
                    return False

        return True

    def __repr__(self):
        return f"{type(self).__name__}({self.items!r})"

    def And(self, *comparisons: "SearchGroup | ASTComparisonNode | bool"):
        return self._add_node_or_group(when(*comparisons), ASTLogicalOperatorNode.AND)

    def Or(self, *comparisons: "SearchGroup | ASTComparisonNode | bool"):
        return self._add_node_or_group(when(*comparisons), ASTLogicalOperatorNode.OR)

    def _add_node_or_group(
        self,
        comparison: "SearchGroup | ASTComparisonNode",
        logical_type: ASTLogicalOperatorNode,
    ):
        match comparison:
            case ASTComparisonNode() if len(comparison.group.items) > 1:
                self.add(comparison.group, logical_type)

            case ASTGroupNode() if len(comparison.items) == 1:
                self.add(comparison.items[0], logical_type)

            case _:
                self.add(comparison, logical_type)

        return self


class ASTComparableNode(ASTNode):
    def __init__(self, group):
        self.group = group

    @staticmethod
    def _safe_compare(func):
        def wrapper(self, *args):
            if self.group.frozen:
                return False

            return func(self, *args)

        return wrapper

    @_safe_compare
    def __eq__(self, other) -> "ASTComparisonNode":
        self.group.add(
            node := ASTComparisonNode(self, other, ASTOperatorNode.EQUALS, self.group)
        )
        return node

    @_safe_compare
    def __ne__(self, other) -> "ASTComparisonNode":
        self.group.add(
            node := ASTComparisonNode(
                self, other, ASTOperatorNode.NOT_EQUALS, self.group
            )
        )
        return node

    def __gt__(self, other) -> "ASTComparisonNode":
        self.group.add(
            node := ASTComparisonNode(
                self, other, ASTOperatorNode.GREATER_THAN, self.group
            )
        )
        return node

    def __ge__(self, other) -> "ASTComparisonNode":
        self.group.add(
            node := ASTComparisonNode(
                self, other, ASTOperatorNode.GREATER_THAN_OR_EQUAL, self.group
            )
        )
        return node

    def __lt__(self, other) -> "ASTComparisonNode":
        self.group.add(
            node := ASTComparisonNode(
                self, other, ASTOperatorNode.LESS_THAN, self.group
            )
        )
        return node

    def __le__(self, other) -> "ASTComparisonNode":
        self.group.add(
            node := ASTComparisonNode(
                self, other, ASTOperatorNode.LESS_THAN_OR_EQUAL, self.group
            )
        )
        return node


class ASTReferenceNode(ASTComparableNode):
    __match_args__ = ("field", "model")

    def __init__(self, field, model, ordering=ResultOrdering.ASCENDING):
        super().__init__(ASTGroupNode())
        self._field = field
        self._model = model
        self._ordering = ordering

    def _eq(self, other):
        return (
            self.field == other.field
            and self.model == other.model
            and self.ordering == other.ordering
        )

    def __iter__(self):
        yield from (self._field, self._model)

    @property
    def field(self):
        return self._field

    @property
    def model(self):
        return self._model

    @property
    def ordering(self):
        return self._ordering

    @property
    def asc(self) -> "ASTReferenceNode":
        return ASTReferenceNode(self._field, self._model, ResultOrdering.ASCENDING)

    @property
    def desc(self) -> "ASTReferenceNode":
        return ASTReferenceNode(self._field, self._model, ResultOrdering.DESCENDING)

    def __hash__(self):
        return hash((self._field, self._model, self._ordering))

    def __repr__(self):
        return (
            f"<{type(self).__qualname__}"
            f" {self.model.__qualname__ if self.model else None}.{getattr(self._field, 'name', self._field)!r}>"
        )


class ASTLiteralNode(ASTComparableNode):
    __match_args__ = ("value",)

    def __init__(self, value):
        super().__init__(ASTGroupNode())
        self._value = value

    def _eq(self, other):
        if not isinstance(other, ASTLiteralNode):
            return NotImplemented

        return self.value == other.value

    def __iter__(self):
        yield self._value

    @property
    def value(self):
        return self._value

    def __repr__(self):
        return f"{type(self).__name__}({self._value!r})"


class ASTComparisonNode(ASTComparableNode):
    __match_args__ = ("left", "right", "operator")

    def __init__(
        self,
        left: ASTLiteralNode | ASTReferenceNode | Any,
        right: ASTLiteralNode | ASTReferenceNode | Any,
        operator: ASTOperatorNode,
        group=None,
    ):
        super().__init__(group or ASTGroupNode())
        self._left = self._make_node(left)
        self._right = self._make_node(right)
        self._operator = operator

    def __iter__(self):
        yield from (self._left, self._right, self._operator)

    @property
    def left(self):
        return self._left

    @property
    def right(self):
        return self._right

    @property
    def operator(self):
        return self._operator

    def __repr__(self):
        return (
            f"{type(self).__name__}("
            f"{self._left!r}, "
            f"{self._right!r}, "
            f"{self._operator})"
        )

    def And(self, *comparisons: "ASTComparisonNode | SearchGroup | bool"):
        return self.group.And(*comparisons)

    def Or(self, *comparisons: "ASTComparisonNode | SearchGroup | bool"):
        return self.group.Or(*comparisons)

    def _make_node(self, value):
        match value:
            case ASTComparableNode():
                return value

            case _:
                return ASTLiteralNode(value)


def when(
    *comparisons: "ASTComparisonNode | Type[models.DatabaseModel] | bool",
) -> ASTGroupNode:
    match comparisons:
        case (ASTComparisonNode() as comparison,):
            return comparison.group

        case (ASTGroupNode() as group,):
            return group

        case _:
            group = ASTGroupNode()
            for c in comparisons:
                match c:
                    case ASTComparisonNode():
                        group.add(c.group)

                    case _:
                        group.add(c)

            return group
