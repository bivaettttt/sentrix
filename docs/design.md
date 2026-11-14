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
