import importlib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ommi.drivers import BaseDriver, BaseDriverTransaction
    from ommi.driver_context import active_driver, use_driver
    from ommi.models import ommi_model
    from ommi.models.field_metadata import Auto, Key, FieldType, StoreAs
    from ommi.database import Ommi

__all__ = [
    "ommi_model",
    "Auto",
    "Key",
    "FieldType",
    "StoreAs",
    "Ommi",
    "active_driver",
    "use_driver",
    "BaseDriver",
    "BaseDriverTransaction",
]


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
}

__modules = set()

# Iterate the local folder and search for all py files and folders
for _path in Path(__file__).parent.iterdir():
    if _path.name.startswith("_"):
        continue

    if not _path.is_dir() and _path.suffix != ".py":
        continue

    __modules.add(_path.stem)


def __getattr__(name):
    if name in __lookup:
        try:
            module = importlib.import_module(__lookup[name])
        except Exception as e:
            raise ImportError(f"Failed to import {name} from {__lookup[name]}: {e}") from e

        return getattr(module, name)

    if name in __modules:
        return importlib.import_module(f"ommi.{name}")

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
