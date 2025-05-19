"""PostgreSQL driver implementation for Ommi.

This module provides a PostgreSQL database driver for the Ommi ORM, offering a robust and
feature-rich solution for working with PostgreSQL databases. The PostgreSQL driver is
well-suited for production environments, complex applications, and systems requiring
advanced database features.

Key features:

- Asynchronous database operations using psycopg3
- Transaction management with ACID guarantees
- Schema management for model collections

Example:
    ```python
    from ommi import Ommi, ommi_model
    from ommi.ext.drivers.postgresql import PostgreSQLDriver, PostgreSQLSettings
    
    # Connect with custom settings
    settings = PostgreSQLSettings(
        host="localhost",
        port=5432,
        database="my_database",
        user="postgres_user",
        password="secure_password"
    )
    
    # Connect to PostgreSQL asynchronously
    async def setup():
        driver = await PostgreSQLDriver.connect(settings)
        db = Ommi(driver)
        return db
    
    # Define a model
    @ommi_model
    class Product:
        id: int
        name: str
        price: float
        in_stock: bool
    
    async def main():
        db = await setup()
        
        # Set up schema for models
        await db.use_models()
        
        # Add a new product
        product = Product(name="Laptop", price=999.99, in_stock=True)
        result = await db.add(product)
        
        # Query products
        expensive_products = await db.find(Product.price > 500).all()
        
        # Use transactions
        async with db.transaction() as txn:
            await txn.add(Product(name="Smartphone", price=699.99, in_stock=True))
            await txn.update(Product.name == "Laptop", {"price": 899.99})
            # Transaction will commit automatically if no exceptions occur
            
        # Disconnect when done
        await db.driver.disconnect()
    ```
"""

from .driver import PostgreSQLDriver, PostgreSQLSettings
from .transaction import PostgreSQLTransaction

__all__ = ["PostgreSQLDriver", "PostgreSQLSettings", "PostgreSQLTransaction"]
