# Verification and traceability / Проверки и трассируемость

| Need | Rule | Components | Automated verification |
| --- | --- | --- | --- |
| FR-01 · Ingestion | BR-01, normalization, consistency, duplicate identity | [Event schema](../backend/sentrix/contracts.py), [service](../backend/sentrix/service.py) | TC-01 · [Unit](../tests/test_detection.py), [HTTP and PostgreSQL](../scripts/smoke.py) |
| FR-02 · Explanation | BR-02, BR-03, exact features and rule versions | [Detection](../backend/sentrix/detection.py) | TC-02 · deterministic scoring, cold start, anomaly in [unit](../tests/test_detection.py) and [Lab](../scripts/verify_lab.py) |
| FR-03 · Rule governance | Separate submit and publish, immutable historical assessment | [Service](../backend/sentrix/service.py), [schema](../backend/migrations/versions/001_schema.py) | TC-03 · forbidden publication, changed R-01 result and idempotent reassessment in [HTTP suite](../scripts/smoke.py) |
| FR-04 · Investigation | BR-04, BR-05, assignment and object scope | [Case service](../backend/sentrix/cases.py) | TC-04 · grouping, forced-transition rejection and cross-assignee 404 in [HTTP suite](../scripts/smoke.py) |
| FR-05 · Review | BR-06, one final decision with evidence and reason | [Case service](../backend/sentrix/cases.py), command receipts | TC-05 · competing requests and exact response replay in [HTTP suite](../scripts/smoke.py), [browser workflow](../frontend/e2e/workspace.spec.ts) |
| FR-06 · Operations | BR-07, BR-08, workload and SLA | [Analytics API](../backend/sentrix/api.py) | TC-06 · SLA experiment in [Lab](../scripts/verify_lab.py), real dashboard in [browser](../frontend/e2e/workspace.spec.ts) |
| FR-07 · Lab | Separate PostgreSQL volume, guarded endpoints | [Compose launcher](../scripts/lab), [scenario runner](../backend/sentrix/lab.py) | TC-07 · 22 scenarios over real HTTP and PostgreSQL |

```sh
python -m pip install -r backend/requirements.txt pytest ruff
ruff check backend scripts tests
ruff format --check backend scripts tests
pytest -q
PYTHONPATH=backend python scripts/contracts.py
scripts/lab up
docker compose -p sentrix-lab exec -T api python - < scripts/smoke.py
docker compose -p sentrix-lab exec -T api python - < scripts/verify_lab.py
cd frontend
npm ci
npx playwright install chromium
npm run e2e
```

Run suites serially against a fresh lab. They create real events, change rule versions, and close investigations. Resetting the lab removes the associated lab volume.
