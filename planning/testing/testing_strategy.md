# Testing Strategy

## Current Testing Status

### Test Coverage Overview
- **Total Test Files:** 15 (7 unit tests + 8 validation tests)
- **Total Test Lines:** ~4,375
- **Current Success Rate:** 40.5% (17/42 tests passing)
- **Critical Gap:** Lazy loading and query API functionality

### Test Categories

#### Unit Tests (`tests/`)
1. **`test_drivers.py`** - Driver interface testing
2. **`test_field_metadata.py`** - Field metadata extraction
3. **`test_driver_context.py`** - Driver context management
4. **`test_ommi.py`** - Core Ommi functionality
5. **`test_query_fields.py`** - Query field behavior
6. **`test_models.py`** - Model system testing
7. **`test_circular_references.py`** - Circular reference handling

#### Validation Test Suite (`driver-validation-test-suite/`)
1. **`test_basic_crud.py`** - Create, Read, Update, Delete operations
2. **`test_complex_queries.py`** - Advanced query functionality
3. **`test_relationships.py`** - Model relationship testing
4. **`test_schema_management.py`** - Database schema operations
5. **`test_transactions.py`** - Transaction management

## Testing Strategy Framework

### 1. Driver Compliance Testing

#### Test Matrix
| Feature | SQLite | PostgreSQL | MongoDB | Priority |
|---------|---------|------------|---------|----------|
| Basic CRUD | ✅ | ❌ | ❌ | HIGH |
| Relationships | ❌ | ❌ | ❌ | CRITICAL |
| Transactions | ⚠️ | ❌ | ❌ | HIGH |
| Complex Queries | ❌ | ❌ | ❌ | MEDIUM |
| Schema Management | ✅ | ❌ | ❌ | HIGH |

**Legend:** ✅ Passing, ❌ Failing, ⚠️ Partial

#### Driver Compliance Checklist
Each driver must pass:
- [ ] **CRUD Operations**
  - Create (add) models
  - Read (fetch) models with filtering
  - Update (set) model fields
  - Delete models with conditions
  - Count operations

- [ ] **Query Capabilities**
  - Basic comparisons (==, !=, >, <, >=, <=)
  - Logical operations (AND, OR, NOT)
  - Contains/In operations
  - Ordering and limiting

- [ ] **Relationship Support**
  - One-to-one relationships
  - One-to-many relationships
  - Many-to-many through association tables
  - Lazy loading functionality

- [ ] **Transaction Management**
  - Basic transactions (commit/rollback)
  - Nested transactions (savepoints)
  - Transaction isolation
  - Error handling and cleanup

- [ ] **Schema Operations**
  - Create tables/collections from models
  - Manage indexes and constraints
  - Handle schema evolution
  - Clean up database objects

### 2. Test Organization Strategy

#### Test Hierarchy
```
tests/
├── unit/                           # Fast, isolated tests
│   ├── core/                      # Core functionality
│   ├── models/                    # Model system
│   ├── drivers/                   # Driver interfaces
│   └── query/                     # Query system
├── integration/                   # Multi-component tests
│   ├── driver_compliance/         # Driver feature tests
│   ├── cross_driver/             # Cross-driver compatibility
│   └── performance/              # Performance benchmarks
└── validation/                    # Full system validation
    ├── basic_operations/         # CRUD operations
    ├── advanced_queries/         # Complex query tests
    ├── relationships/            # Relationship tests
    └── transactions/             # Transaction tests
```

### 3. Test Data Management

#### Model Fixtures
```python
# Standardized test models
@ommi_model
@dataclass
class TestUser:
    id: Annotated[int, Key] = None
    name: str = ""
    age: int = 0
    email: str = ""

@ommi_model  
@dataclass
class TestPost:
    id: Annotated[int, Key] = None
    title: str = ""
    content: str = ""
    author_id: Annotated[int, ReferenceTo(TestUser.id)] = None
    author: LazyLoadTheRelated[TestUser] = field(default_factory=LazyLoadTheRelated)
```

#### Database Fixtures
```python
@pytest.fixture
async def sqlite_db():
    async with SQLiteDriver.from_config(SQLiteConfig(filename=":memory:")) as db:
        await db.schema().create_models().raise_on_errors()
        yield db

@pytest.fixture(params=["sqlite", "postgresql", "mongodb"])
async def any_db(request):
    # Parameterized fixture for cross-driver testing
    pass
```

### 4. Critical Test Areas

#### Priority 1: Lazy Loading Tests
```python
class TestLazyLoading:
    async def test_lazy_load_the_related(self):
        # Test single relationship loading
        pass
        
    async def test_lazy_load_every_related(self):
        # Test collection relationship loading
        pass
        
    async def test_lazy_loading_caching(self):
        # Test that lazy fields cache results
        pass
        
    async def test_lazy_loading_refresh(self):
        # Test refresh functionality
        pass
        
    async def test_association_table_relationships(self):
        # Test many-to-many through association tables
        pass
```

#### Priority 2: Query API Tests
```python
class TestQueryAPI:
    async def test_comparison_operators(self):
        # Test ==, !=, >, <, >=, <=
        pass
        
    async def test_logical_operators(self):
        # Test AND, OR, NOT
        pass
        
    async def test_membership_operators(self):
        # Test contains, in_, not_in
        pass
        
    async def test_query_chaining(self):
        # Test complex query combinations
        pass
        
    async def test_async_query_handling(self):
        # Test coroutine handling in queries
        pass
```

#### Priority 3: Transaction Tests
```python
class TestTransactions:
    async def test_basic_transaction(self):
        # Test commit and rollback
        pass
        
    async def test_nested_transactions(self):
        # Test savepoint functionality
        pass
        
    async def test_transaction_isolation(self):
        # Test isolation levels
        pass
        
    async def test_error_rollback(self):
        # Test automatic rollback on errors
        pass
```

### 5. Performance Testing

#### Benchmark Targets
- **Query Performance:** <100ms for simple queries
- **Batch Operations:** >1000 records/second for inserts
- **Memory Usage:** <10MB baseline, <1KB per model instance
- **Connection Overhead:** <50ms connection establishment

#### Performance Test Categories
```python
class TestPerformance:
    async def test_large_batch_insert(self):
        # Test inserting 10,000+ records
        pass
        
    async def test_complex_query_performance(self):
        # Test performance of joins and filters
        pass
        
    async def test_memory_usage(self):
        # Test memory consumption patterns
        pass
        
    async def test_connection_pooling(self):
        # Test connection reuse efficiency
        pass
```

### 6. Test Automation

#### Continuous Integration
```yaml
# .github/workflows/test.yml
name: Test Suite
on: [push, pull_request]
jobs:
  test:
    strategy:
      matrix:
        python-version: ["3.12"]
        database: ["sqlite", "postgresql", "mongodb"]
    steps:
      - uses: actions/checkout@v2
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: |
          pip install poetry
          poetry install
      - name: Run tests
        run: poetry run pytest --database=${{ matrix.database }}
```

#### Test Reporting
- **Coverage Reports:** Generate coverage reports for each PR
- **Performance Regression:** Alert on performance degradation
- **Driver Compliance:** Track feature implementation across drivers

### 7. Testing Tools and Libraries

#### Current Dependencies
- **pytest:** Test framework
- **pytest-asyncio:** Async test support
- **motor:** MongoDB async driver (for testing)
- **psycopg:** PostgreSQL driver (for testing)

#### Proposed Additions
- **pytest-benchmark:** Performance testing
- **pytest-cov:** Coverage reporting
- **pytest-xdist:** Parallel test execution
- **hypothesis:** Property-based testing
- **factory-boy:** Test data generation

### 8. Test Execution Strategy

#### Development Testing
```bash
# Quick feedback during development
poetry run pytest tests/unit/ -v

# Driver-specific testing
poetry run pytest driver-validation-test-suite/ --driver=sqlite

# Performance testing
poetry run pytest tests/performance/ --benchmark-only
```

#### Comprehensive Testing
```bash
# Full test suite
poetry run pytest

# Cross-driver compatibility
poetry run pytest --drivers=all

# Coverage reporting
poetry run pytest --cov=ommi --cov-report=html
```

### 9. Test Maintenance

#### Regular Maintenance Tasks
- [ ] **Weekly:** Review test failures and fix flaky tests
- [ ] **Monthly:** Update test data and add edge cases
- [ ] **Per Release:** Full driver compliance verification
- [ ] **Quarterly:** Performance baseline updates

#### Test Quality Metrics
- **Test Coverage:** Target >95% line coverage
- **Test Reliability:** <1% flaky test rate
- **Test Performance:** Full suite completion <10 minutes
- **Test Clarity:** All tests have descriptive names and documentation

## Implementation Roadmap

### Phase 1: Fix Critical Tests (Week 1-2)
- [ ] Fix lazy loading test failures
- [ ] Repair query API tests
- [ ] Stabilize SQLite driver tests

### Phase 2: Expand Test Coverage (Week 3-4)
- [ ] Add missing query operator tests
- [ ] Implement transaction isolation tests
- [ ] Add cross-driver compatibility tests

### Phase 3: Performance & Quality (Week 5-6)
- [ ] Add performance benchmarks
- [ ] Implement property-based testing
- [ ] Set up automated testing pipeline

### Phase 4: Advanced Testing (Week 7-8)
- [ ] Add stress testing
- [ ] Implement chaos testing for reliability
- [ ] Add documentation testing