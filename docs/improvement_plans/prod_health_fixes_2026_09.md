# План исправлений по итогам осмотра прода

Дата осмотра: 2026-09-24, сервер `tw` (`/opt/insflow-system`), коммит на проде `6f4ec2b`.
Код на сервере и в образе совпадает с `main`, миграции применены, контейнеры healthy, 5xx за сутки нет,
SSL действителен до 26–29.11.2026, cron-задачи root (бэкап в VK 03:00, автозакрытие сводок 00:10) отрабатывают.

Ниже — найденные проблемы в порядке приоритета. Код в рамках осмотра не менялся.

---

## P1. Нулевая страховая сумма в одном году роняет весь файл страховщика — ✅ сделано

**Итог.** `_extract_year_data`: строка года, где сумма и премия пустые или 0, пропускается как «год не предложен» (INFO).
Ноль только в одном из полей — `RowProcessingError` с адресом ячейки (строка пропускается, остальные годы грузятся).
В `_create_single_offer` проверка `is not None` вместо истинности. Тесты: `summaries/test_offer_zero_year_rows.py`.

**Симптом.** В `django.log` регулярно (20.08, 26.08, 28.08 ×3, 10.09 ×2):

```
Ошибка при создании предложений: {'insurance_sum': ['Это поле не может иметь значение NULL.']}
```

Пример: Ингосстрах, сводка 303 — годы 1 и 2 заполнены, в строке 3-го года `сумма: 0.00, премия: 0.00`.
Файл отклоняется целиком, валидные годы тоже не загружаются.

**Причина.** `summaries/services/excel_services.py`, `create_offers` (~стр. 3831):

```python
insurance_sum = year_data['insurance_sum'].quantize(...) if year_data['insurance_sum'] else None
premium = year_data['premium'].quantize(...) if year_data['premium'] else None
```

`Decimal('0.00')` ложно → `None` → `full_clean()` падает на NOT NULL.
Валидация года (~стр. 3742) проверяет только `is None`, ноль пропускает.

**Что сделать.**
1. Строку года с `insurance_sum == 0` и `premium == 0` трактовать как «год не предложен» и пропускать
   на этапе обнаружения/извлечения лет (так же, как пустые строки 9–10), с `logger.info`.
2. Если ноль только в одном из полей (сумма 0, премия > 0 или наоборот) — понятная `InvalidDataError`
   с указанием строки/ячейки, а не падение на `full_clean`.
3. Заменить `if x else None` на `if x is not None else None` для `insurance_sum`/`premium`.
4. Тесты: файл с годами 1–2 валидными и 3-м нулевым → создаются 2 предложения; файл с суммой 0 и премией > 0 → понятная ошибка.

**Проверка.** Прогнать на реальных файлах из логов (Крымспецавто 10.09, СЕСПЕЛЬ 10.09, НТЗ Волхов 28.08).

---

## P1. Чистка журнала аудита не работает с апреля — ✅ сделано (деплой `ed61f6e`, сервер 2026-09-24)

**Симптом.** `easyaudit_requestevent` — 658 тыс. строк, 125 МБ (85 % БД в 148 МБ), самые старые — 2026-04-26,
хотя retention 1 день. LoginEvent/CRUDEvent (90 дней) тоже не чистятся. Ночные дампы раздуты (~10 МБ и растут).

**Причина.**
- `scripts/audit-cron-setup.sh` вызывается в деплое от пользователя `deploy` и ставит задачу в crontab `deploy`.
- `scripts/cron-purge-audit-log.sh` пишет в `/opt/insflow-system/logs/`, а эта папка — `root:root 755`.
  Под `set -euo pipefail` первая же запись в лог падает, команда не запускается. Лог-файла нет вообще.
- В syslog видно, что cron запускает задачу каждую ночь в 04:00 от `deploy`.
- Там же в crontab `deploy` дублируется бэкап в VK на 03:00 (ставит `backup-cron-setup.sh` из деплоя),
  он тоже тихо падает; реально работает копия из crontab `root`.

**Сделано в коде** (ждёт деплоя):
- Единый владелец cron-задач — `deploy`. Общий хелпер `scripts/cron-common.sh`:
  `cron_install_line` (идемпотентно, добавляет `CRON_TZ=Europe/Moscow`, если его нет) и
  `cron_require_log` (если лог недоступен на запись — сообщение в syslog с тегом `insflow-cron` и в stderr, exit 1).
- `backup-cron-setup.sh`, `audit-cron-setup.sh` переведены на хелпер; новый `auto-close-cron-setup.sh`
  (маркер `# insflow-auto-close`, 00:10) вызывается в шаге «Post-deploy hooks» деплоя.
- `purge_audit_log` удаляет партиями (`--batch-size`, по умолчанию 5000). Проверено: из-за подписки easy-audit
  на `post_delete` быстрого удаления нет, и `qs.delete()` загрузил бы все ~650 тыс. объектов в память.

**Разовые действия на сервере — ✅ выполнено 2026-09-24 после деплоя `ed61f6e`** (от root; `deploy` без sudo сделать это не может).

Итог: копия crontab root — `/root/crontab.root.bak.2026-09-24`; в crontab root осталась только `CRON_TZ`.
Первая чистка удалила 660 753 записи (RequestEvent 657 535, CRUDEvent 2 819, LoginEvent 399) за 28 с,
память web ≤ 190 МБ. `VACUUM (ANALYZE)` выполнен; файл `easyaudit_requestevent` остался 125 МБ
(место переиспользуется внутри таблицы, дамп уменьшается сразу). Вернуть место на диск — `VACUUM FULL`
этой таблицы (кратковременная блокировка), пока не делали.

> Порядок важен. Не делать `chown` до деплоя: иначе в 04:00 старая версия команды удалит 650 тыс. строк одним
> `qs.delete()`. И делать шаги 1 и 2 вместе: иначе в 03:00 бэкап в VK уйдёт дважды (от root и от deploy).

```bash
# 0. Убедиться, что деплой прошёл и cron deploy содержит 3 задачи + CRON_TZ
crontab -l -u deploy

# 1. Отдать логи deploy
chown -R deploy:deploy /opt/insflow-system/logs

# 2. Убрать задачи проекта из crontab root (остальное не трогать)
crontab -l > /root/crontab.root.bak.$(date +%F)
crontab -l | grep -v -e 'cron-auto-close-summaries.sh' -e 'insflow-backup-vk' | crontab -
crontab -l

# 3. Первая чистка вручную: сначала dry-run, потом по-настоящему (от deploy, как в cron)
cd /opt/insflow-system
sudo -u deploy docker compose exec -T web python manage.py purge_audit_log --dry-run
sudo -u deploy env USE_DOCKER=1 scripts/cron-purge-audit-log.sh
tail -20 logs/cron_purge_audit_log.log

# 4. Необязательно: вернуть место на диске (размер дампа уменьшится и без этого — pg_dump берёт только живые строки)
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "VACUUM (ANALYZE) easyaudit_requestevent;"'
```

**Проверка на следующий день:** в `logs/` появились записи от 00:10, 03:00 и 04:00 от `deploy`;
бэкап в VK пришёл один; `min(datetime)` в `easyaudit_requestevent` — около суток назад;
`grep insflow-cron /var/log/syslog` пусто.

---

## P2. HTTP→HTTPS редирект уводит все домены на лендинг — ✅ код готов, ждёт деплоя

**Итог.** Блок `listen 80` для доменов редиректит на `https://$host$request_uri`; отдельный
`listen 80 default_server` для `80.90.189.37` и неизвестных Host — на главную лендинга `https://insflow.ru/` (без пути)
(сотрудники ходят только на zs.insflow.ru; по IP заходят в основном сканеры).
Проверено во временном nginx-контейнере на сервере: `nginx -t` ок, все 4 домена редиректят на себя,
IP/чужой Host/127.0.0.1 → insflow.ru, ACME-location отвечает, HTTPS `/healthz/` 200.
HTTPS по голому IP / без SNI / с чужим SNI — отдельный `listen 443 ssl default_server` с редиректом на
`https://insflow.ru/`; проверено так же (4 домена по HTTPS отвечают как раньше).

**Симптом.** `http://zs.insflow.ru/requests/` → `301 https://insflow.ru/requests/` → 404 на основном домене.
То же для `zs.insflow.tw1.su`, `insflow.tw1.su`. Пользователь, набравший адрес без `https://`, не попадает в приложение.

**Причина.** `nginx-timeweb/default.conf:36`:

```nginx
return 301 https://$server_name$request_uri;
```

`$server_name` — всегда первое имя из `server_name` (`insflow.ru`).

**Что сделать.** Заменить на `https://$host$request_uri`. Для IP `80.90.189.37` в том же блоке — редиректить
на `https://zs.insflow.ru$request_uri` (или вынести IP в отдельный `server`). Проверить `nginx -t` и curl по всем 4 доменам.

---

## P2. Логи приложения без ротации

**Симптом.** Том `logs_data_timeweb` — 567 МБ: `domain_routing.log` 513 МБ, `django.log` 35 МБ, `https.log` 12 МБ.
Свободно на `/` 4,6 ГБ из 14.

**Причина.** В `onlineservice/settings.py` (`LOGGING`, ~стр. 236–280) все файловые хендлеры — `logging.FileHandler`.

**Что сделать.**
1. Перевести на `logging.handlers.RotatingFileHandler` (`maxBytes` ~10–20 МБ, `backupCount` 5) или
   `TimedRotatingFileHandler`. С несколькими воркерами gunicorn ротация из процесса может конфликтовать —
   альтернатива `WatchedFileHandler` + logrotate на хосте для тома.
2. Снизить шум `onlineservice.middleware`: строки `Domain routing` / `Subdomain access` / `HTTPS response` на каждый
   запрос перевести в `DEBUG`, в `INFO` оставить только аномалии (unknown domain, 404 на основном домене).
3. Разово обрезать текущий `domain_routing.log` (после согласования).

---

## P3. Мелочи

- **SECRET_KEY** с префиксом `django-insecure-` → `security.W009` в `check --deploy`. Сгенерировать новый
  (`get_random_secret_key()` без префикса), заменить в секретах/`.env`. Все сессии сбросятся — делать вне рабочего времени.
- **Отчёт деплоя / SSL-скрипты.** `deployment_report.txt` и `ssl-generation.log`: `Permission denied` на
  `/var/log/ssl-certificates.log` и `mkdir /etc/letsencrypt` (скрипт работает от `deploy`). На сайт не влияет,
  но проверка сертификата в отчёте всегда «failed». Писать лог в `logs/` проекта, проверять сертификат через
  `openssl s_client` к 443.
- **Пустая страховая сумма при заполненном годе** — закрыто вместе с P1. Выяснилось, что такие строки и раньше
  пропускались без падения файла (ERROR был только в логе); теперь при пустых сумме и премии это INFO «год не предложен».
- **nginx warnings.** `listen ... http2` устарел → `listen 443 ssl;` + `http2 on;`. `ssl_stapling` бесполезен
  с новыми сертификатами Let's Encrypt (нет OCSP) — убрать `ssl_stapling*`.
- **Память.** 961 МБ RAM, свободно ~100 МБ, swap 408 МБ занят (на хосте ещё два бота). Пока работает;
  следить, при росте — уменьшить число воркеров gunicorn или увеличить тариф.

---

## Порядок работ

| # | Задача | Где | Деплой |
|---|--------|-----|--------|
| 1 ✅ | Нулевой год в файле страховщика | `summaries/services/excel_services.py` + тесты | обычный пуш в `main` |
| 2 ✅ | Права на `logs/`, единый владелец cron, устойчивые обёртки | `scripts/*.sh`, `deploy_timeweb.yml` (отдельный SSH-шаг — основной `script:` на пределе 21k) | пуш + разовые действия на сервере |
| 3 ✅ | Первая чистка аудита + VACUUM | сервер | вручную, после п. 2 |
| 4 ✅ | `$host` в редиректе nginx | `nginx-timeweb/default.conf` | пуш |
| 5 | Ротация и уровень логов | `onlineservice/settings.py`, `onlineservice/middleware.py` | пуш |
| 6 | P3 | разное | по возможности |
