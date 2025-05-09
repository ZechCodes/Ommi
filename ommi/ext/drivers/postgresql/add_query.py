from typing import Any, Iterable, TYPE_CHECKING, List, Tuple, Dict

if TYPE_CHECKING:
    from psycopg import AsyncCursor
    from ommi.shared_types import DBModel
    from ommi.models.field_metadata import FieldMetadata

async def add_models(cursor: "AsyncCursor", models: "Iterable[DBModel]") -> "Iterable[DBModel]":
    """Adds models to the database, updating them with their generated primary keys."""
    processed_models = []
    for model_idx, model_instance in enumerate(models):
        table_name = model_instance.__ommi__.model_name
        all_field_metas: List["FieldMetadata"] = list(model_instance.__ommi__.fields.values())
        pk_metas = model_instance.get_primary_key_fields()

        is_single_serial_pk_case = False
        serial_pk_field_name: str | None = None # Python attribute name

        if len(pk_metas) == 1:
            pk_meta_candidate = pk_metas[0]
            candidate_field_type = pk_meta_candidate.get("field_type")
            # If pk_meta_candidate is the result of get_primary_key_fields(),
            # it IS a primary key. The direct .get("is_primary_key") might be
            # False if Key annotation is missing but convention (e.g. name 'id') made it a PK.
            # For our logic, if it's in pk_metas, it's a PK.
            is_candidate_field_pk = True 
            candidate_field_name = pk_meta_candidate.get("field_name")
            candidate_value = getattr(model_instance, candidate_field_name)

            if issubclass(candidate_field_type, int) and is_candidate_field_pk and candidate_value is None:
                is_single_serial_pk_case = True
                serial_pk_field_name = candidate_field_name

        fields_to_insert: Dict[str, Any] = {}
        for field_idx, field_meta in enumerate(all_field_metas):
            store_as = field_meta.get("store_as")
            field_name = field_meta.get("field_name")
            
            if is_single_serial_pk_case and field_name == serial_pk_field_name:
                continue 
            
            value = getattr(model_instance, field_name)
            fields_to_insert[store_as] = value
        
        returning_columns = ", ".join(pkm.get("store_as") for pkm in pk_metas)
        if not returning_columns:
            # This case should ideally be prevented by model validation earlier
            # or schema creation logic ensuring PKs exist.
            raise ValueError(f"Model {model_instance.__class__.__name__} has no primary key defined for RETURNING clause.")

        if not fields_to_insert:
            # This handles cases where all columns are auto-generated (e.g., a single SERIAL PK and no other fields)
            # or if a model has no fields other than a SERIAL PK.
            sql = f"INSERT INTO {table_name} DEFAULT VALUES RETURNING {returning_columns};"
            await cursor.execute(sql)
        else:
            column_names = ", ".join(fields_to_insert.keys())
            value_placeholders = ", ".join(["%s"] * len(fields_to_insert))
            params = list(fields_to_insert.values())
            sql = f"INSERT INTO {table_name} ({column_names}) VALUES ({value_placeholders}) RETURNING {returning_columns};"
            await cursor.execute(sql, params)
        
        returned_db_values = await cursor.fetchone()
        if returned_db_values:
            for i, pk_meta_for_update in enumerate(pk_metas):
                setattr(model_instance, pk_meta_for_update.get("field_name"), returned_db_values[i])
        
        processed_models.append(model_instance)
        
    return processed_models 