# Price Aggregator Web & Telegram MCP Ecosystem 💊📊

**Price Aggregator MCP Ecosystem** — это независимая многопользовательская веб-панель и интеллектуальная мульти-агентная экосистема из 4 специализированных Telegram-агентов на базе архитектуры **MCP (Model Context Protocol)** и **Google Gemini** для полной автоматизации сбора, сопоставления, аудита и аналитического исследования фармацевтических прайс-листов рынка Узбекистана.

Система круглосуточно осуществляет мониторинг Telegram-каналов и ботов дистрибьюторов, загружает входящие прайс-листы, производит нечёткое сопоставление наименований препаратов (Union-Find + расстояние Левенштейна / RapidFuzz) по каноническому каталогу синонимов, строит визуально оформленные сводные матрицы цен в Excel, проводит автоматический аудит корректности данных с самоисправлением (Self-Healing AI) и предоставляет глубокую бизнес-аналитику (отчёты, интерактивные графики и презентации PowerPoint) через стандартизированный слой **FastMCP** инструментов.

---

## 🌟 Ключевые возможности и архитектура агентов

Экосистема включает в себя 4 четко разграниченных микросервисных компонента, изолированный слой FastMCP-серверов и веб-платформу:

```mermaid
flowchart TD
    subgraph Telegram Infrastructure
        A[TG Channels & Bots Дистрибьюторов] -->|1. Скачивание .xlsx / .xls| B[🕵️‍♂️ Scout Agent (Userbot)]
        U[Пользователь / Фарм-команда] -->|2. Magic Link, ручная загрузка, /collect| C[🤖 Aggregator Bot (@lightprice_aggr_bot)]
        U -->|3. Аналитика цен, продажи, графики, PPTX| D[🧠 Analyst Agent (Gemini 2.5 Flash + MCP)]
        U -->|4. Аудит матриц, /debug, подтверждение правок| E[🛡️ Auditor & Debugger Bot (@lightyak_auditor_bot)]
    end

    subgraph MCP Tool Layer
        M1[📊 Analytics MCP Server] <-->|Tool Calling| D
        M2[🛠️ Debugger MCP Server] <-->|Tool Calling| E
    end

    subgraph Backend & Core Engine
        B -->|HTTP POST /api/files/upload| F[FastAPI REST API]
        C -->|Trigger /collect| B
        M1 -->|REST API Requests| F
        M2 -->|Rules & Files Inspection| F
        F -->|Celery Task: сборка матрицы| G[(Redis + Celery)]
        G -->|Завершение сборки| F
        F -->|Webhook: запуск аудита| E
        E -->|Диагностика расхождений и самоисправление| H[Distributor Rules JSON]
        F <--> I[(PostgreSQL)]
        D -->|Генерация отчетов| J[Google Gemini API]
    end

    subgraph Web Frontend
        W[React Vite SPA Dashboard] <-->|REST API + JWT| F
    end
```

---

### 1. 🕵️‍♂️ Scout Agent (Агент-Сборщик — Pyrogram Userbot)
* **Мониторинг каналов**: Автоматический фоновый сбор свежих прайс-листов из Telegram-каналов и групп ключевых дистрибьюторов (*Meros Pharm, Grand Pharm, Pharm Luxe, Asklepiy, Zenta, Aero Pharm, Drug Promotion, Biotek Farm, Hoji Akbar, Delpharm, Pharma Choice и др.*).
* **Опрос ботов-дистрибьюторов по требованию**: Автоматическое взаимодействие с ботами (например, `@vaksinabot`) по заданному расписанию (APScheduler Cron).
* **Интеллектуальная фильтрация**: Распознавание прайсов предоплаты (100%) и отсрочки (25%), фильтрация рекламных брошюр и промо-файлов.
* **Режим «Только скачивание» (`POST /fetch`)**: Сбор прайс-листов без немедленной генерации сводного отчета с публикацией детального статуса в рабочий Telegram-чат.
* **Безопасная передача**: Отправка файлов на бэкенд через изолированный внутренний протокол с проверкой `INTERNAL_API_KEY`.

---

### 2. 🤖 Aggregator Bot (Технический менеджер — `@lightprice_aggr_bot`)
* **Авторизация Magic Link**: Мгновенный и безопасный вход в веб-панель управления по одноразовой криптографической ссылке (HMAC-SHA256 JWT, TTL 15 минут) без паролей.
* **Ручная загрузка файлов**: Приём `.xlsx` и `.xls` файлов напрямую из личных сообщений и чатов с регистрацией в БД и автоматическим версионированием (`input_history`).
* **Управление конвейером**: Принудительный запуск сборки прайсов по командам `/collect`, `/menu` и триггерным фразам (*«агрегатор»*, *«собери прайсы»*).
* **Мониторинг состояния**: Мгновенный вывод статуса фоновых сервисов и даты последнего сформированного сводного файла (`/status`).

---

### 3. 🧠 Analyst Agent (ИИ-Аналитик рынка — Google Gemini + FastMCP)
* **Автоматический вызов инструментов (Gemini Function Calling & MCP)**: Gemini самостоятельно выбирает и вызывает необходимые инструменты MCP для получения точных фактов перед формированием ответа.
* **Инструменты FastMCP (`mcp_servers/analytics_server.py`)**:
  * `fetch_price_comparison`: сравнение двух сводных прайсов по датам и дефектура.
  * `fetch_manufacturer_trends`: динамика цен брендов за произвольный период (например, *«анализ цен КРКА за 3 дня»*).
  * `fetch_drug_price_history`: детальный срез рынка по конкретному препарату.
  * `fetch_system_summary`: актуальная сводка базы данных, загруженных файлов и сводных отчетов.
  * `fetch_sales_analysis`: анализ помесячной реализации и остатков (XML-парсер `sales_parser.py`).
* **Визуализация (Dark Mode Charts)**: Автоматическая отрисовка графиков динамики цен и структуры продаж в формате PNG (`chart_generator.py`).
* **Генерация презентаций PowerPoint (`.pptx`)**: Сборка полноценных 12-слайдовых презентаций с графиками, таблицами и отдельными слайдами по ключевым препаратам.

---

### 4. 🛡️ Auditor & Debugger Agent (Агент-Аудитор — `@lightyak_auditor_bot` + FastMCP)
* **Автономный аудит сводного прайса**: Срабатывает автоматически после каждой генерации сводной матрицы через внутренний вебхук (`POST /audit`).
* **Инструменты FastMCP (`mcp_servers/debugger_server.py`)**:
  * `get_distributor_rules`: получение актуальной базы правил парсинга.
  * `save_distributor_rule`: обновление правил сопоставления колонок.
  * `audit_excel_file`: инспекция структуры листов, заголовков и строк Excel-файлов дистрибьюторов.
  * `trigger_pipeline_rerun`: запуск фонового пересчета сводного горизонтального отчета.
  * `check_pipeline_task_status`: мониторинг прогресса выполнения задачи в бэкенде.
* **Модуль самоисправления (Self-Healing Engine)**: При обнаружении аномалий ИИ-диагност (`healer.py`) анализирует структуру исходного файла дистрибьютора, находит правильные колонки цен (25% / 100%) и формирует интерактивное предложение по исправлению.
* **Интерактивное утверждение правок**: Публикация карточки ошибки с кнопками *«✅ Применить и пересобрать»* и *«❌ Отклонить»*.

---

## ⚙️ Ядро сопоставления и обработки (Core Engine)

* **Умный детектор заголовков**: Автоматический поиск строки с заголовками колонок (Наименование, Цена 100%, Цена 25%, Остаток, Производитель).
* **Нечеткий матчинг (Fuzzy Matching)**: Алгоритм графической нормализации (Union-Find + RapidFuzz / Левенштейн) объединяет различные варианты написания одного препарата из прайсов разных дистрибьюторов в единую каноническую позицию.
* **Двунаправленная матрица цен**: Формирование как горизонтальной матрицы (препараты в строках, дистрибьюторы в столбцах), так и вертикальной транспонированной матрицы.
* **Стилизация Excel**: Профессиональное оформление отчетов с подсветкой лучших цен, разделением по колонкам 100% и 25% и цветовыми индикаторами.

---

## 📂 Структура проекта

```text
price-aggregator-web-mcp/
├── docker-compose.yml           # Оркестрация микросервисов в Docker
├── .env.example                 # Шаблон переменных окружения
├── README.md                    # Основное руководство пользователя
├── architecture_plan.md         # Архитектурный план экосистемы
│
├── mcp_servers/                 # Стандартизированные серверы Model Context Protocol (FastMCP)
│   ├── __init__.py
│   ├── analytics_server.py      # MCP Tools аналитики цен, препаратов и продаж
│   └── debugger_server.py       # MCP Tools инспекции Excel-файлов, правил и задач
│
├── backend/                     # Бэкенд на FastAPI и Бот-Агрегатор
│   ├── Dockerfile
│   ├── Шаблон.xlsx              # Базовый Excel-шаблон сводной матрицы
│   ├── requirements.txt         # FastAPI, SQLAlchemy, Celery, openpyxl, rapidfuzz, aiogram
│   └── app/
│       ├── main.py              # Точка входа FastAPI REST API
│       ├── config.py            # Конфигурация бэкенда
│       ├── database.py          # Инициализация подключения к PostgreSQL
│       ├── models/              # Модели БД (User, Settings, CatalogItem, FileRecord, TaskRecord)
│       ├── api/                 # REST API (auth, files, settings, catalog, tasks, analysis)
│       ├── bot/                 # Бот-Агрегатор (@lightprice_aggr_bot)
│       ├── core/                # Вычислительное ядро (Union-Find, матрица, sales parser)
│       └── tasks.py             # Задачи Celery и триггеры аудита
│
├── scout_agent/                 # Telegram-парсер каналов дистрибьюторов (Pyrogram)
│   ├── Dockerfile
│   ├── main.py                  # Pyrogram Userbot, APScheduler и HTTP-сервер
│   └── api_client.py            # Отправка файлов на бэкенд
│
├── analyst_agent/               # Аналитический бот (aiogram v3 + Gemini AI + FastMCP)
│   ├── Dockerfile
│   ├── main.py                  # Маршрутизация запросов и отправка отчётов
│   ├── gemini_service.py        # Обработка запросов через Google Gemini с Tool Calling
│   ├── mcp_client.py            # Клиент и схемы MCP Tools для Gemini
│   ├── chart_generator.py       # Построение графиков (Matplotlib Dark Theme PNG)
│   └── presentation_generator.py# Автоматическая сборка презентаций PowerPoint (.pptx)
│
├── debugger_agent/              # Агент-Аудитор и Отладчик (@lightyak_auditor_bot + FastMCP)
│   ├── Dockerfile
│   ├── main.py                  # FastAPI вебхуки и Telegram Polling
│   ├── auditor.py               # Движок аудита файлов сводного прайса
│   ├── healer.py                # ИИ-диагностика и генерация правил исправления
│   ├── mcp_client.py            # Клиент вызова MCP-инструментов аудитора
│   └── api_client.py            # Сохранение правил и запуск пересборки
│
└── frontend/                    # SPA-интерфейс на React (Vite)
    ├── Dockerfile
    ├── src/                     # React компоненты и страницы
    └── index.css                # Дизайн-система Neon Glassmorphism Dark Mode
```

---

## 🔒 Архитектура безопасности (Security Architecture)

1. **Изоляция межсервисного взаимодействия (Internal API Key Mesh)**:
   * Все внутренние запросы между агентами, MCP-серверами и бэкендом защищены ключом `INTERNAL_API_KEY`.
2. **Безопасная авторизация без паролей (Magic Links)**:
   * Ссылки генерируются с криптографической подписью HMAC-SHA256 и имеют ограниченный срок действия (15 минут).
3. **Ролевое разграничение доступа в Telegram (RBAC)**:
   * Боты проверяют `ALLOWED_TELEGRAM_IDS` и `TELEGRAM_GROUP_ID`.
4. **Сетевая изоляция**:
   * Внутренние микросервисы (база данных PostgreSQL, Redis, отладчик) доступны только внутри виртуальной сети Docker или привязаны к локальному интерфейсу `127.0.0.1`.

---

## 🛠 Технологический стек

* **Бэкенд**: Python 3.10+, **FastAPI** (REST API), **SQLAlchemy 2.0**, **PostgreSQL 15**.
* **Архитектура инструментов**: **FastMCP (Model Context Protocol)**.
* **Очереди задач**: **Redis 7** + **Celery**.
* **Фронтенд**: **React 18** (Vite), **Vanilla CSS** (Neon Glassmorphism Design System).
* **Telegram-Инфраструктура**: **aiogram v3** (Aggregator, Analyst, Auditor Bots), **Pyrogram** (Scout Agent Userbot), **APScheduler**.
* **Искусственный Интеллект**: **Google Gemini API** (Gemini 2.5 Flash с поддержкой Tool Calling).
* **Обработка данных**: **Pandas**, **OpenPyXL**, **RapidFuzz**, **Matplotlib**, **python-pptx**, **NetworkX / Union-Find**.
* **Оркестрация**: **Docker**, **Docker Compose**.

---

## 🚀 Запуск через Docker Compose

```bash
docker compose up --build -d
```

Все сервисы запускаются автоматически в изолированных контейнерах:
- `price_aggregator_mcp_db` (PostgreSQL)
- `price_aggregator_mcp_redis` (Redis)
- `price_aggregator_mcp_backend` (FastAPI, порт `8000`)
- `price_aggregator_mcp_worker` (Celery)
- `price_aggregator_mcp_bot` (Бот-Агрегатор)
- `price_aggregator_mcp_scout` (Userbot Scout)
- `price_aggregator_mcp_analyst` (ИИ-Аналитик с поддержкой FastMCP)
- `price_aggregator_mcp_debugger` (Аудитор & Отладчик, порт `127.0.0.1:8001`)
- `price_aggregator_mcp_frontend` (React Web SPA, порт `5173`)
