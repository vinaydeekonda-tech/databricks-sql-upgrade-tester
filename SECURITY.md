# Security

This project sends SQL text to a Databricks SQL warehouse that you configure.
It does not ship workspace URLs, tokens, catalogs, or sample business data.

- Keep `DATABRICKS_TOKEN` in an environment variable, a Databricks CLI profile, or your CI secret store.
- Use a token that can only run SQL on the warehouse you are testing.
- Do not commit `.env`, warehouse ids from a private workspace, or your company's SQL.
- The Git repository you scan stays on your machine or in your own private CI checkout. This tester only reads `*.sql` files from the path you pass.
- DML probes such as `MERGE` are sent as `EXPLAIN`. They are not executed as writes. A missing target table is reported as an object error and does not fail the syntax gate.
