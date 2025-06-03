# Driver Interface Pattern

## Overview
This document defines the clean separation between drivers and the interface layer, ensuring drivers remain simple while the interface layer handles all result wrapping and error management.

## Core Principle: Driver Simplicity

### Driver Responsibility
**Drivers should ONLY:**
- Execute raw database operations
- Convert database results to appropriate Python types/model instances
- Raise appropriate exceptions on errors
- Handle database-specific connection and transaction management

### Driver Should NEVER:
- Create or handle `DatabaseResult` wrappers
- Create `AsyncResultWrapper` objects
- Implement retry logic or complex error handling
- Handle cross-cutting concerns like caching or logging

## Interface Layer Responsibility

### Interface Layer Handles:
- **Result Wrapping:** Convert driver returns/exceptions to `DatabaseResult` objects
- **Async Coordination:** Manage `AsyncResultWrapper` creation and handling
- **Error Standardization:** Convert driver-specific exceptions to standard error types
- **Cross-cutting Concerns:** Logging, caching, retry logic, circuit breakers

## Driver Interface Contract

### Method Signature Pattern
```python
# Driver methods return concrete types or raise exceptions
class DatabaseDriver(ABC):
    
    @abstractmethod
    async def add_models(self, models: Iterable[Model]) -> List[Model]:
        """
        Add models to database.
        
        Returns: List of models with populated IDs
        Raises: DatabaseError subclass on failure
        """
        pass
    
    @abstractmethod
    async def fetch_models(self, query: ASTNode) -> List[Model]:
        """
        Fetch models matching query.
        
        Returns: List of matching model instances
        Raises: DatabaseError subclass on failure
        """
        pass
    
    @abstractmethod
    async def update_models(self, query: ASTNode, updates: Dict[str, Any]) -> int:
        """
        Update models matching query.
        
        Returns: Number of models updated
        Raises: DatabaseError subclass on failure
        """
        pass
    
    @abstractmethod
    async def delete_models(self, query: ASTNode) -> int:
        """
        Delete models matching query.
        
        Returns: Number of models deleted
        Raises: DatabaseError subclass on failure
        """
        pass
    
    @abstractmethod
    async def count_models(self, query: ASTNode) -> int:
        """
        Count models matching query.
        
        Returns: Number of matching models
        Raises: DatabaseError subclass on failure
        """
        pass
```

### Driver Exception Hierarchy
```python
class DatabaseError(Exception):
    """Base exception for all database errors"""
    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message)
        self.original_error = original_error

class ConnectionError(DatabaseError):
    """Database connection failed"""
    pass

class QueryError(DatabaseError):
    """Query execution failed"""
    pass

class ConstraintError(DatabaseError):
    """Database constraint violation"""
    pass

class TransactionError(DatabaseError):
    """Transaction operation failed"""
    pass

class SchemaError(DatabaseError):
    """Schema operation failed"""
    pass
```

## Interface Layer Implementation

### Result Wrapping Pattern
```python
class DatabaseInterface:
    """Interface layer that wraps driver operations"""
    
    def __init__(self, driver: DatabaseDriver):
        self._driver = driver
    
    async def add(self, *models: Model) -> AsyncResultWrapper[List[Model]]:
        """Add models with result wrapping"""
        async def _execute():
            try:
                result = await self._driver.add_models(models)
                return DatabaseResult.Success(result)
            except DatabaseError as e:
                return DatabaseResult.Failure(e)
            except Exception as e:
                # Wrap unexpected exceptions
                wrapped_error = DatabaseError(f"Unexpected error: {e}", e)
                return DatabaseResult.Failure(wrapped_error)
        
        return AsyncResultWrapper(_execute())
    
    def find(self, *conditions: ASTNode) -> QueryBuilder:
        """Create query builder for find operations"""
        return QueryBuilder(self._driver, conditions)

class QueryBuilder:
    """Query builder that wraps driver fetch operations"""
    
    def __init__(self, driver: DatabaseDriver, conditions: List[ASTNode]):
        self._driver = driver
        self._conditions = conditions
        self._query_ast = self._build_ast()
    
    async def fetch(self) -> AsyncResultWrapper[List[Model]]:
        """Fetch models with result wrapping"""
        async def _execute():
            try:
                models = await self._driver.fetch_models(self._query_ast)
                return DatabaseResult.Success(models)
            except DatabaseError as e:
                return DatabaseResult.Failure(e)
            except Exception as e:
                wrapped_error = DatabaseError(f"Query execution failed: {e}", e)
                return DatabaseResult.Failure(wrapped_error)
        
        return AsyncResultWrapper(_execute())
    
    async def count(self) -> AsyncResultWrapper[int]:
        """Count models with result wrapping"""
        async def _execute():
            try:
                count = await self._driver.count_models(self._query_ast)
                return DatabaseResult.Success(count)
            except DatabaseError as e:
                return DatabaseResult.Failure(e)
            except Exception as e:
                wrapped_error = DatabaseError(f"Count operation failed: {e}", e)
                return DatabaseResult.Failure(wrapped_error)
        
        return AsyncResultWrapper(_execute())
```

## Driver Implementation Examples

### SQLite Driver Example
```python
class SQLiteDriver(DatabaseDriver):
    """Clean SQLite driver implementation"""
    
    async def add_models(self, models: Iterable[Model]) -> List[Model]:
        """Add models to SQLite database"""
        if not models:
            return []
        
        models_list = list(models)
        
        try:
            async with self._get_connection() as conn:
                for model in models_list:
                    sql, params = self._build_insert_sql(model)
                    cursor = await conn.execute(sql, params)
                    
                    # Set the generated ID if it's an auto-increment field
                    if hasattr(model, 'id') and model.id is None:
                        model.id = cursor.lastrowid
                
                await conn.commit()
                return models_list
                
        except sqlite3.Error as e:
            raise QueryError(f"Failed to insert models: {e}", e)
        except Exception as e:
            raise DatabaseError(f"Unexpected error during insert: {e}", e)
    
    async def fetch_models(self, query: ASTNode) -> List[Model]:
        """Fetch models from SQLite database"""
        try:
            sql, params = self._translate_query_to_sql(query)
            
            async with self._get_connection() as conn:
                cursor = await conn.execute(sql, params)
                rows = await cursor.fetchall()
                
                models = []
                for row in rows:
                    model = self._row_to_model(row, query.model_type)
                    models.append(model)
                
                return models
                
        except sqlite3.Error as e:
            raise QueryError(f"Query execution failed: {e}", e)
        except Exception as e:
            raise DatabaseError(f"Unexpected error during fetch: {e}", e)
    
    async def count_models(self, query: ASTNode) -> int:
        """Count models in SQLite database"""
        try:
            sql, params = self._translate_query_to_count_sql(query)
            
            async with self._get_connection() as conn:
                cursor = await conn.execute(sql, params)
                row = await cursor.fetchone()
                return row[0] if row else 0
                
        except sqlite3.Error as e:
            raise QueryError(f"Count query failed: {e}", e)
        except Exception as e:
            raise DatabaseError(f"Unexpected error during count: {e}", e)
```

### MongoDB Driver Example
```python
class MongoDriver(DatabaseDriver):
    """Clean MongoDB driver implementation"""
    
    async def add_models(self, models: Iterable[Model]) -> List[Model]:
        """Add models to MongoDB collection"""
        if not models:
            return []
        
        models_list = list(models)
        
        try:
            collection = self._get_collection(models_list[0].__class__)
            documents = [self._model_to_document(model) for model in models_list]
            
            result = await collection.insert_many(documents)
            
            # Set the generated IDs
            for model, inserted_id in zip(models_list, result.inserted_ids):
                if hasattr(model, 'id') and model.id is None:
                    model.id = str(inserted_id)
            
            return models_list
            
        except pymongo.errors.PyMongoError as e:
            raise QueryError(f"Failed to insert documents: {e}", e)
        except Exception as e:
            raise DatabaseError(f"Unexpected error during insert: {e}", e)
    
    async def fetch_models(self, query: ASTNode) -> List[Model]:
        """Fetch models from MongoDB collection"""
        try:
            collection = self._get_collection(query.model_type)
            mongo_query = self._translate_query_to_mongo(query)
            
            cursor = collection.find(mongo_query)
            documents = await cursor.to_list(None)
            
            models = []
            for doc in documents:
                model = self._document_to_model(doc, query.model_type)
                models.append(model)
            
            return models
            
        except pymongo.errors.PyMongoError as e:
            raise QueryError(f"Query execution failed: {e}", e)
        except Exception as e:
            raise DatabaseError(f"Unexpected error during fetch: {e}", e)
```

## Benefits of This Pattern

### 1. Driver Simplicity
- **Focused Responsibility:** Drivers only handle database-specific operations
- **Easier Testing:** Test drivers with simple inputs/outputs
- **Clearer Code:** No mixing of business logic with database operations
- **Better Maintainability:** Changes to result handling don't affect drivers

### 2. Rich Error Context
- **Preserve Original Errors:** Driver exceptions maintain full context
- **Standardized Handling:** Interface layer provides consistent error experience
- **Better Debugging:** Full stack trace available from original database error
- **Flexible Error Policies:** Interface can implement retry, circuit breaker, etc.

### 3. Implementation Flexibility
- **Driver Independence:** Drivers can use any internal patterns
- **Interface Evolution:** Result handling can evolve without driver changes
- **Cross-cutting Concerns:** Logging, metrics, caching added at interface layer
- **Testing Isolation:** Unit test drivers and interface layer separately

## Migration Strategy

### Current State Issues
The current implementation likely has drivers creating `DatabaseResult` objects, causing the `DBStatusNoResultException` errors.

### Fix Approach
1. **Update Driver Contracts:** Remove all result wrapping from drivers
2. **Implement Interface Layer:** Add result wrapping at interface boundaries
3. **Update Error Handling:** Ensure drivers raise appropriate exceptions
4. **Fix Lazy Loading:** Update lazy fields to use interface layer

### Example Fix for Lazy Loading
```python
# Current broken pattern (inferred)
class LazyLoadTheRelated:
    async def __await__(self):
        result = await self._driver.fetch_related(...)  # Returns wrapped result
        return result.value  # Fails if not properly wrapped

# Fixed pattern
class LazyLoadTheRelated:
    async def __await__(self):
        try:
            # Driver returns models directly or raises exception
            models = await self._driver.fetch_related(...)
            return models
        except DatabaseError as e:
            # Handle errors appropriately for lazy loading
            if self._return_empty_on_error:
                return []
            raise
```

## Testing Strategy

### Driver Testing
```python
class TestSQLiteDriver:
    async def test_add_models_success(self):
        """Test driver returns models directly"""
        driver = SQLiteDriver(config)
        models = [User(name="Alice"), User(name="Bob")]
        
        result = await driver.add_models(models)
        
        # Driver returns models directly, not wrapped
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(user.id is not None for user in result)
    
    async def test_add_models_failure(self):
        """Test driver raises appropriate exception"""
        driver = SQLiteDriver(config)
        
        with pytest.raises(DatabaseError):
            await driver.add_models([InvalidModel()])
```

### Interface Layer Testing
```python
class TestDatabaseInterface:
    async def test_add_success_wrapping(self):
        """Test interface wraps driver success"""
        mock_driver = Mock()
        mock_driver.add_models.return_value = [User(id=1, name="Alice")]
        
        interface = DatabaseInterface(mock_driver)
        result = await interface.add(User(name="Alice"))
        
        # Interface returns wrapped result
        assert isinstance(result, AsyncResultWrapper)
        value = await result.value
        assert isinstance(value, list)
    
    async def test_add_error_wrapping(self):
        """Test interface wraps driver errors"""
        mock_driver = Mock()
        mock_driver.add_models.side_effect = QueryError("Database error")
        
        interface = DatabaseInterface(mock_driver)
        result = await interface.add(User(name="Alice"))
        
        # Interface wraps error in result
        db_result = await result
        assert isinstance(db_result, DatabaseResult.Failure)
```

This pattern ensures clean separation of concerns while enabling rich error context and simpler driver implementations.