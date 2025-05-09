from typing import Generator, TYPE_CHECKING, Any, Type, Set

if TYPE_CHECKING:
    from psycopg import AsyncCursor
    from ommi.models.collections import ModelCollection
    from ommi.models.field_metadata import FieldMetadata
    from ommi.shared_types import DBModel

SQLStatement = str

_TYPE_MAPPING = {
    int: "INTEGER",
    str: "TEXT",
    float: "REAL",
    bool: "BOOLEAN",
}

def _get_postgresql_type(python_type: Type[Any], 
                           is_current_field_pk: bool, 
                           is_table_eligible_for_serial_sole_int_pk: bool) -> str:
    """Determines the PostgreSQL column type for a given field."""
    # A field becomes SERIAL if it IS a PK, it's an int, AND it's the sole PK on the table.
    if is_current_field_pk and is_table_eligible_for_serial_sole_int_pk and python_type is int:
        return "SERIAL"
    
    if python_type in _TYPE_MAPPING:
        return _TYPE_MAPPING[python_type]

    return "TEXT"

def _generate_column_sql(field: "FieldMetadata", 
                           is_current_field_pk: bool,
                           is_table_eligible_for_serial_sole_int_pk: bool) -> SQLStatement:
    """Generates the SQL for a single column definition."""
    column_name = field.get("store_as")
    python_type = field.get("field_type")
    
    pg_type = _get_postgresql_type(python_type, 
                                   is_current_field_pk, 
                                   is_table_eligible_for_serial_sole_int_pk)
    
    constraints = []
    # SERIAL columns are implicitly NOT NULL. 
    # If not SERIAL, PK columns must be NOT NULL.
    if is_current_field_pk and pg_type != "SERIAL":
        constraints.append("NOT NULL")
    # Add other constraints here if needed, e.g. UNIQUE, based on field.get("is_unique") etc.

    return f"{column_name} {pg_type} {' '.join(constraints)}".strip()

def _generate_columns_sql(model: "DBModel") -> SQLStatement:
    """Generates the SQL for all column definitions in a table."""
    primary_key_metadatas = model.get_primary_key_fields()
    
    # Determine if the table context makes a sole int PK eligible for SERIAL
    is_table_eligible_for_serial_sole_int_pk = False
    if len(primary_key_metadatas) == 1:
        pk_meta_candidate = primary_key_metadatas[0]
        if pk_meta_candidate.get("field_type") is int:
            is_table_eligible_for_serial_sole_int_pk = True
            
    column_definitions = []
    pk_store_as_names: Set[str] = {pk.get("store_as") for pk in primary_key_metadatas}

    for field_meta in model.__ommi__.fields.values():
        current_field_store_as = field_meta.get("store_as")
        is_current_field_pk = current_field_store_as in pk_store_as_names
        column_definitions.append(_generate_column_sql(field_meta, 
                                                       is_current_field_pk,
                                                       is_table_eligible_for_serial_sole_int_pk))
        
    return ", ".join(column_definitions)

def _generate_primary_keys_sql(model: "DBModel") -> SQLStatement | None:
    """Generates the SQL for the PRIMARY KEY constraint part."""
    primary_key_metadatas = model.get_primary_key_fields()
    if not primary_key_metadatas:
        return None
    return ", ".join(pk_meta.get("store_as") for pk_meta in primary_key_metadatas)

def _generate_create_table_sql_for_model(model: "DBModel") -> SQLStatement:
    """Generates the CREATE TABLE SQL statement for a single model."""
    table_name = model.__ommi__.model_name
    columns_sql = _generate_columns_sql(model)
    primary_keys_clause_sql = _generate_primary_keys_sql(model)

    pk_constraint_sql = ""
    if primary_keys_clause_sql:
         pk_constraint_sql = f", PRIMARY KEY ({primary_keys_clause_sql})"
    
    return f"CREATE TABLE IF NOT EXISTS {table_name} ({columns_sql}{pk_constraint_sql});"

def _generate_create_table_sql(collection: "ModelCollection") -> Generator[SQLStatement, None, None]:
    """Generates CREATE TABLE SQL statements for all models in a collection."""
    for model in collection.models:
        yield _generate_create_table_sql_for_model(model)

async def apply_schema(cursor: "AsyncCursor", model_collection: "ModelCollection"):
    all_models = list(model_collection.models)

    for model_type in all_models:
        table_name = model_type.__ommi__.model_name
        
        pk_metas = model_type.get_primary_key_fields()
        pk_store_as_names: Set[str] = {pk.get("store_as") for pk in pk_metas}

        # Determine if the table context makes a sole int PK eligible for SERIAL
        is_table_eligible_for_serial_sole_int_pk = False
        if len(pk_metas) == 1:
            # No need to check pk_metas[0].get("is_primary_key") here, 
            # if it's in pk_metas (from get_primary_key_fields), it's considered a PK.
            if pk_metas[0].get("field_type") is int:
                is_table_eligible_for_serial_sole_int_pk = True

        columns_sql_parts = []
        field_metadatas = list(model_type.__ommi__.fields.values())
            
        for field_meta in field_metadatas:
            current_field_store_as = field_meta.get("store_as")
            # Check if the current field being processed is one of the PKs for this model
            is_current_field_pk = current_field_store_as in pk_store_as_names
            
            columns_sql_parts.append(
                _generate_column_sql(field_meta, 
                                     is_current_field_pk,
                                     is_table_eligible_for_serial_sole_int_pk)
            )
        
        columns_sql = ", ".join(columns_sql_parts)
        
        pk_constraint_sql = ""
        # _generate_primary_keys_sql already gives a list of store_as names.
        # Use pk_store_as_names which we already computed.
        if pk_store_as_names: # If there are any primary keys
            pk_constraint_sql = f", PRIMARY KEY ({', '.join(sorted(list(pk_store_as_names)))})" # sorted for consistent order
            
        create_table_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({columns_sql}{pk_constraint_sql});"
        await cursor.execute(create_table_sql)

async def delete_schema(cursor: "AsyncCursor", model_collection: "ModelCollection"):
    """Deletes all tables associated with the models in the collection."""
    all_models = list(model_collection.models)
    
    for model_type in reversed(all_models): 
        table_name = model_type.__ommi__.model_name
        drop_table_sql = f"DROP TABLE IF EXISTS {table_name} CASCADE;" 
        await cursor.execute(drop_table_sql) 