# Архитектурный план: Веб-версия и Telegram-бот для Price Aggregator

На основе проведенного интервью мы разрабатываем независимое многопользовательское веб-приложение с интеграцией в Telegram-бот. Проект будет полностью отделен от оригинального десктопного приложения, но унаследует и адаптирует его бизнес-логику.

---

## 🛠 Технологический стек

* **Бэкенд**: Python + **FastAPI** (асинхронный REST API).
* **Фронтенд**: **React** (Vite) + **Vanilla CSS** (премиальный адаптивный дизайн с поддержкой темной темы и эффектов стекла/glassmorphism).
* **СУБД**: **PostgreSQL** (хранение настроек, пользователей, каталогов и метаданных файлов).
* **Брокер сообщений и очередь задач**: **Redis** + **Celery** (для фоновой обработки Excel).
* **Telegram-бот**: **aiogram (v3.x)** (асинхронный бот на вебхуках или polling).
* **ОРМ**: **SQLAlchemy (v2.0)** + миграции **Alembic**.
* **Развертывание**: **Docker Compose** (изолированные контейнеры для всех сервисов).

---

## 📂 Планируемая структура проекта

Новый проект будет размещен в директории `[price-aggregator-web](file:///home/ubuntu/price-aggregator-web)` со следующей структурой:

```text
price-aggregator-web/
├── docker-compose.yml           # Оркестрация всех контейнеров (db, redis, backend, bot, worker, frontend)
├── .env.example                 # Шаблон переменных окружения
├── backend/                     # Код бэкенда и Telegram-бота
│   ├── Dockerfile
│   ├── requirements.txt         # Зависимости (fastapi, aiogram, celery, sqlalchemy, pandas, openpyxl, etc.)
│   ├── alembic.ini              # Настройки миграций БД
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # Точка входа FastAPI
│   │   ├── config.py            # Настройки приложения (env, пути)
│   │   ├── database.py          # Инициализация SQLAlchemy
│   │   ├── models/              # Таблицы базы данных
│   │   │   ├── user.py          # Пользователи (Telegram ID, Web сессии)
│   │   │   ├── settings.py      # Настройки (колонки, производители)
│   │   │   ├── catalog.py       # Препараты и синонимы
│   │   │   └── file.py          # История загрузок и отчетов
│   │   ├── schemas/             # Схемы Pydantic для API
│   │   ├── api/                 # Эндпоинты REST API (auth, settings, files, catalog)
│   │   ├── bot/                 # Код Telegram-бота на aiogram
│   │   │   ├── handlers/        # Обработчики сообщений и файлов
│   │   │   ├── keyboards/       # Кнопки и инлайн-клавиатуры
│   │   │   └── loader.py        # Инициализация бота и диспетчера
│   │   ├── worker.py            # Настройка Celery app
│   │   ├── tasks.py             # Фоновые задачи Celery (вызов логики парсинга)
│   │   └── core/                # Адаптированная логика парсинга (из оригинального проекта)
│   │       ├── price_utils.py   # Утилиты нормализации
│   │       ├── svodny_price.py  # Сборка матрицы
│   │       ├── assortment.py    # Подсчет ассортимента
│   │       └── suppliers.py     # Анализ лучших поставщиков
│   └── migrations/              # Автогенерация миграций Alembic
│
└── frontend/                    # SPA-приложение на React
    ├── Dockerfile
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── index.css            # Премиальный дизайн-система (CSS-переменные)
        ├── components/          # Компоненты UI (таблицы, кнопки, загрузчики)
        └── pages/               # Страницы (Дашборд, Каталог, Настройки, История)
```

---

## 🗄 Схема базы данных (Концепт)

Для реализации многопользовательского режима (multi-tenancy) все сущности будут связаны с таблицей `users`.

```mermaid
erDiagram
    users {
        int id PK
        int telegram_id UK "Уникальный ID пользователя в Telegram"
        string username
        string first_name
        datetime created_at
    }
    settings {
        int id PK
        int user_id FK "Связь 1-к-1 с users"
        jsonb columns "Кандидаты названий колонок"
        string array producers "Список брендов/производителей"
        boolean use_catalog_matching
        boolean legacy_priority_rules
    }
    catalog {
        int id PK
        int user_id FK "Связь 1-к-many с users"
        string canonical "Каноническое название препарата"
        string array aliases "Список синонимов"
    }
    files {
        int id PK
        int user_id FK "Связь 1-к-many с users"
        string filename "Имя файла на диске"
        string display_name "Отображаемое имя"
        string file_type "input (прайс) или output (отчет)"
        string read_preset "khoji_akbar / grand_farm / auto"
        int file_size
        string storage_path "Путь на сервере"
        datetime uploaded_at
    }
    tasks {
        int id PK
        int user_id FK "Связь 1-к-many с users"
        string celery_task_id UK
        string task_type "svodny / assortment / cheapest / best_suppliers"
        string status "pending / running / completed / failed"
        string progress_message
        string result_file_path
        datetime created_at
    }

    users ||--|| settings : "имеет"
    users ||--o{ catalog : "настраивает"
    users ||--o{ files : "загружает/получает"
    users ||--o{ tasks : "запускает"
```

---

## 🔄 Схема взаимодействия и авторизации

1. **Авторизация по ссылке (Magic Link)**:
   * Пользователь заходит в Telegram-бот и пишет `/start`.
   * Бот сохраняет пользователя в БД `users` (если его нет).
   * Бот генерирует одноразовый JWT-токен входа и выдает ссылку вида: `https://our-site.com/auth?token=JWT_TOKEN`.
   * Пользователь переходит по ссылке. Браузер сохраняет токен, и пользователь авторизован на сайте под своей учетной записью.
   
2. **Telegram Mini App (Альтернатива)**:
   * Пользователь запускает WebApp внутри Telegram-бота.
   * Фронтенд React открывается внутри Telegram, валидирует `initData` от Telegram на бэкенде FastAPI и автоматически авторизует пользователя.

3. **Фоновая обработка файлов**:
   * Пользователь отправляет Excel-файлы в бот или загружает через сайт.
   * Файлы сохраняются в `/data/inputs/<user_id>/`.
   * Пользователь нажимает "Собрать сводный прайс".
   * FastAPI ставит задачу в Celery: `run_pipeline_task.delay(user_id, task_type)`.
   * Бэкенд возвращает `task_id`. Фронтенд (или бот) периодически опрашивает статус задачи.
   * Celery-воркер считывает файлы, производит сопоставление через адаптированную логику [svodny_price.py](file:///home/ubuntu/price-aggregator/svodny_price.py).
   * По завершении Celery-воркер генерирует Excel-файл в `/data/outputs/<user_id>/`, обновляет статус в БД, и Telegram-бот отправляет готовый файл в чат пользователю (или выводит кнопку скачать на сайте).

---

## 🚀 Этапы реализации

* [ ] **Этап 1: Инициализация проекта и Docker**
  * Создание структуры каталогов, настройка `docker-compose.yml` (PostgreSQL, Redis, FastAPI, Celery, React/Vite).
  * Настройка подключения к БД SQLAlchemy + Alembic, генерация стартовых миграций.
* [ ] **Этап 2: Адаптация ядра обработки (Core Engine)**
  * Перенос логики из [svodny_price.py](file:///home/ubuntu/price-aggregator/svodny_price.py), [cheapest_svodny_prices.py](file:///home/ubuntu/price-aggregator/cheapest_svodny_prices.py), [assortment_prices.py](file:///home/ubuntu/price-aggregator/assortment_prices.py), [best_suppliers_analysis.py](file:///home/ubuntu/price-aggregator/best_suppliers_analysis.py) и [price_utils.py](file:///home/ubuntu/price-aggregator/price_utils.py) в `backend/app/core/`.
  * Рефакторинг кода ядра для работы с БД (загрузка настроек колонок, каталога синонимов и списка производителей из таблиц вместо конфигурационных файлов на диске).
* [ ] **Этап 3: Telegram-бот и авторизация**
  * Разработка Telegram-бота на `aiogram 3.x`.
  * Реализация хендлеров `/start`, генерации Magic Link для веб-версии.
  * Реализация приема файлов Excel (сохранение на сервер, запись в БД).
* [ ] **Этап 4: API Бэкенда и Celery**
  * Эндпоинты для управления настройками, каталогом и файлами.
  * Интеграция Celery-задач для фонового процессинга.
  * WebSocket или SSE эндпоинт для отслеживания логов/прогресса работы воркера.
* [ ] **Этап 5: Разработка Фронтенда (React)**
  * Настройка дизайн-системы (Vanilla CSS, темная тема, стеклянные карточки).
  * Создание страниц: загрузка прайсов, редактор каталога, редактор кандидатов колонок, история запусков и отчетов.
  * Интеграция с Telegram WebApp для работы внутри мессенджера.
* [ ] **Этап 6: Тестирование и деплой**
  * Написание базовых интеграционных тестов.
  * Проверка полного сценария (Загрузка файлов в бот -> Запуск на сайте -> Получение отчета в боте).
