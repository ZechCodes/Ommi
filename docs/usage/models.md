# Working with Models

Ommi primarily uses Python `dataclasses` decorated with `@ommi_model` to define your data structures. When you define models this way without assigning them to a specific collection, Ommi automatically manages their database schema (e.g., creating tables when they are first used or when the Ommi instance initializes).

While Ommi is built with dataclasses in mind, its flexibility might allow for other model types if they can be adapted to Ommi's introspection mechanisms. However, the standard and tested approach is to use `@ommi_model` with `@dataclass`.

## Defining Models (Default Automatic Schema Management)

You define your data structures using `@dataclass` and then decorate them with `@ommi_model()`. These models are implicitly part of a default setup managed by Ommi.

```python
import asyncio
from dataclasses import dataclass
from typing import Optional, Annotated

from ommi import Ommi, ommi_model
from ommi.models.field_metadata import Key, Auto, StoreAs
from ommi.ext.drivers.sqlite import SQLiteDriver

# Models defined with @ommi_model() are automatically managed by Ommi regarding their schema.
@ommi_model()
@dataclass
class Product:
    product_id: Annotated[int, Key | Auto]
    name: str
    description: Optional[str] = None
    price: float
    stock_count: int = 0

@ommi_model()
@dataclass
class Customer:
    customer_id: Annotated[int, Key]
    first_name: str
    last_name: str
    email: str
    created_at: Annotated[str, StoreAs("registration_date")]

async def setup_and_use_models():
    driver = SQLiteDriver.connect()
    async with Ommi(driver) as db:
        # No explicit schema setup call is needed here for these default models.
        # Ommi handles their schema automatically.
        print("Product and Customer tables will be managed automatically by Ommi.")

        new_product = Product(product_id=1, name="Laptop", price=1200.00, stock_count=50)
        await db.add(new_product).or_raise()
        print(f"Added product: {new_product}")

        retrieved_product = await db.find(Product.product_id == 1).one.or_raise()
        print(f"Found: {retrieved_product}")

        await db.find(Product.product_id == 1).update(price=1150.00, stock_count=45).or_raise()
        updated_product = await db.find(Product.product_id == 1).one.or_raise()
        print(f"Updated: {updated_product}")

        available_count = await db.find(Product.stock_count > 0).count.or_raise()
        print(f"Products available: {available_count}")

        # Teardown for automatically managed tables depends on DB & driver.
        # In-memory SQLite tables are gone when connection closes.

# if __name__ == "__main__":
#     asyncio.run(setup_and_use_models())

```

**Key Points for Model Definition:**

*   **`@ommi_model()`:** Decorates your dataclass. Without a `collection` argument, Ommi handles its schema implicitly.
*   **`@dataclass`:** Standard for field definitions.
*   **Type Hinting & Metadata (`typing.Annotated`):** For database-specific properties like `Key`, `Auto`, `StoreAs`, `ReferenceTo` from `ommi.models.field_metadata`. Combine using `|`.
*   **Automatic Schema Handling (Default):** For models not assigned to an explicit collection, Ommi manages table creation/updates automatically. You don't need to call explicit setup functions for them.
*   **Explicit Model Collections:** For more control, use explicit `ModelCollection` instances. These require `await db.use_models(your_collection)` for schema setup. (See the [Model Collections](model-collections.md) tutorial).

## Using Models with `Ommi`

Once your models are defined and their tables created via `collection.setup_on(db)`:

*   **Adding Objects:** `await db.add(YourModel(...)).or_raise()`
*   **Finding Objects:** `await db.find(YourModel.field == value).one.or_raise()` (for a single object) or `await db.find(...).or_raise()` (for multiple, then iterate asynchronously).
*   **Updating Objects:** `await db.find(YourModel.field == value).update(new_field_value=...).or_raise()`
*   **Deleting Objects:** `await db.find(YourModel.field == value).delete.or_raise()`
*   **Counting Objects:** `await db.find(YourModel.field == value).count.or_raise()`

All interactions are asynchronous and utilize the `Ommi` instance (`db`). The `.or_raise()` method is commonly used to raise an exception if the operation fails or finds no results (for `.one`).

Next, learn about [Lazy Fields (Query Fields)](lazy-fields.md), which also work with these automatically managed models. 