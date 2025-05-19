# Ommi Driver Validation Test Suite

This test suite ensures that all database drivers in Ommi behave consistently and correctly. The goal is to validate that regardless of which database backend a user chooses, the behavior of Ommi remains predictable and reliable.

## Purpose

The driver validation tests verify:

1. **Functional Equivalence**: All drivers support the same features and behave identically for the same operations
2. **Edge Case Handling**: Drivers properly handle unusual scenarios like concurrent transactions, large datasets, and error conditions
3. **Compliance with Ommi API Contract**: Drivers adhere to the expected behaviors defined by the Ommi interface
4. **Data Integrity**: Operations maintain data consistency across all drivers

## Driver Behavior Standards

To ensure consistency across all Ommi drivers, we've established the following standards:

### Transactions
1. **Simple Transactions**: All drivers must support basic transactions with commit and rollback functionality
2. **Nested Transactions**: Drivers should emulate nested transaction behavior even if the underlying database doesn't support it natively:
   - Inner transaction commits are no-ops (they don't finalize changes)
   - Inner transaction rollbacks should rollback the entire outer transaction
   - Only the outermost transaction commit actually persists changes

### Schema Management
1. **Case Sensitivity**: All drivers should treat column names as case-sensitive in models, even if the underlying database is case-insensitive
   - Drivers for case-insensitive databases should maintain internal mappings
2. **Schema Evolution**: All drivers must support adding new columns to existing tables
   - New fields should default to NULL for existing records
   - Drivers should emulate this capability even if native support is limited

### Relationships and Queries
1. **Query Consistency**: All query operations must produce identical results across all drivers
2. **Relationship Loading**: Lazy loading must work identically across all drivers

### Error Handling
1. **Standardized Errors**: Drivers should translate native database errors into consistent Ommi error types
2. **Detailed Diagnostics**: Error messages should include relevant details for debugging while maintaining consistent formats

## Running the Tests

### Prerequisites

- Python 3.10+ with pytest and pytest-asyncio installed
- Access to test instances of all supported databases:
  - SQLite (included with Python)
  - PostgreSQL 
  - MongoDB

### Configuration

Each driver might require specific configuration for testing. By default, tests use:

- SQLite: In-memory database
- PostgreSQL: Connection to localhost:5432, database "test_ommi", user "postgres"
- MongoDB: Connection to localhost:27017, database "test_ommi"

You can override these settings using environment variables:

```
# PostgreSQL
OMMI_TEST_PG_HOST=localhost
OMMI_TEST_PG_PORT=5432
OMMI_TEST_PG_DB=test_ommi
OMMI_TEST_PG_USER=postgres
OMMI_TEST_PG_PASS=password

# MongoDB
OMMI_TEST_MONGO_URI=mongodb://localhost:27017
OMMI_TEST_MONGO_DB=test_ommi
```

### Running Tests

To run all driver validation tests:

```bash
pytest driver-validation-test-suite
```

To run tests for a specific driver:

```bash
# For SQLite only
pytest driver-validation-test-suite -k "sqlite"

# For PostgreSQL only
pytest driver-validation-test-suite -k "postgresql"

# For MongoDB only
pytest driver-validation-test-suite -k "mongodb"
```

To run a specific test category:

```bash
# For transaction tests
pytest driver-validation-test-suite/test_transactions.py

# For query tests
pytest driver-validation-test-suite/test_queries.py
```

## Test Categories

The test suite is organized into the following categories:

1. **Basic CRUD Operations**: Tests for creating, reading, updating, and deleting models
2. **Transactions**: Tests for transaction isolation, commit, rollback, and error handling
3. **Queries**: Tests for complex query construction and execution
4. **Relationships**: Tests for model relationships and lazy/eager loading
5. **Schema Management**: Tests for schema creation, modification, and deletion
6. **Performance**: Tests for batch processing and handling large datasets
7. **Concurrency**: Tests for concurrent transactions and operations
8. **Unicode**: Tests for proper handling of international text and characters

## Adding New Tests

When adding new tests, ensure:

1. Tests are driver-agnostic and parameterized to run against all supported drivers
2. Tests validate both success and failure paths
3. Tests include clear assertions with descriptive failure messages
4. Tests are independently runnable and don't depend on state from other tests

Follow the existing patterns in the test suite for consistency. 