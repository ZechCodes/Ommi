# Core Design Principles

## Overview
Ommi is built on three foundational design principles that guide all architectural decisions and ensure the framework remains flexible, maintainable, and user-friendly.

## 1. Database Agnostic Design

### Principle
Provide a consistent interface across different database types (SQL and NoSQL) without forcing users to learn database-specific APIs.

### Implementation Strategy
- **Abstraction Layer:** Common interface that hides database implementation details
- **Driver Pattern:** Database-specific implementations behind uniform API
- **Query AST:** Abstract syntax tree for cross-database query translation

### Benefits
- **Portability:** Switch databases without changing application code
- **Learning Curve:** One API to learn instead of multiple database APIs
- **Future-Proof:** New databases can be added without breaking existing code

### Example
```python
# Same code works with any database
async with driver.from_config(config) as db:
    users = await db.find(User.age > 18).fetch.all()
```

## 2. Model Library Agnostic

### Principle
Work with any Python model library (dataclasses, Attrs, Pydantic) rather than forcing users to adopt a specific modeling approach.

### Implementation Strategy
- **Decorator Pattern:** `@ommi_model` enhances existing models without replacing them
- **Metadata Extraction:** Runtime introspection discovers field information
- **Type Preservation:** Original model behavior and features are maintained

### Benefits
- **User Choice:** Work with preferred model library
- **Migration Path:** Easy adoption in existing projects
- **Compatibility:** Support multiple modeling paradigms in same project
- **Future-Proof:** New model libraries can be supported

### Example
```python
# Works with dataclasses
@ommi_model
@dataclass
class User:
    name: str
    age: int

# Works with Pydantic
@ommi_model
class User(BaseModel):
    name: str
    age: int

# Works with Attrs
@ommi_model
@attrs.define
class User:
    name: str
    age: int
```

## 3. Async-First Design

### Principle
All database operations are asynchronous by default to ensure optimal performance and scalability in modern Python applications.

### Implementation Strategy
- **Non-blocking Operations:** All database I/O is async
- **Connection Pooling:** Efficient resource management with async context managers
- **Transaction Support:** Async transaction handling with proper cleanup

### Benefits
- **Performance:** Non-blocking operations improve throughput
- **Scalability:** Handle many concurrent database operations
- **Modern Python:** Aligns with current async ecosystem standards
- **Resource Efficiency:** Better connection pool utilization

### Example
```python
# All operations are async
async with SQLiteDriver.from_config(config) as db:
    user = User(name="Alice", age=25)
    await db.add(user).raise_on_errors()
    
    users = await db.find(User.age > 18).fetch.all()
```

## Design Principle Trade-offs

### Abstraction vs Performance
- **Trade-off:** Abstraction layer may add overhead
- **Mitigation:** Direct driver access available for performance-critical code
- **Monitoring:** Continuous performance benchmarking

### Flexibility vs Complexity
- **Trade-off:** Supporting multiple model libraries increases complexity
- **Mitigation:** Clear internal interfaces and comprehensive testing
- **Documentation:** Clear patterns for each supported library

### Async vs Learning Curve
- **Trade-off:** Async-first may be challenging for some developers
- **Mitigation:** Comprehensive documentation and examples
- **Alternative:** Future consideration of sync wrapper APIs

## Principle Validation

### Database Agnostic Validation
```python
# Test that same code works across databases
@pytest.mark.parametrize("driver", [SQLiteDriver, PostgreSQLDriver, MongoDriver])
async def test_cross_database_compatibility(driver):
    async with driver.from_config(config) as db:
        user = User(name="Alice", age=25)
        await db.add(user).raise_on_errors()
        found = await db.find(User.name == "Alice").fetch.one()
        assert found.name == "Alice"
```

### Model Library Agnostic Validation
```python
# Test that same operations work with different model libraries
@pytest.mark.parametrize("model_class", [DataclassUser, PydanticUser, AttrsUser])
async def test_cross_model_compatibility(model_class):
    user = model_class(name="Alice", age=25)
    await db.add(user).raise_on_errors()
    # ... rest of test
```

### Async-First Validation
```python
# Ensure all operations are properly async
async def test_async_operations():
    async with driver.from_config(config) as db:
        # All these should be awaitable
        await db.add(user)
        await db.find(User.name == "Alice").count().value
        await db.find(User.age > 18).fetch.all()
```

## Evolution of Principles

### Lessons Learned
- **Query AST Complexity:** Initially underestimated complexity of cross-database query translation
- **Type System Integration:** Model library integration more complex than anticipated
- **Performance Overhead:** Abstraction layer performance impact requires careful optimization

### Future Considerations
- **Sync API Option:** Consider optional synchronous API for simpler use cases
- **Plugin System:** Allow third-party extensions while maintaining principles
- **Performance Modes:** Optional direct driver access for performance-critical paths

## Compliance Checklist

Every new feature must align with core principles:

### Database Agnostic Checklist
- [ ] Feature works identically across all supported databases
- [ ] No database-specific code in user-facing APIs
- [ ] Query AST properly abstracts database differences
- [ ] Driver-specific optimizations hidden from users

### Model Library Agnostic Checklist
- [ ] Feature works with dataclasses, Attrs, and Pydantic
- [ ] No assumptions about specific model library features
- [ ] Metadata extraction handles all model types
- [ ] Original model behavior preserved

### Async-First Checklist
- [ ] All database operations are async
- [ ] Proper async context manager usage
- [ ] No blocking operations in main code paths
- [ ] Error handling works correctly in async context

## Measuring Success

### Metrics
- **Portability:** Number of databases supported with identical API
- **Compatibility:** Number of model libraries supported
- **Performance:** Async overhead <10% compared to direct drivers
- **Usability:** Developer onboarding time <15 minutes

### Success Criteria
- Users can switch databases without code changes
- Users can choose their preferred model library
- Performance is competitive with direct database drivers
- Learning curve is minimal for Python developers familiar with async/await