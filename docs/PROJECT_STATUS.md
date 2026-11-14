# Sentrix status / Состояние проекта

The core workspace accepts REST, batch and CSV inputs, keeps assessments and reasons, supports independent case closure and provides synthetic operational reports. The Postgres lab covers 22 scenarios, including fault injection and retry with transaction rollback.

## Boundaries

- This delivery uses a synchronous, transactional ingestion path. There is no background queue or external bank connector.
- The risk score is a prioritization score. There is no independently labeled dataset and no ML model or measured production detection performance.
- The rule catalog has eight built-in types. The workflow creates immutable versions with parameter changes. Drafts are replaced by creating a new draft. Typed conditions are implemented in code.
- Evidence is text with a case-revision snapshot. File uploads, external integrations, automatic SLA reminders and a formal reopening workflow are outside the current workspace.
- PostgreSQL stores anomaly results inside assessments and rule evaluation details in JSON. These views are available from transaction details. Separate anomaly and model registry screens remain open.
- Further work includes persistent per-row rejected import records, richer API response schemas and dedicated historical analytics.

## Verification record

Local verification passed seven unit cases, the PostgreSQL HTTP suite all 22 laboratory scenarios, and three Chromium E2E cases. The normal and lab deployments use separate Compose projects and database volumes. Screenshots and the video were produced through Playwright against the lab. See the [published pipeline](https://github.com/bivaettttt/sentrix/actions) for the current commit result and [traceability](verification.md) for the commands and acceptance mapping.
