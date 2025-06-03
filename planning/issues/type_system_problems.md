# Type System Problems

## Issue Classification
**Priority:** MEDIUM  
**Status:** Runtime type validation failures  
**Impact:** Model validation unreliable  
**Affected Components:** `ommi/models/field_metadata.py`, type checking throughout codebase

## Problem Description

### Overview
The type system in Ommi fails to properly handle modern Python type annotations, causing runtime errors and unreliable model validation. This affects model registration, field validation, and database schema generation.

### Primary Error Types
```python
# TypeError: issubclass() arg 1 must be a class
TypeError: issubclass() arg 1 must be a class

# Issues with generic types
TypeError: issubclass() arg 1 must be a class when checking Optional[str]
TypeError: issubclass() arg 1 must be a class when checking List[int]
TypeError: issubclass() arg 1 must be a class when checking Union[str, int]
```

## Root Cause Analysis

### 1. Incompatible Type Checking Patterns

#### Current Broken Implementation
The type checking system uses `issubclass()` with modern type annotations that are not classes:

```python
# Current broken pattern (inferred from errors)
def validate_field_type(field_type):
    if issubclass(field_type, str):  # Fails for Optional[str]
        return "string"
    elif issubclass(field_type, int):  # Fails for List[int]
        return "integer"
    # ... more checks
```

#### Problematic Type Annotations
```python
from typing import Optional, List, Dict, Union, Tuple, Annotated

@ommi_model
@dataclass
class User:
    # These all cause issubclass() errors:
    name: Optional[str]           # Union[str, None]
    tags: List[str]              # Generic type
    metadata: Dict[str, Any]     # Generic type
    settings: Union[str, dict]   # Union type
    coordinates: Tuple[float, float]  # Generic tuple
    email: Annotated[str, EmailField]  # Annotated type
```

### 2. Python 3.9+ Type System Evolution

#### Modern Type Annotations
Python's type system has evolved significantly, introducing generic types and special forms that don't work with traditional `issubclass()`:

```python
# Python 3.9+ type annotations that break old patterns
from typing import get_origin, get_args

# These are not classes and fail with issubclass():
Optional[str]     # get_origin() -> Union, get_args() -> (str, NoneType)
List[int]         # get_origin() -> list, get_args() -> (int,)
Dict[str, Any]    # get_origin() -> dict, get_args() -> (str, Any)
Union[str, int]   # get_origin() -> Union, get_args() -> (str, int)
```

### 3. Missing Type Introspection

#### Insufficient Type Analysis
The current system doesn't properly analyze complex type structures:

```python
# Current limitation - can't handle:
class ComplexModel:
    # Nested generics
    data: Dict[str, List[Optional[int]]]
    
    # Forward references
    parent: Optional['ComplexModel']
    
    # Custom generic types
    result: Result[User, DatabaseError]
    
    # Literal types
    status: Literal['active', 'inactive', 'pending']
```

## Specific Problem Areas

### 1. Field Metadata Extraction

#### Current Failures
```python
# This fails during model registration
@ommi_model
@dataclass
class Product:
    id: int
    name: str
    tags: Optional[List[str]] = None  # Causes TypeError
    metadata: Dict[str, Any] = field(default_factory=dict)  # Fails
```

#### Error Trace
```python
# Somewhere in field_metadata.py (inferred)
def extract_field_info(field_name, field_type):
    if issubclass(field_type, str):  # TypeError here
        return FieldInfo(name=field_name, db_type="TEXT")
    # ... more type checking
```

### 2. Database Schema Generation

#### SQL Type Mapping Failures
```python
# Current broken mapping (inferred)
def python_type_to_sql(py_type):
    if issubclass(py_type, str):  # Fails for Optional[str]
        return "TEXT"
    elif issubclass(py_type, int):  # Fails for List[int]
        return "INTEGER"
    else:
        raise ValueError(f"Unsupported type: {py_type}")
```

#### Should Handle
```python
# Expected functionality
def python_type_to_sql(py_type):
    # Handle Optional[T] -> same as T but nullable
    if is_optional_type(py_type):
        inner_type = get_optional_inner_type(py_type)
        return python_type_to_sql(inner_type)  # Recursive handling
    
    # Handle List[T] -> JSON or TEXT representation
    if is_list_type(py_type):
        return "JSON"  # or "TEXT" depending on database
    
    # Handle basic types
    if is_compatible_with(py_type, str):
        return "TEXT"
    elif is_compatible_with(py_type, int):
        return "INTEGER"
```

### 3. Runtime Validation

#### Validation Failures
```python
# Current broken validation (inferred)
def validate_field_value(value, expected_type):
    if not isinstance(value, expected_type):  # Fails for generic types
        raise ValidationError(f"Expected {expected_type}, got {type(value)}")
```

#### Complex Validation Scenarios
```python
# Should be able to validate:
class UserProfile:
    preferences: Dict[str, Union[str, int, bool]]
    
# Validate this data:
profile_data = {
    "preferences": {
        "theme": "dark",      # str value
        "notifications": True, # bool value  
        "max_items": 50       # int value
    }
}
```

## Solution Strategy

### 1. Modern Type Introspection System

#### Core Type Analysis Functions
```python
import typing
from typing import get_origin, get_args, Union, Optional, List, Dict, Tuple

class TypeAnalyzer:
    """Advanced type analysis for modern Python type annotations"""
    
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
        if TypeAnalyzer.is_optional(annotation):
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
        if TypeAnalyzer.is_generic_list(annotation):
            args = get_args(annotation)
            return args[0] if args else Any
        return Any
    
    @staticmethod
    def is_generic_dict(annotation: Any) -> bool:
        """Check if type is Dict[K, V]"""
        return get_origin(annotation) is dict
    
    @staticmethod
    def get_dict_types(annotation: Any) -> Tuple[Any, Any]:
        """Get (K, V) from Dict[K, V]"""
        if TypeAnalyzer.is_generic_dict(annotation):
            args = get_args(annotation)
            if len(args) >= 2:
                return args[0], args[1]
        return Any, Any
    
    @staticmethod
    def is_union_type(annotation: Any) -> bool:
        """Check if type is Union[T1, T2, ...]"""
        return get_origin(annotation) is Union and not TypeAnalyzer.is_optional(annotation)
    
    @staticmethod
    def get_union_types(annotation: Any) -> List[Any]:
        """Get [T1, T2, ...] from Union[T1, T2, ...]"""
        if TypeAnalyzer.is_union_type(annotation):
            return list(get_args(annotation))
        return [annotation]
```

#### Safe Type Compatibility Checking
```python
class TypeCompatibility:
    """Safe type compatibility checking for modern Python types"""
    
    @staticmethod
    def is_compatible_with(annotation: Any, target_type: type) -> bool:
        """Safely check if annotation is compatible with target_type"""
        try:
            # Handle Optional types
            if TypeAnalyzer.is_optional(annotation):
                inner_type = TypeAnalyzer.get_optional_inner_type(annotation)
                return TypeCompatibility.is_compatible_with(inner_type, target_type)
            
            # Handle Union types
            if TypeAnalyzer.is_union_type(annotation):
                union_types = TypeAnalyzer.get_union_types(annotation)
                return any(
                    TypeCompatibility.is_compatible_with(t, target_type) 
                    for t in union_types
                )
            
            # Handle generic types
            origin = get_origin(annotation)
            if origin is not None:
                return issubclass(origin, target_type)
            
            # Handle regular types
            if isinstance(annotation, type):
                return issubclass(annotation, target_type)
                
            return False
        except (TypeError, AttributeError):
            return False
    
    @staticmethod
    def get_base_type(annotation: Any) -> Any:
        """Get the base type from a complex annotation"""
        if TypeAnalyzer.is_optional(annotation):
            return TypeCompatibility.get_base_type(
                TypeAnalyzer.get_optional_inner_type(annotation)
            )
        
        origin = get_origin(annotation)
        if origin is not None:
            return origin
            
        return annotation
```

### 2. Enhanced Field Metadata System

#### Robust Field Analysis
```python
class FieldMetadata:
    def __init__(self, name: str, type_annotation: Any, default: Any = None):
        self.name = name
        self.type_annotation = type_annotation
        self.default = default
        
        # Analyze type structure
        self.is_optional = TypeAnalyzer.is_optional(type_annotation)
        self.base_type = TypeCompatibility.get_base_type(type_annotation)
        self.is_list = TypeAnalyzer.is_generic_list(type_annotation)
        self.is_dict = TypeAnalyzer.is_generic_dict(type_annotation)
        
        # SQL type mapping
        self.sql_type = self._determine_sql_type()
        
    def _determine_sql_type(self) -> str:
        """Determine SQL type for this field"""
        base_type = self.base_type
        
        if TypeCompatibility.is_compatible_with(self.type_annotation, str):
            return "TEXT"
        elif TypeCompatibility.is_compatible_with(self.type_annotation, int):
            return "INTEGER"
        elif TypeCompatibility.is_compatible_with(self.type_annotation, float):
            return "REAL"
        elif TypeCompatibility.is_compatible_with(self.type_annotation, bool):
            return "INTEGER"  # SQLite stores booleans as integers
        elif self.is_list or self.is_dict:
            return "JSON"  # Store complex types as JSON
        else:
            return "BLOB"  # Fallback for unknown types
    
    def validate_value(self, value: Any) -> bool:
        """Validate that value matches this field's type"""
        return self._validate_recursive(value, self.type_annotation)
    
    def _validate_recursive(self, value: Any, expected_type: Any) -> bool:
        """Recursively validate value against type annotation"""
        # Handle None values
        if value is None:
            return TypeAnalyzer.is_optional(expected_type)
        
        # Handle Optional types
        if TypeAnalyzer.is_optional(expected_type):
            inner_type = TypeAnalyzer.get_optional_inner_type(expected_type)
            return self._validate_recursive(value, inner_type)
        
        # Handle List types
        if TypeAnalyzer.is_generic_list(expected_type):
            if not isinstance(value, list):
                return False
            item_type = TypeAnalyzer.get_list_item_type(expected_type)
            return all(self._validate_recursive(item, item_type) for item in value)
        
        # Handle Dict types
        if TypeAnalyzer.is_generic_dict(expected_type):
            if not isinstance(value, dict):
                return False
            key_type, value_type = TypeAnalyzer.get_dict_types(expected_type)
            return all(
                self._validate_recursive(k, key_type) and 
                self._validate_recursive(v, value_type)
                for k, v in value.items()
            )
        
        # Handle Union types
        if TypeAnalyzer.is_union_type(expected_type):
            union_types = TypeAnalyzer.get_union_types(expected_type)
            return any(self._validate_recursive(value, t) for t in union_types)
        
        # Handle basic types
        base_type = TypeCompatibility.get_base_type(expected_type)
        try:
            return isinstance(value, base_type)
        except TypeError:
            return True  # Fallback to permissive validation
```

### 3. Database Type Mapping

#### Advanced SQL Type Generation
```python
class DatabaseTypeMapper:
    """Map Python types to database-specific types"""
    
    def __init__(self, database_type: str):
        self.database_type = database_type
    
    def python_to_sql_type(self, py_type: Any) -> str:
        """Convert Python type to SQL type"""
        # Handle Optional types - same as inner type but nullable
        if TypeAnalyzer.is_optional(py_type):
            inner_type = TypeAnalyzer.get_optional_inner_type(py_type)
            return self.python_to_sql_type(inner_type)
        
        # Handle collection types
        if TypeAnalyzer.is_generic_list(py_type) or TypeAnalyzer.is_generic_dict(py_type):
            return self._get_json_type()
        
        # Handle basic types
        if TypeCompatibility.is_compatible_with(py_type, str):
            return "TEXT"
        elif TypeCompatibility.is_compatible_with(py_type, int):
            return "INTEGER"
        elif TypeCompatibility.is_compatible_with(py_type, float):
            return "REAL"
        elif TypeCompatibility.is_compatible_with(py_type, bool):
            return "INTEGER"  # Most databases store bool as int
        else:
            return self._get_blob_type()
    
    def _get_json_type(self) -> str:
        """Get JSON type for current database"""
        if self.database_type == "postgresql":
            return "JSONB"
        elif self.database_type == "mysql":
            return "JSON"
        else:  # SQLite, others
            return "TEXT"  # Store as JSON text
    
    def _get_blob_type(self) -> str:
        """Get BLOB type for current database"""
        if self.database_type == "postgresql":
            return "BYTEA"
        else:
            return "BLOB"
```

## Testing Strategy

### Unit Tests for Type Analysis
```python
class TestTypeAnalyzer:
    def test_optional_detection(self):
        assert TypeAnalyzer.is_optional(Optional[str])
        assert TypeAnalyzer.is_optional(Union[str, None])
        assert not TypeAnalyzer.is_optional(str)
        assert not TypeAnalyzer.is_optional(Union[str, int])
    
    def test_generic_list_detection(self):
        assert TypeAnalyzer.is_generic_list(List[str])
        assert TypeAnalyzer.is_generic_list(List[int])
        assert not TypeAnalyzer.is_generic_list(str)
        assert not TypeAnalyzer.is_generic_list(list)  # Non-generic
    
    def test_complex_type_analysis(self):
        complex_type = Optional[List[Dict[str, Union[str, int]]]]
        
        assert TypeAnalyzer.is_optional(complex_type)
        inner = TypeAnalyzer.get_optional_inner_type(complex_type)
        assert TypeAnalyzer.is_generic_list(inner)
```

### Integration Tests with Models
```python
class TestComplexModelTypes:
    async def test_model_with_complex_types(self):
        @ommi_model
        @dataclass
        class ComplexModel:
            id: int
            name: Optional[str] = None
            tags: List[str] = field(default_factory=list)
            metadata: Dict[str, Any] = field(default_factory=dict)
            settings: Union[str, dict] = ""
        
        # Should not raise TypeError during registration
        async with SQLiteDriver.from_config(config) as db:
            await db.schema().create_models()  # Should work
            
            model = ComplexModel(
                id=1,
                name="test",
                tags=["python", "orm"],
                metadata={"version": 1, "active": True},
                settings={"theme": "dark"}
            )
            
            await db.add(model)  # Should work
            found = await db.find(ComplexModel.id == 1).fetch.one()
            assert found.name == "test"
```

### Validation Tests
```python
class TestTypeValidation:
    def test_optional_validation(self):
        field = FieldMetadata("name", Optional[str])
        
        assert field.validate_value("hello")  # Valid string
        assert field.validate_value(None)     # Valid None
        assert not field.validate_value(123) # Invalid int
    
    def test_list_validation(self):
        field = FieldMetadata("tags", List[str])
        
        assert field.validate_value(["a", "b"])    # Valid list of strings
        assert not field.validate_value(["a", 1]) # Invalid mixed types
        assert not field.validate_value("string") # Invalid non-list
```

## Success Criteria

### Technical Requirements
- **Zero `TypeError: issubclass()` errors** for standard type annotations
- **Support for all common typing constructs** (Optional, List, Dict, Union, etc.)
- **Proper SQL type mapping** for complex types
- **Runtime validation** working for nested generic types

### Functional Requirements
```python
# All these should work without errors:
@ommi_model
@dataclass
class AdvancedModel:
    # Basic types
    id: int
    name: str
    
    # Optional types
    description: Optional[str] = None
    
    # Generic collections
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Union types
    config: Union[str, dict] = ""
    
    # Nested generics
    data: Dict[str, List[Optional[int]]] = field(default_factory=dict)
    
    # Forward references
    parent: Optional['AdvancedModel'] = None
```

## Implementation Timeline

### Week 1: Core Type Analysis
- Implement `TypeAnalyzer` class
- Add `TypeCompatibility` checking
- Replace all `issubclass()` calls with safe alternatives

### Week 2: Field Metadata Enhancement
- Update `FieldMetadata` to use new type system
- Implement recursive type validation
- Add comprehensive type mapping

### Week 3: Database Integration
- Update SQL type generation
- Fix schema creation for complex types
- Add JSON handling for collections

### Week 4: Testing & Validation
- Comprehensive test suite for type system
- Integration tests with complex models
- Performance testing for type analysis

This type system improvement will make Ommi much more robust and compatible with modern Python development practices, eliminating a major source of runtime errors.