# Getting Started with Ommi

This guide will walk you through the initial setup of Ommi in your project.

## Installation

Ommi is available on PyPI and can be installed using Poetry (or pip). Since this project uses Poetry, you would typically add it to your `pyproject.toml`:

```bash
poetry add ommi
```

You will also need a driver for your target database. For example, to use SQLite (which is great for getting started):

```bash
poetry add ommi-sqlite # Or the specific package name for the SQLite driver if different
```
You may need to install `ommi[sqlite]` if the driver is an extra.

## Basic Setup

The core of using Ommi involves:
1. Defining your models using `@ommi_model()`.
2. Initializing an `Ommi` instance with a configured driver.
3. Ommi automatically handles the database schema (like creating tables) for your defined models when needed.

Here's an example using an in-memory SQLite database:

```python
import asyncio
from dataclasses import dataclass
from typing import Optional

from ommi import Ommi, ommi_model
from ommi.ext.drivers.sqlite import SQLiteDriver

# 1. Define your models
# Models decorated with @ommi_model() are automatically managed by Ommi.
@ommi_model()
@dataclass
class User:
    id: int # Ommi typically infers primary keys from fields named 'id' or via Key metadata.
    name: str
    email: Optional[str] = None

async def main():
    # 2. Initialize your chosen driver
    driver = SQLiteDriver.connect()

    # 3. Initialize Ommi with the driver
    # The Ommi instance will manage the schema for models like User.
    async with Ommi(driver) as db:
        print("Ommi is ready. User table will be created automatically when needed.")

        # Now you can use `db` to interact with your database!
        # The first operation on a model might trigger table creation if it doesn't exist.
        new_user = User(id=1, name="Alice", email="alice@example.com")
        await db.add(new_user).or_raise()
        print(f"Added user: {new_user}")

        retrieved_user = await db.find(User.id == 1).one.or_raise()
        print(f"Found user: {retrieved_user}")

        # Schema teardown for such automatically managed models is usually handled
        # by the database connection lifecycle or specific driver features,
        # especially for in-memory databases that are discarded on disconnect.
        # For persistent databases, tables remain unless explicitly dropped.

if __name__ == "__main__":
    asyncio.run(main())
```

**Important Notes:**

*   **Async Operations:** Ommi is designed for asynchronous programming.
*   **Automatic Schema Management (Default):** When you define models with `@ommi_model()` (without specifying a `collection`), Ommi automatically handles their table creation as needed (e.g., on first use or when the `Ommi` instance is initialized). You generally don't need to call an explicit schema setup function for this default case.
*   **Explicit Collections:** For more control over groups of models, especially in larger projects, you can use explicit `ModelCollection` instances. These require specific setup calls (e.g., `await db.use_models(your_collection)`). This is detailed in the [Model Collections](usage/model-collections.md) tutorial.
*   **Driver Specifics:** Driver initialization and database behavior can vary.
*   **Focus on `Ommi`:** All database operations are performed through the `Ommi` instance (`db`).

Next, learn how to further define and work with [Models](usage/models.md). 