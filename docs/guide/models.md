# Models and Fields

::: ommi.models.models
    options:
      show_root_heading: false
      show_root_toc_entry: false
      show_source: false
      show_bases: false
      show_docstring: true
      members: []

::: ommi.models.ommi_model
    options:
      show_root_heading: true
      heading_level: 3

::: ommi.models.models.OmmiModel
    options:
      show_root_heading: true
      heading_level: 3
      filters:
        - "!^ommi_model$"
        - "!^_"
        - "!^get_primary_key_fields$"
        - "!^get_driver$"
