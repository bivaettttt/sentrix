import { expect, test, type Page } from "@playwright/test";

const password = process.env.SENTRIX_DEMO_PASSWORD ?? "Sentrix-local-demo";

async function login(page: Page, user: string) {
  await page.getByLabel("Логин", { exact: true }).fill(user);
  await page.getByLabel("Пароль", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByRole("button", { name: "Выйти" })).toBeVisible();
}
async function swap(page: Page, user: string) {
  await page.getByRole("button", { name: "Выйти" }).click();
  await login(page, user);
}
async function nav(page: Page, name: string) {
  await page
    .getByRole("navigation")
    .getByRole("link", { name, exact: true })
    .click();
}
async function shot(page: Page, name: string) {
  if (!process.env.SENTRIX_SHOTS) return;
  await page.evaluate(() => document.fonts.ready);
  await page.mouse.move(4, 4);
  await page.evaluate(() =>
    (document.activeElement as HTMLElement | null)?.blur(),
  );
  await page.screenshot({
    path: process.env.SENTRIX_SHOTS + "/" + name + ".png",
  });
}

test("a separately authorized reviewer closes an evidence-backed investigation", async ({
  page,
}) => {
  await page.goto("/");
  await shot(page, "login");
  await login(page, "manager");
  await expect(page.getByText("Принятые операции")).toBeVisible();
  await shot(page, "dashboard");
  await page
    .getByRole("heading", { name: "Срабатывания по версиям правил" })
    .scrollIntoViewIfNeeded();
  await shot(page, "analytics");
  await nav(page, "Транзакции");
  await expect(
    page.getByRole("heading", { name: "Реестр операций" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "review-1", exact: true }))
    .toBeVisible({ timeout: 1000 })
    .catch(async () => {
      await page.getByLabel("Поиск").fill("review-1");
      await page.getByRole("button", { name: "Применить" }).click();
    });
  await expect(
    page.getByRole("link", { name: "review-1", exact: true }),
  ).toBeVisible();
  await shot(page, "transactions");
  await page.getByRole("link", { name: "review-1", exact: true }).click();
  await expect(page.getByText("R-01 · Крупная операция")).toBeVisible();
  await shot(page, "transaction");
  await page
    .getByText("Сигналы аномалий и признаки расчёта", { exact: true })
    .click();
  await shot(page, "risk");
  await nav(page, "Предупреждения");
  await expect(
    page.getByRole("heading", { name: "Очередь предупреждений" }),
  ).toBeVisible();
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await shot(page, "alerts");
  await nav(page, "Расследования");
  await page.getByLabel("Поиск").fill("Учебный профиль 02");
  await page.getByRole("button", { name: "Применить" }).click();
  const row = page
    .getByRole("row")
    .filter({ hasText: "Учебный профиль 02" })
    .filter({ hasText: "Новая" })
    .first();
  await expect(row).toBeVisible();
  await shot(page, "cases");
  await row.getByRole("link").click();
  await page
    .getByRole("combobox", { name: "Аналитик", exact: true })
    .selectOption("analyst");
  await page.getByLabel("Обоснование").fill("Проверить историю получателя");
  await page.getByRole("button", { name: "Выполнить" }).click();
  await expect(page.getByRole("cell", { name: "Назначение" })).toBeVisible();
  const address = page.url();
  await swap(page, "analyst");
  await expect(page.getByRole("combobox", { name: "Действие" })).toBeVisible();
  for (const [action, text, evidence] of [
    ["triage", "Проверены данные события", "Первичная проверка"],
    ["investigate", "Начат анализ истории", "Расследование"],
    ["evidence", "Сумма отличается от типичных операций профиля", "Материал"],
    ["submit", "Передано на независимую проверку", "На согласовании"],
  ]) {
    await page.getByRole("combobox", { name: "Действие" }).selectOption(action);
    await page.getByLabel("Обоснование").fill(text);
    const response = page.waitForResponse(
      (r) => r.url().endsWith("/commands") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Выполнить" }).click();
    expect((await response).ok()).toBeTruthy();
    await expect(
      page.locator("main").getByText(evidence, { exact: true }).first(),
    ).toBeVisible();
  }
  await page
    .getByText("Открыть транзакцию")
    .first()
    .evaluate((node) => (node.closest("details")!.open = true));
  await shot(page, "investigation");
  await page
    .getByRole("heading", { name: "История расследования" })
    .scrollIntoViewIfNeeded();
  await shot(page, "evidence");
  await swap(page, "reviewer");
  await expect(page.getByRole("combobox", { name: "Результат" })).toBeVisible();
  await shot(page, "review");
  await page
    .getByRole("combobox", { name: "Результат" })
    .selectOption("FALSE_POSITIVE");
  await page
    .getByLabel("Обоснование")
    .fill("История согласуется с учебным заявлением клиента");
  await page.getByRole("button", { name: "Выполнить" }).click();
  await expect(
    page.getByText("Ложное срабатывание", { exact: true }),
  ).toBeVisible();
  expect(page.url()).toBe(address);
});

test("rule preview and isolated laboratory render their actual results", async ({
  page,
}) => {
  await page.goto("/");
  await login(page, "rules");
  await expect(
    page.getByText("R-01 · Крупная операция", { exact: true }).first(),
  ).toBeVisible();
  await shot(page, "rule-registry");
  await page.getByLabel("threshold", { exact: true }).fill("100000000000");
  await page
    .getByLabel("Обоснование", { exact: true })
    .fill("Сравнение на фиксированной выборке");
  await page.getByRole("button", { name: "Сравнить оценки" }).click();
  await expect(
    page.getByRole("heading", { name: "Сравнение оценок" }),
  ).toBeVisible();
  await shot(page, "rules");
  await swap(page, "admin");
  await nav(page, "Лаборатория");
  await page
    .getByRole("combobox", { name: "Сценарий" })
    .selectOption("concurrency");
  await page.getByRole("button", { name: "Запустить" }).click();
  await expect(
    page.getByRole("heading", { name: "Проверка пройдена" }),
  ).toBeVisible();
  await expect(page.getByRole("cell", { name: "single_winner" })).toBeVisible();
  await shot(page, "lab");
  await nav(page, "Аудит");
  await expect(
    page.getByRole("heading", { name: "Последние события" }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "CASE_CLOSE", exact: true }).first(),
  ).toBeVisible();
  await shot(page, "audit");
});

test("CSV import adds one alert and the rule workflow separates author from publisher", async ({
  page,
}) => {
  const external = "browser-" + Date.now();
  const occurred = new Date();
  occurred.setUTCHours(12, 0, 0, 0);
  occurred.setUTCDate(occurred.getUTCDate() - 1);
  const csv = [
    "source,external_id,account,amount,currency,category,channel,recipient,occurred_at",
    [
      "browser",
      external,
      "A-007",
      20000000,
      "RUB",
      "GROCERY",
      "CARD",
      "synthetic-shop",
      occurred.toISOString(),
    ].join(","),
  ].join("\n");

  await page.goto("/");
  await login(page, "manager");
  await nav(page, "Транзакции");
  await page.getByRole("button", { name: "Импорт CSV" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "synthetic.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv),
  });
  const imported = page.waitForResponse((r) =>
    r.url().endsWith("/transactions/import"),
  );
  await page.getByRole("button", { name: "Загрузить пакет" }).click();
  const reply = await imported;
  expect(reply.status()).toBe(201);
  const [created] = await reply.json();
  expect(created.assessment.risk).toBe("HIGH");
  await expect(
    page.getByRole("link", { name: external, exact: true }),
  ).toBeVisible();
  await nav(page, "Предупреждения");
  const alert = page
    .getByRole("row")
    .filter({ hasText: created.transaction.slice(0, 8) });
  await expect(alert).toHaveCount(1);
  await expect(alert.getByRole("link", { name: /SX-/ })).toBeVisible();

  await nav(page, "Правила");
  await swap(page, "rules");
  await page.getByLabel("threshold", { exact: true }).fill("16000000");
  const reason = "Проверка публикации " + external;
  await page.getByLabel("Обоснование", { exact: true }).fill(reason);
  await page.getByRole("button", { name: "Создать черновик" }).click();
  const version = page.getByRole("row").filter({ hasText: reason });
  await expect(version.getByText("Черновик", { exact: true })).toBeVisible();
  await version.getByRole("button", { name: "Передать", exact: true }).click();
  await expect(
    version.getByText("На согласовании", { exact: true }),
  ).toBeVisible();
  await expect(
    version.getByRole("button", { name: "Опубликовать" }),
  ).toHaveCount(0);
  await swap(page, "manager");
  await version.getByRole("button", { name: "Опубликовать" }).click();
  await expect(
    version.getByText("Опубликована", { exact: true }),
  ).toBeVisible();
});
