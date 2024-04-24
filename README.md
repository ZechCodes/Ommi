# Ommi

> [!CAUTION]
> Ommi is under construction and much of the functionality is undergoing frequent revision. There is no guaratee future versions will be backwards compatible.

An object model mapper intended to provide a consistent interface for many underlying database implementations using whatever model implementations are desired.

### Compatible Model Implementations

My test suite checks for compatibility with the following model implementations:

- Python's `dataclass` model types
- [Attrs](https://www.attrs.org/en/stable/comparison.html) model types
- [Pydantic](https://docs.pydantic.dev/latest/) model types

### Included Database Support

- SQLite3 (Basic functionality, ⚠️Under Construction⚠️)

### Defining Models

All models that support Ommi database drivers need to use the `ommi_model` class decorator.
```python
from ommi import ommi_model, Key
from dataclasses import dataclass
from typing import Annotated

@ommi_model
@dataclass
class User:
    name: str
    age: int
    id: Annotated[int, Key] = None  # Optional primary key
```

### Connecting

```python
from ommi.ext.drivers.sqlite import SQLiteDriver, SQLiteConfig


async def example():
    async with SQLiteDriver(SQLiteConfig(filename=":memory:")) as db:
        ...
```

### Database Actions

The database driver object provides `add`, `delete`, `update`