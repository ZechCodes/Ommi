# Ommi Module Structure Refactoring Plan

## Overview

This document outlines a comprehensive plan to improve Ommi's module structure, making it cleaner and reducing dependencies between modules. The refactoring will maintain backward compatibility while improving maintainability and code organization.

## Current Architecture Assessment

### Strengths
- Good separation between abstract driver interfaces (`ommi/drivers/`) and concrete implementations (`ommi/ext/drivers/`)
- Proper use of `TYPE_CHECKING` to avoid circular imports
- Clean database result handling with separate modules for different result types
- Effective lazy loading in main `__init__.py`

### Issues Identified

1. **Over-sized `models/models.py` (894 lines)** - Contains too many responsibilities
2. **Models directory lacks clear organization** - Query functionality, metadata, and core model logic are mixed
3. **Repeated patterns across drivers** - Each driver reimplements similar patterns without shared base classes
4. **Potential for better abstraction** - Missing interface layer for better decoupling

## Refactoring Plan

### Phase 1: Core Model System Restructuring (High Priority)

#### 1.1 Split `models/models.py`

**Current State**: Single large file with multiple responsibilities
**Target State**: Multiple focused modules

```
models/
├── __init__.py                 # Public API exports
├── core/
│   ├── __init__.py
│   ├── base.py                 # OmmiModel base class only
│   ├── decorators.py           # @ommi_model decorator logic
│   ├── registry.py             # Model registration and collection utilities
│   └── metadata.py             # Model metadata management
├── fields/
│   ├── __init__.py
│   ├── metadata.py             # Field metadata processing (from field_metadata.py)
│   ├── descriptors.py          # Queryable descriptors (from queryable_descriptors.py)
│   ├── query_fields.py         # Query field types (existing)
│   └── types.py                # Field type definitions
├── queries/
│   ├── __init__.py
│   ├── references.py           # Reference handling (existing)
│   └── builders.py             # Query building utilities
└── collections.py              # Collection management (existing)
```

**Files to Create/Modify**:
- Extract from `models/models.py`:
  - `models/core/base.py` - `OmmiModel` class definition
  - `models/core/decorators.py` - `ommi_model` decorator and related logic
  - `models/core/registry.py` - Model registration utilities
  - `models/core/metadata.py` - Model metadata processing
- Rename `models/field_metadata.py` → `models/fields/metadata.py`
- Rename `models/queryable_descriptors.py` → `models/fields/descriptors.py`
- Update imports across the codebase

#### 1.2 Create Shared Driver Utilities

**Current State**: Each driver reimplements similar patterns
**Target State**: Shared base classes and utilities

```
drivers/
├── __init__.py                 # Existing driver interfaces
├── base/
│   ├── __init__.py
│   ├── query_builders.py       # Base query builder classes
│   ├── transactions.py         # Base transaction classes
│   └── utils.py                # Shared utilities across all drivers
└── sql/
    ├── __init__.py
    ├── base.py                 # SQL-specific base classes
    └── utils.py                # SQL-specific utilities
```

**Benefits**:
- Reduce code duplication across SQLite and PostgreSQL drivers
- Easier to add new SQL-based drivers
- Consistent behavior across similar database types

### Phase 2: Query System Extraction (Medium Priority)

#### 2.1 Extract Query System

**Current State**: Query logic scattered across multiple modules
**Target State**: Dedicated query subsystem

```
ommi/
├── query/
│   ├── __init__.py
│   ├── ast/
│   │   ├── __init__.py
│   │   ├── nodes.py            # AST node definitions (from query_ast.py)
│   │   ├── builders.py         # Query building logic (from query_ast.py)
│   │   └── operators.py        # Operator definitions (from query_ast.py)
│   ├── fields/
│   │   ├── __init__.py
│   │   ├── descriptors.py      # Moved from models/fields/
│   │   └── references.py       # Moved from models/queries/
│   └── execution/
│       ├── __init__.py
│       └── context.py          # Query execution context
```

**Files to Modify**:
- Split `query_ast.py` into multiple focused modules
- Move query-specific logic from models package
- Update imports throughout codebase

#### 2.2 Create Core Interfaces Package

**Current State**: Protocols scattered across modules
**Target State**: Centralized interface definitions

```
ommi/
├── interfaces/
│   ├── __init__.py
│   ├── model.py               # Model protocol definitions
│   ├── queryable.py           # Queryable protocol definitions
│   ├── driver.py              # Driver protocol (moved from drivers/)
│   ├── result.py              # Result protocol definitions
│   └── transaction.py         # Transaction protocol definitions
```

**Benefits**:
- Clear contracts between modules
- Easier testing with mock implementations
- Better type checking and IDE support
- Reduced circular dependency risks

### Phase 3: Advanced Reorganization (Lower Priority)

#### 3.1 Database Operations Restructuring

**Current State**: Good organization but could be enhanced
**Target State**: More explicit operation categories

```
database/
├── __init__.py
├── ommi.py                    # Main database interface (existing)
├── transaction.py             # Transaction management (existing)
├── results/
│   ├── __init__.py
│   ├── single.py              # Single value results (from results.py)
│   ├── collections.py         # Collection results (from query_results.py)
│   └── builders.py            # Result builder utilities
└── operations/
    ├── __init__.py
    ├── crud.py                # CRUD operation wrappers
    └── schema.py              # Schema management operations
```

#### 3.2 Shared Utilities Package

**Current State**: Utilities scattered across modules
**Target State**: Centralized utility functions

```
ommi/
├── utils/
│   ├── __init__.py
│   ├── imports.py             # Import utilities and lazy loading
│   ├── annotations.py         # Annotation processing utilities
│   ├── validation.py          # Field validation utilities
│   └── collections.py         # Collection manipulation utilities
```

## Implementation Strategy

### Backward Compatibility

- Maintain all existing public APIs during refactoring
- Use `__init__.py` files to re-export moved functionality
- Add deprecation warnings for any changed import paths
- Provide migration guide for users importing internal modules

### Migration Steps

#### Step 1: Prepare Infrastructure
1. Create new directory structures
2. Set up `__init__.py` files with proper exports
3. Create base classes and interfaces

#### Step 2: Move Code Incrementally
1. Extract code to new locations
2. Update internal imports
3. Add compatibility imports in old locations
4. Run full test suite after each major move

#### Step 3: Update Documentation
1. Update API documentation
2. Create migration guide
3. Update examples in documentation

#### Step 4: Clean Up
1. Remove compatibility imports after deprecation period
2. Remove empty modules
3. Final documentation updates

### Testing Strategy

- Run existing test suite after each phase
- Add integration tests for new module boundaries
- Test import paths for backward compatibility
- Performance testing to ensure no regressions

### Risk Mitigation

- **Circular Import Risk**: Use interfaces package and maintain `TYPE_CHECKING` patterns
- **Performance Risk**: Profile import times and lazy loading behavior
- **API Breakage Risk**: Comprehensive compatibility testing and gradual migration

## Expected Benefits

### Code Quality
- Smaller, more focused modules (target <300 lines per file)
- Clear separation of concerns
- Reduced cognitive load when reading code
- Easier unit testing of individual components

### Maintainability
- Easier to locate relevant code
- Reduced risk of circular dependencies
- Clear module boundaries and responsibilities
- Better IDE support and navigation

### Extensibility
- Easier to add new database drivers
- Clear extension points for new functionality
- Better plugin architecture potential
- Simplified contribution process for new developers

## Timeline Estimate

- **Phase 1**: 2-3 weeks (models restructuring and driver utilities)
- **Phase 2**: 1-2 weeks (query system extraction and interfaces)
- **Phase 3**: 1 week (advanced reorganization)
- **Total**: 4-6 weeks for complete implementation

## Success Metrics

- All existing tests pass
- No circular import warnings
- Improved code coverage due to better testability
- Documentation builds successfully
- Performance benchmarks show no regression
- Developer feedback on improved code navigation

## Conclusion

This refactoring plan addresses the main structural issues in Ommi while maintaining stability and backward compatibility. The phased approach allows for incremental progress and validation at each step, minimizing risk while achieving significant improvements in code organization and maintainability.