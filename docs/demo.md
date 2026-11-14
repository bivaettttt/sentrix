# Sentrix demo / Демонстрация

1. Запустите `scripts/lab up` и войдите под `admin`. Выберите «Комбинация факторов». Разверните HTTP-трассу и откройте оценку риска, где записаны сумма, профиль, сохранённые признаки и версии правил.
2. Откройте новое дело под `manager` и назначьте `analyst`. Под `analyst` отметьте первичную проверку, начните расследование, добавьте материал, передайте дело старшему аналитику. Под `reviewer` сохраните итог и обоснование.
3. В Lab выполните «Конкурентное решение». Сопоставьте HTTP 200 и 409 с единственной записью о решении.
4. Под `rules` сравните порог R-01 на фиксированной выборке, создайте и передайте черновик. Под `manager` опубликуйте версию. Откройте историческую оценку, чтобы увидеть сохранённую версию и факторы.

| Операция | Снимок из браузера |
| --- | --- |
| Вход | [Login](../assets/screenshots/login.png) |
| Мониторинг | [Monitoring dashboard](../assets/screenshots/dashboard.png) |
| Список операций | [Transactions](../assets/screenshots/transactions.png) |
| Детали операции | [Transaction details](../assets/screenshots/transaction.png) |
| Причины риска | [Risk assessment](../assets/screenshots/risk.png) |
| Правила | [Rule registry](../assets/screenshots/rule-registry.png) |
| Сравнение | [Rule editor and preview](../assets/screenshots/rules.png) |
| Сигналы | [Alerts queue](../assets/screenshots/alerts.png) |
| Дела | [Case queue](../assets/screenshots/cases.png) |
| Расследование | [Investigation](../assets/screenshots/investigation.png) |
| Материалы | [Evidence history](../assets/screenshots/evidence.png) |
| Решение | [Decision review](../assets/screenshots/review.png) |
| Показатели | [Analytics](../assets/screenshots/analytics.png) |
| Аудит | [Audit](../assets/screenshots/audit.png) |
| Лаборатория | [Lab](../assets/screenshots/lab.png) |

[Видео двух прогонов Playwright](../assets/demo/sentrix.mp4). Запись включает назначение и закрытие дела, сравнение правил и запуск проверки конкурентного решения.
