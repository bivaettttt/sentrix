from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE users(login text PRIMARY KEY, name text NOT NULL, password text NOT NULL, role text NOT NULL
      CHECK(role IN ('FRAUD_ANALYST','SENIOR_ANALYST','FRAUD_MANAGER','RULES_ADMIN','ADMIN')));
    CREATE TABLE sessions(digest text PRIMARY KEY, login text NOT NULL REFERENCES users, expires timestamptz NOT NULL);
    CREATE TABLE customers(id text PRIMARY KEY, name text NOT NULL, category text NOT NULL);
    CREATE TABLE accounts(id text PRIMARY KEY, customer text NOT NULL REFERENCES customers);
    CREATE TABLE transactions(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source text NOT NULL,
      external_id text NOT NULL, account text NOT NULL REFERENCES accounts, amount bigint NOT NULL CHECK(amount>0),
      currency text NOT NULL CHECK(currency='RUB'), category text NOT NULL, channel text NOT NULL,
      recipient text NOT NULL, occurred_at timestamptz NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
      fingerprint text NOT NULL, late bool NOT NULL, features jsonb NOT NULL, UNIQUE(source,external_id));
    CREATE INDEX transaction_history ON transactions(account,occurred_at);
    CREATE TABLE rules(code text PRIMARY KEY, name text NOT NULL, enabled bool NOT NULL DEFAULT true);
    CREATE TABLE rule_versions(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL REFERENCES rules,
      version int NOT NULL, status text NOT NULL CHECK(status IN ('DRAFT','SUBMITTED','PUBLISHED')),
      parameters jsonb NOT NULL, reason text NOT NULL, author text NOT NULL REFERENCES users,
      publisher text REFERENCES users, published_at timestamptz, UNIQUE(code,version));
    CREATE TABLE assessments(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), transaction uuid NOT NULL REFERENCES transactions,
      basis text NOT NULL, methodology text NOT NULL, score int NOT NULL CHECK(score BETWEEN 0 AND 100),
      risk text NOT NULL CHECK(risk IN ('LOW','MEDIUM','HIGH','CRITICAL')),
      evaluations jsonb NOT NULL, anomaly jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(transaction,basis));
    CREATE TABLE cases(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), number bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
      customer text NOT NULL REFERENCES customers, window_start timestamptz NOT NULL,
      status text NOT NULL DEFAULT 'NEW' CHECK(status IN ('NEW','TRIAGED','INVESTIGATING','NEEDS_INFORMATION','REVIEW_REQUIRED',
      'CLOSED_CONFIRMED','CLOSED_FALSE_POSITIVE','CLOSED_INCONCLUSIVE')),
      priority int NOT NULL, assignee text REFERENCES users, submitter text REFERENCES users,
      revision int NOT NULL DEFAULT 1, first_review timestamptz, closed_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(), due_at timestamptz NOT NULL);
    CREATE INDEX cases_grouping ON cases(customer,window_start,created_at);
    CREATE TABLE alerts(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), assessment uuid UNIQUE NOT NULL REFERENCES assessments,
      case_id uuid NOT NULL REFERENCES cases, severity text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
    CREATE TABLE case_entries(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, case_id uuid NOT NULL REFERENCES cases,
      kind text NOT NULL CHECK(kind IN ('COMMENT','EVIDENCE','TRANSITION','ASSIGNMENT','DECISION')),
      author text NOT NULL REFERENCES users, body text NOT NULL, revision int NOT NULL,
      details jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now());
    CREATE UNIQUE INDEX one_case_decision ON case_entries(case_id) WHERE kind='DECISION';
    CREATE TABLE receipts(actor text REFERENCES users, key text, fingerprint text NOT NULL, result jsonb NOT NULL,
      PRIMARY KEY(actor,key));
    CREATE TABLE audit(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, actor text REFERENCES users,
      correlation uuid NOT NULL, action text NOT NULL, subject text NOT NULL, detail jsonb NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now());
    CREATE FUNCTION immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Immutable history' USING ERRCODE='23514'; END $$;
    CREATE FUNCTION protect_published() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.status='PUBLISHED' THEN
        RAISE EXCEPTION 'Published version is immutable' USING ERRCODE='23514';
      END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER immutable_rule BEFORE UPDATE OR DELETE ON rule_versions FOR EACH ROW EXECUTE FUNCTION protect_published();
    CREATE TRIGGER immutable_cases_history BEFORE UPDATE OR DELETE ON case_entries FOR EACH ROW EXECUTE FUNCTION immutable();
    CREATE TRIGGER immutable_audit BEFORE UPDATE OR DELETE ON audit FOR EACH ROW EXECUTE FUNCTION immutable();
    CREATE TRIGGER immutable_assessments BEFORE UPDATE OR DELETE ON assessments FOR EACH ROW EXECUTE FUNCTION immutable();
    CREATE TRIGGER immutable_transactions BEFORE UPDATE OR DELETE ON transactions FOR EACH ROW EXECUTE FUNCTION immutable();
    """)


def downgrade():
    op.execute(
        "DROP TABLE audit,receipts,case_entries,alerts,cases,assessments,rule_versions,rules,transactions,accounts,customers,sessions,users CASCADE"
    )
    op.execute("DROP FUNCTION immutable(), protect_published()")
