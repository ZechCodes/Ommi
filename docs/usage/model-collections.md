# Using Explicit Model Collections

By default, Ommi automatically manages the database schema for models defined with `@ommi_model()` that are not assigned to a specific collection (these effectively belong to an implicit, global setup). However, for more structured applications, using explicit `ModelCollection` instances provides greater control over model grouping and schema management.

## Why Use Explicit Model Collections?

*   **Modularity:** Group related models for different features or domains.
*   **Granular Schema Management:** Set up or tear down tables for specific model groups independently using `await db.use_models(your_collection)`.
*   **Testing:** Easily manage schemas for specific test suites.
*   **Clarity:** Clearly define which models belong together.

## How to Use Explicit Model Collections

1.  **Import `ModelCollection`:** From `ommi.models.collections`.
2.  **Instantiate Collections:** Create one or more `ModelCollection` instances (e.g., `core_models = ModelCollection()`, `feature_models = ModelCollection()`).
3.  **Assign Models:** Use `@ommi_model(collection=your_collection_instance)` to associate models with an explicit collection.
4.  **Manage Schema via `Ommi` instance:** Use `await db.use_models(your_collection_instance)` to create tables for that collection and `await db.remove_models(your_collection_instance)` to remove them.

### Example

```python
import asyncio
from dataclasses import dataclass
from typing import Optional, Annotated

from ommi import Ommi, ommi_model
from ommi.models.collections import ModelCollection
from ommi.models.field_metadata import Key, Auto
from ommi.ext.drivers.sqlite import SQLiteDriver

# 1. Instantiate explicit collections
core_app_models = ModelCollection()
blog_feature_models = ModelCollection()

# --- Models assigned to core_app_models ---
@ommi_model(collection=core_app_models)
@dataclass
class User:
    id: Annotated[int, Key | Auto]
    username: str

# --- Models assigned to blog_feature_models ---
@ommi_model(collection=blog_feature_models)
@dataclass
class BlogPost:
    post_id: Annotated[int, Key | Auto]
    title: str
    author_id: int # FK to User.id

# --- A model NOT in an explicit collection (part of Ommi's default/global setup) ---
@ommi_model()
@dataclass
class LogEntry:
    log_id: Annotated[int, Key | Auto]
    message: str

async def manage_collections_example():
    driver = SQLiteDriver.connect()
    async with Ommi(driver) as db:
        # Ommi automatically handles schema for LogEntry (default/global setup)
        # For explicit collections, we call db.use_models() with the collection:
        print("Setting up tables for core_app_models...")
        await db.use_models(core_app_models)

        print("Setting up tables for blog_feature_models...")
        await db.use_models(blog_feature_models)

        print("Explicit collection tables created. Default model tables (LogEntry) managed automatically.")

        # Add some data
        await db.add(User(username="core_user")).or_raise()
        await db.add(BlogPost(title="My Blog Post", author_id=1)).or_raise() # Assuming User ID 1 exists
        await db.add(LogEntry(message="Application started")).or_raise()

        print(f"User count: {await db.find(User).count.or_raise()}")
        print(f"BlogPost count: {await db.find(BlogPost).count.or_raise()}")
        print(f"LogEntry count: {await db.find(LogEntry).count.or_raise()}")

        # Teardown for explicit collections
        print("Removing tables for blog_feature_models...")
        await db.remove_models(blog_feature_models)

        print("Removing tables for core_app_models...")
        await db.remove_models(core_app_models)

        # Tables for LogEntry (default/global) would remain if DB is persistent,
        # or be gone if DB is in-memory and connection is closed.

        print("Explicit collection tables removed.")

if __name__ == "__main__":
    asyncio.run(manage_collections_example())
```

## Key Takeaways

*   **`@ommi_model(collection=...)`**: Assigns a model to an explicit collection.
*   **`await db.use_models(your_collection)`**: Essential for creating tables for models within an *explicit* collection.
*   **`await db.remove_models(your_collection)`**: Removes tables for an *explicit* collection.
*   **Automatic Handling for Default Models**: Models defined with `@ommi_model()` (no `collection`) have their schema managed implicitly by Ommi. You do *not* call `db.use_models()` without arguments for this purpose.
*   **Mixing**: You can have some models in explicit collections and others handled by Ommi's default mechanism within the same application.

Explicit model collections give you precise control when your project's complexity grows. 