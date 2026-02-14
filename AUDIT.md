# Ommi ORM Project Audit

**Date:** 2026-02-14
**Version:** 0.2.2
**Branch:** claude/audit-project-status-eDKLA

## Test Results Summary

SQLite-only test run (MongoDB/PostgreSQL servers unavailable in test environment):

| Category | Passed | Failed | Error |
|----------|--------|--------|-------|
| Driver context | 7 | 0 | 0 |
| Driver operations (SQLite) | 18 | 1 | 0 |
| Models | 8 | 0 | 0 |
| Ommi class | 10 | 0 | 0 |
| Query fields | 3 | 0 | 0 |
| Field metadata | 1 | 0 | 0 |
| Circular references | 0 | 0 | 4 |
| **Total (SQLite only)** | **47** | **1** | **4** |

All 46 MongoDB/PostgreSQL parameterized tests ERROR due to unavailable servers. The test suite does not gracefully skip unavailable backends.

---

## Critical Bugs

### 1. BaseDriverTransaction.__aexit__ does not await commit

**File:** `ommi/drivers/transactions.py:99`

```python
async def __aexit__(self, exc_type, exc_val, exc_tb):
    await self.rollback() if exc_type else self.commit()  # BUG
    await self.close()
```

Due to Python operator precedence, `await` binds tighter than the ternary. This parses as `(await self.rollback()) if exc_type else self.commit()`. On the success path, `self.commit()` creates a coroutine that is never awaited -- the transaction silently never commits. The `SQLiteTransactionExplicitTransactions` override at `ommi/ext/drivers/sqlite/transaction.py:241` has the correct form. PostgreSQL and MongoDB transactions inherit the broken base version.

### 2. SQLiteDriver.connect() rejects string arguments

**File:** `ommi/ext/drivers/sqlite/driver.py:94-95`

```python
_settings = cls._default_settings
if settings:
    _settings |= settings  # Crashes when settings is ":memory:"
```

All 4 `test_circular_references.py` tests fail because `SQLiteDriver.connect(":memory:")` tries to merge a string into a TypedDict using `|=`, raising `ValueError`.

### 3. Pagination offset is broken

**File:** `ommi/ext/drivers/sqlite/utils.py:112`

```python
query = SelectQuery(
    limit=ast.max_results,
    offset=ast.results_page,  # Treats page number as raw offset
)
```

`ASTGroupNode.limit(5, 1)` stores `page=1` in `results_page`, but `build_query` uses it as a direct byte offset. The test expects page 1 (items 5-9) but gets offset 1 (items 1-5). `test_async_batch_iterator_offset` fails: expects `"dummy_5"`, gets `"dummy_1"`.

### 4. SetupOnAwait proxy bypasses implicit model setup

**File:** `ommi/database/ommi.py:375-384`

```python
class SetupOnAwait:
    def __getattr__(self, name):
        return getattr(self._awaitable, name)  # Delegates WITHOUT running setup
```

When implicit model setup is needed, accessing `.one`, `.count`, `.delete`, or `.update` via `__getattr__` returns the underlying builder's methods directly, skipping setup. Only bare `await db.find(...)` triggers setup; `await db.find(...).one` does not. Same issue affects `db.add(...).or_raise()`.

---

## Design Issues

### 5. Typo in public API parameter

**File:** `ommi/database/ommi.py:103`

`allow_imlicit_model_setup` -- missing 'p', should be `allow_implicit_model_setup`.

### 6. use_models() destructively drops then recreates schema

**File:** `ommi/database/ommi.py:303-306`

Every call to `use_models` drops existing tables before recreating them, destroying data. This happens transparently on first `add`/`find` if implicit model setup is enabled. Repeated calls or restarts wipe the database.

### 7. OmmiModel methods reference nonexistent driver APIs

**File:** `ommi/models/models.py:326-500`

`OmmiModel` methods (`save()`, `delete()`, `reload()`, `fetch()`, `count()`) call `self.get_driver(driver).find(...)`, but `BaseDriver` has no `find()` method -- that belongs to the `Ommi` class. These are dead code that raise `AttributeError` at runtime.

---

## Top-Level Abstraction Status

The `Ommi` class core flow works for the basic case:

- `await db.add(model)` -- **works** (tests confirm CRUD)
- `await db.find(predicate)` -- **works** (returns all results)
- `await db.find(...).one` -- **works but skips implicit model setup** (bug #4)
- `db.transaction()` -- **works for SQLite** (explicit transaction subclass is correct), but **base class silently drops commits** (bug #1)
- Pagination via `.limit(n, page)` -- **broken** (bug #3)
- Implicit model setup -- **partial** (only works for bare await, not `.one`/`.count`/etc)
- `use_models()` -- **destructive** (drops and recreates tables every time)

The query AST system, result types (`DBResult`/`DBQueryResult`), and `WrapInResult` descriptor pattern are well-designed and functional.

---

## Low-Level Driver Interface Status

### SQLite: Mostly functional

- CRUD operations: pass all tests
- Schema management: works
- Joins, lazy loading, relationships: all pass
- Transaction management: works (explicit transaction subclass is correct)
- Pagination offset: **broken** (bug #3)
- `connect(":memory:")`: **crashes** for string args (bug #2)

### PostgreSQL: Untested (requires running server)

- Uses psycopg3 async properly
- Hardcoded default credentials in `connect()`
- Does not override `__aexit__` from base -- inherits unawaited-commit bug (#1)

### MongoDB: Untested (requires running server)

- Uses Motor correctly for async
- `connect()` is synchronous (Motor client init is non-blocking)
- Also inherits base `__aexit__` commit bug (#1) unless overridden

---

## Performance Issues

### 8. SQLite blocks the event loop

The SQLite driver uses the synchronous `sqlite3` stdlib module in `async def` methods. Every database operation blocks the event loop, stalling all concurrent async tasks. Standard mitigation: `aiosqlite` or `asyncio.to_thread()`.

### 9. No connection pooling

All three drivers create and hold a single connection. No pooling for concurrent operations. Significant limitation for PostgreSQL under load.

### 10. New cursor per operation in SQLite

`SQLiteDriver` calls `self.connection.cursor()` in every method, creating unnecessary overhead at scale.

### 11. Hardcoded batch size

`BATCH_SIZE = 100` in `ommi/ext/drivers/sqlite/fetch_query.py:15` is not configurable.

---

## Infrastructure Gaps

- **No CI test pipeline**: Only GitHub Action is `release.yaml` for PyPI publishing
- **No linting or type checking**: No mypy, ruff, flake8, or similar
- **No test coverage reporting**: No pytest-cov configuration
- **Tests don't skip unavailable backends**: MongoDB/PostgreSQL tests error instead of skipping
- **Testing strategy doc reports 40.5% pass rate**: `planning/testing/testing_strategy.md` documents only 17/42 tests passing

---

## Summary

The core architecture -- AST-based queries, driver abstraction, decorator-based model registration, discriminated union result types -- is well-designed. The SQLite driver is the most complete and functional. However, there are 4 critical bugs (unawaited commit, broken connect(), broken pagination, setup bypass) and several design issues that need attention before the ORM can be relied upon beyond simple single-driver SQLite use cases. The biggest performance concern is synchronous SQLite blocking the event loop.
