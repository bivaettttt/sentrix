import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/600.css";
import "./style.css";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import {
  HashRouter,
  Link,
  NavLink,
  Route,
  Routes,
  useParams,
} from "react-router";
import {
  Activity,
  ArrowUpRight,
  Bell,
  BriefcaseBusiness,
  ChevronLeft,
  ClipboardList,
  FlaskConical,
  Gauge,
  ListFilter,
  LogOut,
  ShieldCheck,
  UsersRound,
} from "lucide-react";
import {
  api,
  session,
  type Alert,
  type Analytics,
  type Case,
  type Factor,
  type RecordRow,
  type Rule,
  type Tx,
  type TxDetail,
  type User,
} from "./api";

const names: Record<string, string> = {
  NEW: "Новая",
  TRIAGED: "Первичная проверка",
  INVESTIGATING: "Расследование",
  NEEDS_INFORMATION: "Нужны сведения",
  REVIEW_REQUIRED: "На согласовании",
  CLOSED_CONFIRMED: "Подозрительность подтверждена",
  CLOSED_FALSE_POSITIVE: "Ложное срабатывание",
  CLOSED_INCONCLUSIVE: "Недостаточно данных",
  HIGH: "Высокий",
  CRITICAL: "Критический",
  MEDIUM: "Средний",
  LOW: "Низкий",
  GROCERY: "Повседневные расходы",
  SERVICES: "Услуги",
  TRAVEL: "Поездки",
  ELECTRONICS: "Электроника",
  TRANSFER: "Переводы",
  COMMENT: "Комментарий",
  EVIDENCE: "Материал",
  ASSIGNMENT: "Назначение",
  DECISION: "Решение",
  TRANSITION: "Переход",
  DRAFT: "Черновик",
  SUBMITTED: "На согласовании",
  PUBLISHED: "Опубликована",
  FRAUD_ANALYST: "Аналитик",
  SENIOR_ANALYST: "Старший аналитик",
  FRAUD_MANAGER: "Руководитель",
  RULES_ADMIN: "Администратор правил",
  ADMIN: "Администратор",
};
const label = (value: string) => names[value] ?? value;
const money = (amount: number) =>
  new Intl.NumberFormat("ru", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
  }).format(amount / 100);
const time = (value: string) =>
  new Intl.DateTimeFormat("ru", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(value));
const values = (event: FormEvent<HTMLFormElement>) => {
  event.preventDefault();
  return Object.fromEntries(new FormData(event.currentTarget));
};

function useData<T>(path: string, version = 0) {
  const [state, set] = useState<{ data?: T; error?: string }>({});
  useEffect(() => {
    if (!path) return;
    let active = true;
    set({});
    api<T>(path).then(
      (data) => {
        if (active) set({ data });
      },
      (error) => {
        if (active) set({ error: String(error.message) });
      },
    );
    return () => {
      active = false;
    };
  }, [path, version]);
  return state;
}
function useCommand(refresh: () => void) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function run<T>(
    path: string,
    body?: unknown,
    key?: string,
    method = "POST",
  ) {
    setError("");
    setBusy(true);
    try {
      const result = await api<T>(path, method, body, key);
      refresh();
      return result;
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem));
    } finally {
      setBusy(false);
    }
  }
  return { run, error, busy };
}
function Badge({ value }: { value: string }) {
  return <span className={"badge " + value.toLowerCase()}>{label(value)}</span>;
}
function ErrorView({ error }: { error?: string }) {
  return error ? (
    <p className="error" role="alert">
      {error}
    </p>
  ) : null;
}
function Head({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {children}
    </header>
  );
}
function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {children}
    </section>
  );
}
function Table({
  columns,
  rows,
  empty = "Записей пока нет.",
}: {
  columns: string[];
  rows: ReactNode[][];
  empty?: string;
}) {
  if (!rows.length) return <p className="pad muted">{empty}</p>;
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function DataRows({ data }: { data: RecordRow[] }) {
  const cols = Object.keys(data[0] ?? {});
  return (
    <Table
      columns={cols}
      rows={data.map((row) =>
        Object.values(row).map((v) =>
          v === null ? "—" : typeof v === "string" ? label(v) : v,
        ),
      )}
    />
  );
}
function Wait({ error }: { error?: string }) {
  return error ? (
    <ErrorView error={error} />
  ) : (
    <p role="status" className="pad muted">
      Загрузка…
    </p>
  );
}
function Json({ value }: { value: unknown }) {
  return <pre>{JSON.stringify(value, null, 2)}</pre>;
}
function Brand() {
  return (
    <div className="brand">
      <span>
        <ShieldCheck size={23} />
      </span>
      Sentrix
    </div>
  );
}
function LoginScreen({ done }: { done: (user: User) => void }) {
  const action = useCommand(() => {});
  return (
    <div className="signin">
      <section>
        <Brand />
        <h1>Вход в Sentrix</h1>
        <p>Рабочее пространство антифрод-команды</p>
        <form
          onSubmit={async (e) => {
            const item = await action.run<User & { token: string }>(
              "/auth/login",
              values(e),
            );
            if (item) {
              session(item.token);
              done(item);
            }
          }}
        >
          <label>
            Логин
            <input name="login" autoComplete="username" required />
          </label>
          <label>
            Пароль
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
            />
          </label>
          <ErrorView error={action.error} />
          <button className="primary" disabled={action.busy}>
            Войти
          </button>
        </form>
      </section>
      <div className="signin-side">
        <Activity size={48} />
        <h2>От сигнала к решению</h2>
        <p>
          Оценка риска, история срабатываний и ход расследования в одном рабочем
          пространстве.
        </p>
      </div>
    </div>
  );
}
function App() {
  const [user, setUser] = useState<User | null>(null);
  const [rev, setRev] = useState(0);
  const refresh = () => setRev((v) => v + 1);
  const lab = useData<{ enabled: boolean }>(
    user?.role === "ADMIN" ? "/lab" : "",
  );
  const action = useCommand(refresh);
  if (!user) return <LoginScreen done={setUser} />;
  const ops = user.role !== "RULES_ADMIN";
  const manager = ["FRAUD_MANAGER", "ADMIN"].includes(user.role);
  const items = [
    ...(ops
      ? [
          { path: "/", name: "Мониторинг", Icon: Gauge },
          { path: "/transactions", name: "Транзакции", Icon: Activity },
          { path: "/alerts", name: "Предупреждения", Icon: Bell },
          { path: "/cases", name: "Расследования", Icon: BriefcaseBusiness },
        ]
      : []),
    { path: "/rules", name: "Правила", Icon: ListFilter },
    ...(manager
      ? [{ path: "/audit", name: "Аудит", Icon: ClipboardList }]
      : []),
    ...(user.role === "ADMIN"
      ? [{ path: "/users", name: "Пользователи", Icon: UsersRound }]
      : []),
    ...(lab.data?.enabled
      ? [{ path: "/lab", name: "Лаборатория", Icon: FlaskConical }]
      : []),
  ];
  const props = { rev, refresh, user };
  return (
    <div className="shell">
      <aside>
        <Brand />
        <nav aria-label="Разделы">
          {items.map(({ path, name, Icon }) => (
            <NavLink key={path} to={path} end={path === "/"}>
              <Icon size={17} />
              {name}
            </NavLink>
          ))}
        </nav>
        <footer>Учебные данные</footer>
      </aside>
      <div className="workspace">
        <div className="top">
          <span>Рабочая область / Антифрод</span>
          <div>
            <b>{user.name}</b>
            <span>{label(user.role)}</span>
            <button
              aria-label="Выйти"
              onClick={() =>
                void action.run("/auth/logout").then(() => {
                  session("");
                  setUser(null);
                })
              }
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
        <main>
          <Routes>
            <Route
              path="/"
              element={ops ? <Dashboard rev={rev} /> : <RulesPage {...props} />}
            />
            {ops && (
              <>
                <Route
                  path="/transactions"
                  element={<Transactions {...props} />}
                />
                <Route
                  path="/transactions/:id"
                  element={<Transaction {...props} />}
                />
                <Route path="/alerts" element={<Alerts rev={rev} />} />
                <Route path="/cases" element={<Cases rev={rev} />} />
                <Route
                  path="/cases/:id"
                  element={<Investigation {...props} />}
                />
              </>
            )}
            <Route path="/rules" element={<RulesPage {...props} />} />
            {manager && <Route path="/audit" element={<Audit rev={rev} />} />}
            {user.role === "ADMIN" && (
              <Route path="/users" element={<Users {...props} />} />
            )}
            {lab.data?.enabled && (
              <Route path="/lab" element={<Lab {...props} />} />
            )}
            <Route path="*" element={<Head title="Раздел недоступен" />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
type Props = { rev: number; refresh: () => void; user: User };
function Dashboard({ rev }: { rev: number }) {
  const a = useData<Analytics>("/analytics", rev);
  const s = a.data?.summary;
  return (
    <>
      <Head
        title="Мониторинг операций"
        subtitle="Объём обработки, активные расследования и контроль сроков"
      />
      {!a.data ? (
        <Wait error={a.error} />
      ) : (
        <>
          <div className="metrics">
            {[
              ["transactions", "Принятые операции"],
              ["processed", "Оценено"],
              ["alerts", "Предупреждения"],
              ["critical_open", "Критические дела"],
              ["overdue", "Просрочки SLA"],
            ].map(([k, n]) => (
              <section key={k}>
                <span>{n}</span>
                <strong>{s?.[k] ?? "—"}</strong>
              </section>
            ))}
          </div>
          <div className="split">
            <Panel title="Очередь аналитиков">
              <Table
                columns={["Ответственный", "Открытые дела"]}
                rows={a.data.workload.map((x) => [x.analyst, x.total])}
              />
            </Panel>
            <Panel title="Сроки расследований">
              <Table
                columns={["Показатель", "Значение"]}
                rows={[
                  ["Просрочена первичная проверка", s?.untriaged_overdue],
                  [
                    "Среднее время до проверки",
                    s?.mean_review_seconds == null
                      ? "—"
                      : s.mean_review_seconds + " с",
                  ],
                  [
                    "Среднее время до закрытия",
                    s?.mean_closure_seconds == null
                      ? "—"
                      : s.mean_closure_seconds + " с",
                  ],
                  [
                    "Ложные срабатывания среди закрытых",
                    s?.false_positive_percent == null
                      ? "—"
                      : s.false_positive_percent + " %",
                  ],
                ]}
              />
            </Panel>
          </div>
          <div className="split">
            <Panel title="Состояния дел">
              <Table
                columns={["Состояние", "Дела"]}
                rows={a.data.outcomes.map((x) => [
                  <Badge value={String(x.status)} />,
                  x.total,
                ])}
              />
            </Panel>
            <Panel title="Уровни предупреждений">
              <Table
                columns={["Риск", "Предупреждения"]}
                rows={a.data.severity.map((x) => [
                  <Badge value={String(x.severity)} />,
                  x.total,
                ])}
              />
            </Panel>
          </div>
          <Panel title="Срабатывания по версиям правил">
            <Table
              columns={["Правило", "Версия", "Срабатывания"]}
              rows={a.data.hits.map((x) => [x.code, x.version, x.total])}
            />
          </Panel>
        </>
      )}
    </>
  );
}
function Pager({
  offset,
  set,
  count,
}: {
  offset: number;
  set: (value: number) => void;
  count: number;
}) {
  return (
    <div className="toolbar pad">
      <button disabled={!offset} onClick={() => set(offset - 50)}>
        Назад
      </button>
      <span className="muted">Страница {offset / 50 + 1}</span>
      <button disabled={count < 50} onClick={() => set(offset + 50)}>
        Далее
      </button>
    </div>
  );
}
function TxTable({ data }: { data: Tx[] }) {
  return (
    <Table
      columns={[
        "Операция",
        "Клиент",
        "Категория",
        "Сумма",
        "Время UTC",
        "Риск",
      ]}
      rows={data.map((t) => [
        <Link to={"/transactions/" + t.id}>
          {t.external_id ?? t.id.slice(0, 8)}
        </Link>,
        t.customer ?? "—",
        label(t.category),
        money(t.amount),
        time(t.occurred_at) + (t.late ? " · позднее" : ""),
        t.risk ? <Badge value={t.risk} /> : "—",
      ])}
    />
  );
}
function Transactions({ rev, refresh }: Props) {
  const [offset, set] = useState(0),
    [filter, setFilter] = useState(""),
    [upload, setUpload] = useState(false),
    [report, setReport] = useState<number>();
  const r = useData<Tx[]>("/transactions?offset=" + offset + filter, rev);
  const act = useCommand(refresh);
  return (
    <>
      <Head
        title="Транзакции"
        subtitle="Журнал нормализованных событий и оценок"
      >
        <button className="primary" onClick={() => setUpload((v) => !v)}>
          Импорт CSV
        </button>
      </Head>
      {upload && (
        <Panel title="Загрузка CSV">
          <form
            className="pad form"
            onSubmit={async (e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget).get("file");
              if (f instanceof File) {
                const result = await act.run<unknown[]>(
                  "/transactions/import",
                  { text: await f.text() },
                );
                if (result) setReport(result.length);
              }
            }}
          >
            <label>
              Файл CSV
              <input type="file" name="file" accept=".csv,text/csv" required />
            </label>
            <button disabled={act.busy}>Загрузить пакет</button>
            <ErrorView error={act.error} />
            {report !== undefined && (
              <p role="status">Событий в пакете: {report}</p>
            )}
          </form>
        </Panel>
      )}
      <Panel title="Реестр операций">
        <form
          className="toolbar pad"
          onSubmit={(e) => {
            const f = values(e);
            set(0);
            setFilter(
              "&q=" + encodeURIComponent(String(f.q)) + "&sort=" + f.sort,
            );
          }}
        >
          <label>
            Поиск
            <input name="q" placeholder="Событие или клиент" />
          </label>
          <label>
            Сортировка
            <select name="sort">
              <option value="recent">Сначала новые</option>
              <option value="amount">По сумме</option>
            </select>
          </label>
          <button>Применить</button>
        </form>
        {r.data ? (
          <>
            <TxTable data={r.data} />
            <Pager offset={offset} set={set} count={r.data.length} />
          </>
        ) : (
          <Wait error={r.error} />
        )}
      </Panel>
    </>
  );
}
function Factors({ factors }: { factors: Factor[] }) {
  return (
    <Table
      columns={["Правило", "Версия", "Результат", "Баллы"]}
      rows={factors.map((f) => [
        f.code + " · " + f.name,
        "v" + f.version,
        f.hit ? "Сработало" : "Без срабатывания",
        f.points,
      ])}
    />
  );
}
function Transaction({ rev, refresh, user }: Props) {
  const { id } = useParams();
  const r = useData<TxDetail>("/transactions/" + id, rev);
  const act = useCommand(refresh);
  if (!r.data) return <Wait error={r.error} />;
  const tx = r.data;
  return (
    <>
      <Link to="/transactions">
        <ChevronLeft size={15} /> Транзакции
      </Link>
      <Head
        title={"Операция " + tx.external_id}
        subtitle={tx.source + " / " + tx.customer_name}
      >
        {["ADMIN", "FRAUD_MANAGER"].includes(user.role) && (
          <button
            onClick={() => void act.run("/transactions/" + id + "/evaluations")}
          >
            Переоценить
          </button>
        )}
      </Head>
      <ErrorView error={act.error} />
      <Panel title="Событие">
        <Table
          columns={[
            "Сумма",
            "Счёт",
            "Категория",
            "Канал",
            "Получатель",
            "Время UTC",
          ]}
          rows={[
            [
              money(tx.amount),
              tx.account,
              label(tx.category),
              tx.channel,
              tx.recipient,
              time(tx.occurred_at) + (tx.late ? " · позднее" : ""),
            ],
          ]}
        />
      </Panel>
      {tx.assessments.map((s, i) => (
        <Panel
          key={s.id}
          title={
            (i === 0 ? "Последняя оценка" : "Историческая оценка") +
            " · " +
            s.methodology
          }
        >
          <p className="toolbar pad">
            <strong>{s.score} / 100</strong>
            <Badge value={s.risk} />
          </p>
          <Factors factors={s.evaluations} />
          <details>
            <summary>Сигналы аномалий и признаки расчёта</summary>
            <Json value={{ anomaly: s.anomaly, features: tx.features }} />
          </details>
        </Panel>
      ))}
      <Panel title="Предыдущие операции клиента">
        <TxTable data={tx.history} />
      </Panel>
    </>
  );
}
function Alerts({ rev }: { rev: number }) {
  const [offset, set] = useState(0),
    [filter, setFilter] = useState("");
  const r = useData<Alert[]>("/alerts?offset=" + offset + filter, rev);
  return (
    <>
      <Head
        title="Предупреждения"
        subtitle="Сигналы оценки, связанные с операциями и делами"
      />
      <Panel title="Очередь предупреждений">
        <form
          className="toolbar pad"
          onSubmit={(e) => {
            const f = values(e);
            set(0);
            setFilter(f.severity ? "&severity=" + f.severity : "");
          }}
        >
          <label>
            Уровень риска
            <select name="severity">
              <option value="">Все</option>
              <option value="HIGH">Высокий</option>
              <option value="CRITICAL">Критический</option>
            </select>
          </label>
          <button>Применить</button>
        </form>
        {r.data ? (
          <>
            <Table
              columns={[
                "Клиент",
                "Уровень риска",
                "Баллы",
                "Транзакция",
                "Дело",
                "Состояние",
              ]}
              rows={r.data.map((a) => [
                a.customer_name,
                <Badge value={a.severity} />,
                a.score,
                <Link to={"/transactions/" + a.transaction}>
                  {a.transaction.slice(0, 8)}
                </Link>,
                <Link to={"/cases/" + a.case_id}>SX-{a.number}</Link>,
                <Badge value={a.status} />,
              ])}
            />
            <Pager offset={offset} set={set} count={r.data.length} />
          </>
        ) : (
          <Wait error={r.error} />
        )}
      </Panel>
    </>
  );
}
function Cases({ rev }: { rev: number }) {
  const [offset, set] = useState(0),
    [filter, setFilter] = useState("");
  const r = useData<Case[]>("/cases?offset=" + offset + filter, rev);
  return (
    <>
      <Head
        title="Расследования"
        subtitle="Очередь дел, назначения и контроль SLA"
      />
      <Panel title="Рабочая очередь">
        <form
          className="toolbar pad"
          onSubmit={(e) => {
            const f = values(e);
            set(0);
            setFilter(
              "&q=" + encodeURIComponent(String(f.q)) + "&state=" + f.state,
            );
          }}
        >
          <label>
            Поиск
            <input name="q" placeholder="Номер или клиент" />
          </label>
          <label>
            Состояние
            <select name="state">
              <option value="">Все</option>
              {Object.keys(names)
                .filter(
                  (k) =>
                    [
                      "NEW",
                      "TRIAGED",
                      "INVESTIGATING",
                      "NEEDS_INFORMATION",
                      "REVIEW_REQUIRED",
                    ].includes(k) || k.startsWith("CLOSED_"),
                )
                .map((k) => (
                  <option key={k} value={k}>
                    {label(k)}
                  </option>
                ))}
            </select>
          </label>
          <button>Применить</button>
        </form>
        {r.data ? (
          <>
            <Table
              columns={[
                "Дело",
                "Клиент",
                "Приоритет",
                "Состояние",
                "Ответственный",
                "Срок UTC",
              ]}
              rows={r.data.map((c) => [
                <Link to={"/cases/" + c.id}>SX-{c.number}</Link>,
                c.customer_name,
                <Badge value={c.priority === 2 ? "CRITICAL" : "HIGH"} />,
                <Badge value={c.status} />,
                c.assignee_name ?? "—",
                time(c.due_at) + (c.overdue ? " · просрочено" : ""),
              ])}
            />
            <Pager offset={offset} set={set} count={r.data.length} />
          </>
        ) : (
          <Wait error={r.error} />
        )}
      </Panel>
    </>
  );
}
const commandNames: Record<string, string> = {
  assign: "Назначить",
  triage: "Отметить первичную проверку",
  investigate: "Начать расследование",
  request_information: "Запросить сведения",
  resume: "Возобновить расследование",
  submit: "Передать на согласование",
  return: "Вернуть на доработку",
  close: "Закрыть дело",
  comment: "Добавить комментарий",
  evidence: "Добавить материал",
};
function Investigation({ rev, refresh, user }: Props) {
  const { id } = useParams();
  const path = "/cases/" + id;
  const r = useData<Case>(path, rev);
  const people = useData<User[]>(
    user.role === "FRAUD_MANAGER" ? "/users" : "",
    rev,
  );
  const act = useCommand(refresh);
  const [chosen, setChosen] = useState("");
  if (!r.data) return <Wait error={r.error} />;
  const c = r.data;
  let commands: string[] = [];
  if (
    !c.closed_at &&
    user.role === "FRAUD_MANAGER" &&
    c.status !== "REVIEW_REQUIRED"
  )
    commands = ["assign"];
  if (c.status === "REVIEW_REQUIRED" && user.role === "SENIOR_ANALYST")
    commands = ["close", "return"];
  if (
    !c.closed_at &&
    c.status !== "REVIEW_REQUIRED" &&
    user.role === "FRAUD_ANALYST" &&
    c.assignee === user.login
  ) {
    commands = [
      ...({
        NEW: ["triage"],
        TRIAGED: ["investigate"],
        INVESTIGATING: ["submit", "request_information"],
        NEEDS_INFORMATION: ["resume"],
      }[c.status] ?? []),
      "evidence",
      "comment",
    ];
  }
  const command = commands.includes(chosen) ? chosen : commands[0];
  return (
    <>
      <Link to="/cases">
        <ChevronLeft size={15} /> Расследования
      </Link>
      <Head
        title={"Дело SX-" + c.number}
        subtitle={c.customer_name + " · редакция " + c.revision}
      >
        <Badge value={c.status} />
      </Head>
      <div className="strip">
        <span>
          Ответственный <b>{c.assignee_name ?? "не назначен"}</b>
        </span>
        <span>
          Срок UTC <b>{time(c.due_at)}</b>
        </span>
        <Badge value={c.priority === 2 ? "CRITICAL" : "HIGH"} />
        {c.overdue && <span className="error">Просрочено</span>}
      </div>
      <div className="investigation">
        <div>
          <Panel title="Связанные предупреждения">
            {c.alerts.map((a) => (
              <details key={a.id}>
                <summary>
                  <b>{money(a.amount)}</b> · {label(a.category)} · {a.score}{" "}
                  баллов · {time(a.occurred_at)}
                </summary>
                <Link to={"/transactions/" + a.transaction}>
                  Открыть транзакцию <ArrowUpRight size={14} />
                </Link>
                <Factors factors={a.evaluations} />
              </details>
            ))}
          </Panel>
          <Panel title="История расследования">
            <Table
              columns={["Событие", "Автор", "Обоснование", "Время UTC"]}
              rows={c.entries.map((e) => [
                label(e.kind),
                e.author,
                e.body,
                time(e.created_at),
              ])}
            />
          </Panel>
        </div>
        <div>
          <Panel title="Действия по делу">
            {command ? (
              <form
                className="pad form"
                onSubmit={async (e) => {
                  const f = values(e);
                  await act.run(
                    path + "/commands",
                    { ...f, action: command, revision: c.revision },
                    crypto.randomUUID(),
                  );
                }}
              >
                <label>
                  Действие
                  <select
                    value={command}
                    onChange={(e) => setChosen(e.target.value)}
                  >
                    {commands.map((x) => (
                      <option key={x} value={x}>
                        {commandNames[x]}
                      </option>
                    ))}
                  </select>
                </label>
                {command === "assign" && (
                  <label>
                    Аналитик
                    <select name="assignee" required>
                      <option value="">Выберите аналитика</option>
                      {people.data
                        ?.filter((u) => u.role === "FRAUD_ANALYST")
                        .map((u) => (
                          <option key={u.login} value={u.login}>
                            {u.name}
                          </option>
                        ))}
                    </select>
                  </label>
                )}
                {command === "close" && (
                  <label>
                    Результат
                    <select name="outcome">
                      <option value="FALSE_POSITIVE">
                        Ложное срабатывание
                      </option>
                      <option value="CONFIRMED">
                        Подозрительность подтверждена
                      </option>
                      <option value="INCONCLUSIVE">Недостаточно данных</option>
                    </select>
                  </label>
                )}
                <label>
                  Обоснование
                  <textarea name="reason" required minLength={4} rows={4} />
                </label>
                <button className="primary" disabled={act.busy}>
                  Выполнить
                </button>
                <ErrorView error={act.error} />
              </form>
            ) : (
              <p className="pad muted">
                Для текущего состояния и вашей роли действий нет.
              </p>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}
function RulesPage({ rev, refresh, user }: Props) {
  const r = useData<Rule[]>("/rules", rev);
  const act = useCommand(refresh);
  const [selected, setSelected] = useState("R-01");
  const [report, setReport] = useState<
    {
      id: string;
      before: { risk: string; score: number };
      after: { risk: string; score: number };
    }[]
  >();
  const rule = r.data?.find((x) => x.code === selected);
  const permitted = ["RULES_ADMIN", "FRAUD_MANAGER"].includes(user.role);
  return (
    <>
      <Head
        title="Антифрод-правила"
        subtitle="Параметры, версии и сравнение на фиксированных операциях"
      />
      {!r.data ? (
        <Wait error={r.error} />
      ) : (
        <div className="investigation rules-layout">
          <Panel title="Реестр">
            <Table
              columns={["Правило", "Статус"]}
              rows={r.data.map((x) => [
                <button
                  className={selected === x.code ? "chosen" : ""}
                  onClick={() => {
                    setSelected(x.code);
                    setReport(undefined);
                  }}
                >
                  {x.code} · {x.name}
                </button>,
                x.enabled ? "Активно" : "Отключено",
              ])}
            />
          </Panel>
          {rule && (
            <div>
              <Panel title={rule.code + " · " + rule.name}>
                <ErrorView error={act.error} />
                {permitted && (
                  <form
                    className="pad form"
                    key={rule.code}
                    onSubmit={async (e) => {
                      const submitter = (e.nativeEvent as SubmitEvent)
                        .submitter as HTMLButtonElement | null;
                      const data = values(e);
                      const payload = {
                        reason: data.reason,
                        parameters: Object.fromEntries(
                          Object.keys(rule.parameters).map((k) => [
                            k,
                            Number(data[k]),
                          ]),
                        ),
                      };
                      if (submitter?.value === "save")
                        await act.run(
                          "/rules/" + rule.code + "/versions",
                          payload,
                        );
                      else
                        setReport(
                          await act.run<typeof report>(
                            "/rules/" + rule.code + "/preview",
                            payload,
                          ),
                        );
                    }}
                  >
                    {Object.entries(rule.parameters).map(([key, p]) => (
                      <label key={key}>
                        {key}
                        <input
                          name={key}
                          type="number"
                          required
                          min={p.min}
                          max={p.max}
                          defaultValue={
                            rule.versions.find((v) => v.status === "PUBLISHED")
                              ?.parameters[key] ?? p.default
                          }
                        />
                      </label>
                    ))}
                    <label>
                      Обоснование
                      <input name="reason" required minLength={4} />
                    </label>
                    <div className="toolbar">
                      <button disabled={act.busy}>Сравнить оценки</button>
                      {user.role === "RULES_ADMIN" && (
                        <button
                          className="primary"
                          value="save"
                          disabled={act.busy}
                        >
                          Создать черновик
                        </button>
                      )}
                    </div>
                  </form>
                )}
                {user.role === "FRAUD_MANAGER" && (
                  <form
                    className="pad toolbar"
                    onSubmit={(e) =>
                      void act.run(
                        "/rules/" + rule.code + "/status",
                        { ...values(e), enabled: !rule.enabled },
                        undefined,
                        "PUT",
                      )
                    }
                  >
                    <label>
                      Причина изменения статуса
                      <input name="reason" required minLength={4} />
                    </label>
                    <button>{rule.enabled ? "Отключить" : "Включить"}</button>
                  </form>
                )}
              </Panel>
              {report && (
                <Panel title="Сравнение оценок">
                  <Table
                    columns={["Операция", "До", "После"]}
                    rows={report.map((x) => [
                      <Link to={"/transactions/" + x.id}>
                        {x.id.slice(0, 8)}
                      </Link>,
                      x.before.score + " · " + label(x.before.risk),
                      x.after.score + " · " + label(x.after.risk),
                    ])}
                  />
                </Panel>
              )}
              <Panel title="История версий">
                <Table
                  columns={[
                    "Версия",
                    "Состояние",
                    "Обоснование и параметры",
                    "Действие",
                  ]}
                  rows={rule.versions.map((v) => [
                    v.version,
                    <Badge value={v.status} />,
                    <details>
                      <summary>{v.reason}</summary>
                      <Json value={v.parameters} />
                    </details>,
                    v.status === "DRAFT" &&
                    user.role === "RULES_ADMIN" &&
                    user.login === v.author ? (
                      <button
                        onClick={() =>
                          void act.run("/rules/versions/" + v.id + "/submit")
                        }
                      >
                        Передать
                      </button>
                    ) : v.status === "SUBMITTED" &&
                      user.role === "FRAUD_MANAGER" ? (
                      <button
                        onClick={() =>
                          void act.run("/rules/versions/" + v.id + "/publish")
                        }
                      >
                        Опубликовать
                      </button>
                    ) : (
                      (v.publisher ?? "—")
                    ),
                  ])}
                />
              </Panel>
            </div>
          )}
        </div>
      )}
    </>
  );
}
function Audit({ rev }: { rev: number }) {
  const r = useData<(RecordRow & { detail: unknown })[]>("/audit", rev);
  return (
    <>
      <Head title="Аудит действий" />
      <Panel title="Последние события">
        {r.data ? (
          <Table
            columns={["Событие", "Автор", "Объект", "Время UTC", "Контекст"]}
            rows={r.data.map((x) => [
              x.action,
              x.actor,
              x.subject,
              time(String(x.created_at)),
              <details>
                <summary>{String(x.correlation).slice(0, 8)}</summary>
                <Json
                  value={{ correlation: x.correlation, detail: x.detail }}
                />
              </details>,
            ])}
          />
        ) : (
          <Wait error={r.error} />
        )}
      </Panel>
    </>
  );
}
function Users({ rev, refresh }: Props) {
  const r = useData<User[]>("/users", rev);
  const action = useCommand(refresh);
  return (
    <>
      <Head title="Пользователи" />
      <Panel title="Учётные записи">
        {r.data ? (
          <Table
            columns={["Логин", "Имя", "Роль"]}
            rows={r.data.map((u) => [u.login, u.name, label(u.role)])}
          />
        ) : (
          <Wait error={r.error} />
        )}
      </Panel>
      <Panel title="Добавить пользователя">
        <form
          className="pad form"
          onSubmit={(e) => void action.run("/users", values(e))}
        >
          <label>
            Логин
            <input name="login" required />
          </label>
          <label>
            Имя
            <input name="name" required minLength={4} />
          </label>
          <label>
            Пароль
            <input name="password" type="password" required minLength={12} />
          </label>
          <label>
            Роль
            <select name="role">
              {[
                "FRAUD_ANALYST",
                "SENIOR_ANALYST",
                "FRAUD_MANAGER",
                "RULES_ADMIN",
                "ADMIN",
              ].map((x) => (
                <option key={x} value={x}>
                  {label(x)}
                </option>
              ))}
            </select>
          </label>
          <button className="primary" disabled={action.busy}>
            Создать
          </button>
          <ErrorView error={action.error} />
        </form>
      </Panel>
    </>
  );
}
const scenarios: Record<string, string> = {
  normal: "Обычная операция",
  large: "Высокая сумма",
  burst: "Серия операций",
  outlier: "Отклонение от истории",
  recipient: "Новый получатель",
  combination: "Комбинация факторов",
  duplicate: "Повтор события",
  invalid: "Невалидное событие",
  late: "Запоздавшее событие",
  version: "Новая версия правила",
  reassessment: "Переоценка",
  multiple_alerts: "Несколько предупреждений клиента",
  grouping: "Группировка предупреждений",
  assignment: "Назначение аналитика",
  escalation: "Передача на согласование",
  false_positive: "Ложное срабатывание",
  confirmed: "Подтверждение подозрительности",
  concurrency: "Конкурентное решение",
  close_replay: "Повтор команды закрытия",
  compare: "Сравнение порогов",
  sla: "Просрочка SLA",
  recovery: "Повтор после отката",
};
function Lab({ refresh }: Props) {
  const action = useCommand(refresh);
  const [result, setResult] = useState<{
    passed: boolean;
    checks: Record<string, boolean>;
    traffic: unknown[];
    state: unknown;
  }>();
  return (
    <>
      <Head
        title="Лаборатория Sentrix"
        subtitle="Изолированная база и реальные запросы к API"
      />
      <Panel title="Выбор сценария">
        <form
          className="pad toolbar"
          onSubmit={async (e) => {
            const f = values(e);
            setResult(await action.run<typeof result>("/lab/" + f.scenario));
          }}
        >
          <label>
            Сценарий
            <select name="scenario">
              {Object.entries(scenarios).map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <button className="primary" disabled={action.busy}>
            Запустить
          </button>
        </form>
        <ErrorView error={action.error} />
      </Panel>
      {result && (
        <Panel
          title={result.passed ? "Проверка пройдена" : "Проверка не пройдена"}
        >
          <DataRows
            data={Object.entries(result.checks).map(([name, value]) => ({
              name,
              result: value ? "OK" : "FAIL",
            }))}
          />
          <details>
            <summary>Запросы и ответы API</summary>
            <Json value={result.traffic} />
          </details>
          <details>
            <summary>Состояние PostgreSQL после сценария</summary>
            <Json value={result.state} />
          </details>
        </Panel>
      )}
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <HashRouter>
    <App />
  </HashRouter>,
);
