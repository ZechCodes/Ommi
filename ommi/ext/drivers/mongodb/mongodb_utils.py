from typing import Type, Any
from ommi.models import OmmiModel
from ommi.models.field_metadata import FieldMetadata, Key

def get_collection_name(model_type: Type[OmmiModel]) -> str:
    """Gets the MongoDB collection name for a given model type."""
    ommi_meta = getattr(model_type, "__ommi__", None)
    if ommi_meta and hasattr(ommi_meta, "collection_name") and ommi_meta.collection_name:
        return ommi_meta.collection_name
    # Fallback for models not created by @ommi_model, or if collection_name is not set in metadata
    # This case should ideally not happen for fully processed Ommi models.
    if hasattr(model_type, "_ommi") and hasattr(model_type._ommi, "collection_name") and model_type._ommi.collection_name:
        return model_type._ommi.collection_name
    return model_type.__name__


def get_model_field_name(model_type: Type[OmmiModel], attribute_name: str) -> str:
    """Gets the database field name for a model attribute, respecting StoreAs, and applying id->_id convention."""
    field_meta = None
    if hasattr(model_type, '__ommi__') and hasattr(model_type.__ommi__, 'fields'):
        field_meta = model_type.__ommi__.fields.get(attribute_name)
    
    if attribute_name == "id":
        # If attribute is "id", it maps to "_id" by convention for MongoDB,
        # UNLESS StoreAs explicitly maps it to something else *other* than "id" itself.
        # If StoreAs is present and its value is "id", we still prefer "_id" for MongoDB's PK behavior.
        if field_meta and field_meta.get("store_as"):
            stored_as_value = field_meta.get("store_as")
            if stored_as_value != "id": # e.g. StoreAs("custom_identifier") would be used
                return stored_as_value 
        return "_id" # Default for "id" attribute, or if StoreAs was "id"
            
    # For other attributes (not named "id"), StoreAs takes simple precedence
    if field_meta and field_meta.get("store_as"):
        return field_meta.get("store_as")
            
    return attribute_name

def model_to_document(model_instance: OmmiModel) -> dict[str, Any]:
    """Converts an OmmiModel instance to a MongoDB document (dictionary)."""
    doc = {}
    model_type = type(model_instance)
    
    if not hasattr(model_type, '__ommi__') or not hasattr(model_type.__ommi__, 'fields'):
        if hasattr(model_instance, "__dict__"): 
             return {k: v for k, v in model_instance.__dict__.items() if not k.startswith('_') and not callable(v)}
        return {} 

    # Iterate over fields defined in Ommi metadata
    for field_name in model_type.__ommi__.fields.keys():
        field_meta = model_type.__ommi__.fields.get(field_name)
        if field_meta and (field_meta.get("is_lazy_load_many") or field_meta.get("is_lazy_load_one") or field_meta.get("is_association_proxy")):
            continue

        # Ensure the attribute actually exists on the instance before getattr
        if hasattr(model_instance, field_name):
            value = getattr(model_instance, field_name)
            db_field_name = get_model_field_name(model_type, field_name)
            doc[db_field_name] = value
        # else: field is in metadata but not on instance (e.g. if __init__ didn't set it and no default)
        # This case should be fine, we just don't include it in the document.

    return doc

def document_to_model(model_type: Type[OmmiModel], document: dict[str, Any]) -> OmmiModel:
    """Converts a MongoDB document (dictionary) to an OmmiModel instance."""
    init_data = {}

    if not hasattr(model_type, '__ommi__') or not hasattr(model_type.__ommi__, 'fields'):
        try:
            # Attempt to instantiate with the raw document if no Ommi metadata
            # This is a best-effort for plain classes or non-Ommi types.
            return model_type(**document) 
        except Exception as e:
            raise TypeError(f"Failed to instantiate {model_type.__name__} from document. Ommi metadata missing and direct instantiation failed: {e}") from e

    model_attribute_names = model_type.__ommi__.fields.keys()

    for attr_name in model_attribute_names:
        db_field_name = get_model_field_name(model_type, attr_name)
        if db_field_name in document:
            init_data[attr_name] = document[db_field_name]
        # If db_field_name is different from attr_name and only attr_name is in document, 
        # we prioritize db_field_name. If not found by db_field_name, it means the specific
        # stored-as name was not in the document. We don't fallback to attr_name here
        # if a specific store_as was defined, as that would be ambiguous.

    # Special handling for MongoDB's _id if the model's PK is 'id' (or equivalent) and maps to '_id'
    # This check is simplified; assumes get_model_pk_name and get_model_pk_db_name correctly identify the PK.
    pk_attr_name = get_model_pk_name(model_type)
    pk_db_name = get_model_pk_db_name(model_type)

    if pk_db_name == "_id" and "_id" in document:
        # If the PK is stored as '_id' and '_id' is in the document,
        # ensure the model's PK attribute gets this value, especially if not already covered.
        if pk_attr_name not in init_data or init_data[pk_attr_name] is None: # Prioritize if already mapped, but fill if missing
            init_data[pk_attr_name] = document["_id"]
    
    try:
        instance = model_type(**init_data)
    except Exception as e:
        raise TypeError(f"Failed to instantiate {model_type.__name__} with init_data {init_data} from document {document}. Error: {e}") from e
    return instance


def get_model_pk_name(model_type: Type[OmmiModel]) -> str:
    """Gets the primary key *attribute* name for a model."""
    if not hasattr(model_type, '__ommi__') or not hasattr(model_type.__ommi__, 'fields'):
        if hasattr(model_type, "id"): return "id"
        raise ValueError(f"Cannot determine primary key for {model_type.__name__}: missing Ommi metadata.")

    for attr_name, field_meta in model_type.__ommi__.fields.items():
        if field_meta.matches(Key):
            return attr_name
    
    if "id" in model_type.__ommi__.fields:
        return "id"
    
    if model_type.__ommi__.fields: # Fallback to first field if no 'id' or Key
        return next(iter(model_type.__ommi__.fields.keys()))

    raise ValueError(f"Cannot determine primary key for model {model_type.__name__}: No fields with Key metadata, no 'id' field, and no fields defined.")

def get_model_pk_db_name(model_type: Type[OmmiModel]) -> str:
    """Gets the database column name for the primary key of a model."""
    pk_attr_name = get_model_pk_name(model_type)
    
    field_meta = None
    if hasattr(model_type, '__ommi__') and hasattr(model_type.__ommi__, 'fields'):
        field_meta = model_type.__ommi__.fields.get(pk_attr_name)
    
    if pk_attr_name == "id":
        # If PK attribute is "id", it maps to "_id" by convention for MongoDB,
        # UNLESS StoreAs explicitly maps it to something else *other* than "id" itself.
        if field_meta and field_meta.get("store_as"):
            stored_as_value = field_meta.get("store_as")
            if stored_as_value != "id": # e.g. StoreAs("custom_identifier")
                return stored_as_value
        return "_id" # Default for "id" PK attribute, or if StoreAs was "id"
    
    # For PK attributes not named "id", StoreAs takes simple precedence
    if field_meta and field_meta.get("store_as"):
        return field_meta.get("store_as")
    
    return pk_attr_name 