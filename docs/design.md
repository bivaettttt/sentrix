# Sentrix · Product and design

A fraud operations team needs to explain why a transaction was flagged, reproduce past assessments and record who decided a case. The workspace uses synthetic customer profiles and single-currency transaction histories. An alert opens a queue item for human review. The result has no effect on a payment.

| ID | Actor and need | Acceptance |
| --- | --- | --- |
| FR-01 | An authorized analyst imports transactions | A source and event ID identify one normalized payload. Exact replay returns its recorded assessment. A changed replay conflicts. A batch commits atomically |
| FR-02 | An analyst explains a signal | The assessment stores methodology, rule versions, inputs, pass/fail outcomes and point contributions, alongside anomaly signals |
| FR-03 | A rules administrator tests a change | Typed, bounded parameters are evaluated on fixed stored features. A different authorized actor publishes. Existing assessments preserve their versions |
| FR-04 | An analyst investigates assigned cases | Eligible alerts group by customer and a fixed 24-hour receipt window. A case exposes its alerts, evidence, comments and current revision |
| FR-05 | A senior reviewer decides independently | A distinct actor closes a submitted case with reasons and a retained evidence snapshot. Concurrent commands cannot produce two decisions |
| FR-06 | A manager monitors workload | The backend derives volumes, ages, SLA, resolved outcomes and rule hits from PostgreSQL |
| FR-07 | An administrator demonstrates behavior | An isolated Compose database can be rebuilt independently |

## Domain decisions

**ADR-01.** Use a modular monolith and one PostgreSQL transaction per ingest. A customer advisory lock orders history-dependent assessments and grouping. A uniqueness constraint arbitrates a source event even if its payload names a different customer. Replay is recognized before validation against time. Database failure rolls back the operation and the same event can be retried.

**ADR-02.** Persist immutable feature snapshots. History includes events known at ingestion strictly before the evaluated event time. Reassessment applies the active set to the original snapshot. This makes version comparisons reproducible. Late arrivals never recalculate other transactions.

**ADR-03.** Role-based API access and per-case assignee gates serve synthetic datasets. Senior analysts may review submitted cases. Rules administrators prepare versions and managers authorize publication. Advisory locks serialize configuration changes with assessment snapshots. Case rows use optimistic revision checks under row locks. Evidence, decisions and audit records are append-only.

**ADR-04.** Statistics use medians and median absolute deviations with cold-start handling. Sentrix does not train a model on analyst outcomes because case decisions alone cannot establish a reference label. Risk is a bounded points score. Units are integer kopecks, timestamps are UTC, and SLA runs 24/7.

## Workflows

| Rule | Behavior |
| --- | --- |
| BR-01 | Timestamps require an offset. UTC normalization precedes fingerprinting. Events older than 30 days remain recorded with a late marker |
| BR-02 | Rules use typed thresholds over amount, counts, deviation, category, recipient history, UTC time, near-threshold series and combined factors |
| BR-03 | Alerts are generated at HIGH or CRITICAL risk. Assessments are unique per transaction and ordered rule set |
| BR-04 | Cases group by customer and open receipt window. A case in review or closed cannot receive new alerts |
| BR-05 | NEW → TRIAGED → INVESTIGATING → REVIEW_REQUIRED → CLOSED_* is the main flow. NEEDS_INFORMATION pauses investigation work. Review can return to INVESTIGATING |
| BR-06 | Managers assign cases to analysts. The assignee submits a preliminary finding. A reviewer provides a reason and selects a supported outcome |
| BR-07 | First review target is 2 hours. Closure target is 24 hours, shortened to 4 hours for CRITICAL |
| BR-08 | Metrics distinguish rule hits, risks, alerts, cases and analyst outcomes |

Glossary. A transaction is a normalized synthetic event. An assessment is a reproducible scoring run. An alert is an assessment that merits review. A case groups alerts. Evidence records analyst context. A decision is a human conclusion for a specific case revision.

## Use cases and permissions

| ID | Main path | Alternate |
| --- | --- | --- |
| UC-01 | Operations user sends a single or batched synthetic event | Invalid data returns 422. A changed event replay returns 409. A lab fault returns 503 and rolls back |
| UC-02 | Manager assigns an alert group, analyst triages, investigates, adds evidence and submits | Reviewer returns a finding to investigation. A stale revision returns 409 |
| UC-03 | Rules administrator compares a candidate on fixed features, creates a draft and submits | Invalid parameters return 422. A manager publishes a newer submitted version |
| UC-04 | Administrator runs an experiment in an isolated environment | An ordinary deployment rejects the experiment endpoint. Simultaneous lab runs conflict |

| Role | Main permissions |
| --- | --- |
| Analyst | Read operations and assigned cases, add material and submit a finding |
| Senior analyst | Read case context, return or close a submitted finding |
| Manager | Read operational queues, assign, reassess, approve rule versions and read audit |
| Rules administrator | Read rules, evaluate candidate, create and submit drafts |
| Administrator | Create users, inspect the audit, run Lab when enabled |

NFR-01 requires atomic persistence and explicit replay semantics. NFR-02 requires object-level authorization and append-only evidence. NFR-03 requires independently reproducible scoring with versions and features. NFR-04 requires a request ID in application errors and successful responses.

## Rule and score policy

| Rule | Condition | Points when true |
| --- | --- | --- |
| R-01 | Amount at least candidate threshold | 55 |
| R-02 | At least configured count in 10 minutes, including current event | 55 |
| R-03 | Amount at least selected multiple of baseline median | 35 |
| R-04 | Category departs from profile with at least five earlier observations | 12 |
| R-05 | Recipient absent from history with at least five earlier observations | 18 |
| R-06 | UTC hour outside the configured start-inclusive, end-exclusive range | 10 |
| R-07 | Enough transactions from 80% inclusive to 100% exclusive of a fixed threshold | 35 |
| R-08 | At least configured count of preceding active factors | 22 |

History uses up to 1,000 events from the prior 30 days, ordered by event time with a stable tie break. The baseline excludes the most recent ten minutes and requires five points. The amount outlier adds 15 points when the deviation is at least six times the greatest of MAD, 10 percent of the median and one kopeck. Velocity and category signals are also retained. Score is capped at 100. LOW is 0–24, MEDIUM 25–49, HIGH 50–79 and CRITICAL 80–100. These are design thresholds for synthetic demonstrations. A rule comparison uses the same saved feature vector on both sides.

The SLA mean uses observed triage and closure events. Late queues count open cases beyond the applicable elapsed deadline. False positive share divides cases closed with that outcome by all closed cases. Rule hits are attributed to the version recorded on each assessment. Analyst decisions remain distinct from ground truth.

[Container view](diagrams/containers.mmd) · [Data model](diagrams/data.mmd) · [Ingestion sequence](diagrams/ingest.mmd) · [Case lifecycle](diagrams/cases.mmd) · [OpenAPI](openapi.json) · [Verification](verification.md)
