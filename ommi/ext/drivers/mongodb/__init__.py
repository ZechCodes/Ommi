"""MongoDB driver implementation for Ommi.

This module provides a MongoDB database driver for the Ommi ORM, offering a document-oriented
database solution with the flexibility of schema-less collections. The MongoDB driver
bridges the gap between Ommi's ORM patterns and MongoDB's document model, providing a
consistent interface while preserving MongoDB's unique strengths.

Key features:

- Asynchronous database operations using Motor
- Support for MongoDB's rich query language
- Seamless integration with Ommi's ORM patterns

Example:
    ```python
    from ommi import Ommi, ommi_model
    from ommi.ext.drivers.mongodb import MongoDBDriver, MongoDBSettings
    
    # Connect with custom settings
    settings = MongoDBSettings(
        host="localhost", 
        port=27017,
        database_name="my_database",
        username="mongo_user",  # Optional
        password="secure_password",  # Optional
        authSource="admin",
        connection_options={"tlsAllowInvalidCertificates": True}  # Optional
    )
    
    # Connect to MongoDB
    db = Ommi(MongoDBDriver.connect(settings))
    
    # Define a model
    @ommi_model
    class Document:
        id: str
        title: str
        tags: list[str]
        metadata: dict
    
    async def main():
        # Set up schema for models (creates collections)
        await db.use_models()
        
        # Add a new document
        doc = Document(
            title="MongoDB Guide", 
            tags=["database", "nosql", "document"], 
            metadata={"author": "John Doe", "published": True}
        )
        result = await db.add(doc)
        
        # Query documents
        docs = await db.find(Document.tags.contains("nosql")).all()
        
        # Use transactions (requires MongoDB replica set)
        async with db.transaction() as txn:
            await txn.add(Document(
                title="Advanced MongoDB",
                tags=["database", "advanced"],
                metadata={"author": "Jane Smith", "published": False}
            ))
            await txn.update(Document.title == "MongoDB Guide", {"metadata.views": 100})
            # Transaction will commit automatically if no exceptions occur
            
        # Disconnect when done
        await db.driver.disconnect()
    ```
"""

from .driver import MongoDBDriver, MongoDBSettings
from .transaction import MongoDBTransaction


__all__ = ["MongoDBDriver", "MongoDBSettings", "MongoDBTransaction"]