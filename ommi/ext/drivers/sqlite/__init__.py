"""SQLite driver implementation for Ommi.

This module provides a SQLite database driver for the Ommi ORM, offering a simple and
lightweight database solution. The SQLite driver is ideal for local development, 
testing, small applications, or embedded systems where a full client-server database
is not required.

Key features:

- In-memory or file-based database support
- Configurable transaction isolation levels
- Full support for all Ommi ORM operations
- Schema management for model collections

Example:
    ```python
    from ommi import Ommi, ommi_model
    from ommi.ext.drivers.sqlite import SQLiteDriver, SQLiteSettings
    
    # Connect to an in-memory SQLite database (default)
    db = Ommi(SQLiteDriver.connect())
    
    # Or connect to a file-based database with custom settings
    settings = SQLiteSettings(
        database="my_database.db",
        isolation_level="IMMEDIATE"  # Options: "OMMI_DEFAULT", "SQLITE_DEFAULT", "DEFERRED", "IMMEDIATE", "EXCLUSIVE", "NONE"
    )
    db = Ommi(SQLiteDriver.connect(settings))
    
    # Define a model
    @ommi_model
    class User:
        id: int
        name: str
        age: int
    
    async def main():
        # Set up schema for models
        await db.use_models()
        
        # Add a new user
        user = User(name="Alice", age=30)
        result = await db.add(user)
        
        # Query users
        users = await db.find(User.age > 25).all()
        
        # Use transactions
        async with db.transaction() as txn:
            await txn.add(User(name="Bob", age=28))
            await txn.add(User(name="Charlie", age=35))
            # Transaction will commit automatically if no exceptions occur
    ```
"""

from .driver import SQLiteDriver, SQLiteSettings
from .transaction import SQLiteTransaction


__all__ = ["SQLiteDriver", "SQLiteSettings", "SQLiteTransaction"]
