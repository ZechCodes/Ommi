# SQLite Driver Issues

## Issue Classification
**Priority:** HIGH  
**Status:** Multiple syntax and feature gaps  
**Impact:** Primary testing driver unreliable  
**Affected Components:** `ommi/ext/drivers/sqlite/`

## Problem Description

### Overview
The SQLite driver, which serves as the primary driver for development and testing, has multiple critical issues that make it unreliable. These issues prevent proper testing of other components and limit the framework's usability.

### Primary Issue Categories
1. **SQL Syntax Errors** - Reserved keywords and improper escaping
2. **Transaction Limitations** - Nested transaction failures  
3. **Type System Issues** - Runtime type validation failures

## SQL Syntax Issues

### 1. Reserved Keyword Problems

#### Problem Description
The SQLite driver generates SQL that uses reserved keywords as table or column names without proper escaping, causing syntax errors.

#### Error Examples
```sql
-- Current broken output
CREATE TABLE Order (
    id INTEGER PRIMARY KEY,
    total REAL
);
-- sqlite3.OperationalError: near "Order": syntax error

CREATE TABLE User (
    id INTEGER PRIMARY KEY,
    index INTEGER  -- "index" is reserved
);
-- sqlite3.OperationalError: near "index": syntax error
```

#### Root Cause
The schema generation code doesn't check for or escape SQL reserved keywords:

```python
# Current broken implementation (inferred)
def create_table_sql(model_class):
    table_name = model_class.__name__  # No escaping
    columns = []
    for field_name, field_type in get_fields(model_class):
        column_sql = f"{field_name} {sql_type}"  # No escaping
        columns.append(column_sql)
    
    return f"CREATE TABLE {table_name} ({', '.join(columns)})"
```

#### Solution Strategy
```python
# Proposed fix
SQLITE_RESERVED_KEYWORDS = {
    'order', 'index', 'group', 'where', 'select', 'from', 'join',
    'inner', 'outer', 'left', 'right', 'on', 'and', 'or', 'not',
    'in', 'like', 'between', 'is', 'null', 'true', 'false',
    'create', 'drop', 'alter', 'table', 'column', 'primary', 'key',
    'foreign', 'references', 'unique', 'check', 'default'
}

def escape_identifier(identifier: str) -> str:
    """Escape SQL identifier if it's a reserved keyword"""
    if identifier.lower() in SQLITE_RESERVED_KEYWORDS:
        return f'"{identifier}"'
    return identifier

def create_table_sql(model_class):
    table_name = escape_identifier(model_class.__name__)
    columns = []
    for field_name, field_type in get_fields(model_class):
        escaped_name = escape_identifier(field_name)
        column_sql = f"{escaped_name} {sql_type}"
        columns.append(column_sql)
    
    return f"CREATE TABLE {table_name} ({', '.join(columns)})"
```

### 2. Query Generation Issues

#### Problem Description
Dynamic query generation creates malformed SQL in various scenarios.

#### Examples
```python
# Broken query generation (inferred current state)
def build_where_clause(conditions):
    # Missing proper parameter binding
    where_parts = []
    for field, value in conditions:
        where_parts.append(f"{field} = {value}")  # SQL injection risk
    return " AND ".join(where_parts)

# Should be:
def build_where_clause(conditions):
    where_parts = []
    params = []
    for field, value in conditions:
        escaped_field = escape_identifier(field)
        where_parts.append(f"{escaped_field} = ?")
        params.append(value)
    return " AND ".join(where_parts), params
```

## Transaction Limitations

### 1. Nested Transaction Failures

#### Problem Description
SQLite doesn't support true nested transactions, but the driver attempts to create them anyway, causing errors.

#### Error Example
```python
# This fails in SQLite
async with db.transaction():
    await db.add(user1)
    
    async with db.transaction():  # Nested transaction
        await db.add(user2)
        # sqlite3.OperationalError: cannot start a transaction within a transaction
```

#### Root Cause
The transaction implementation doesn't account for SQLite's limitations:

```python
# Current broken implementation (inferred)
class SQLiteTransaction:
    async def begin(self):
        await self.connection.execute("BEGIN TRANSACTION")  # Always tries to begin
    
    async def commit(self):
        await self.connection.execute("COMMIT")
    
    async def rollback(self):
        await self.connection.execute("ROLLBACK")
```

#### Solution Strategy
Implement savepoint-based nested transaction emulation:

```python
class SQLiteTransaction:
    def __init__(self):
        self.savepoint_counter = 0
        self.is_nested = False
    
    async def begin(self):
        if self.is_in_transaction():
            # Use savepoint for nested transaction
            self.savepoint_counter += 1
            savepoint_name = f"sp_{self.savepoint_counter}"
            await self.connection.execute(f"SAVEPOINT {savepoint_name}")
            self.is_nested = True
        else:
            # Start main transaction
            await self.connection.execute("BEGIN TRANSACTION")
    
    async def commit(self):
        if self.is_nested:
            # Release savepoint
            savepoint_name = f"sp_{self.savepoint_counter}"
            await self.connection.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            self.savepoint_counter -= 1
        else:
            await self.connection.execute("COMMIT")
    
    async def rollback(self):
        if self.is_nested:
            # Rollback to savepoint
            savepoint_name = f"sp_{self.savepoint_counter}"
            await self.connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            self.savepoint_counter -= 1
        else:
            await self.connection.execute("ROLLBACK")
```

### 2. Transaction Isolation Problems

#### Problem Description
Transaction isolation is not working correctly, allowing uncommitted changes to be visible outside transaction boundaries.

#### Error Example
```python
# This test fails - outside connection sees uncommitted data
async with db.transaction():
    user = User(name="Alice")
    await db.add(user)
    
    # This should NOT see the uncommitted user
    outside_users = await other_connection.find(User.name == "Alice").fetch.all()
    assert len(outside_users) == 0  # FAILS - sees uncommitted data
```

#### Root Cause Analysis
- **Connection sharing:** Transactions may be sharing connections incorrectly
- **Isolation level:** Database isolation level not properly configured
- **Connection pooling:** Pool may be reusing connections across transactions

#### Solution Strategy
```python
class SQLiteDriver:
    async def transaction(self):
        # Ensure each transaction gets its own connection
        connection = await self.get_dedicated_connection()
        
        # Set proper isolation level
        await connection.execute("PRAGMA read_uncommitted = 0")
        
        return SQLiteTransaction(connection)
    
    async def get_dedicated_connection(self):
        """Get a dedicated connection for transaction use"""
        # Don't use connection pool for transactions
        return await aiosqlite.connect(self.database_path)
```

## Type System Issues

### 1. Type Validation Failures

#### Problem Description
Runtime type validation fails with certain type annotations, causing crashes.

#### Error Example
```python
# TypeError: issubclass() arg 1 must be a class
def validate_field_type(field_type):
    if issubclass(field_type, str):  # Fails for generic types
        return "TEXT"
    elif issubclass(field_type, int):
        return "INTEGER"
```

#### Root Cause
The type checking doesn't handle modern Python type annotations:

```python
# Problematic types that cause issues
from typing import Optional, List, Union

class User:
    name: Optional[str]  # issubclass fails on Optional[str]
    tags: List[str]      # issubclass fails on List[str]
    data: Union[str, int]  # issubclass fails on Union types
```

#### Solution Strategy
```python
import typing
from typing import get_origin, get_args

def safe_type_check(field_type, target_type):
    """Safely check if field_type is compatible with target_type"""
    try:
        # Handle Optional types
        if get_origin(field_type) is Union:
            args = get_args(field_type)
            if len(args) == 2 and type(None) in args:
                # This is Optional[T]
                inner_type = next(arg for arg in args if arg is not type(None))
                return safe_type_check(inner_type, target_type)
        
        # Handle generic types
        origin = get_origin(field_type)
        if origin is not None:
            return issubclass(origin, target_type)
        
        # Handle regular types
        return issubclass(field_type, target_type)
    except TypeError:
        # Fallback for types that don't work with issubclass
        return False

def get_sql_type(field_type):
    """Convert Python type to SQL type safely"""
    if safe_type_check(field_type, str):
        return "TEXT"
    elif safe_type_check(field_type, int):
        return "INTEGER"
    elif safe_type_check(field_type, float):
        return "REAL"
    elif safe_type_check(field_type, bool):
        return "INTEGER"  # SQLite stores booleans as integers
    else:
        return "BLOB"  # Default fallback
```

## Affected Test Cases

### Currently Failing Tests
```python
# From driver_test_report.md
test_schema_management.py::test_create_tables_with_reserved_keywords - FAIL
test_transactions.py::test_nested_transactions - FAIL  
test_transactions.py::test_transaction_isolation - FAIL
test_basic_crud.py::test_models_with_complex_types - FAIL
```

### Expected Behavior After Fixes
```python
class TestSQLiteDriver:
    async def test_reserved_keywords(self):
        """Test that reserved keywords are properly escaped"""
        @ommi_model
        @dataclass
        class Order:  # Reserved keyword
            id: int
            index: int  # Also reserved
        
        async with SQLiteDriver.from_config(config) as db:
            await db.schema().create_models()  # Should not fail
            
            order = Order(id=1, index=5)
            await db.add(order)
            
            found = await db.find(Order.id == 1).fetch.one()
            assert found.index == 5
    
    async def test_nested_transactions(self):
        """Test that nested transactions work with savepoints"""
        async with db.transaction():
            user1 = User(name="Alice")
            await db.add(user1)
            
            async with db.transaction():
                user2 = User(name="Bob")
                await db.add(user2)
                # This should work now
            
            # Both users should be committed
            users = await db.find().fetch.all()
            assert len(users) == 2
    
    async def test_transaction_isolation(self):
        """Test that transaction isolation works correctly"""
        connection1 = db.get_connection()
        connection2 = db.get_connection()
        
        async with connection1.transaction():
            user = User(name="Alice")
            await connection1.add(user)
            
            # Connection2 should not see uncommitted data
            users = await connection2.find(User.name == "Alice").fetch.all()
            assert len(users) == 0
        
        # After commit, connection2 should see the data
        users = await connection2.find(User.name == "Alice").fetch.all()
        assert len(users) == 1
```

## Implementation Priority

### Phase 1: SQL Syntax Fixes (Week 1)
1. **Implement identifier escaping** for reserved keywords
2. **Fix parameter binding** in query generation
3. **Add SQL injection protection**

### Phase 2: Transaction System (Week 1-2)
1. **Implement savepoint-based nested transactions**
2. **Fix transaction isolation** with dedicated connections
3. **Add transaction state management**

### Phase 3: Type System Hardening (Week 2)
1. **Implement safe type checking** for modern Python types
2. **Add defensive type validation**
3. **Improve error messages** for type-related issues

## Success Metrics

### Technical Metrics
- **Zero SQL syntax errors** for reasonable model definitions
- **100% transaction tests passing**
- **No runtime type errors** for standard type annotations
- **SQLite driver test success rate >80%**

### Functional Validation
```python
# All these should work after fixes
@ommi_model
@dataclass  
class Order:  # Reserved keyword - should work
    id: int
    index: int  # Reserved keyword - should work
    total: float
    items: Optional[List[str]] = None  # Complex type - should work

# Nested transactions should work
async with db.transaction():
    order = Order(id=1, index=0, total=99.99)
    await db.add(order)
    
    async with db.transaction():  # Nested - should work
        order.total = 149.99
        await order.save()

# Complex queries should work
orders = await db.find(
    Order.total > 100.0 &
    Order.index.is_not_null()
).fetch.all()
```

## Risk Assessment

### Low Risk Changes
- **Identifier escaping** - Straightforward implementation
- **Type checking improvements** - Defensive coding, minimal impact

### Medium Risk Changes
- **Transaction system overhaul** - Could affect existing functionality
- **Query generation changes** - Need thorough testing

### Mitigation Strategies
- **Incremental implementation** - Fix one issue at a time
- **Comprehensive testing** - Test each fix independently
- **Rollback capability** - Keep ability to revert changes
- **Cross-driver validation** - Ensure fixes don't break other drivers

The SQLite driver fixes are essential because this driver serves as the foundation for testing all other components. A stable SQLite driver will enable reliable testing and development of the rest of the framework.