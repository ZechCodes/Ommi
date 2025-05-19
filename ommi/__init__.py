"""Ommi ORM Package.

This is the main package for Ommi, a modern, asynchronous Object-Relational Mapper (ORM)
for the 80% case. It provides a flexible and intuitive way to interact with various
databases, focusing on ease of use, type safety, and asynchronous operations.

Key features of Ommi include:

-   **Asynchronous Core**: Built from the ground up for `async/await` syntax, making
    it suitable for high-performance, I/O-bound applications.
-   **Intuitive Model Definition**: Define database models using simple Python classes
    and type hints with the `@ommi_model` decorator. It works with various model types
    including Pydantic, attrs, and standard dataclasses.
-   **Versatile Querying**: Construct database queries using Pythonic expressions.
-   **Driver-Based Architecture**: Supports multiple database backends through a
    pluggable driver system. The bundled drivers include SQLite, PostgreSQL, and
    MongoDB.
-   **Transaction Management**: Provides robust mechanisms for managing database
    transactions using async context managers.
-   **Schema Management**: Utilities for applying and deleting database schemas based
    on your model definitions.

Note:
This `__init__.py` file uses a custom `__getattr__` to enable lazy loading of
submodules and specific symbols, improving import times, reducing initial overhead, and
avoiding some circular import issues.
"""
import importlib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ommi.drivers import BaseDriver, BaseDriverTransaction
    from ommi.driver_context import active_driver, use_driver
    from ommi.models import ommi_model
    from ommi.models.field_metadata import Auto, Key, FieldType, StoreAs
    from ommi.database import Ommi, DBResult, DBQueryResult, OmmiTransaction

__lookup = {
    "BaseDriver": "ommi.drivers",
    "BaseDriverTransaction": "ommi.drivers",
    "active_driver": "ommi.driver_context",
    "use_driver": "ommi.driver_context",
    "Ommi": "ommi.database",
    "ommi_model": "ommi.models",
    "FieldType": "ommi.models.field_metadata",
    "StoreAs": "ommi.models.field_metadata",
    "Auto": "ommi.models.field_metadata",
    "Key": "ommi.models.field_metadata",
    "DBResult": "ommi.database",
    "DBQueryResult": "ommi.database",
    "OmmiTransaction": "ommi.database",
}

__all__ = list(__lookup.keys())

__modules = set()

# Iterate the local folder and search for all py files and folders
for _path in Path(__file__).parent.iterdir():
    if _path.name.startswith("_"):
        continue

    if not _path.is_dir() and _path.suffix != ".py":
        continue

    __modules.add(_path.stem)


def __getattr__(name):
    """Lazily loads submodules and specific symbols for the Ommi package.

    This function is a part of Python's module import machinery. It's called when an
    attribute (submodule or symbol) is accessed on the `ommi` package that hasn't
    been explicitly imported or defined.

    It serves two main purposes:

    1.  **Lazy Loading of Predefined Symbols**: For a specific set of important symbols
        (like `Ommi`, `ommi_model`, `BaseDriver`, etc.), it imports them from their
        respective submodules on demand. This is managed by the `__lookup` dictionary.
    2.  **Lazy Loading of Submodules**: For any other name that matches a submodule
        within the `ommi` package (e.g., `ommi.database`, `ommi.models`), it imports
        that submodule. This is managed by inspecting the filesystem and populating
        the `__modules` set.

    This approach helps in reducing the initial import time of the `ommi` package,
    as modules and symbols are only loaded when they are actually used.

    Args:
        name (str): The name of the attribute being accessed.

    Returns:
        The requested module or symbol.

    Raises:
        ImportError: If a symbol listed in `__lookup` cannot be imported from its
                     specified module.
        AttributeError: If the requested name does not correspond to a known symbol
                        or submodule.
    """
    if name in __lookup:
        try:
            module = importlib.import_module(__lookup[name])
        except Exception as e:
            raise ImportError(f"Failed to import {name} from {__lookup[name]}: {e}") from e

        return getattr(module, name)

    if name in __modules:
        return importlib.import_module(f"ommi.{name}")

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
