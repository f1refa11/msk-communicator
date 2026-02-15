# msk-communicator

Легкое веб-приложение на Microdot + Jinja2 для пошаговых учебных модулей с учетными записями пользователей, авторизацией на основе сессий и ресурсами для каждого туториала (HTML, изображения, CSS, видео).

## Что умеет
- Отдает каталог туториалов (`/tutorials`), разделенный по уровням (basic/advanced), из `templates/tutorials/<slug>/`.
- Рендерит отдельные шаги (`1.tmpl`, `1.html` и т.д.) внутри общей оболочки просмотрщика.
- Отдает статические ресурсы конкретного туториала (CSS, изображения, видео) через `/tutorials-assets/<slug>/<path>` с поддержкой byte-range для медиа.
- Хранит пользователей в SQLite (`database.db`) с хешированием паролей SHA-256 и выбором аватара.

## Быстрый старт (локально)
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install bcrypt jinja2 microdot pyjwt
set SESSION_SECRET=change-me  # Windows
export SESSION_SECRET=change-me  # Linux/macOS
python main.py
```
Откройте в браузере: http://127.0.0.1:5000

## Запуск на Windows
1) Установите Python 3.12+.
2) Клонируйте/скопируйте проект, например в `C:\msk-communicator`.
3) Создайте виртуальное окружение и установите зависимости:
   ```cmd
   cd C:\msk-communicator
   py -3.12 -m venv .venv
   .venv\Scripts\activate
   pip install bcrypt jinja2 microdot pyjwt
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
   pip install bcrypt jinja2 microdot pyjwt
   ```
4) Задайте секрет сессии и запустите приложение:
   ```bash
   export SESSION_SECRET="your-strong-secret"
   python main.py
   ```

Опционально можно поставить обратный прокси (Nginx/Apache) перед `http://127.0.0.1:5000`.

## Добавление туториалов
- Создайте директорию `templates/tutorials/<slug>/`.
- Добавьте `meta.json` с полями `title`, `description` и `level` (`basic` или `advanced`).
- Добавьте файлы шагов: `1.tmpl`/`1.html`, `2.tmpl` и т.д. Они автоматически сортируются по номеру.
- Разместите ресурсы (CSS, изображения, видео) рядом и ссылайтесь на них как `/tutorials-assets/<slug>/file.ext`.

## Переменные окружения
- `SESSION_SECRET` — секретный ключ для сессий (обязательно задайте на продакшене).

## Порты и данные
- Порт по умолчанию: `5000` (стандарт Microdot). Для публикации на `80/443` используйте reverse proxy.
- Данные: файл SQLite `database.db` в корне проекта.
