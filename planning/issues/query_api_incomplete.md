# Query API Incomplete Implementation

## Issue Classification
**Priority:** CRITICAL  
**Status:** Missing core functionality  
**Impact:** Query capabilities severely limited  
**Affected Components:** `ommi/query_ast.py`, all driver query implementations

## Problem Description

### Missing Operators and Methods
The Query AST system is missing essential operators and methods that users expect from a modern ORM, causing runtime errors and limiting query expressiveness.

### Primary Error Types
```python
# AttributeError: Missing methods
AttributeError: 'ASTReferenceNode' object has no attribute 'contains'
AttributeError: 'ASTReferenceNode' object has no attribute 'in_'

# TypeError: Object not callable or subscriptable
TypeError: 'ASTReferenceNode' object is not callable
TypeError: bad operand type for unary ~: 'ASTReferenceNode'
TypeError: 'coroutine' object is not subscriptable
```

## Missing Functionality Analysis

### 1. Missing Comparison Operators

#### Contains Operations
```python
# Currently broken - these don't exist
User.name.contains("alice")      # AttributeError
User.tags.contains("python")     # AttributeError
User.bio.not_contains("spam")    # AttributeError
```

#### Membership Operations
```python
# Currently broken - these don't exist
User.age.in_([18, 19, 20, 21])   # AttributeError
User.status.not_in_(["banned", "suspended"])  # AttributeError
```

#### String Operations
```python
# Currently broken - these don't exist
User.name.starts_with("A")       # AttributeError
User.email.ends_with(".com")     # AttributeError
User.name.ilike("%alice%")       # AttributeError (case-insensitive like)
```

#### Null Operations
```python
# Currently broken - these don't exist
User.deleted_at.is_null()        # AttributeError
User.verified_at.is_not_null()   # AttributeError
```

### 2. Missing Logical Operators

#### Negation Operator
```python
# Currently broken
~(User.active == True)           # TypeError: bad operand type for unary ~
```

#### Complex Logical Combinations
```python
# Limited logical operator support
complex_query = (
    (User.age > 18) & 
    ~User.name.contains("admin") &  # Broken
    User.email.is_not_null()        # Broken
)
```

### 3. Coroutine Handling Issues

#### Async Query Chain Problems
```python
# TypeError: 'coroutine' object is not subscriptable
async def broken_query():
    result = db.find(User.age > 18).fetch()  # Returns coroutine
    return result[0]  # Trying to subscript before awaiting

# Should be:
async def working_query():
    result = await db.find(User.age > 18).fetch()
    return result[0]  # Now result is awaited and subscriptable
```

#### Improper Await Patterns
```python
# Current broken patterns in codebase (inferred)
class SomeQueryHandler:
    def process_query(self):
        # Missing await
        result = self.execute_query()  # Returns coroutine
        return result.value  # Error: coroutine has no attribute 'value'
```

## Root Cause Analysis

### 1. Incomplete AST Node Implementation
The `ASTReferenceNode` class is missing operator methods that users expect:

```python
# Current incomplete implementation (inferred)
class ASTReferenceNode:
    def __init__(self, field: str, model: Type):
        self.field = field
        self.model = model
    
    # Only basic operators implemented
    def __eq__(self, other):
        return ASTComparisonNode(self, ASTOperatorNode.EQUALS, other)
    
    def __ne__(self, other):
        return ASTComparisonNode(self, ASTOperatorNode.NOT_EQUALS, other)
    
    # Missing: contains, in_, starts_with, ends_with, is_null, etc.
    # Missing: __invert__ for ~ operator
    # Missing: __call__ for callable syntax
```

### 2. Driver Translation Gaps
Even if AST nodes existed, drivers lack translation logic for advanced operators:

```python
# Current driver limitation (inferred)
SQLITE_OPERATORS = {
    ASTOperatorNode.EQUALS: "=",
    ASTOperatorNode.NOT_EQUALS: "!=",
    # Missing: CONTAINS, IN, STARTS_WITH, etc.
}

def translate_operator(operator):
    if operator not in SQLITE_OPERATORS:
        raise NotImplementedError(f"Operator {operator} not supported")
```

### 3. Async Pattern Inconsistencies
Mixed async/sync patterns and improper coroutine handling throughout the codebase.

## Affected Use Cases

### 1. Text Search Queries
```python
# Users expect these to work but they don't
blog_posts = await db.find(
    Post.title.contains("python") |
    Post.content.contains("programming")
).fetch.all()

user_search = await db.find(
    User.name.starts_with("John") &
    User.email.ends_with("@company.com")
).fetch.all()
```

### 2. Membership Queries
```python
# Common filtering patterns that are broken
active_users = await db.find(
    User.status.in_(["active", "premium"]) &
    User.role.not_in_(["banned", "suspended"])
).fetch.all()

valid_ages = await db.find(
    User.age.in_(range(18, 65))
).fetch.all()
```

### 3. Null Checking
```python
# Essential database operations that don't work
incomplete_profiles = await db.find(
    User.bio.is_null() |
    User.avatar.is_null()
).fetch.all()

verified_users = await db.find(
    User.email_verified_at.is_not_null() &
    User.phone_verified_at.is_not_null()
).fetch.all()
```

### 4. Complex Filtering
```python
# Real-world filtering scenarios
filtered_posts = await db.find(
    ~Post.deleted_at.is_null() &  # Not deleted
    Post.published == True &
    Post.tags.contains("tutorial") &
    Post.view_count > 100
).fetch.all()
```

## Implementation Plan

### Phase 1: Core Operator Implementation (Week 1)

#### 1.1 Extend ASTReferenceNode
```python
class ASTReferenceNode:
    # Membership operators
    def in_(self, values: List[Any]) -> ASTComparisonNode:
        return ASTComparisonNode(self, ASTOperatorNode.IN, values)
    
    def not_in(self, values: List[Any]) -> ASTComparisonNode:
        return ASTComparisonNode(self, ASTOperatorNode.NOT_IN, values)
    
    # String operators
    def contains(self, value: str) -> ASTComparisonNode:
        return ASTComparisonNode(self, ASTOperatorNode.CONTAINS, value)
    
    def starts_with(self, prefix: str) -> ASTComparisonNode:
        return ASTComparisonNode(self, ASTOperatorNode.STARTS_WITH, prefix)
    
    def ends_with(self, suffix: str) -> ASTComparisonNode:
        return ASTComparisonNode(self, ASTOperatorNode.ENDS_WITH, suffix)
    
    # Null operators
    def is_null(self) -> ASTComparisonNode:
        return ASTComparisonNode(self, ASTOperatorNode.IS_NULL, None)
    
    def is_not_null(self) -> ASTComparisonNode:
        return ASTComparisonNode(self, ASTOperatorNode.IS_NOT_NULL, None)
    
    # Logical operators
    def __invert__(self) -> ASTLogicalNode:
        return ASTLogicalNode(ASTLogicalOperator.NOT, [self])
```

#### 1.2 Extend Operator Enums
```python
class ASTOperatorNode(Enum):
    # Existing operators
    EQUALS = "eq"
    NOT_EQUALS = "ne"
    
    # New operators
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    REGEX = "regex"
    ILIKE = "ilike"
```

### Phase 2: Driver Translation Support (Week 1-2)

#### 2.1 SQLite Operator Translation
```python
SQLITE_OPERATORS = {
    # Existing
    ASTOperatorNode.EQUALS: "=",
    ASTOperatorNode.NOT_EQUALS: "!=",
    
    # New operators
    ASTOperatorNode.IN: "IN",
    ASTOperatorNode.NOT_IN: "NOT IN", 
    ASTOperatorNode.CONTAINS: "LIKE",  # Translate to %value%
    ASTOperatorNode.STARTS_WITH: "LIKE",  # Translate to value%
    ASTOperatorNode.ENDS_WITH: "LIKE",  # Translate to %value
    ASTOperatorNode.IS_NULL: "IS NULL",
    ASTOperatorNode.IS_NOT_NULL: "IS NOT NULL",
    ASTOperatorNode.REGEX: "REGEXP",
    ASTOperatorNode.ILIKE: "LIKE COLLATE NOCASE",
}

def translate_contains(field: str, value: str) -> Tuple[str, List[Any]]:
    return f"{field} LIKE ?", [f"%{value}%"]

def translate_starts_with(field: str, value: str) -> Tuple[str, List[Any]]:
    return f"{field} LIKE ?", [f"{value}%"]
```

#### 2.2 MongoDB Operator Translation
```python
MONGO_OPERATORS = {
    ASTOperatorNode.EQUALS: "$eq",
    ASTOperatorNode.IN: "$in",
    ASTOperatorNode.NOT_IN: "$nin",
    ASTOperatorNode.CONTAINS: "$regex",  # Translate to regex
    ASTOperatorNode.IS_NULL: "$eq",  # {field: null}
    ASTOperatorNode.IS_NOT_NULL: "$ne",  # {field: {$ne: null}}
}

def translate_contains(field: str, value: str) -> Dict[str, Any]:
    return {field: {"$regex": value, "$options": "i"}}

def translate_starts_with(field: str, value: str) -> Dict[str, Any]:
    return {field: {"$regex": f"^{value}", "$options": "i"}}
```

### Phase 3: Async/Await Fixes (Week 2)

#### 3.1 Audit Coroutine Usage
```python
# Find and fix patterns like this:
class QueryHandler:
    async def execute_query(self):
        # Bad: not awaiting coroutine
        result = self.some_async_operation()
        return result.value  # Error
        
    async def execute_query_fixed(self):
        # Good: properly awaiting
        result = await self.some_async_operation()
        return result.value
```

#### 3.2 Fix Query Chain Handling
```python
class QueryBuilder:
    async def fetch(self):
        # Ensure this returns awaitable result properly
        return AsyncResultWrapper(self._execute_query())
    
    async def _execute_query(self):
        # Proper async implementation
        raw_result = await self._driver.execute(self._query)
        return DatabaseResult.Success(raw_result)
```

## Testing Strategy

### Unit Tests for New Operators
```python
class TestQueryOperators:
    def test_contains_operator(self):
        query = User.name.contains("alice")
        assert isinstance(query, ASTComparisonNode)
        assert query.operator == ASTOperatorNode.CONTAINS
    
    def test_in_operator(self):
        query = User.age.in_([18, 19, 20])
        assert isinstance(query, ASTComparisonNode)
        assert query.operator == ASTOperatorNode.IN
    
    def test_negation_operator(self):
        query = ~(User.active == True)
        assert isinstance(query, ASTLogicalNode)
        assert query.operator == ASTLogicalOperator.NOT
```

### Integration Tests with Database
```python
class TestQueryIntegration:
    async def test_contains_with_sqlite(self):
        users = await db.find(User.name.contains("alice")).fetch.all()
        assert all("alice" in user.name.lower() for user in users)
    
    async def test_in_operator_with_sqlite(self):
        users = await db.find(User.age.in_([18, 19, 20])).fetch.all()
        assert all(user.age in [18, 19, 20] for user in users)
    
    async def test_null_checks_with_sqlite(self):
        users = await db.find(User.email.is_not_null()).fetch.all()
        assert all(user.email is not None for user in users)
```

### Cross-Driver Compatibility Tests
```python
@pytest.mark.parametrize("driver", [SQLiteDriver, PostgreSQLDriver, MongoDriver])
class TestCrossDriverOperators:
    async def test_contains_across_drivers(self, driver):
        async with driver.from_config(config) as db:
            users = await db.find(User.name.contains("test")).fetch.all()
            # Should work identically across all drivers
```

## Success Criteria

### Functional Requirements
- **All missing operators implemented** and working
- **Consistent behavior across drivers** for all operators
- **No runtime errors** for documented query patterns
- **Proper async/await handling** throughout query system

### Performance Requirements
- **Query translation overhead** <1ms per operator
- **No performance regression** compared to existing operators
- **Efficient SQL/NoSQL generation** for all new operators

### API Requirements
- **Intuitive method names** matching common ORM patterns
- **Type hints** for all new methods
- **Comprehensive documentation** with examples
- **Backwards compatibility** with existing query patterns

## Risk Mitigation

### Breaking Changes
- **Gradual rollout** - Add new operators without changing existing ones
- **Feature flags** - Allow disabling new operators if issues arise
- **Comprehensive testing** - Ensure existing functionality not affected

### Performance Impact
- **Benchmark new operators** against simple alternatives
- **Optimize query translation** for common patterns
- **Monitor query complexity** to prevent inefficient queries

This query API completion is essential for making Ommi competitive with other ORMs and meeting user expectations for query expressiveness.