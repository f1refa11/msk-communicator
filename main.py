import microdot.jinja
import os
from microdot import Microdot, send_file, redirect
from microdot.session import Session, with_session
from jinja2 import Environment, PackageLoader, select_autoescape
import base64
import hashlib
import bcrypt
import json
import sqlite3
import mimetypes
import jwt
from datetime import datetime, timezone

db = sqlite3.connect("database.db", autocommit=True)
cur = db.cursor()

# todo: rate limiting на post запросы

env = Environment(loader=PackageLoader("main"), autoescape=select_autoescape())

page_index = env.get_template("index.tmpl")
page_login = env.get_template("login.tmpl")
page_register = env.get_template("register.tmpl")
page_tutorial = env.get_template("tutorial.tmpl")
page_account = env.get_template("account.tmpl")
page_forgot = env.get_template("forgot.tmpl")
page_tutorial_viewer = env.get_template("tutorial_viewer.tmpl")
page_support = env.get_template("support.tmpl")
TUTORIALS_DIR = os.path.join("templates", "tutorials")
TUTORIAL_PAGE_EXTENSIONS = (".tmpl", ".html", ".htm")
BUGREPORTS_FILE = os.path.join(os.path.dirname(__file__), "bugreports.json")
TUTORIAL_SLUG_RENAMES = {
    "rustoredowload": "rustoredownload",
}
DEFAULT_COURSE_SLUG = "smartphone-basics"
COURSE_DEFINITIONS = [
    {
        "slug": "smartphone-basics",
        "title": "Основы смартфона",
        "description": "Базовые интерактивные модули: подключение к Wi-Fi и установка приложений.",
    },
    {
        "slug": "max-messenger",
        "title": "Работа с мессенджером MAX",
        "description": "Курс запланирован. Интерактивные модули скоро появятся.",
    },
    {
        "slug": "online-shopping",
        "title": "Онлайн-покупки",
        "description": "Курс запланирован. Интерактивные модули скоро появятся.",
    },
    {
        "slug": "gosuslugi",
        "title": "Госуслуги",
        "description": "Курс запланирован. Интерактивные модули скоро появятся.",
    },
]

SUPPORT_PROBLEM_LABELS = {
    "video_not_opening": "не открывается видео",
    "tutorial_not_opening": "не открывается интерактивный модуль",
    "account_not_created": "не создаётся аккаунт",
    "account_login_failed": "не получается зайти в аккаунт",
}

SUPPORT_FAQ_DATA = {
    "change_password": {
        "question": "как поменять пароль для аккаунта?",
        "answer": (
            "Вы можете поменять пароль в настройках аккаунта. Нажмите кнопку "
            "«Перейти в настройки аккаунта» ниже и введите старый и новый пароли."
        ),
    },
    "delete_account": {
        "question": "как удалить аккаунт?",
        "answer": (
            "Вы можете удалить аккаунт через страницу настроек аккаунта: "
            "в самом конце страницы есть кнопка удаления."
        ),
    },
}

SUPPORT_FEEDBACK_LABELS = {
    "resolved": "Всё получилось",
    "issues": "Возникли проблемы",
}

app = Microdot()


def _ensure_jwt_compat():
    """Provide PyJWT-like encode/decode if another jwt package is installed."""
    if hasattr(jwt, "encode") and hasattr(jwt, "decode"):
        return

    jwt_engine = jwt.JWT()

    def _to_oct_jwk(secret_key):
        key_bytes = (
            secret_key
            if isinstance(secret_key, bytes)
            else str(secret_key).encode("utf-8")
        )
        key_b64 = base64.urlsafe_b64encode(key_bytes).rstrip(b"=").decode("ascii")
        return jwt.jwk_from_dict({"kty": "oct", "k": key_b64})

    def _encode(payload, secret_key, algorithm="HS256"):
        return jwt_engine.encode(payload, _to_oct_jwk(secret_key), alg=algorithm)

    def _decode(token, secret_key, algorithms=None):
        allowed = set(algorithms) if algorithms else {"HS256"}
        return jwt_engine.decode(token, _to_oct_jwk(secret_key), algorithms=allowed)

    jwt.encode = _encode
    jwt.decode = _decode

    if not hasattr(jwt, "exceptions"):
        class _CompatExceptions:
            pass
        jwt.exceptions = _CompatExceptions()

    if not hasattr(jwt.exceptions, "PyJWTError"):
        fallback_error = getattr(jwt.exceptions, "JWTException", Exception)
        jwt.exceptions.PyJWTError = fallback_error


_ensure_jwt_compat()

SESSION_SECRET = os.environ.get("SESSION_SECRET", "change-me")
Session(app, secret_key=SESSION_SECRET)


def normalize_tutorial_slug(slug: str):
    """Normalize tutorial slug to the canonical route."""
    raw_slug = (slug or "").strip().lower()
    return TUTORIAL_SLUG_RENAMES.get(raw_slug, raw_slug)


def resolve_tutorial_directory(tutorial_slug: str):
    """Map canonical slug to an existing tutorials directory."""
    normalized_slug = normalize_tutorial_slug(tutorial_slug)
    if not normalized_slug or not os.path.exists(TUTORIALS_DIR):
        return None

    for directory_name in sorted(os.listdir(TUTORIALS_DIR)):
        tutorial_path = os.path.join(TUTORIALS_DIR, directory_name)
        if not os.path.isdir(tutorial_path):
            continue
        if not any(
            os.path.splitext(filename)[1].lower() in TUTORIAL_PAGE_EXTENSIONS
            for filename in os.listdir(tutorial_path)
        ):
            continue
        if normalize_tutorial_slug(directory_name) == normalized_slug:
            return directory_name
    return None


def load_tutorials(include_hidden=False):
    """Return tutorial metadata for interface and viewer pages."""
    tutorials = []
    seen_slugs = set()

    if not os.path.exists(TUTORIALS_DIR):
        try:
            os.makedirs(TUTORIALS_DIR, exist_ok=True)
        except OSError:
            return tutorials

    for directory_name in sorted(os.listdir(TUTORIALS_DIR)):
        tutorial_path = os.path.join(TUTORIALS_DIR, directory_name)
        if not os.path.isdir(tutorial_path):
            continue

        page_files = [
            f
            for f in os.listdir(tutorial_path)
            if os.path.splitext(f)[1].lower() in TUTORIAL_PAGE_EXTENSIONS
        ]
        if not page_files:
            continue

        slug = normalize_tutorial_slug(directory_name)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        meta_path = os.path.join(tutorial_path, "meta.json")
        meta = {}

        if os.path.exists(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as meta_file:
                    meta = json.load(meta_file)
            except Exception:
                meta = {}

        level = str(meta.get("level", "basic")).lower()
        if level not in ("basic", "advanced"):
            level = "basic"

        visible_in_interface = meta.get("visible_in_interface", True)
        if isinstance(visible_in_interface, str):
            visible_in_interface = (
                visible_in_interface.strip().lower() not in ("0", "false", "no")
            )
        else:
            visible_in_interface = bool(visible_in_interface)

        if not include_hidden and not visible_in_interface:
            continue

        course = str(meta.get("course", DEFAULT_COURSE_SLUG)).strip() or DEFAULT_COURSE_SLUG
        viewer_navigation = str(meta.get("viewer_navigation", "pages")).strip().lower()
        if viewer_navigation not in ("pages", "style-switch"):
            viewer_navigation = "pages"

        style_options = meta.get("style_options")
        if not isinstance(style_options, list):
            style_options = []

        tutorials.append(
            {
                "slug": slug,
                "directory": directory_name,
                "title": meta.get("title") or slug,
                "description": meta.get("description") or "Описание появится позже.",
                "level": level,
                "course": course,
                "viewer_navigation": viewer_navigation,
                "style_options": style_options,
            }
        )

    return tutorials


def _tutorial_sort_key(filename: str):
    """Sort tutorial pages numerically when possible, otherwise alphabetically."""
    stem, _ = os.path.splitext(filename)
    try:
        return (0, int(stem))
    except ValueError:
        return (1, stem.lower())


def mark_tutorial_completed(user_id: int, tutorial_slug: str):
    """Mark tutorial as completed for a user on first visit."""
    if not user_id or not tutorial_slug:
        return
    cur.execute(
        """
        INSERT INTO tutorial_progress (user_id, tutorial_slug)
        VALUES (?, ?)
        ON CONFLICT(user_id, tutorial_slug) DO NOTHING
        """,
        (user_id, tutorial_slug),
    )


def get_user_tutorial_progress(user_id: int):
    """Return tutorial list with completion status for the given user."""
    tutorials = load_tutorials()
    cur.execute(
        "SELECT tutorial_slug, completed_at FROM tutorial_progress WHERE user_id = ?",
        (user_id,),
    )
    completed_by_slug = {}
    for row in cur.fetchall():
        normalized_slug = normalize_tutorial_slug(row[0])
        completed_by_slug[normalized_slug] = row[1]

    progress = []
    for tutorial in tutorials:
        completed_at = completed_by_slug.get(tutorial["slug"])
        progress.append(
            {
                "slug": tutorial["slug"],
                "title": tutorial["title"],
                "description": tutorial["description"],
                "level": tutorial["level"],
                "completed": bool(completed_at),
                "completed_at": completed_at,
            }
        )
    return progress


def get_current_user(session):
    user_id = session.get("user_id")
    if not user_id:
        return None
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cur.fetchone()


def init_db():
    """
    Checks if the 'users' table exists, and creates it if it doesn't.
    """
    # Query the sqlite_master table to check for existence
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if cur.fetchone() is None:
        print("Table 'users' not found. Creating it...")
        # using 'name' as Primary Key ensures no duplicate usernames
        cur.execute("""
            CREATE TABLE users (
                id INTEGER NOT NULL UNIQUE,
                tel TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                pass TEXT NOT NULL,
                admin INTEGER DEFAULT 0,
                avatar TEXT DEFAULT 'avatar-1',
                PRIMARY KEY(id AUTOINCREMENT)
            )
        """)
    else:
        print("Table 'users' found.")


# Run the check on startup
init_db()

# add missing columns for existing dbs
cur.execute("PRAGMA table_info(users)")
_cols = [row[1] for row in cur.fetchall()]
if "avatar" not in _cols:
    cur.execute("ALTER TABLE users ADD COLUMN avatar TEXT DEFAULT 'avatar-1'")

cur.execute(
    """
    CREATE TABLE IF NOT EXISTS tutorial_progress (
        user_id INTEGER NOT NULL,
        tutorial_slug TEXT NOT NULL,
        completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(user_id, tutorial_slug)
    )
    """
)

AVATARS = ["avatar-1", "avatar-2", "avatar-3", "avatar-4", "avatar-5"]


def _load_bug_reports():
    if not os.path.exists(BUGREPORTS_FILE):
        return []
    try:
        with open(BUGREPORTS_FILE, encoding="utf-8-sig") as reports_file:
            data = json.load(reports_file)
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return data
    return []


def append_bug_report(report_kind: str, report_code: str, label: str, user):
    reports = _load_bug_reports()
    reports.append(
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "report_kind": report_kind,
            "report_code": report_code,
            "label": label,
            "user": (
                {
                    "id": user[0],
                    "tel": user[1],
                    "name": user[2],
                }
                if user
                else None
            ),
        }
    )
    with open(BUGREPORTS_FILE, "w", encoding="utf-8") as reports_file:
        json.dump(reports, reports_file, ensure_ascii=False, indent=2)


def _is_support_widget_request(request):
    return (
        request.headers.get("X-Support-Widget") == "1"
        or request.form.get("source") == "widget"
    )


def _support_api_response(request, ok: bool, message: str, fallback_url: str):
    if _is_support_widget_request(request):
        body = json.dumps({"ok": ok, "message": message}, ensure_ascii=False)
        return (
            body,
            200 if ok else 400,
            {"Content-Type": "application/json; charset=utf-8"},
        )
    return redirect(fallback_url)

# -- PAGES


# index
@app.route("/")
@with_session
async def index(request, session):
    user = get_current_user(session)
    alert_message = None
    alert_type = None  # success | error

    reg_status = request.args.get("reg")
    if reg_status:
        if reg_status == "success":
            alert_type = "success"
            alert_message = "Регистрация прошла успешно. Теперь войдите в аккаунт."
        else:
            alert_type = "error"
            alert_message = "Не удалось зарегистрироваться. Попробуйте ещё раз."

    login_status = request.args.get("login")
    if login_status == "success":
        alert_type = "success"
        alert_message = "Вход выполнен."
    elif login_status == "fail":
        alert_type = "error"
        alert_message = "Не удалось войти. Проверьте номер телефона и пароль."

    return (
        page_index.render(
            alert_message=alert_message,
            alert_type=alert_type,
            yes_login=bool(user),
            user_name=user[2] if user else "",
        ),
        200,
        {"Content-Type": "text/html"},
    )


# login
@app.route("/login")
@with_session
async def index(request, session):
    user = get_current_user(session)
    status = ""
    if request.args.get("reset") == "success":
        status = "пароль обновлен, войдите снова"
    return (
        page_login.render(
            test=status, yes_login=bool(user), user_name=user[2] if user else ""
        ),
        200,
        {"Content-Type": "text/html"},
    )


# login
@app.route("/register")
@with_session
async def index(request, session):
    user = get_current_user(session)
    return (
        page_register.render(
            test="test", yes_login=bool(user), user_name=user[2] if user else ""
        ),
        200,
        {"Content-Type": "text/html"},
    )


# static
@app.route("/static/<path:path>")
async def static(request, path):
    if ".." in path:
        return "Not found", 404
    return send_file("static/" + path)


@app.route("/tutorials-assets/<tutorial_name>/<path:path>")
async def tutorial_assets(request, tutorial_name, path):
    """Serve per-tutorial static assets (css, images) located next to templates."""
    if ".." in path or path.startswith("/"):
        return "Not found", 404
    resolved_tutorial_name = resolve_tutorial_directory(tutorial_name)
    if not resolved_tutorial_name:
        return "Not found", 404
    asset_path = os.path.join(TUTORIALS_DIR, resolved_tutorial_name, path)
    if not os.path.isfile(asset_path):
        return "Not found", 404
    # Basic Range support for media files (videos) so seeking works
    range_header = request.headers.get("Range") or request.headers.get("range")
    if range_header and range_header.startswith("bytes="):
        file_size = os.path.getsize(asset_path)
        bytes_range = range_header.split("=", 1)[1]
        start_str, end_str = (bytes_range.split("-") + [""])[:2]
        try:
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
        except ValueError:
            return "Invalid Range", 400
        if start >= file_size:
            return "Range Not Satisfiable", 416
        end = min(end, file_size - 1)
        length = end - start + 1
        with open(asset_path, "rb") as f:
            f.seek(start)
            data = f.read(length)
        mime, _ = mimetypes.guess_type(asset_path)
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Content-Type": mime or "application/octet-stream",
        }
        return data, 206, headers

    mime, _ = mimetypes.guess_type(asset_path)
    return send_file(asset_path, content_type=mime or "application/octet-stream")


# tutorial
@app.route("/tutorials")
@with_session
async def tutorials_list(request, session):
    user = get_current_user(session)

    tutorials = load_tutorials()
    courses = [
        {
            "slug": course["slug"],
            "title": course["title"],
            "description": course["description"],
            "modules": [],
        }
        for course in COURSE_DEFINITIONS
    ]
    course_map = {course["slug"]: course for course in courses}

    for tutorial in tutorials:
        course_slug = tutorial.get("course") or DEFAULT_COURSE_SLUG
        course = course_map.get(course_slug)
        if course is None:
            continue
        course["modules"].append(tutorial)

    return (
        page_tutorial.render(
            courses=courses,
            has_any=any(course["modules"] for course in courses),
            yes_login=bool(user),
            user_name=user[2] if user else "",
        ),
        200,
        {"Content-Type": "text/html"},
    )


@app.route("/tutorials/<tutorial_name>")
@app.route("/tutorials/<tutorial_name>/")
@with_session
async def tutorial_entrypoint(request, session, tutorial_name):
    canonical_slug = normalize_tutorial_slug(tutorial_name)
    return redirect(f"/tutorials/{canonical_slug}/1")


# 3. Добавляем новый маршрут для просмотра страницы туториала
@app.route("/tutorials/<tutorial_name>/<int:page_num>")
@with_session
async def tutorial_viewer(request, session, tutorial_name, page_num):
    user = get_current_user(session)

    canonical_slug = normalize_tutorial_slug(tutorial_name)
    if tutorial_name != canonical_slug:
        return redirect(f"/tutorials/{canonical_slug}/{page_num}")

    # Путь к папке конкретного туториала
    resolved_tutorial_name = resolve_tutorial_directory(canonical_slug)
    if not resolved_tutorial_name:
        return "Интерактивный модуль не найден", 404

    tutorial_path = os.path.join(TUTORIALS_DIR, resolved_tutorial_name)

    if not os.path.exists(tutorial_path):
        return "Интерактивный модуль не найден", 404

    tutorial_meta = next(
        (t for t in load_tutorials(include_hidden=True) if t["slug"] == canonical_slug),
        None,
    )

    # Ищем страницы туториала: Jinja-шаблоны (.tmpl) и обычные HTML (.html/.htm)
    files = [
        f
        for f in os.listdir(tutorial_path)
        if os.path.splitext(f)[1].lower() in TUTORIAL_PAGE_EXTENSIONS
    ]
    # Сортируем по номеру (1, 2, 10), затем по имени
    files.sort(key=_tutorial_sort_key)

    total_pages = len(files)

    if total_pages == 0:
        return "В этом интерактивном модуле нет страниц", 404

    if page_num < 1 or page_num > total_pages:
        return "Такой страницы не существует", 404

    current_file = files[page_num - 1]
    if user and page_num == total_pages:
        mark_tutorial_completed(user[0], canonical_slug)

    viewer_navigation = (
        tutorial_meta["viewer_navigation"] if tutorial_meta else "pages"
    )
    style_options = []
    if tutorial_meta and viewer_navigation == "style-switch":
        for item in tutorial_meta.get("style_options", []):
            if not isinstance(item, dict):
                continue
            option_label = str(item.get("label", "")).strip()
            option_page = item.get("page")
            if not option_label or not isinstance(option_page, int):
                continue
            if option_page < 1 or option_page > total_pages:
                continue
            style_options.append({"label": option_label, "page": option_page})
        if len(style_options) < 2:
            viewer_navigation = "pages"
            style_options = []

    # Формируем путь для Jinja (относительно папки templates)
    # Например: "tutorials/taxi/1.tmpl" или "tutorials/taxi/1.html"
    template_name = f"tutorials/{resolved_tutorial_name}/{current_file}"

    try:
        # 1. Рендерим саму страницу туториала (контент)
        content_template = env.get_template(template_name)
        # Если внутри слайдов нужны переменные (например, user), передайте их сюда
        rendered_content = content_template.render(user=user)

        # 2. Рендерим оболочку-вьювер и вставляем туда контент
        return (
            page_tutorial_viewer.render(
                tutorial_name=canonical_slug,
                tutorial_title=(
                    tutorial_meta["title"] if tutorial_meta else canonical_slug
                ),
                tutorial_level=(tutorial_meta["level"] if tutorial_meta else "basic"),
                viewer_navigation=viewer_navigation,
                style_options=style_options,
                current_page=page_num,
                total_pages=total_pages,
                content=rendered_content,  # Передаем готовый HTML
                yes_login=bool(user),
                user_name=user[2] if user else "",
            ),
            200,
            {"Content-Type": "text/html"},
        )

    except Exception as e:
        return f"Ошибка при загрузке шаблона: {e}", 500


@app.route("/forgot")
@with_session
async def forgot_password_page(request, session):
    user = get_current_user(session)
    status = request.args.get("status") or ""
    status_map = {
        "blank": "заполните все поля",
        "nomatch": "пароли не совпадают",
        "notfound": "аккаунт не найден",
    }
    return (
        page_forgot.render(
            status=status_map.get(status, ""),
            yes_login=bool(user),
            user_name=user[2] if user else "",
        ),
        200,
        {"Content-Type": "text/html"},
    )


@app.route("/support")
@with_session
async def support_page(request, session):
    user = get_current_user(session)
    mode = request.args.get("mode") or "root"
    if mode not in ("root", "problem", "faq"):
        mode = "root"

    faq_key = request.args.get("faq") or ""
    selected_faq = SUPPORT_FAQ_DATA.get(faq_key)

    sent = request.args.get("sent")
    status_message = None
    status_type = "success"
    if sent == "1":
        status_message = "Сообщение отправлено разработчикам сайта."
    elif sent == "0":
        status_type = "error"
        status_message = "Не удалось отправить сообщение. Попробуйте снова."

    return (
        page_support.render(
            yes_login=bool(user),
            user_name=user[2] if user else "",
            mode=mode,
            selected_faq=selected_faq,
            selected_faq_key=faq_key,
            status_message=status_message,
            status_type=status_type,
        ),
        200,
        {"Content-Type": "text/html"},
    )


# account settings
@app.route("/account/")
@with_session
async def account_settings(request, session):
    user = get_current_user(session)
    if not user:
        return redirect("/login")
    if user[5] is None:
        cur.execute("UPDATE users SET avatar = ? WHERE id = ?", ("avatar-1", user[0]))
        user = get_current_user(session)
    tutorial_progress = get_user_tutorial_progress(user[0])
    completed_tutorials_count = sum(1 for t in tutorial_progress if t["completed"])
    return (
        page_account.render(
            yes_login=True,
            user=user,
            avatars=AVATARS,
            user_name=user[2],
            tutorial_progress=tutorial_progress,
            completed_tutorials_count=completed_tutorials_count,
            total_tutorials_count=len(tutorial_progress),
        ),
        200,
        {"Content-Type": "text/html"},
    )


# @app.route('/db/<path:path>')
# async def dbdownload(request, path):
#     if '..' in path:
#         return 'Not found', 404

#     return send_file('db/' + path)


@app.route("/assets/<path:path>")
async def logoload(request, path):
    # Я установил в темплейте прям длину и высоту в img
    if ".." in path:
        return "Not found", 404

    return send_file("assets/" + path)


# register route
@app.route("/api/account/register", methods=["POST"])
@with_session
async def handle_reg(request, session):
    # todo: проверить, существует ли уже пользователь

    # fetch form info
    name = request.form.get("name")
    tel = request.form.get("tel")
    pwd = request.form.get("pwd")

    if not name or not tel or not pwd:
        return redirect("/register?error=blank")

    cur.execute("SELECT tel FROM users WHERE tel = ?", (tel,))
    existing_user = cur.fetchone()

    if existing_user:
        return redirect("/register?error=exists")

    # pwd hashs
    hash_object = hashlib.sha256(pwd.encode("utf-8"))
    dpass = hash_object.hexdigest()

    # send db insert
    try:
        cur.execute(
            "INSERT INTO users(tel, name, pass) VALUES (?, ?, ?)", (tel, name, dpass)
        )
        print(f"Registered {name}")
        return redirect(f"/?reg=success")
    except Exception as e:
        print(f"Database error: {e}")
        return redirect(f"/?reg=error")
    # COMMIT не нужен потому что при подключении указана настройка autocommit

    # Проверка хеша

    # stored_hash = b''
    # user_input_password = ""
    # if bcrypt.checkpw(user_input_password.encode('utf-8'), stored_hash):
    #     print("Пароль верный")
    # else:
    #     print("Неверный пароль")

    # print(name)

    # return {'Имя': name,'Пароль':passw,'Хеш пароля':dpass}


@app.route("/api/account/login", methods=["POST"])
@with_session
async def handle_login(request, session):
    # 1. Fetch form info
    tel = request.form.get("tel")
    pwd = request.form.get("pwd")

    # 2. Hash the input password (must match the method used in register)
    hash_object = hashlib.sha256(pwd.encode("utf-8"))
    input_hash = hash_object.hexdigest()

    # 3. Check DB for matching Name AND Password Hash
    # Using '?' prevents SQL Injection
    cur.execute("SELECT * FROM users WHERE tel = ? AND pass = ?", (tel, input_hash))
    user = cur.fetchone()

    if user:
        response = redirect("/?login=success")
        session["user_id"] = user[0]
        session.save()
        return response
    else:
        return redirect("/?login=fail")


@app.route("/api/account/update_name", methods=["POST"])
@with_session
async def handle_update_name(request, session):
    user = get_current_user(session)
    if not user:
        return redirect("/login")
    new_name = request.form.get("name")
    if not new_name:
        return redirect("/account/?name=blank")
    cur.execute("UPDATE users SET name = ? WHERE id = ?", (new_name, user[0]))
    return redirect("/account/?name=success")


@app.route("/api/account/update_tel", methods=["POST"])
@with_session
async def handle_update_tel(request, session):
    user = get_current_user(session)
    if not user:
        return redirect("/login")
    new_tel = request.form.get("tel")
    if not new_tel:
        return redirect("/account/?tel=blank")
    cur.execute("SELECT id FROM users WHERE tel = ? AND id != ?", (new_tel, user[0]))
    if cur.fetchone():
        return redirect("/account/?tel=exists")
    cur.execute("UPDATE users SET tel = ? WHERE id = ?", (new_tel, user[0]))
    return redirect("/account/?tel=success")


@app.route("/api/account/update_password", methods=["POST"])
@with_session
async def handle_update_password(request, session):
    user = get_current_user(session)
    if not user:
        return redirect("/login")
    current_pwd = request.form.get("current_pwd")
    new_pwd = request.form.get("new_pwd")
    new_pwd_confirm = request.form.get("new_pwd_confirm")
    if not current_pwd or not new_pwd or not new_pwd_confirm:
        return redirect("/account/?pwd=blank")
    if new_pwd != new_pwd_confirm:
        return redirect("/account/?pwd=nomatch")
    current_hash = hashlib.sha256(current_pwd.encode("utf-8")).hexdigest()
    if current_hash != user[3]:
        return redirect("/account/?pwd=wrong")
    new_hash = hashlib.sha256(new_pwd.encode("utf-8")).hexdigest()
    cur.execute("UPDATE users SET pass = ? WHERE id = ?", (new_hash, user[0]))
    return redirect("/account/?pwd=success")


@app.route("/api/account/update_avatar", methods=["POST"])
@with_session
async def handle_update_avatar(request, session):
    user = get_current_user(session)
    if not user:
        return redirect("/login")
    avatar = request.form.get("avatar")
    if avatar not in AVATARS:
        return redirect("/account/?avatar=invalid")
    cur.execute("UPDATE users SET avatar = ? WHERE id = ?", (avatar, user[0]))
    return redirect("/account/?avatar=success")


@app.route("/api/account/delete", methods=["POST"])
@with_session
async def handle_delete_account(request, session):
    user = get_current_user(session)
    if not user:
        return redirect("/login")
    confirm = request.form.get("confirm_delete")
    pwd = request.form.get("delete_pwd")
    if confirm != "on" or not pwd:
        return redirect("/account/?delete=confirm")
    pwd_hash = hashlib.sha256(pwd.encode("utf-8")).hexdigest()
    if pwd_hash != user[3]:
        return redirect("/account/?delete=wrong")
    cur.execute("DELETE FROM tutorial_progress WHERE user_id = ?", (user[0],))
    cur.execute("DELETE FROM users WHERE id = ?", (user[0],))
    response = redirect("/?account=deleted")
    session.delete()
    return response


@app.route("/api/account/forgot_password", methods=["POST"])
@with_session
async def handle_forgot_password(request, session):
    name = request.form.get("name")
    tel = request.form.get("tel")
    new_pwd = request.form.get("new_pwd")
    new_pwd_confirm = request.form.get("new_pwd_confirm")
    if not name or not tel or not new_pwd or not new_pwd_confirm:
        return redirect("/forgot?status=blank")
    if new_pwd != new_pwd_confirm:
        return redirect("/forgot?status=nomatch")
    cur.execute("SELECT id FROM users WHERE tel = ? AND name = ?", (tel, name))
    user = cur.fetchone()
    if not user:
        return redirect("/forgot?status=notfound")
    new_hash = hashlib.sha256(new_pwd.encode("utf-8")).hexdigest()
    cur.execute("UPDATE users SET pass = ? WHERE id = ?", (new_hash, user[0]))
    return redirect("/login?reset=success")


@app.route("/api/support/problem", methods=["POST"])
@with_session
async def handle_support_problem_report(request, session):
    user = get_current_user(session)
    problem_key = request.form.get("problem")
    problem_label = SUPPORT_PROBLEM_LABELS.get(problem_key)
    if not problem_label:
        return _support_api_response(
            request,
            ok=False,
            message="Не удалось определить тип проблемы.",
            fallback_url="/support?mode=problem&sent=0",
        )

    try:
        append_bug_report(
            report_kind="problem",
            report_code=problem_key,
            label=problem_label,
            user=user,
        )
    except OSError:
        return _support_api_response(
            request,
            ok=False,
            message="Не удалось отправить сообщение. Попробуйте снова.",
            fallback_url="/support?mode=problem&sent=0",
        )
    return _support_api_response(
        request,
        ok=True,
        message="Сообщение отправлено разработчикам сайта.",
        fallback_url="/support?mode=problem&sent=1",
    )


@app.route("/api/support/faq_feedback", methods=["POST"])
@with_session
async def handle_support_faq_feedback(request, session):
    user = get_current_user(session)
    faq_key = request.form.get("faq")
    feedback_key = request.form.get("feedback")
    faq_data = SUPPORT_FAQ_DATA.get(faq_key)
    feedback_label = SUPPORT_FEEDBACK_LABELS.get(feedback_key)
    if not faq_data or not feedback_label:
        return _support_api_response(
            request,
            ok=False,
            message="Не удалось обработать ответ по вопросу.",
            fallback_url=f"/support?mode=faq&faq={faq_key or ''}&sent=0",
        )

    try:
        append_bug_report(
            report_kind="faq_feedback",
            report_code=f"{faq_key}:{feedback_key}",
            label=f"{faq_data['question']} / {feedback_label}",
            user=user,
        )
    except OSError:
        return _support_api_response(
            request,
            ok=False,
            message="Не удалось отправить сообщение. Попробуйте снова.",
            fallback_url=f"/support?mode=faq&faq={faq_key}&sent=0",
        )
    return _support_api_response(
        request,
        ok=True,
        message="Сообщение отправлено разработчикам сайта.",
        fallback_url=f"/support?mode=faq&faq={faq_key}&sent=1",
    )


@app.route("/getcookie")
@with_session
async def get_cookie_page(request, session):
    user_data = get_current_user(session)
    if user_data:
        user_name = user_data[2]
        return (
            f"Имя пользователя в этой сессии: <b>{user_name}</b>",
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )
    else:
        return (
            "Cookie не найдены или сессия истекла (перезайдите в аккаунт)",
            404,
            {"Content-Type": "text/html; charset=utf-8"},
        )


@app.route("/logout")
@with_session
async def logout(request, session):
    response = redirect("/")
    session.delete()
    return response


app.run()
