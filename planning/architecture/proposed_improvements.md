# Proposed Architecture Improvements

## Overview
This document outlines proposed improvements to Ommi's architecture that will address current issues while positioning the system for future growth and enhanced capabilities.

## Immediate Improvements (Phase 1)

### 1. Enhanced Result System

#### Current Problem
Inconsistent result wrapping causing `DBStatusNoResultException` errors and unreliable error handling.

#### Proposed Solution: Result Monad Pattern
```python
from typing import TypeVar, Generic, Union, Callable, Awaitable
from abc import ABC, abstractmethod

T = TypeVar('T')
E = TypeVar('E')

class Result(Generic[T, E], ABC):
    """Base result type implementing monadic operations"""
    
    @abstractmethod
    def is_success(self) -> bool:
        pass
    
    @abstractmethod
    def map(self, func: Callable[[T], U]) -> 'Result[U, E]':
        pass
    
    @abstractmethod
    def flat_map(self, func: Callable[[T], 'Result[U, E]']) -> 'Result[U, E]':
        pass

class Success(Result[T, E]):
    def __init__(self, value: T):
        self._value = value
    
    @property
    def value(self) -> T:
        return self._value
    
    def is_success(self) -> bool:
        return True
    
    def map(self, func: Callable[[T], U]) -> Result[U, E]:
        try:
            return Success(func(self._value))
        except Exception as e:
            return Failure(e)

class Failure(Result[T, E]):
    def __init__(self, error: E):
        self._error = error
    
    @property
    def error(self) -> E:
        return self._error
    
    def is_success(self) -> bool:
        return False
    
    def map(self, func: Callable[[T], U]) -> Result[U, E]:
        return Failure(self._error)

# Enhanced AsyncResultWrapper
class AsyncResultWrapper(Generic[T]):
    def __init__(self, future_result: Awaitable[Result[T, Exception]]):
        self._future_result = future_result
    
    async def __await__(self):
        return await self._future_result
    
    @property
    async def value(self) -> T:
        result = await self._future_result
        if result.is_success():
            return result.value
        raise result.error
    
    async def value_or(self, default: T) -> T:
        result = await self._future_result
        return result.value if result.is_success() else default
    
    async def map(self, func: Callable[[T], U]) -> 'AsyncResultWrapper[U]':
        result = await self._future_result
        return AsyncResultWrapper(asyncio.create_task(
            asyncio.coroutine(lambda: result.map(func))()
        ))
```

#### Benefits
- **Consistency:** All operations return wrapped results
- **Composability:** Results can be chained and transformed
- **Type Safety:** Compile-time guarantees about result handling
- **Error Propagation:** Automatic error propagation through chains

### 2. Complete Query AST Implementation

#### Current Problem
Missing operators and methods in AST nodes limiting query expressiveness.

#### Proposed Solution: Comprehensive Operator Support
```python
from enum import Enum
from typing import Any, List, Optional

class QueryOperator(Enum):
    # Comparison operators
    EQUALS = "eq"
    NOT_EQUALS = "ne"
    GREATER_THAN = "gt"
    GREATER_THAN_OR_EQUAL = "gte"
    LESS_THAN = "lt"
    LESS_THAN_OR_EQUAL = "lte"
    
    # Membership operators
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    
    # String operators
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    REGEX = "regex"
    ILIKE = "ilike"  # Case-insensitive like
    
    # Null operators
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"

class ASTReferenceNode:
    def __init__(self, field: str, model: Type):
        self.field = field
        self.model = model
    
    # Comparison operators
    def __eq__(self, other) -> 'ASTComparisonNode':
        return ASTComparisonNode(self, QueryOperator.EQUALS, other)
    
    def __ne__(self, other) -> 'ASTComparisonNode':
        return ASTComparisonNode(self, QueryOperator.NOT_EQUALS, other)
    
    def __gt__(self, other) -> 'ASTComparisonNode':
        return ASTComparisonNode(self, QueryOperator.GREATER_THAN, other)
    
    def __ge__(self, other) -> 'ASTComparisonNode':
        return ASTComparisonNode(self, QueryOperator.GREATER_THAN_OR_EQUAL, other)
    
    def __lt__(self, other) -> 'ASTComparisonNode':
        return ASTComparisonNode(self, QueryOperator.LESS_THAN, other)
    
    def __le__(self, other) -> 'ASTComparisonNode':
        return ASTComparisonNode(self, QueryOperator.LESS_THAN_OR_EQUAL, other)
    
    # Membership operators
    def in_(self, values: List[Any]) -> 'ASTComparisonNode':
        return ASTComparisonNode(self, QueryOperator.IN, values)
    
    def not_in(self, values: List[Any]) -> 'ASTComparisonNode':
        return ASTComparisonNode(self, QueryOperator.NOT_IN, values)
    
    def contains(self, value: Any) -> 'ASTComparisonNode':
        return ASTComparisonNode(self, QueryOperator.CONTAINS, value)
    
    # String operators
    def starts_with(self, prefix: str) -> 'ASTComparisonNode':
        return ASTComparisonNode(self, QueryOperator.STARTS_WITH, prefix)
    
    def ends_with(self, suffix: str) -> 'ASTComparisonNode':
        return ASTComparisonNode(self, QueryOperator.ENDS_WITH, suffix)
    
    def regex(self, pattern: str) -> 'ASTComparisonNode':
        return ASTComparisonNode(self, QueryOperator.REGEX, pattern)
    
    # Null operators
    def is_null(self) -> 'ASTComparisonNode':
        return ASTComparisonNode(self, QueryOperator.IS_NULL, None)
    
    def is_not_null(self) -> 'ASTComparisonNode':
        return ASTComparisonNode(self, QueryOperator.IS_NOT_NULL, None)
    
    # Logical operators
    def __and__(self, other) -> 'ASTLogicalNode':
        return ASTLogicalNode(LogicalOperator.AND, [self, other])
    
    def __or__(self, other) -> 'ASTLogicalNode':
        return ASTLogicalNode(LogicalOperator.OR, [self, other])
    
    def __invert__(self) -> 'ASTLogicalNode':
        return ASTLogicalNode(LogicalOperator.NOT, [self])
```

#### Usage Examples
```python
# Enhanced query capabilities
users = await db.find(
    (User.name.starts_with("A")) & 
    (User.age.in_([18, 19, 20])) &
    (User.email.is_not_null())
).fetch.all()

# String search
posts = await db.find(
    Post.content.contains("python") |
    Post.title.regex(r".*[Pp]ython.*")
).fetch.all()

# Complex conditions
active_users = await db.find(
    ~User.deleted_at.is_null() &
    User.last_login > datetime.now() - timedelta(days=30)
).fetch.all()
```

### 3. Robust Type System

#### Current Problem
Type validation fails with modern Python type annotations and generic types.

#### Proposed Solution: Advanced Type Handling
```python
import typing
from typing import get_origin, get_args, Union, Optional, List, Dict, Any
import inspect

class TypeSystem:
    """Advanced type system for handling all Python type annotations"""
    
    @staticmethod
    def is_optional(annotation: Any) -> bool:
        """Check if type is Optional[T] (Union[T, None])"""
        origin = get_origin(annotation)
        if origin is Union:
            args = get_args(annotation)
            return len(args) == 2 and type(None) in args
        return False
    
    @staticmethod
    def get_optional_inner_type(annotation: Any) -> Any:
        """Get T from Optional[T]"""
        if TypeSystem.is_optional(annotation):
            args = get_args(annotation)
            return next(arg for arg in args if arg is not type(None))
        return annotation
    
    @staticmethod
    def is_generic_list(annotation: Any) -> bool:
        """Check if type is List[T]"""
        return get_origin(annotation) is list
    
    @staticmethod
    def get_list_item_type(annotation: Any) -> Any:
        """Get T from List[T]"""
        if TypeSystem.is_generic_list(annotation):
            args = get_args(annotation)
            return args[0] if args else Any
        return Any
    
    @staticmethod
    def validate_value(value: Any, expected_type: Any) -> bool:
        """Validate that value matches expected type"""
        if expected_type is Any:
            return True
        
        # Handle Optional types
        if TypeSystem.is_optional(expected_type):
            if value is None:
                return True
            expected_type = TypeSystem.get_optional_inner_type(expected_type)
        
        # Handle generic types
        origin = get_origin(expected_type)
        if origin is not None:
            if origin is list:
                if not isinstance(value, list):
                    return False
                item_type = TypeSystem.get_list_item_type(expected_type)
                return all(TypeSystem.validate_value(item, item_type) for item in value)
            
            # Add more generic type handlers as needed
            
        # Handle basic types
        try:
            return isinstance(value, expected_type)
        except TypeError:
            # Handle cases where isinstance doesn't work (e.g., with some generics)
            return True  # Fall back to permissive validation

# Usage in field metadata
class FieldMetadata:
    def __init__(self, name: str, type_annotation: Any, default: Any = None):
        self.name = name
        self.type_annotation = type_annotation
        self.default = default
        self.is_optional = TypeSystem.is_optional(type_annotation)
        self.inner_type = TypeSystem.get_optional_inner_type(type_annotation)
    
    def validate_value(self, value: Any) -> bool:
        return TypeSystem.validate_value(value, self.type_annotation)
```

## Medium-Term Improvements (Phase 2)

### 1. Query Builder API

#### Proposed Enhancement: Fluent Query Interface
```python
class QueryBuilder(Generic[T]):
    """Fluent interface for building complex queries"""
    
    def __init__(self, model: Type[T], driver: DatabaseDriver):
        self._model = model
        self._driver = driver
        self._where_conditions: List[ASTNode] = []
        self._order_by: List[Tuple[str, OrderDirection]] = []
        self._limit_value: Optional[int] = None
        self._offset_value: Optional[int] = None
    
    def where(self, condition: ASTNode) -> 'QueryBuilder[T]':
        """Add WHERE condition"""
        self._where_conditions.append(condition)
        return self
    
    def order_by(self, field: str, direction: OrderDirection = OrderDirection.ASC) -> 'QueryBuilder[T]':
        """Add ORDER BY clause"""
        self._order_by.append((field, direction))
        return self
    
    def limit(self, count: int) -> 'QueryBuilder[T]':
        """Add LIMIT clause"""
        self._limit_value = count
        return self
    
    def offset(self, count: int) -> 'QueryBuilder[T]':
        """Add OFFSET clause"""
        self._offset_value = count
        return self
    
    async def fetch_all(self) -> List[T]:
        """Execute query and return all results"""
        query = self._build_query()
        result = await self._driver.fetch(query)
        return await result.value
    
    async def fetch_one(self) -> Optional[T]:
        """Execute query and return first result"""
        query = self._build_query()
        results = await self._driver.fetch(query.limit(1))
        result_list = await results.value
        return result_list[0] if result_list else None
    
    async def count(self) -> int:
        """Execute count query"""
        query = self._build_count_query()
        result = await self._driver.count(query)
        return await result.value

# Usage examples
users = await (db.query(User)
    .where(User.age > 18)
    .where(User.active == True)
    .order_by("name")
    .limit(10)
    .fetch_all())

user = await (db.query(User)
    .where(User.email == "alice@example.com")
    .fetch_one())
```

### 2. Enhanced Transaction Management

#### Proposed Solution: Comprehensive Transaction System
```python
from contextlib import asynccontextmanager
from enum import Enum
from typing import Optional, Dict, Any

class IsolationLevel(Enum):
    READ_UNCOMMITTED = "READ_UNCOMMITTED"
    READ_COMMITTED = "READ_COMMITTED"
    REPEATABLE_READ = "REPEATABLE_READ"
    SERIALIZABLE = "SERIALIZABLE"

class TransactionOptions:
    def __init__(
        self,
        isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED,
        timeout: Optional[int] = None,
        retry_on_conflict: bool = False,
        max_retries: int = 3
    ):
        self.isolation_level = isolation_level
        self.timeout = timeout
        self.retry_on_conflict = retry_on_conflict
        self.max_retries = max_retries

class Transaction:
    def __init__(self, driver: DatabaseDriver, options: TransactionOptions):
        self._driver = driver
        self._options = options
        self._savepoints: List[str] = []
        self._is_active = False
        self._connection = None
    
    async def begin(self) -> None:
        """Start the transaction"""
        self._connection = await self._driver.get_connection()
        await self._connection.begin_transaction(self._options.isolation_level)
        self._is_active = True
    
    async def commit(self) -> None:
        """Commit the transaction"""
        if self._is_active:
            await self._connection.commit()
            self._is_active = False
    
    async def rollback(self) -> None:
        """Rollback the transaction"""
        if self._is_active:
            await self._connection.rollback()
            self._is_active = False
    
    async def savepoint(self, name: str) -> None:
        """Create a savepoint"""
        await self._connection.savepoint(name)
        self._savepoints.append(name)
    
    async def rollback_to_savepoint(self, name: str) -> None:
        """Rollback to a specific savepoint"""
        await self._connection.rollback_to_savepoint(name)
        # Remove savepoints created after this one
        try:
            index = self._savepoints.index(name)
            self._savepoints = self._savepoints[:index + 1]
        except ValueError:
            pass

# Enhanced transaction context manager
@asynccontextmanager
async def transaction(
    driver: DatabaseDriver,
    options: Optional[TransactionOptions] = None
):
    """Enhanced transaction context manager with retry logic"""
    options = options or TransactionOptions()
    
    for attempt in range(options.max_retries + 1):
        tx = Transaction(driver, options)
        try:
            await tx.begin()
            yield tx
            await tx.commit()
            break
        except ConflictError as e:
            await tx.rollback()
            if not options.retry_on_conflict or attempt == options.max_retries:
                raise
            # Exponential backoff before retry
            await asyncio.sleep(2 ** attempt * 0.1)
        except Exception as e:
            await tx.rollback()
            raise

# Usage examples
async with transaction(db, TransactionOptions(
    isolation_level=IsolationLevel.SERIALIZABLE,
    retry_on_conflict=True,
    max_retries=3
)) as tx:
    user = User(name="Alice")
    await db.add(user)
    
    # Nested savepoint
    await tx.savepoint("before_posts")
    try:
        post = Post(title="Hello", author_id=user.id)
        await db.add(post)
    except Exception:
        await tx.rollback_to_savepoint("before_posts")
```

### 3. Advanced Schema Management

#### Proposed Solution: Migration System
```python
from typing import List, Callable, Awaitable
from datetime import datetime
from abc import ABC, abstractmethod

class Migration(ABC):
    """Base class for database migrations"""
    
    def __init__(self, version: str, description: str):
        self.version = version
        self.description = description
        self.created_at = datetime.now()
    
    @abstractmethod
    async def up(self, schema: 'SchemaManager') -> None:
        """Apply the migration"""
        pass
    
    @abstractmethod
    async def down(self, schema: 'SchemaManager') -> None:
        """Reverse the migration"""
        pass

class SchemaManager:
    """Manages database schema evolution"""
    
    def __init__(self, driver: DatabaseDriver):
        self._driver = driver
        self._migrations: List[Migration] = []
    
    def add_migration(self, migration: Migration) -> None:
        """Register a migration"""
        self._migrations.append(migration)
        self._migrations.sort(key=lambda m: m.version)
    
    async def migrate_up(self, target_version: Optional[str] = None) -> None:
        """Apply migrations up to target version"""
        current_version = await self._get_current_version()
        
        for migration in self._migrations:
            if self._should_apply_migration(migration, current_version, target_version):
                async with transaction(self._driver) as tx:
                    await migration.up(self)
                    await self._record_migration(migration)
    
    async def migrate_down(self, target_version: str) -> None:
        """Rollback migrations to target version"""
        current_version = await self._get_current_version()
        
        for migration in reversed(self._migrations):
            if self._should_rollback_migration(migration, current_version, target_version):
                async with transaction(self._driver) as tx:
                    await migration.down(self)
                    await self._remove_migration_record(migration)
    
    async def create_table(self, model: Type) -> None:
        """Create table for model"""
        await self._driver.create_table(model)
    
    async def drop_table(self, model: Type) -> None:
        """Drop table for model"""
        await self._driver.drop_table(model)
    
    async def add_column(self, model: Type, column_name: str, column_type: Type) -> None:
        """Add column to table"""
        await self._driver.add_column(model, column_name, column_type)
    
    async def drop_column(self, model: Type, column_name: str) -> None:
        """Drop column from table"""
        await self._driver.drop_column(model, column_name)

# Example migration
class AddUserEmailMigration(Migration):
    def __init__(self):
        super().__init__("001", "Add email column to users table")
    
    async def up(self, schema: SchemaManager) -> None:
        await schema.add_column(User, "email", str)
    
    async def down(self, schema: SchemaManager) -> None:
        await schema.drop_column(User, "email")

# Usage
schema = SchemaManager(db)
schema.add_migration(AddUserEmailMigration())
await schema.migrate_up()
```

## Long-Term Improvements (Phase 3)

### 1. Performance Optimization Framework

#### Connection Pool Optimization
```python
class ConnectionPool:
    def __init__(
        self,
        min_connections: int = 5,
        max_connections: int = 20,
        connection_timeout: float = 30.0,
        idle_timeout: float = 300.0
    ):
        self._min_connections = min_connections
        self._max_connections = max_connections
        self._connection_timeout = connection_timeout
        self._idle_timeout = idle_timeout
        self._pool: asyncio.Queue = asyncio.Queue(maxsize=max_connections)
        self._active_connections: Set[Connection] = set()
        self._connection_stats = ConnectionStats()
    
    async def get_connection(self) -> Connection:
        """Get connection with automatic pool management"""
        try:
            connection = await asyncio.wait_for(
                self._pool.get(), 
                timeout=self._connection_timeout
            )
            if await connection.is_healthy():
                self._active_connections.add(connection)
                return connection
            else:
                # Connection is stale, create new one
                await connection.close()
        except asyncio.TimeoutError:
            if len(self._active_connections) < self._max_connections:
                connection = await self._create_connection()
                self._active_connections.add(connection)
                return connection
            raise ConnectionPoolExhausted()
    
    async def return_connection(self, connection: Connection) -> None:
        """Return connection to pool"""
        self._active_connections.discard(connection)
        if await connection.is_healthy():
            await self._pool.put(connection)
        else:
            await connection.close()
```

#### Query Caching System
```python
class QueryCache:
    def __init__(self, max_size: int = 1000, ttl: int = 300):
        self._cache: Dict[str, CacheEntry] = {}
        self._max_size = max_size
        self._ttl = ttl
        self._stats = CacheStats()
    
    async def get(self, query_key: str) -> Optional[Any]:
        """Get cached query result"""
        entry = self._cache.get(query_key)
        if entry and not entry.is_expired():
            self._stats.hit()
            return entry.value
        
        if entry:
            del self._cache[query_key]
        
        self._stats.miss()
        return None
    
    async def set(self, query_key: str, value: Any) -> None:
        """Cache query result"""
        if len(self._cache) >= self._max_size:
            await self._evict_lru()
        
        self._cache[query_key] = CacheEntry(value, self._ttl)
```

### 2. Plugin Architecture

#### Proposed Solution: Extensible Plugin System
```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class DriverPlugin(Protocol):
    """Protocol for database driver plugins"""
    
    def get_driver_name(self) -> str:
        """Return the name of the driver"""
        ...
    
    async def create_driver(self, config: Dict[str, Any]) -> DatabaseDriver:
        """Create driver instance from configuration"""
        ...
    
    def get_config_schema(self) -> Dict[str, Any]:
        """Return JSON schema for driver configuration"""
        ...

class PluginManager:
    def __init__(self):
        self._drivers: Dict[str, DriverPlugin] = {}
        self._middleware: List[Middleware] = []
    
    def register_driver(self, plugin: DriverPlugin) -> None:
        """Register a database driver plugin"""
        name = plugin.get_driver_name()
        self._drivers[name] = plugin
    
    def get_driver(self, name: str) -> Optional[DriverPlugin]:
        """Get registered driver plugin"""
        return self._drivers.get(name)
    
    def register_middleware(self, middleware: Middleware) -> None:
        """Register middleware for request processing"""
        self._middleware.append(middleware)

# Usage
plugin_manager = PluginManager()

# Third-party driver plugin
class RedisDriverPlugin:
    def get_driver_name(self) -> str:
        return "redis"
    
    async def create_driver(self, config: Dict[str, Any]) -> DatabaseDriver:
        return RedisDriver(config)

plugin_manager.register_driver(RedisDriverPlugin())
```

## Implementation Strategy

### Phase 1: Critical Fixes (4-6 weeks)
1. **Week 1-2:** Implement enhanced result system
2. **Week 3-4:** Complete query AST implementation
3. **Week 5-6:** Robust type system and basic transaction fixes

### Phase 2: Enhanced Features (3-4 weeks)
1. **Week 1-2:** Query builder API and advanced transactions
2. **Week 3-4:** Schema management and migration system

### Phase 3: Advanced Features (4-6 weeks)
1. **Week 1-3:** Performance optimization framework
2. **Week 4-6:** Plugin architecture and ecosystem tools

## Success Metrics

### Technical Metrics
- **Result Consistency:** 100% operations use enhanced result system
- **Query Completeness:** All planned operators implemented and tested
- **Type Safety:** Zero runtime type errors in normal operation
- **Performance:** <5% overhead compared to direct drivers

### Quality Metrics
- **Test Coverage:** >95% code coverage
- **API Stability:** No breaking changes in public APIs
- **Documentation:** Complete coverage of all features
- **Community:** Active plugin ecosystem developing

These improvements will transform Ommi from a promising but unstable framework into a production-ready, feature-complete ORM that can compete with established solutions while maintaining its unique advantages.