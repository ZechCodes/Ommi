# Result Types

Ommi provides two main result types: `DBResult` and `DBQueryResult`. They wrap the outcome of database
operations, providing a structured way to handle success or failure.

It also provides `DBResultBuilder` and `DBQueryResultBuilder` that are awaitable and wrap the outcome of an
operation in a `DBResult` or `DBQueryResult`. They provide useful methods for determining how the outcome
should be handled.

## `DBResult`

::: ommi.database.results
    options:
      show_root_heading: false
      show_root_toc_entry: false
      members_order: source
      heading_level: 3
      members: [DBResult, DBSuccess, DBFailure, DBResultBuilder, DBStatusNoResultException]
      filters:
        - "!^_"

## `DBQueryResult`

::: ommi.database.query_results
    options:
      show_root_heading: false
      show_root_toc_entry: false
      members_order: source
      heading_level: 3
      members: [DBQueryResult, DBQuerySuccess, DBQueryFailure, DBQueryResultBuilder, DBEmptyQueryException]
      filters:
        - "!^_"