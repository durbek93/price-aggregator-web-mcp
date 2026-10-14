# Архитектурный план: Экосистема Price Aggregator (Web & Telegram ИИ-Агенты)

Данный документ описывает современную архитектуру системы **Price Aggregator Web & Telegram Ecosystem** — независимой многопользовательской веб-панели и мульти-агентной Telegram-системы для автоматизации сбора, сопоставления и анализа фармацевтических прайс-листов рынка Узбекистана.

---

## 🛠 Технологический стек

* **Бэкенд & Core Engine**: Python + **FastAPI** (асинхронный REST API + Internal API для агентов).
* **Фронтенд**: **React** (Vite) + **Vanilla CSS** (премиальный стеклянный дизайн Glassmorphism с поддержкой тёмной темы).
* **СУБД**: **PostgreSQL** (пользователи, каталоги синонимов, настройки нормализации, история файлов и задач).
* **Брокер сообщений и очередь задач**: **Redis** + **Celery** (фоновый нечеткий матчинг и сборка матриц Excel).
* **Telegram-Инфраструктура и ИИ-Агенты (4 Агента/Сервиса)**:
  1. **Scout Agent**: Pyrogram (Userbot / Telegram Client API) — сборщик файлов из каналов дистрибьюторов.
  2. **Aggregator Bot**: aiogram v3 (Telegram Bot API — технический бот `@lightprice_aggr_bot`).
  3. **Analyst Agent**: aiogram v3 + aiohttp + **Google Gemini 2.5 Flash** (Telegram Bot API — ИИ-Аналитик `@lightprice_analyst_bot`).
  4. **Debugger Agent (Auditor & Healer)**: FastAPI + aiogram v3 + **Google Gemini 2.5 Flash** (порт 8001 — `@lightprice_debugger_bot`).
* **ОРМ & Миграции**: **SQLAlchemy v2.0** + **Alembic**.
* **Развертывание**: **Docker Compose** (изолированные микросервисы).

---

## 🤖 Архитектура ИИ-Агентов и Сервисов

Экосистема включает в себя 4 четко разграниченных микросервиса-агента:

```mermaid
flowchart TD
    subgraph Telegram Infrastructure
        A[TG Channels & Chats Дистрибьюторов] -->|1. Скачивание .xlsx| B[Scout Agent (Pyrogram Userbot)]
        U[Пользователь / Администратор] -->|2. Команды /collect, статусы| C[Aggregator Bot (@lightprice_aggr_bot)]
        TG_GROUP[Общая TG Группа] <--|3. Аналитические отчеты| D[Analyst Agent (@lightprice_analyst_bot)]
        TG_GROUP <--|4. Аудит и алерты сбоев| DBG[Debugger Agent (@lightprice_debugger_bot)]
    end

    subgraph Core System
        B -->|HTTP POST /api/files/upload| E[Backend FastAPI]
        C -->|Trigger /fetch| B
        E -->|Celery Task| H[(Redis / Celery)]
        H -->|Генерация Сводного прайса| E
        E -->|HTTP POST /trigger_report| D
        E -->|HTTP POST /audit| DBG
        D -->|HTTP GET /api/analysis/compare| E
        D -->|Генерация отчетов| G[Gemini 2.5 Flash API]
        DBG -->|Автоисправление правил| G
        E <--> F[(PostgreSQL)]
    end
```

### 1. 🕵️‍♂️ Scout Agent (`scout_agent/`)
* **Технология**: Pyrogram (Telegram Userbot / Client API).
* **Контейнер**: `price_aggregator_mcp_scout`
* **Назначение**: Фоновый сборщик прайс-листов.
  * **Республиканский контур**: мониторит каналы ключевых дистрибьюторов (Гранд Фарм, Мерос, Фарм Люкс, Асклепий, Зента, Аэро, Биотек, Дельфарм и др.), запрашивает ботов (например, `@vaksinabot`);
  * **Контур Ферганской долины**: изолированный сбор из 17 каналов и групп оптовиков Ферганы, Андижана и Намангана (*Верона, Эверест, Мемори, Гейт, Аззам, Саида, Хожи Акбар, Акмал Фарм, Зилол мед, Фармакосмос, Турон, Макро, Охотник, Гармония, Рефлекс, Саховат, Саидмед Фарм*) по расписанию в **14:00 (Asia/Tashkent)**;
  * Скачивает поступающие Excel-файлы (100% и 25%) и передает их в Backend API с привязкой к целевой задаче.
* **HTTP API (порт 8080)**:
  * `/collect` — сбор и построение республиканского сводного прайса;
  * `/fetch` — режим «только скачивание» республиканских прайсов без генерации отчёта;
  * `/collect_fergana` — целевой опрос 17 оптовиков Долины и построение сводного прайса Ферганской долины;
  * `/fetch_fergana` — режим «только скачивание» прайсов Долины в изолированную папку `fergana/`.

### 2. 🤖 Aggregator Bot (`backend/app/bot/`)
* **Технология**: aiogram v3.
* **Контейнер**: `price_aggregator_mcp_bot` (username `@lightprice_aggr_bot`).
* **Назначение**: Главный технический и управляющий бот. 
  * Принимает ручные файлы от администраторов;
  * Генерирует одноразовые ссылки для входа на веб-панель (Magic Links);
  * Обрабатывает команды управления и триггеры:
    * **Республика**: `/collect`, `/fetch`, `/just_collect` (*"агрегатор"*, *"скачай прайсы"*);
    * **Ферганская долина**: `/collect_fergana` (или `/fergana`), `/fetch_fergana`, `/just_collect_fergana` (*"долина"*, *"фергана"*, *"собери фергану"*);
    * **Инфо и сервис**: `/status`, `/menu`, `/link`;
  * Предоставляет интерактивное меню с раздельными кнопками запуска: `📊 Сводный прайс (Республика)` и `🍇 Сводный (Ферганская долина)`;
  * Инициирует сбор прайсов через Scout Agent.

### 3. 📊 Analyst Agent (`analyst_agent/`)
* **Технология**: aiogram v3 + aiohttp web server + **Google Gemini 2.5 Flash**.
* **Контейнер**: `price_aggregator_mcp_analyst` (username `@lightprice_analyst_bot`).
* **Внутренний порт**: `8002` (эндпоинт `POST /trigger_report`).
* **Назначение**: Интеллектуальный ИИ-аналитик фармацевтического рынка.
  * **Автоматический отчёт**: сразу после генерации Сводного прайса формирует структурированный 3-блочный отчёт по 6 ключевым препаратам;
  * **Интерактивный анализ по запросам**: понимает запросы по производителям (*«анализ цен КРКА за 3 дня»*), препаратам (*«динамика по Виферон»*), продажам (*«отчет продаж за декабрь 2025»*);
  * **Визуализация**: генерация графиков трендов цен и структуры продаж (matplotlib), построение аналитических презентаций PowerPoint (`.pptx`);
  * **Поддержка MCP**: интеграция с инструментами бэкенда через Model Context Protocol.

### 4. 🩺 Debugger Agent (`debugger_agent/`)
* **Технология**: FastAPI + aiogram v3 + **Google Gemini 2.5 Flash**.
* **Контейнер**: `price_aggregator_mcp_debugger` (username `@lightprice_debugger_bot`).
* **Внутренний порт**: `8001` (эндпоинт `POST /audit`).
* **Назначение**: Автоматический аудит качества сборки прайсов и самовосстановление (Self-Healing).
  * Сравнивает исходные сырые прайс-листы дистрибьюторов с результирующим Сводным прайсом;
  * Обнаруживает расхождения (пропущенные колонки со скидками 100%, ошибки наименований, сдвиги строк);
  * С помощью Gemini генерирует исправления для `distributor_rules.json` и предлагает их администратору с кнопками подтверждения в Telegram.

---

## 📈 Логика Сводного прайса и Аналитических отчётов

### 1. Визуализация изменений в Excel-матрице (`СвПрайс`)
В результирующем файле `Сводный прайс ДД.ММ.ГГГГ.xlsx` реализована наглядная цветовая индикация изменений относительно предыдущей сборки:

| Состояние ячейки | Визуальное оформление | Описание |
| :--- | :--- | :--- |
| **Рост цены** | Фон `#FCE4D6` (светло-красный), шрифт `#C65911`, стрелка `↑` | Цена выросла по сравнению с прошлым прайсом (`45 000 ↑`) |
| **Падение цены** | Фон `#E2EFDA` (светло-зеленый), шрифт `#375623`, стрелка `↓` | Цена снизилась по сравнению с прошлым прайсом (`42 000 ↓`) |
| **Появление новинки / возврат** | Фон **`#DDEBF7`** (мягкий голубой), шрифт **`#000000`** (чёрный жирный) | Препарат появился у дистрибьютора, когда в прошлый раз отсутствовал |
| **Вымывание (исчезновение)** | Фон **`#F4CCCC`** (пастельно-розовый), **ячейка пустая** | Препарат был в наличии в прошлый раз, но пропал из текущего прайса |
| **Без изменений** | Стандартный белый фон, обычный числовой формат | Цена не изменилась относительно прошлой сборки |

### 2. Структура аналитического отчёта Gemini (3 блока)
Отчёт строго сфокусирован на **6 ключевых препаратах компании «Материа Медика»**:
1. *Анаферон Детский* (таблетки)
2. *Анаферон Детский капли*
3. *Эргоферон*
4. *Ренгалин* (таблетки / раствор)
5. *Тенотен*
6. *Тенотен Детский*

Отчёт состоит из 3 обязательных блоков:
* 🏆 **Блок 1: Самые дешёвые препараты (Минимальные цены)** — по 1 абсолютному лидеру с лучшей ценой на каждый доступный ключевой препарат.
* 📈 **Блок 2: Изменение цен (Динамика)** — подорожавшие (📈) и подешевевшие (📉) позиции среди 6 препаратов с указанием дистрибьютора, старой цены, новой цены и дельты в %.
* 🔄 **Блок 3: Отслеживание наличия (Появление и вымывание)**:
  * ❇️ *Появились / вернулись в прайс* — у кого из поставщиков препарат появился с ценой;
  * ⚠️ *Пропали из прайса (вымылись)* — у кого позиция исчезла;
  * 🚨 *Отсутствуют в наличии* — общий дефицит у конкретных дистрибьюторов.

### 3. Сквозной автоматический цикл Республики (Republic Pipeline Event Loop)
```text
1. Завершение сборки прайса (Celery task: svodny_horizontal)
   │
   ├─► Сохранение файла на диск и запись в БД (FileRecord)
   │
   ├─► Отправка .xlsx файла в Telegram-группу (send_telegram_doc_sync)
   │
   ├─► HTTP POST http://analyst_agent:8002/trigger_report
   │    │
   │    ├─► Analyst Agent запрашивает дельту: GET /api/analysis/compare
   │    ├─► Gemini 2.5 Flash генерирует 3-блочный отчёт
   │    └─► Публикация отчёта в Telegram-группу вторым сообщением
   │
   └─► HTTP POST http://debugger_agent:8001/audit (Фоновый аудит корректности)
```

### 4. Автоматический цикл Ферганской долины (Fergana Pipeline Event Loop)
```text
1. Срабатывание расписания (14:00 Asia/Tashkent) или вызов /collect_fergana
   │
   ├─► Scout Agent: опрос 17 каналов и групп оптовиков Ферганской долины (fergana_collector.py)
   │    └─► Скачивание и фильтрация свежих .xlsx/.xls прайсов
   │
   ├─► Загрузка файлов на бэкенд (POST /api/files/upload)
   │
   ├─► Инициация Celery задачи: task_type="svodny_fergana" с точным списком file_ids
   │    │
   │    ├─► Чтение файлов с поддержкой узбекских колонок (Номи, Махсулот, Нархи, 100% тўлов)
   │    ├─► Нечеткий матчинг и сборка динамической матрицы по оптовикам Долины
   │    └─► Генерация: "Сводный прайс Ферганская долина ДД.ММ.ГГГГ.xlsx"
   │
   └─► Отправка готового файла в рабочую Telegram-группу с пометкой [ФЕРГАНСКАЯ ДОЛИНА] 🍇
```

---

## 📂 Структура проекта

```text
price-aggregator-web-mcp/
├── docker-compose.yml           # Оркестрация микросервисов (db, redis, backend, worker, bot, scout, analyst, debugger, frontend)
├── .env.example                 # Шаблон переменных окружения
├── README.md                    # Основное руководство пользователя
├── architecture_plan.md         # Описание архитектуры системы (Этот документ)
├── AI_PROMPTS.md                # Полный реестр используемых ИИ-промптов Gemini
├── Шаблон.xlsx                  # Базовый шаблон Сводного прайса
│
├── backend/                     # Бэкенд FastAPI, Celery Tasks и Бот-Агрегатор
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py              # Точка входа REST API
│   │   ├── config.py            # Конфигурация и переменные окружения
│   │   ├── database.py          # SQLAlchemy Session & Engine
│   │   ├── tasks.py             # Celery Tasks (сборка прайсов Республики и Долины, автоотправка)
│   │   ├── models/              # Модели БД (User, UserSettings, CatalogItem, FileRecord, TaskRecord)
│   │   ├── api/                 # Эндпоинты (auth, files, settings, catalog, tasks, analysis)
│   │   │   └── analysis.py      # Сравнение прайсов (/compare), отслеживание appeared/disappeared
│   │   ├── bot/                 # Бот-Агрегатор (@lightprice_aggr_bot)
│   │   └── core/                # Алгоритмы конвейера
│   │       ├── pipeline.py      # Сборка республиканского (гориз./верт.) и Ферганского прайса
│   │       ├── excel_reader.py  # Адаптивное чтение прайс-листов (русские и узбекские колонки)
│   │       ├── grouping.py      # Нормализация наименований и сопоставление синонимов
│   │       └── report_formatter.py # Оформление стилей выходного Excel-файла
│   └── migrations/              # Миграции Alembic
│
├── analyst_agent/               # Микросервис ИИ-Аналитика
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                  # aiogram polling + aiohttp HTTP server (порт 8002: /trigger_report)
│   ├── gemini_service.py        # Промпты и обращение к Gemini 2.5 Flash
│   ├── backend_client.py        # HTTP-клиент к REST API бэкенда
│   ├── chart_generator.py       # Визуализация графиков (matplotlib)
│   ├── presentation_generator.py# Построение презентаций (.pptx)
│   └── mcp_client.py            # MCP Tool Calling клиент
│
├── debugger_agent/              # Микросервис Аудитора и Целителя (Self-Healing)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                  # FastAPI server (порт 8001: /audit) + aiogram бот
│   ├── auditor.py               # Проверка расхождений сырых прайсов со Сводным
│   └── healer.py                # Генерация исправлений правил парсинга через Gemini
│
├── scout_agent/                 # Микросервис Сборщика прайсов
│   ├── Dockerfile
│   ├── main.py                  # HTTP-сервер (порт 8080) + Pyrogram клиент + APScheduler
│   ├── fergana_channels.py      # Конфигурация 17 каналов и групп оптовиков Ферганской долины
│   ├── fergana_collector.py     # Изолированный сбор и фильтрация прайсов Долины
│   ├── api_client.py            # Отправка файлов на бэкенд (поддержка svodny_fergana)
│   └── config.py
│
├── mcp_servers/                 # Конфигурации серверов Model Context Protocol
│
└── frontend/                    # Веб-панель управления на React (Vite)
    ├── Dockerfile
    ├── package.json
    └── src/                     # Компоненты UI (Glassmorphism, файлы, настройки, задачи, аналитика)
```

---

## 🗄 Схема базы данных

```mermaid
erDiagram
    users {
        int id PK
        int telegram_id UK "ID пользователя в Telegram"
        string username
        string first_name
        datetime created_at
    }
    settings {
        int id PK
        int user_id FK
        jsonb columns "Кандидаты названий колонок"
        string array producers "Список брендов/производителей"
        boolean use_catalog_matching
        boolean legacy_priority_rules
        boolean clear_inputs_after_processing
    }
    catalog {
        int id PK
        int user_id FK
        string canonical "Каноническое название препарата"
        string array aliases "Синонимы"
    }
    files {
        int id PK
        int user_id FK
        string filename
        string display_name
        string file_type "input или output"
        int file_size
        string storage_path
        datetime uploaded_at
    }
    tasks {
        int id PK
        int user_id FK
        string celery_task_id UK
        string task_type "svodny_horizontal, assortment и др."
        string status "pending / running / completed / failed"
        string progress_message
        string result_file_path
        boolean is_automated
        datetime created_at
    }

    users ||--|| settings : "имеет"
    users ||--o{ catalog : "настраивает"
    users ||--o{ files : "загружает/получает"
    users ||--o{ tasks : "запускает"
```
