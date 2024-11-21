from typing import Any, Type

type_mapping: dict[Type[Any], str] = {
    int: "INTEGER",
    str: "TEXT",
    float: "REAL",
    bool: "INTEGER",
}


def get_sqlite_type(obj_type: Type[Any]) -> str:
    return type_mapping.get(obj_type, "TEXT")