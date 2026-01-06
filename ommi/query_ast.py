"""
AST (Abstract Syntax Tree) Implementation for Ommi Query System

This module provides a set of classes for constructing and managing an abstract
syntax tree (AST) for query operations within the Ommi framework. The classes
defined here allow for the creation of logical operators (`ASTLogicalOperatorNode`),
comparison operators (`ASTOperatorNode`), and nodes representing model fields
(`ASTReferenceNode`) or literal values (`ASTLiteralNode`). These are combined into
comparison expressions (`ASTComparisonNode`) and grouped within `ASTGroupNode`
instances to form complex, structured queries.

The AST is the core representation of a query before it is translated by a
database driver into a native database query language (e.g., SQL).

Key components:
-   `ASTNode`: Base class for all AST nodes.
-   `ASTLogicalOperatorNode`: Enum for AND/OR logical operators.
-   `ASTOperatorNode`: Enum for comparison operators (==, !=, >, <, etc.).
-   `ASTGroupFlagNode`: Enum for marking the start and end of groups when iterating.
-   `ASTGroupNode`: Represents a group of comparisons, potentially nested.
    This is the main builder for queries, with methods like `And()`, `Or()`, `limit()`, `sort()`.
-   `ASTComparableNode`: Base class for nodes that can be part of a comparison (references and literals).
-   `ASTReferenceNode`: Represents a reference to a model field (e.g., `User.name`).
-   `ASTLiteralNode`: Represents a literal value in a comparison (e.g., "Alice", 18).
-   `ASTComparisonNode`: Represents a single comparison (e.g., `User.name == "Alice"`).
-   `when()`: A factory function to start building an `ASTGroupNode` from initial comparisons.

Usage typically starts with `when()` or by using comparison operators directly on
model field descriptors (which are instances of `ASTReferenceNode` under the hood via `QueryField`).

Example:
    ```python
    from ommi.query_ast import when
    from my_app.models import User # Assuming User is an @ommi_model

    # Simple query: User.name == "Alice"
    query1 = when(User.name == "Alice")

    # Complex query: (User.age > 18 AND User.is_active == True) OR User.name == "Admin"
    query2 = when((User.age > 18).And(User.is_active == True)).Or(User.name == "Admin")

    # Query with sorting and limit
    query3 = when(User.is_active == True).sort(User.name.asc).limit(10)
    ```
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
    """Specifies the ordering direction for query results (ascending or descending)."""
    ASCENDING = auto()
    DESCENDING = auto()


class ASTNode:
    """Base class for all nodes in the Abstract Syntax Tree (AST).

    This class serves as a common ancestor for all elements that can form part
    of an Ommi query AST. It doesn't provide any functionality itself but is used
    for type checking and classification of AST components.
    """
    pass


class ASTLogicalOperatorNode(ASTNode, Enum):
    """Represents logical operators (AND, OR) within the AST.

    These are used in `ASTGroupNode` to combine multiple `ASTComparisonNode`
    instances or other `ASTGroupNode`s.
    """
    AND = auto()
    OR = auto()


class ASTOperatorNode(ASTNode, Enum):
    """Represents comparison operators (e.g., ==, !=, >, <) within the AST.

    These are used in `ASTComparisonNode` to define the type of comparison
    being made between a left-hand side (typically an `ASTReferenceNode`)
    and a right-hand side (typically an `ASTLiteralNode` or another `ASTReferenceNode`).
    """
    EQUALS = auto()
    NOT_EQUALS = auto()
    GREATER_THAN = auto()
    GREATER_THAN_OR_EQUAL = auto()
    LESS_THAN = auto()
    LESS_THAN_OR_EQUAL = auto()
    IN = auto()


class ASTGroupFlagNode(ASTNode, Enum):
    """Represents flags for marking the opening and closing of a group in the AST iteration.

    When an `ASTGroupNode` is iterated, these flags are yielded to indicate the
    logical structure of nested groups. This is primarily for internal use by
    query processing logic.
    """
    OPEN = auto()
    CLOSE = auto()


class ASTGroupNode(ASTNode):
    """Represents a group of AST nodes, forming a query or a sub-query.

    An `ASTGroupNode` can contain `ASTComparisonNode`s and `ASTLogicalOperatorNode`s
    (AND/OR) to connect them. It can also contain `ASTReferenceNode` directly if the query
    is meant to target a specific model type without explicit field comparisons initially.

    This is the primary building block for constructing queries. It supports adding
    conditions, logical grouping (AND/OR), result limiting, and sorting.

    Attributes:
        items (list): A list of `ASTComparisonNode` or `ASTLogicalOperatorNode` instances.
        frozen (bool): If True, the group cannot be modified (used during iteration).
        max_results (int): The maximum number of results to return (-1 for no limit).
        results_page (int): The page number for paginated results (0-indexed).
        sorting (list[ASTReferenceNode]): A list of `ASTReferenceNode`s specifying
                                          the sort order for the query results.
    """
    def __init__(
        self, items: "list[ASTComparableNode | ASTLogicalOperatorNode] | None" = None
    ):
        """
        Args:
            items: An optional initial list of items for the group.
        """
        self.items: list[ASTComparableNode | ASTLogicalOperatorNode] = (
            [] if items is None else items
        )
        self.frozen = False
        self.max_results = -1
        self.results_page = 0
        self.sorting: list[ASTReferenceNode] = []

    def __iter__(self):
        """Iterates over the items in the group, adding open/close flags if needed.

        If the group contains more than one item, `ASTGroupFlagNode.OPEN` is yielded
        before the items, and `ASTGroupFlagNode.CLOSE` is yielded after. This helps
        in processing the AST by clearly demarcating group boundaries.

        The group is temporarily marked as `frozen` during iteration to prevent
        modification while it's being traversed.
        """
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
        """Adds an item (comparison, model reference, or group) to this group.

        If the group is not empty and the last item added was a comparison or reference
        (not a logical operator), the specified `logical_type` (defaulting to AND)
        is inserted before the new item.

        If the item is an `OmmiModel` subclass, it's wrapped in an `ASTReferenceNode`.

        Args:
            item: The item to add. Can be an `ASTComparisonNode`, an `OmmiModel` subclass,
                  an `ASTReferenceNode`, or another `ASTGroupNode`.
            logical_type: The `ASTLogicalOperatorNode` (AND/OR) to use if a logical
                          connector is needed before this item. Defaults to AND.
        """
        if self.frozen:
            return

        if isinstance(item, type) and issubclass(item, models.OmmiModel):
            item = ASTReferenceNode(None, item)

        elif len(self.items) > 0 and getattr(self.items[~0], "field", True) is not None:
            self.items.append(logical_type)

        self.items.append(item)

    def limit(self, limit: int, page: int = 0) -> Self:
        """Sets the limit and page for query results (pagination).

        Args:
            limit: The maximum number of results to return.
            page: The page number (0-indexed). For example, if `limit` is 10 and
                  `page` is 1, results 11-20 would be targeted.

        Returns:
            The `ASTGroupNode` instance, allowing for method chaining.
        """
        self.max_results = limit
        self.results_page = page
        return self

    def sort(self, *on_fields: "ASTReferenceNode") -> Self:
        """Adds sorting criteria to the query.

        Accepts one or more `ASTReferenceNode` instances, which typically include
        an ordering direction (e.g., `User.name.asc` or `User.age.desc`).

        Duplicate sort fields are handled gracefully, maintaining the order of first appearance.

        Args:
            *on_fields: `ASTReferenceNode` instances specifying the fields and
                        directions to sort by.

        Returns:
            The `ASTGroupNode` instance, for method chaining.
        """
        # Gotta jump through some hoops to compare ASTReferenceNodes and maintain ordering
        unique = set(on_fields) | set(self.sorting)
        for field in on_fields:
            if field in unique:
                self.sorting.append(field)
                unique.remove(field)

        return self

    def __eq__(self, other):
        """Compares this ASTGroupNode with another for equality.

        Two `ASTGroupNode` instances are considered equal if they contain the
        same sequence of items (comparisons, logical operators, nested groups)
        in the same order.

        Args:
            other: The object to compare with.

        Returns:
            `True` if the groups are equal, `False` otherwise, or `NotImplemented`
            if the other object is not an `ASTGroupNode`.
        """
        if not isinstance(other, ASTGroupNode):
            return NotImplemented

        return self._compare_items(other)

    def _compare_items(self, other):
        """Internal helper to compare the items lists of two ASTGroupNodes."""
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

    def and_(self, *comparisons: "SearchGroup | ASTComparisonNode | bool"):
        """Adds one or more comparisons to this group, joined by AND with previous items.

        If multiple comparisons are provided, they are first combined into their own
        `ASTGroupNode` (using `where()`) before being added.

        Args:
            *comparisons: One or more comparison expressions (e.g., `User.name == "X"`),
                          `ASTGroupNode` instances, or boolean values (which are ignored).

        Returns:
            The `ASTGroupNode` instance, for method chaining.
        """
        return self._add_node_or_group(where(*comparisons), ASTLogicalOperatorNode.AND)

    def or_(self, *comparisons: "SearchGroup | ASTComparisonNode | bool"):
        """Adds one or more comparisons to this group, joined by OR with previous items.

        If multiple comparisons are provided, they are first combined into their own
        `ASTGroupNode` (using `where()`) before being added.

        Args:
            *comparisons: One or more comparison expressions (e.g., `User.name == "X"`),
                          `ASTGroupNode` instances, or boolean values (which are ignored).

        Returns:
            The `ASTGroupNode` instance, for method chaining.
        """
        return self._add_node_or_group(where(*comparisons), ASTLogicalOperatorNode.OR)

    # Deprecated aliases for backwards compatibility
    And = and_
    Or = or_

    def _add_node_or_group(
        self,
        comparison: "SearchGroup | ASTComparisonNode",
        logical_type: ASTLogicalOperatorNode,
    ):
        """Internal helper to add a comparison node or a group node to the items list.

        Handles unwrapping single-item groups to avoid unnecessary nesting.
        """
        match comparison:
            case ASTComparisonNode() if len(comparison.group.items) > 1:
                self.add(comparison.group, logical_type)

            case ASTGroupNode() if len(comparison.items) == 1:
                self.add(comparison.items[0], logical_type)

            case _:
                self.add(comparison, logical_type)

        return self


class ASTComparableNode(ASTNode):
    """Base class for AST nodes that can be used in comparisons (literals and references).

    This class overloads Python's comparison operators (==, !=, >, >=, <, <=)
    to create `ASTComparisonNode` instances and add them to an associated `ASTGroupNode`.

    When a comparison like `MyModel.field == value` is made, `MyModel.field` (an
    `ASTReferenceNode`, which inherits from `ASTComparableNode`) uses these overloaded
    methods to construct the query AST.

    Attributes:
        group (ASTGroupNode): The `ASTGroupNode` to which new comparison nodes
                              generated by operator overloads will be added.
    """
    def __init__(self, group):
        """Initializes an ASTComparableNode.

        Args:
            group: The `ASTGroupNode` this comparable node is associated with. When
                   comparison operators are used on this node, the resulting
                   `ASTComparisonNode` will be added to this group.
        """
        self.group = group

    @staticmethod
    def _safe_compare(func):
        """Decorator to prevent modification of a frozen group during comparison."""
        def wrapper(self, *args):
            if self.group.frozen:
                return False

            return func(self, *args)

        return wrapper

    @_safe_compare
    def __eq__(self, other) -> "ASTComparisonNode":
        """Creates an EQUALS comparison node.

        Args:
            other: The value or `ASTNode` to compare against.

        Returns:
            An `ASTComparisonNode` representing this equality comparison, which has also
            been added to the `self.group`.
        """
        self.group.add(
            node := ASTComparisonNode(self, other, ASTOperatorNode.EQUALS, self.group)
        )
        return node

    @_safe_compare
    def __ne__(self, other) -> "ASTComparisonNode":
        """Creates a NOT_EQUALS comparison node.

        Args:
            other: The value or `ASTNode` to compare against.

        Returns:
            An `ASTComparisonNode` representing this inequality comparison, which has also
            been added to the `self.group`.
        """
        self.group.add(
            node := ASTComparisonNode(
                self, other, ASTOperatorNode.NOT_EQUALS, self.group
            )
        )
        return node

    def __gt__(self, other) -> "ASTComparisonNode":
        """Creates a GREATER_THAN comparison node.

        Args:
            other: The value or `ASTNode` to compare against.

        Returns:
            An `ASTComparisonNode` representing this comparison, which has also
            been added to the `self.group`.
        """
        self.group.add(
            node := ASTComparisonNode(
                self, other, ASTOperatorNode.GREATER_THAN, self.group
            )
        )
        return node

    def __ge__(self, other) -> "ASTComparisonNode":
        """Creates a GREATER_THAN_OR_EQUAL comparison node.

        Args:
            other: The value or `ASTNode` to compare against.

        Returns:
            An `ASTComparisonNode` representing this comparison, which has also
            been added to the `self.group`.
        """
        self.group.add(
            node := ASTComparisonNode(
                self, other, ASTOperatorNode.GREATER_THAN_OR_EQUAL, self.group
            )
        )
        return node

    def __lt__(self, other) -> "ASTComparisonNode":
        """Creates a LESS_THAN comparison node.

        Args:
            other: The value or `ASTNode` to compare against.

        Returns:
            An `ASTComparisonNode` representing this comparison, which has also
            been added to the `self.group`.
        """
        self.group.add(
            node := ASTComparisonNode(
                self, other, ASTOperatorNode.LESS_THAN, self.group
            )
        )
        return node

    def __le__(self, other) -> "ASTComparisonNode":
        """Creates a LESS_THAN_OR_EQUAL comparison node.

        Args:
            other: The value or `ASTNode` to compare against.

        Returns:
            An `ASTComparisonNode` representing this comparison, which has also
            been added to the `self.group`.
        """
        self.group.add(
            node := ASTComparisonNode(
                self, other, ASTOperatorNode.LESS_THAN_OR_EQUAL, self.group
            )
        )
        return node


class ASTReferenceNode(ASTComparableNode):
    """Represents a reference to a model field in an AST query.

    This node is typically created when a model's field attribute (which is usually
    an `ommi.models.QueryField` descriptor) is used in a query expression.
    For example, in `User.name == "Alice"`, `User.name` would become an `ASTReferenceNode`.

    It stores the field name, the model class it belongs to, and the desired sorting
    order if this reference is used for sorting.
    """
    __match_args__ = ("field", "model")

    def __init__(self, field, model, ordering=ResultOrdering.ASCENDING):
        """Initializes an ASTReferenceNode.

        Args:
            field: The name of the field (e.g., "name").
            model: The `OmmiModel` subclass this field belongs to.
            ordering: The default `ResultOrdering` for this field if used in sorting.
                      Defaults to ASCENDING.
        """
        super().__init__(ASTGroupNode())
        self._field = field
        self._model = model
        self._ordering = ordering

    def _eq(self, other):
        """Custom equality check for comparing with another ASTReferenceNode.

        Considers field name, model type, and ordering.
        """
        return (
            self.field == other.field
            and self.model == other.model
            and self.ordering == other.ordering
        )

    def __iter__(self):
        yield from (self._field, self._model)

    @property
    def field(self):
        """The name of the database field this node refers to."""
        return self._field

    @property
    def model(self):
        """The `OmmiModel` class this node's field belongs to."""
        return self._model

    @property
    def ordering(self):
        """The `ResultOrdering` (ASCENDING/DESCENDING) for this reference, primarily for sorting."""
        return self._ordering

    @property
    def asc(self) -> "ASTReferenceNode":
        """Returns a new `ASTReferenceNode` for this field with ASCENDING order.

        Useful for explicitly specifying sort order: `my_query.sort(MyModel.field_name.asc)`
        """
        return ASTReferenceNode(self._field, self._model, ResultOrdering.ASCENDING)

    @property
    def desc(self) -> "ASTReferenceNode":
        """Returns a new `ASTReferenceNode` for this field with DESCENDING order.

        Useful for explicitly specifying sort order: `my_query.sort(MyModel.field_name.desc)`
        """
        return ASTReferenceNode(self._field, self._model, ResultOrdering.DESCENDING)

    def in_(self, values: list) -> "ASTComparisonNode":
        """Creates an IN comparison node for checking membership in a list.

        Args:
            values: A list of values to check membership against.

        Returns:
            An `ASTComparisonNode` representing this IN comparison.

        Example:
            ```python
            # Find users with specific statuses
            db.find(User.status.in_(["active", "pending"]))
            ```
        """
        self.group.add(
            node := ASTComparisonNode(self, values, ASTOperatorNode.IN, self.group)
        )
        return node

    def __hash__(self):
        return hash((self._field, self._model, self._ordering))

    def __repr__(self):
        return (
            f"<{type(self).__qualname__}"
            f" {self.model.__qualname__ if self.model else None}.{getattr(self._field, 'name', self._field)!r}>"
        )


class ASTLiteralNode(ASTComparableNode):
    """Represents a literal value in an AST query (e.g., a string, number, boolean).

    This node is created when a model field is compared to a direct value.
    For example, in `User.age == 18`, the `18` would become an `ASTLiteralNode`.

    Attributes:
        _value: The actual literal value being represented.
    """
    __match_args__ = ("value",)

    def __init__(self, value):
        """Initializes an ASTLiteralNode.

        Args:
            value: The literal value this node represents.
        """
        super().__init__(ASTGroupNode())
        self._value = value

    def _eq(self, other):
        """Custom equality check for comparing with another ASTLiteralNode.

        Compares the underlying `_value`.
        """
        if not isinstance(other, ASTLiteralNode):
            return NotImplemented

        return self._value == other._value

    def __iter__(self):
        """Allows the ASTLiteralNode to be iterated, yielding its single value."""
        yield self._value

    @property
    def value(self):
        """The literal value held by this node."""
        return self._value

    def __repr__(self):
        return f"{type(self).__name__}({self._value!r})"


class ASTComparisonNode(ASTComparableNode):
    """Represents a comparison operation in an AST query.

    A comparison typically involves a left-hand side (usually an `ASTReferenceNode`
    for a model field), an operator (`ASTOperatorNode`), and a right-hand side
    (usually an `ASTLiteralNode` for a value, or another `ASTReferenceNode` for
    field-to-field comparison).

    For example, `User.name == "Alice"` would be represented as an `ASTComparisonNode`
    with `User.name` as left, `ASTOperatorNode.EQUALS` as operator, and `"Alice"` as right.

    It inherits from `ASTComparableNode` itself, allowing comparisons to be chained
    (e.g., `(User.name == "A").And(User.age > 18)`), where the result of the first
    comparison becomes the context for the `And` method.
    """
    __match_args__ = ("left", "right", "operator")

    def __init__(
        self,
        left: ASTLiteralNode | ASTReferenceNode | Any,
        right: ASTLiteralNode | ASTReferenceNode | Any,
        operator: ASTOperatorNode,
        group=None,
    ):
        """Initializes an ASTComparisonNode.

        Args:
            left: The left operand (field reference or literal).
            right: The right operand (value or field reference).
            operator: The `ASTOperatorNode` defining the comparison type.
            group: An optional `ASTGroupNode` to associate with. If None, a new
                   one is created. This group is used when chaining comparisons
                   with `.And()` or `.Or()`.
        """
        super().__init__(group or ASTGroupNode())
        self._left = self._make_node(left)
        self._right = self._make_node(right)
        self._operator = operator

    def __iter__(self):
        """Iterates over the components of the comparison: left, operator, right."""
        yield self.left
        yield self.operator
        yield self.right

    @property
    def left(self):
        """The left operand of the comparison (an `ASTReferenceNode` or `ASTLiteralNode`)."""
        return self._left

    @property
    def right(self):
        """The right operand of the comparison (an `ASTReferenceNode` or `ASTLiteralNode`)."""
        return self._right

    @property
    def operator(self):
        """The `ASTOperatorNode` representing the type of comparison (e.g., EQUALS)."""
        return self._operator

    def __repr__(self):
        return (
            f"{type(self).__name__}("
            f"{self._left!r}, "
            f"{self._right!r}, "
            f"{self._operator})"
        )

    def and_(self, *comparisons: "ASTComparisonNode | SearchGroup | bool"):
        """Combines this comparison with others using an AND operator.

        Adds the current comparison node to its associated group (if not already added
        implicitly during creation) and then calls `and_()` on that group.

        Args:
            *comparisons: Other comparison nodes or groups to AND with.

        Returns:
            The `ASTGroupNode` containing this and the other comparisons.
        """
        self.group.add(self)
        return self.group.and_(*comparisons)

    def or_(self, *comparisons: "ASTComparisonNode | SearchGroup | bool"):
        """Combines this comparison with others using an OR operator.

        Adds the current comparison node to its associated group (if not already added
        implicitly during creation) and then calls `or_()` on that group.

        Args:
            *comparisons: Other comparison nodes or groups to OR with.

        Returns:
            The `ASTGroupNode` containing this and the other comparisons.
        """
        self.group.add(self)
        return self.group.or_(*comparisons)

    # Deprecated aliases for backwards compatibility
    And = and_
    Or = or_

    def _make_node(self, value):
        match value:
            case ASTComparableNode():
                return value

            case _:
                return ASTLiteralNode(value)


def where(
    *comparisons: "ASTComparisonNode | Type[models.DatabaseModel] | bool",
) -> ASTGroupNode:
    """Creates a new query group from one or more comparisons.

    This is the primary entry point for building complex queries. It takes one or more
    comparison nodes, model types, or boolean values and combines them into an
    `ASTGroupNode` that can be used for database operations.

    Args:
        *comparisons: One or more of:
            - ASTComparisonNode: Direct field comparisons (e.g., User.name == "Alice")
            - Type[DatabaseModel]: Model type to query all instances
            - bool: Static boolean value to always include/exclude

    Returns:
        ASTGroupNode: A new query group containing the provided comparisons.

    Example:
        ```python
        # Simple equality comparison
        query1 = where(User.name == "Alice")

        # Query all users
        query2 = where(User)

        # Complex query with multiple conditions
        query3 = where(User.age > 18, User.is_active == True)
        ```
    """
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


# Deprecated alias for backwards compatibility
when = where
