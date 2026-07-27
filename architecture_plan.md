# Архитектурный план: Экосистема Price Aggregator (Web & Telegram ИИ-Агенты)

Данный документ описывает современную архитектуру системы **Price Aggregator Web & Telegram Ecosystem** — независимой многопользовательской веб-панели и мульти-агентной Telegram-системы для автоматизации сбора, сопоставления и анализа фармацевтических прайс-листов рынка Узбекистана.

---

## 🛠 Технологический стек

* **Бэкенд & Core Engine**: Python + **FastAPI** (асинхронный REST API + Internal API для агентов).
* **Фронтенд**: **React** (Vite) + **Vanilla CSS** (премиальный стеклянный дизайн Glassmorphism с поддержкой тёмной темы).
* **СУБД**: **PostgreSQL** (пользователи, каталоги синонимов, настройки нормализации, история файлов и задач).
* **Брокер сообщений и очередь задач**: **Redis** + **Celery** (фоновый нечеткий матчинг и сборка матриц Excel).
* **Telegram-Инфраструктура (3 Агента/Сервиса)**:
  1. **Scout Agent**: Pyrogram (Userbot / Telegram Client API).
  2. **Aggregator Bot**: aiogram v3 (Telegram Bot API — технический бот `@lightprice_aggr_bot`).
  3. **Analyst Agent**: aiogram v3 + **Google Gemini 2.5 Flash** (Telegram Bot API — ИИ-Аналитик).
* **ОРМ & Миграции**: **SQLAlchemy v2.0** + **Alembic**.
* **Развертывание**: **Docker Compose** (изолированные микросервисы).

---

## 🤖 Архитектура ИИ-Агентов и Сервисов Telegram

Экосистема включает в себя 3 четко разграниченных компонента для работы с Telegram:

```mermaid
flowchart TD
    subgraph Telegram Infrastructure
        A[TG Channels & Chats] -->|1. Скачивание .xlsx| B[Scout Agent (Pyrogram Userbot)]
        U[Пользователь в TG Чате] -->|2. Команды /collect, статусы| C[Aggregator Bot (@lightprice_aggr_bot)]
        U -->|3. Вопросы: анализ цен, дефицит, КРКА| D[Analyst Agent (Gemini 2.5 Flash)]
    end

    subgraph Core System
        B -->|HTTP POST /api/files/upload| E[Backend FastAPI]
        C -->|Trigger /collect| B
        D -->|HTTP GET /api/analysis| E
        D -->|Генерация отчетов| G[Gemini API]
        E <--> F[(PostgreSQL)]
        E <--> H[(Redis / Celery)]
    end
```

### 1. 🕵️‍♂️ Scout Agent (`scout_agent/`)
* **Технология**: Pyrogram (Telegram Userbot / Client API).
* **Контейнер**: `price_aggregator_scout`
* **Назначение**: Фоновый сборщик. Мониторит каналы и чаты дистрибьюторов в Telegram (Гранд Фарм, Мерос, Фарм Люкс, Асклепий, Зента, Аэро и др.), автоматически скачивает поступающие Excel-файлы и передает их в Backend API.

### 2. 🤖 Aggregator Bot (`backend/app/bot/`)
* **Технология**: aiogram v3.
* **Контейнер**: `price_aggregator_bot` (username `@lightprice_aggr_bot`).
* **Назначение**: Главный технический и управляющий бот. 
  * Принимает ручные файлы от администраторов;
  * Генерирует одноразовые ссылки для входа на веб-панель (Magic Links);
  * Обрабатывает команды управления и триггеры (`/collect`, *"агрегатор"*, *"сборка"*, *"статус систем"*);
  * Инициирует принудительный сбор прайсов через Scout Agent.

### 3. 📊 Analyst Agent (`analyst_agent/`)
* **Технология**: aiogram v3 + **Google Gemini 2.5 Flash**.
* **Контейнер**: `price_aggregator_analyst`
* **Назначение**: Интеллектуальный ИИ-аналитик рынка.
  * Классифицирует произвольные текстовые запросы пользователей из чата;
  * Формирует аналитические сводки по дефицитным препаратам, конкретным производителям (например, *«анализ цен КРКА за 3 дня»*) и отдельным препаратам (*«динамика по Виферон»*);
  * Публикует еженедельные аналитические отчеты после сборки сводного прайса.

---

## 📂 Структура проекта

```text
price-aggregator-web/
├── docker-compose.yml           # Оркестрация контейнеров (db, redis, backend, bot, scout_agent, analyst_agent, frontend)
├── .env.example                 # Шаблон переменных окружения
├── README.md                    # Основное руководство пользователя и документация
├── architecture_plan.md         # Описание архитектурных решений (Этот файл)
│
├── backend/                     # Бэкенд на FastAPI и Бот-Агрегатор
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py              # Точка входа FastAPI REST API
│   │   ├── config.py            # Конфигурация и переменные окружения
│   │   ├── database.py          # Инициализация SQLAlchemy
│   │   ├── models/              # Таблицы БД (User, Settings, Catalog, FileRecord, TaskRecord)
│   │   ├── api/                 # REST API (auth, files, settings, catalog, tasks, analysis)
│   │   ├── bot/                 # Бот-Агрегатор (aiogram v3)
│   │   │   ├── handlers/        # Обработчики технического бота (@lightprice_aggr_bot)
│   │   │   └── main.py          # Точка входа контейнера price_aggregator_bot
│   │   └── core/                # Ядро алгоритмов нечеткого сопоставления и сборки матриц
│   │       ├── price_utils.py   # Нормализация наименований и цен
│   │       ├── sales_parser.py  # Высокоскоростной XML-парсер файлов отчетов по продажам
│   │       ├── grouping.py      # Алгоритм сопоставления препаратов (Union-Find + Левенштейн)
│   │       ├── matrix_builder.py# Формирование матриц цен
│   │       └── report_formatter.py # Генерация стилизованных .xlsx файлов
│   └── migrations/              # Автогенерация миграций Alembic
│
├── scout_agent/                 # Telegram-парсер дистрибьюторских каналов
│   ├── Dockerfile
│   ├── main.py                  # Pyrogram клиент
│   └── api_client.py            # Отправка скачанных прайсов в backend API
│
├── analyst_agent/               # ИИ-Аналитик (aiogram + Gemini API)
│   ├── Dockerfile
│   ├── main.py                  # Обработка запросов из чата и классификация intents
│   ├── gemini_service.py        # Взаимодействие с Google Gemini 2.5 Flash
│   └── backend_client.py        # Получение аналитических данных с бэкенда
│
└── frontend/                    # SPA-приложение на React (Vite)
    ├── Dockerfile
    ├── package.json
    └── src/                     # Компоненты панели управления, история отчетов и настройки
```

---

## 🗄 Схема базы данных (Концепт)

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
        string task_type
        string status "pending / running / completed / failed"
        datetime created_at
    }

    users ||--|| settings : "имеет"
    users ||--o{ catalog : "настраивает"
    users ||--o{ files : "загружает/получает"
    users ||--o{ tasks : "запускает"
```

---

## 🔄 Схемы главных пользовательских сценариев

1. **Автоматический сбор и подготовка сводного прайса**:
   - `Scout Agent` скачивает Excel-файл дистрибьютора из Telegram-канала -> передаёт в `/api/files/upload`.
   - Файл регистрируется в БД, старые версии с тем же именем уходят в soft-archive `history`.
   - Пользователь или `Aggregator Bot` запускает процесс сборки -> `Celery` производит нечеткий матчинг по каталогу синонимов (`grouping.py`) -> генерирует результирующий `.xlsx`.

2. **Запрос ИИ-аналитики в чате**:
   - Пользователь пишет в групповой чат: *"Агрегатор, сделай анализ цен КРКА за 3 дня"*.
   - `Analyst Agent` распознает запрос с помощью `gemini_service.py` (intent: `manufacturer`, target: `КРКА`, days: `3`).
   - `Analyst Agent` запрашивает бэкенд `/api/analysis/manufacturer` -> отправляет полученную дельту цен в Gemini 2.5 Flash -> публикует форматированный HTML-отчет в чат.

3. **Запрос статуса системы и доступных сводных прайсов**:
   - Пользователь пишет в чат: *"Агрегатор, когда был последний сводный прайс?"* или команду `/status`.
   - `Aggregator Bot` запрашивает состояния задач и файлов бэкенда -> мгновенно отписывает дату свежей сборки и статус работы Scout-агента.
