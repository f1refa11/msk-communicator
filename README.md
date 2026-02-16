# msk-communicator

ССЫЛКА НА ВИДЕО: https://disk.yandex.ru/i/vfDQqxTXkSiMBg

## Быстрый старт (локально)
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install bcrypt jinja2 microdot pyjwt psycopg[binary]
export SESSION_SECRET=change-me  # Windows cmd: set SESSION_SECRET=change-me
python main.py
```

Откройте в браузере: http://127.0.0.1:5000

## Настройка БД

### 1) По умолчанию: SQLite
Никакой доп. настройки не требуется. Будет использоваться файл `database.db` в корне проекта.

При необходимости можно указать другой путь:

```bash
export SQLITE_DB_PATH="/var/lib/msk-communicator/database.db"
```

### 2) Внешний PostgreSQL (рекомендуется для продакшена)
Есть два способа настройки.

#### Способ A: единый `DATABASE_URL`
```bash
export DATABASE_URL="postgresql://msk_user:strong_password@db.example.com:5432/msk_communicator?sslmode=require"
```

Также поддерживается алиас `postgres://...` (будет автоматически преобразован).

#### Способ B: раздельные переменные
```bash
export POSTGRES_HOST="db.example.com"
export POSTGRES_PORT="5432"
export POSTGRES_DB="msk_communicator"
export POSTGRES_USER="msk_user"
export POSTGRES_PASSWORD="strong_password"
export POSTGRES_SSLMODE="require"  # опционально
```

Если `DATABASE_URL` задан, он имеет приоритет над `POSTGRES_*`.

## Запуск на Windows
1) Установите Python 3.12+.
2) Клонируйте/скопируйте проект, например в `C:\msk-communicator`.
3) Создайте виртуальное окружение и установите зависимости:
   ```cmd
   cd C:\msk-communicator
   py -3.12 -m venv .venv
   .venv\Scripts\activate
   pip install bcrypt jinja2 microdot pyjwt psycopg[binary]
   ```
4) Задайте секрет сессии:
   ```powershell
   setx SESSION_SECRET "your-strong-secret"
   ```
5) Запустите приложение:
   ```cmd
   .venv\Scripts\python main.py
   ```

## Запуск на Linux
Пример для Ubuntu/Debian:

1) Установите зависимости:
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-venv git
   ```
2) Клонируйте/скопируйте проект:
   ```bash
   git clone /path/to/repo msk-communicator
   cd msk-communicator
   ```
3) Создайте виртуальное окружение и установите зависимости:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install bcrypt jinja2 microdot pyjwt psycopg[binary]
   ```
4) Задайте секрет сессии и запустите приложение:
   ```bash
   export SESSION_SECRET="your-strong-secret"
   python main.py
   ```

Опционально можно поставить обратный прокси (Nginx/Apache) перед `http://127.0.0.1:5000`.

## Автоматизированные тесты (unit tests)
В проект добавлены unit-тесты для ключевых backend-модулей:
- конфигурация/адаптация БД (`db_backend.py`),
- расчет прогресса для личного кабинета (`progress_metrics.py`).

### Установка зависимостей для тестов
```bash
pip install pytest
```

### Запуск всех тестов
```bash
pytest
```

### Запуск конкретного файла тестов
```bash
pytest tests/test_db_backend.py
pytest tests/test_progress_metrics.py
```

## Добавление туториалов
- Создайте директорию `templates/tutorials/<slug>/`.
- Добавьте `meta.json` с полями `title`, `description` и `level` (`basic` или `advanced`).
- Добавьте файлы шагов: `1.tmpl`/`1.html`, `2.tmpl` и т.д. Они автоматически сортируются по номеру.
- Разместите ресурсы (CSS, изображения, видео) рядом и ссылайтесь на них как `/tutorials-assets/<slug>/file.ext`.

## Переменные окружения
- `SESSION_SECRET` — секретный ключ для сессий (обязательно задайте на продакшене).
- `DATABASE_URL` — полный DSN БД (`postgresql://...` или `sqlite:///...`).
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_SSLMODE` — настройка PostgreSQL без `DATABASE_URL`.
- `SQLITE_DB_PATH` — путь к файлу SQLite (если не используется PostgreSQL).

## Порты и данные
- Порт по умолчанию: `5000` (стандарт Microdot). Для публикации на `80/443` используйте reverse proxy.
- Данные:
  - SQLite: файл БД (по умолчанию `database.db`),
  - PostgreSQL: внешняя БД по параметрам окружения.
