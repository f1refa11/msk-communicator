import microdot.jinja
import os
from microdot import Microdot, Response, send_file, redirect
from microdot.session import Session, with_session
from jinja2 import Environment, PackageLoader, select_autoescape
import base64
import hashlib
import bcrypt
import json
import sqlite3
import mimetypes
import jwt
from urllib.parse import unquote, urlencode
from datetime import datetime, timezone

db = sqlite3.connect("database.db", autocommit=True)
cur = db.cursor()

# todo: rate limiting на post запросы

env = Environment(loader=PackageLoader("main"), autoescape=select_autoescape())

page_index = env.get_template("index.tmpl")
page_login = env.get_template("login.tmpl")
page_register = env.get_template("register.tmpl")
page_tutorial = env.get_template("tutorial.tmpl")
page_tutorial_course = env.get_template("tutorial_course.tmpl")
page_account = env.get_template("account.tmpl")
page_forgot = env.get_template("forgot.tmpl")
page_tutorial_viewer = env.get_template("tutorial_viewer.tmpl")
page_support = env.get_template("support.tmpl")
TUTORIALS_DIR = os.path.join("templates", "tutorials")
TUTORIAL_PAGE_EXTENSIONS = (".tmpl", ".html", ".htm")
BUGREPORTS_FILE = os.path.join(os.path.dirname(__file__), "bugreports.json")
PROGRESS_COOKIE_NAME = "guest_tutorial_progress"
PROGRESS_COOKIE_MAX_AGE = 60 * 60 * 24 * 365
DIFFICULTY_LEVELS = ("basic", "advanced")
DIFFICULTY_LABELS = {
    "basic": "Базовый",
    "advanced": "Расширенный",
}
TUTORIAL_SLUG_RENAMES = {
    "rustoredowload": "rustoredownload",
}
DEFAULT_COURSE_SLUG = "smartphone-basics"
COURSE_DEFINITIONS = [
    {
        "slug": "smartphone-basics",
        "title": "Основы Смартфона",
        "description": "Первые шаги со смартфоном: базовые настройки, кнопки и установка приложений.",
        "basic_description": "Простые и понятные модули для ежедневного использования смартфона.",
        "advanced_description": "Больше практики и дополнительных сценариев для уверенного использования.",
    },
    {
        "slug": "max-messenger",
        "title": "Работа с мессенджером MAX",
        "description": "Общение в MAX: личные и групповые чаты, сообщения, фото, эмодзи и стикеры.",
        "basic_description": "Базовые модули: как написать сообщение, отправить фото и создать чат.",
        "advanced_description": "Расширенные сценарии общения, включая групповые функции и мультимедиа.",
    },
    {
        "slug": "online-shopping",
        "title": "Онлайн-покупки",
        "description": "Пошаговые тренировки покупок в интернете: поиск товара, корзина и доставка.",
        "basic_description": "Учимся находить нужный товар и добавлять его в корзину.",
        "advanced_description": "Полный путь до завершения заказа: доставка, адрес, оплата, подтверждение.",
    },
    {
        "slug": "gosuslugi",
        "title": "Госуслуги",
        "description": "Курс по работе с государственными онлайн-сервисами и электронными заявлениями.",
        "basic_description": "Основные действия в сервисе: вход, поиск услуги, просмотр информации.",
        "advanced_description": "Сложные сценарии: оформление заявлений и проверка статусов заявок.",
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
        if level not in DIFFICULTY_LEVELS:
            level = "basic"

        order = meta.get("order")
        try:
            order = int(str(order).strip())
        except (TypeError, ValueError):
            order = 1000

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
                "order": order,
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


def _tutorial_module_sort_key(tutorial):
    """Stable sorting for tutorial cards inside courses."""
    return (
        int(tutorial.get("order", 1000)),
        str(tutorial.get("title", "")).casefold(),
        str(tutorial.get("slug", "")),
    )


def _dedupe_tutorials(tutorials):
    """Remove duplicate tutorial slugs while preserving order."""
    seen = set()
    unique = []
    for tutorial in tutorials:
        slug = tutorial.get("slug")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        unique.append(tutorial)
    return unique


def normalize_difficulty(level: str):
    """Normalize difficulty level to basic/advanced."""
    normalized = str(level or "").strip().lower()
    if normalized not in DIFFICULTY_LEVELS:
        return "basic"
    return normalized


def build_course_catalog(include_hidden=False):
    """Build course list with grouped tutorials and counts."""
    tutorials = load_tutorials(include_hidden=include_hidden)
    courses = []
    course_map = {}

    for definition in COURSE_DEFINITIONS:
        course_data = {
            "slug": definition["slug"],
            "title": definition["title"],
            "description": definition["description"],
            "basic_description": definition.get("basic_description", ""),
            "advanced_description": definition.get("advanced_description", ""),
            "basic_modules": [],
            "advanced_only_modules": [],
            "advanced_modules": [],
            "module_count": 0,
            "basic_count": 0,
            "advanced_count": 0,
        }
        courses.append(course_data)
        course_map[course_data["slug"]] = course_data

    for tutorial in tutorials:
        course_slug = str(tutorial.get("course") or DEFAULT_COURSE_SLUG).strip()
        course_data = course_map.get(course_slug)
        if not course_data:
            continue

        if tutorial.get("level") == "advanced":
            course_data["advanced_only_modules"].append(tutorial)
        else:
            course_data["basic_modules"].append(tutorial)

    for course_data in courses:
        course_data["basic_modules"].sort(key=_tutorial_module_sort_key)
        course_data["advanced_only_modules"].sort(key=_tutorial_module_sort_key)

        combined = _dedupe_tutorials(
            course_data["basic_modules"] + course_data["advanced_only_modules"]
        )
        course_data["advanced_modules"] = combined
        course_data["module_count"] = len(combined)
        course_data["basic_count"] = len(course_data["basic_modules"])
        course_data["advanced_count"] = len(course_data["advanced_modules"])

    return courses


def get_course_track_modules(course_data, difficulty):
    """Return linear module list for selected difficulty."""
    if normalize_difficulty(difficulty) == "advanced":
        return list(course_data.get("advanced_modules") or [])
    return list(course_data.get("basic_modules") or [])


def get_user_completed_tutorial_slugs(user_id: int):
    """Load completed tutorial slugs from DB for logged-in user."""
    if not user_id:
        return set()
    cur.execute(
        "SELECT tutorial_slug FROM tutorial_progress WHERE user_id = ?",
        (user_id,),
    )
    return {
        normalize_tutorial_slug(row[0])
        for row in cur.fetchall()
        if row and row[0]
    }


def _normalize_progress_cookie_items(values):
    """Convert raw cookie payload into a normalized slug set."""
    if not isinstance(values, list):
        return set()
    normalized = set()
    for raw_value in values[:300]:
        slug = normalize_tutorial_slug(str(raw_value))
        if slug:
            normalized.add(slug)
    return normalized


def get_guest_completed_tutorial_slugs(request):
    """Load completed tutorial slugs from guest cookie."""
    raw_value = (request.cookies or {}).get(PROGRESS_COOKIE_NAME)
    if not raw_value:
        return set()
    try:
        parsed = json.loads(raw_value)
    except (TypeError, ValueError):
        return set()
    return _normalize_progress_cookie_items(parsed)


def encode_guest_completed_tutorial_slugs(completed_slugs):
    """Serialize guest tutorial progress for cookie storage."""
    return json.dumps(sorted(completed_slugs), ensure_ascii=False, separators=(",", ":"))


def get_completed_tutorial_slugs(request, user):
    """Return completed tutorial slugs from DB or cookies."""
    if user:
        return get_user_completed_tutorial_slugs(user[0])
    return get_guest_completed_tutorial_slugs(request)


def annotate_track_modules(modules, completed_slugs):
    """Mark each module as completed/current/locked for linear flow."""
    completed_set = set(completed_slugs)
    first_pending_idx = None
    for idx, module in enumerate(modules):
        if module.get("slug") not in completed_set:
            first_pending_idx = idx
            break

    locked_gate_title = (
        modules[first_pending_idx]["title"]
        if first_pending_idx is not None and first_pending_idx < len(modules)
        else ""
    )

    annotated = []
    for idx, module in enumerate(modules):
        slug = module.get("slug")
        is_completed = slug in completed_set
        is_current = (
            first_pending_idx is not None
            and idx == first_pending_idx
            and not is_completed
        )
        is_unlocked = is_completed or is_current or first_pending_idx is None

        status = "locked"
        if is_completed:
            status = "completed"
        elif is_current:
            status = "current"

        locked_reason = ""
        if status == "locked" and locked_gate_title:
            locked_reason = f"Сначала завершите «{locked_gate_title}»."

        annotated.append(
            {
                **module,
                "sequence_number": idx + 1,
                "status": status,
                "completed": is_completed,
                "unlocked": is_unlocked,
                "locked_reason": locked_reason,
            }
        )

    return annotated


def build_viewer_query(course_slug="", difficulty=""):
    """Build query-string for preserving course context in viewer."""
    params = {}
    if course_slug:
        params["course"] = course_slug
    if difficulty:
        normalized_difficulty = normalize_difficulty(difficulty)
        if normalized_difficulty in DIFFICULTY_LEVELS:
            params["difficulty"] = normalized_difficulty
    if not params:
        return ""
    return "?" + urlencode(params)


def format_module_count(count: int):
    """Format module count in Russian (модуль/модуля/модулей)."""
    value = int(count or 0)
    n10 = value % 10
    n100 = value % 100
    if n10 == 1 and n100 != 11:
        suffix = "модуль"
    elif 2 <= n10 <= 4 and not (12 <= n100 <= 14):
        suffix = "модуля"
    else:
        suffix = "модулей"
    return f"{value} {suffix}"


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
                PRIMARY KEY(id AUTOINCREMENT)
            )
        """)
    else:
        print("Table 'users' found.")


# Run the check on startup
init_db()

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
    decoded_path = unquote(path)
    if ".." in decoded_path or decoded_path.startswith("/") or decoded_path.startswith("\\"):
        return "Not found", 404
    return send_file("static/" + decoded_path)


@app.route("/tutorials-assets/<tutorial_name>/<path:path>")
async def tutorial_assets(request, tutorial_name, path):
    """Serve per-tutorial static assets (css, images) located next to templates."""
    decoded_path = unquote(path)
    if (
        ".." in decoded_path
        or decoded_path.startswith("/")
        or decoded_path.startswith("\\")
    ):
        return "Not found", 404
    resolved_tutorial_name = resolve_tutorial_directory(tutorial_name)
    if not resolved_tutorial_name:
        return "Not found", 404
    asset_path = os.path.join(TUTORIALS_DIR, resolved_tutorial_name, decoded_path)
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
    courses = build_course_catalog()
    for course in courses:
        course["module_count_label"] = format_module_count(course["module_count"])
        course["basic_count_label"] = format_module_count(course["basic_count"])
        course["advanced_count_label"] = format_module_count(course["advanced_count"])
        course["basic_url"] = f"/tutorials/course/{course['slug']}/basic"
        course["advanced_url"] = f"/tutorials/course/{course['slug']}/advanced"

    return (
        page_tutorial.render(
            courses=courses,
            has_any=any(course["module_count"] > 0 for course in courses),
            yes_login=bool(user),
            user_name=user[2] if user else "",
        ),
        200,
        {"Content-Type": "text/html"},
    )


@app.route("/tutorials/course/<course_slug>")
@with_session
async def tutorial_course_default(request, session, course_slug):
    normalized_course_slug = str(course_slug or "").strip().lower()
    return redirect(f"/tutorials/course/{normalized_course_slug}/basic")


@app.route("/tutorials/course")
@app.route("/tutorials/course/")
@with_session
async def tutorial_course_root(request, session):
    return redirect("/tutorials")


@app.route("/tutorials/course/<course_slug>/<difficulty>")
@with_session
async def tutorial_course_page(request, session, course_slug, difficulty):
    user = get_current_user(session)
    normalized_course_slug = str(course_slug or "").strip().lower()
    raw_difficulty = str(difficulty or "").strip().lower()
    normalized_difficulty = normalize_difficulty(difficulty)

    if raw_difficulty != normalized_difficulty:
        return redirect(
            f"/tutorials/course/{normalized_course_slug}/{normalized_difficulty}"
        )

    courses = build_course_catalog()
    course_map = {course["slug"]: course for course in courses}
    course = course_map.get(normalized_course_slug)
    if not course:
        return "Курс не найден", 404

    completed_slugs = get_completed_tutorial_slugs(request, user)
    track_modules = get_course_track_modules(course, normalized_difficulty)
    modules = annotate_track_modules(track_modules, completed_slugs)

    viewer_query = build_viewer_query(course["slug"], normalized_difficulty)
    for module in modules:
        module["start_url"] = f"/tutorials/{module['slug']}/1{viewer_query}"

    completed_count = sum(1 for module in modules if module["completed"])
    is_advanced = normalized_difficulty == "advanced"
    difficulty_note = (
        "Расширенный режим включает все базовые модули и дополнительные задания."
        if is_advanced
        else "В базовом режиме доступна основная программа курса."
    )

    return (
        page_tutorial_course.render(
            course=course,
            modules=modules,
            difficulty=normalized_difficulty,
            difficulty_label=DIFFICULTY_LABELS[normalized_difficulty],
            difficulty_note=difficulty_note,
            module_count_label=format_module_count(len(modules)),
            completed_count_label=format_module_count(completed_count),
            basic_count_label=format_module_count(course["basic_count"]),
            advanced_count_label=format_module_count(course["advanced_count"]),
            basic_href=f"/tutorials/course/{course['slug']}/basic",
            advanced_href=f"/tutorials/course/{course['slug']}/advanced",
            locked_notice=(request.args.get("locked") == "1"),
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
    query = {}
    raw_course = str(request.args.get("course") or "").strip().lower()
    if raw_course:
        query["course"] = raw_course

    raw_difficulty = request.args.get("difficulty")
    if raw_difficulty:
        query["difficulty"] = normalize_difficulty(raw_difficulty)

    query_suffix = ("?" + urlencode(query)) if query else ""
    return redirect(f"/tutorials/{canonical_slug}/1{query_suffix}")


# 3. Добавляем новый маршрут для просмотра страницы туториала
@app.route("/tutorials/<tutorial_name>/<int:page_num>")
@with_session
async def tutorial_viewer(request, session, tutorial_name, page_num):
    user = get_current_user(session)
    completed_slugs = get_completed_tutorial_slugs(request, user)

    raw_requested_course = str(request.args.get("course") or "").strip().lower()
    raw_requested_difficulty = str(request.args.get("difficulty") or "").strip().lower()
    requested_difficulty = (
        normalize_difficulty(raw_requested_difficulty)
        if raw_requested_difficulty
        else ""
    )

    canonical_slug = normalize_tutorial_slug(tutorial_name)
    if tutorial_name != canonical_slug:
        redirect_query = build_viewer_query(raw_requested_course, requested_difficulty)
        return redirect(f"/tutorials/{canonical_slug}/{page_num}{redirect_query}")

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

    course_catalog = build_course_catalog()
    course_map = {course["slug"]: course for course in course_catalog}

    course_slug = str(tutorial_meta.get("course") or "").strip().lower() if tutorial_meta else ""
    if raw_requested_course and raw_requested_course == course_slug:
        course_slug = raw_requested_course

    course_data = course_map.get(course_slug)
    viewer_difficulty = requested_difficulty if requested_difficulty in DIFFICULTY_LEVELS else "basic"
    if tutorial_meta and tutorial_meta.get("level") == "advanced":
        viewer_difficulty = "advanced"

    if course_data and tutorial_meta:
        track_modules = get_course_track_modules(course_data, viewer_difficulty)
        track_states = annotate_track_modules(track_modules, completed_slugs)
        state_by_slug = {module["slug"]: module for module in track_states}
        current_state = state_by_slug.get(canonical_slug)
        if current_state and not current_state["unlocked"]:
            return redirect(
                f"/tutorials/course/{course_slug}/{viewer_difficulty}?locked=1"
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

    current_file = files[page_num - 1]
    should_update_guest_cookie = False
    should_mark_completed = (
        page_num == total_pages or viewer_navigation == "style-switch"
    )
    if should_mark_completed:
        if user:
            mark_tutorial_completed(user[0], canonical_slug)
            completed_slugs.add(canonical_slug)
        elif canonical_slug not in completed_slugs:
            completed_slugs.add(canonical_slug)
            should_update_guest_cookie = True

    # Формируем путь для Jinja (относительно папки templates)
    # Например: "tutorials/taxi/1.tmpl" или "tutorials/taxi/1.html"
    template_name = f"tutorials/{resolved_tutorial_name}/{current_file}"

    back_href = "/tutorials"
    viewer_query = ""
    if course_data:
        back_href = f"/tutorials/course/{course_data['slug']}/{viewer_difficulty}"
        viewer_query = build_viewer_query(course_data["slug"], viewer_difficulty)

    tutorial_title = canonical_slug
    tutorial_level = "basic"
    if tutorial_meta:
        tutorial_title = str(tutorial_meta.get("title") or canonical_slug)
        tutorial_level = str(tutorial_meta.get("level") or "basic")

    try:
        # 1. Рендерим саму страницу туториала (контент)
        content_template = env.get_template(template_name)
        # Если внутри слайдов нужны переменные (например, user), передайте их сюда
        rendered_content = content_template.render(user=user)

        # 2. Рендерим оболочку-вьювер и вставляем туда контент
        rendered_page = page_tutorial_viewer.render(
            tutorial_name=canonical_slug,
            tutorial_title=tutorial_title,
            tutorial_level=tutorial_level,
            viewer_navigation=viewer_navigation,
            style_options=style_options,
            current_page=page_num,
            total_pages=total_pages,
            content=rendered_content,
            back_href=back_href,
            viewer_query=viewer_query,
            yes_login=bool(user),
            user_name=user[2] if user else "",
        )

        response = Response(
            rendered_page,
            headers={"Content-Type": "text/html"},
        )
        if should_update_guest_cookie:
            response.set_cookie(
                PROGRESS_COOKIE_NAME,
                encode_guest_completed_tutorial_slugs(completed_slugs),
                path="/",
                max_age=PROGRESS_COOKIE_MAX_AGE,
            )
        return response

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
    return (
        page_account.render(
            yes_login=True,
            user=user,
            user_name=user[2],
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
    decoded_path = unquote(path)
    if ".." in decoded_path or decoded_path.startswith("/") or decoded_path.startswith("\\"):
        return "Not found", 404

    return send_file("assets/" + decoded_path)


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
