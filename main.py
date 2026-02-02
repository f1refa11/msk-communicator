import microdot.jinja
import os
from microdot import Microdot, send_file, redirect
from microdot.session import Session, with_session
from jinja2 import Environment, PackageLoader, select_autoescape
import hashlib
import bcrypt
import sqlite3
db = sqlite3.connect('database.db', autocommit=True)
cur = db.cursor()

# todo: rate limiting на post запросы

env = Environment(
    loader=PackageLoader("main"),
    autoescape=select_autoescape()
)

page_index = env.get_template("index.tmpl")
page_login = env.get_template("login.tmpl")
page_register = env.get_template("register.tmpl")
page_tutorial = env.get_template("tutorial.tmpl")
page_account = env.get_template("account.tmpl")
page_forgot = env.get_template("forgot.tmpl")
page_tutorial_viewer = env.get_template("tutorial_viewer.tmpl")
TUTORIALS_DIR = os.path.join('templates', 'tutorials')

app = Microdot()

SESSION_SECRET = os.environ.get("SESSION_SECRET", "change-me")
Session(app, secret_key=SESSION_SECRET)

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
        cur.execute('''
            CREATE TABLE users (
                id INTEGER NOT NULL UNIQUE,
                tel TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                pass TEXT NOT NULL,
                admin INTEGER DEFAULT 0,
                avatar TEXT DEFAULT 'avatar-1',
                PRIMARY KEY(id AUTOINCREMENT)
            )
        ''')
    else:
        print("Table 'users' found.")

# Run the check on startup
init_db()

# add missing columns for existing dbs
cur.execute("PRAGMA table_info(users)")
_cols = [row[1] for row in cur.fetchall()]
if "avatar" not in _cols:
    cur.execute("ALTER TABLE users ADD COLUMN avatar TEXT DEFAULT 'avatar-1'")

AVATARS = ["avatar-1", "avatar-2", "avatar-3", "avatar-4", "avatar-5"]

# -- PAGES

# index
@app.route('/')
@with_session
async def index(request, session):
    user = get_current_user(session)
    login_status = ""
    if request.args.get("reg"):
        if request.args.get("reg") == "success":
            login_status = "ты удачно зарегал акк, заходи в меню входа в акк"
        else:
            login_status = "акк не зареган, попробуй ещё раз"
    if request.args.get("login") == "success":
        login_status = "вход успешен"
    return page_index.render(
        test=login_status,
        yes_login=bool(user),
        user_name=user[2] if user else ""
    ), 200, {'Content-Type': 'text/html'}

# login
@app.route('/login')
@with_session
async def index(request, session):
    user = get_current_user(session)
    status = ""
    if request.args.get("reset") == "success":
        status = "пароль обновлен, войдите снова"
    return page_login.render(
        test=status,
        yes_login=bool(user),
        user_name=user[2] if user else ""
    ), 200, {'Content-Type': 'text/html'}

# login
@app.route('/register')
@with_session
async def index(request, session):
    user = get_current_user(session)
    return page_register.render(
        test="test",
        yes_login=bool(user),
        user_name=user[2] if user else ""
    ), 200, {'Content-Type': 'text/html'}

# static
@app.route('/static/<path:path>')
async def static(request, path):
    if '..' in path:
        return 'Not found', 404
    return send_file('static/' + path)


# tutorial
@app.route('/tutorials')
@with_session
async def tutorials_list(request, session):
    user = get_current_user(session)
    
    tutorials = []
    
    # Создаем папку, если нет
    if not os.path.exists(TUTORIALS_DIR):
        try:
            os.makedirs(TUTORIALS_DIR)
        except OSError:
            pass # Игнорируем ошибку, если не удалось создать (например, нет прав)
    else:
        # Ищем папки внутри templates/tutorials
        tutorials = [d for d in os.listdir(TUTORIALS_DIR) if os.path.isdir(os.path.join(TUTORIALS_DIR, d))]
        tutorials.sort()

    return page_tutorial.render(
        tutorials=tutorials,
        yes_login=bool(user),
        user_name=user[2] if user else ""
    ), 200, {'Content-Type': 'text/html'}

# 3. Добавляем новый маршрут для просмотра страницы туториала
@app.route('/tutorials/<tutorial_name>/<int:page_num>')
@with_session
async def tutorial_viewer(request, session, tutorial_name, page_num):
    user = get_current_user(session)
    
    # Путь к папке конкретного туториала
    tutorial_path = os.path.join(TUTORIALS_DIR, tutorial_name)
    
    if not os.path.exists(tutorial_path):
         return "Туториал не найден", 404
    
    # Ищем все файлы .tmpl в папке туториала
    files = [f for f in os.listdir(tutorial_path) if f.endswith('.tmpl')]
    # Сортируем (важно называть файлы 1.tmpl, 2.tmpl или 01.tmpl, чтобы порядок был верным)
    files.sort() 
    
    total_pages = len(files)
    
    if total_pages == 0:
        return "В этом туториале нет страниц", 404

    if page_num < 1 or page_num > total_pages:
        return "Такой страницы не существует", 404
        
    current_file = files[page_num - 1]
    
    # Формируем путь для Jinja (относительно папки templates)
    # Например: "tutorials/taxi/1.tmpl"
    template_name = f"tutorials/{tutorial_name}/{current_file}"
    
    try:
        # 1. Рендерим саму страницу туториала (контент)
        content_template = env.get_template(template_name)
        # Если внутри слайдов нужны переменные (например, user), передайте их сюда
        rendered_content = content_template.render(user=user)
        
        # 2. Рендерим оболочку-вьювер и вставляем туда контент
        return page_tutorial_viewer.render(
            tutorial_name=tutorial_name,
            current_page=page_num,
            total_pages=total_pages,
            content=rendered_content,  # Передаем готовый HTML
            yes_login=bool(user),
            user_name=user[2] if user else ""
        ), 200, {'Content-Type': 'text/html'}
        
    except Exception as e:
        return f"Ошибка при загрузке шаблона: {e}", 500

@app.route('/forgot')
@with_session
async def forgot_password_page(request, session):
    user = get_current_user(session)
    status = request.args.get("status") or ""
    status_map = {
        "blank": "заполните все поля",
        "nomatch": "пароли не совпадают",
        "notfound": "аккаунт не найден",
    }
    return page_forgot.render(
        status=status_map.get(status, ""),
        yes_login=bool(user),
        user_name=user[2] if user else ""
    ), 200, {'Content-Type': 'text/html'}

# account settings
@app.route('/account/')
@with_session
async def account_settings(request, session):
    user = get_current_user(session)
    if not user:
        return redirect('/login')
    if user[5] is None:
        cur.execute("UPDATE users SET avatar = ? WHERE id = ?", ("avatar-1", user[0]))
        user = get_current_user(session)
    return page_account.render(
        yes_login=True,
        user=user,
        avatars=AVATARS,
        user_name=user[2]
    ), 200, {'Content-Type': 'text/html'}

# @app.route('/db/<path:path>')
# async def dbdownload(request, path):
#     if '..' in path:
#         return 'Not found', 404
        
#     return send_file('db/' + path)


@app.route('/assets/<path:path>')
async def logoload(request, path):
    #Я установил в темплейте прям длину и высоту в img
    if '..' in path:
        return 'Not found', 404
    
    return send_file('assets/' + path)

# register route
@app.route('/api/account/register', methods=['POST'])
@with_session
async def handle_reg(request, session):
    # todo: проверить, существует ли уже пользователь

    # fetch form info
    name = request.form.get("name")
    tel = request.form.get("tel")
    pwd = request.form.get("pwd")

    if not name or not tel or not pwd:
        return redirect('/register?error=blank')

    cur.execute("SELECT tel FROM users WHERE tel = ?", (tel,))
    existing_user = cur.fetchone()

    if existing_user:
        return redirect('/register?error=exists')

    # pwd hashs
    hash_object = hashlib.sha256(pwd.encode('utf-8'))
    dpass = hash_object.hexdigest()

    # send db insert
    try:
        cur.execute("INSERT INTO users(tel, name, pass) VALUES (?, ?, ?)", (tel, name, dpass))
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

@app.route('/api/account/login', methods=['POST'])
@with_session
async def handle_login(request, session):
    # 1. Fetch form info
    tel = request.form.get('tel')
    pwd = request.form.get('pwd')

    # 2. Hash the input password (must match the method used in register)
    hash_object = hashlib.sha256(pwd.encode('utf-8'))
    input_hash = hash_object.hexdigest()

    # 3. Check DB for matching Name AND Password Hash
    # Using '?' prevents SQL Injection
    cur.execute("SELECT * FROM users WHERE tel = ? AND pass = ?", (tel, input_hash))
    user = cur.fetchone()

    if user:
        response = redirect('/?login=success')
        session["user_id"] = user[0]
        session.save()
        return response
    else:
        return redirect('/?login=fail')

@app.route('/api/account/update_name', methods=['POST'])
@with_session
async def handle_update_name(request, session):
    user = get_current_user(session)
    if not user:
        return redirect('/login')
    new_name = request.form.get("name")
    if not new_name:
        return redirect('/account/?name=blank')
    cur.execute("UPDATE users SET name = ? WHERE id = ?", (new_name, user[0]))
    return redirect('/account/?name=success')

@app.route('/api/account/update_tel', methods=['POST'])
@with_session
async def handle_update_tel(request, session):
    user = get_current_user(session)
    if not user:
        return redirect('/login')
    new_tel = request.form.get("tel")
    if not new_tel:
        return redirect('/account/?tel=blank')
    cur.execute("SELECT id FROM users WHERE tel = ? AND id != ?", (new_tel, user[0]))
    if cur.fetchone():
        return redirect('/account/?tel=exists')
    cur.execute("UPDATE users SET tel = ? WHERE id = ?", (new_tel, user[0]))
    return redirect('/account/?tel=success')

@app.route('/api/account/update_password', methods=['POST'])
@with_session
async def handle_update_password(request, session):
    user = get_current_user(session)
    if not user:
        return redirect('/login')
    current_pwd = request.form.get("current_pwd")
    new_pwd = request.form.get("new_pwd")
    new_pwd_confirm = request.form.get("new_pwd_confirm")
    if not current_pwd or not new_pwd or not new_pwd_confirm:
        return redirect('/account/?pwd=blank')
    if new_pwd != new_pwd_confirm:
        return redirect('/account/?pwd=nomatch')
    current_hash = hashlib.sha256(current_pwd.encode('utf-8')).hexdigest()
    if current_hash != user[3]:
        return redirect('/account/?pwd=wrong')
    new_hash = hashlib.sha256(new_pwd.encode('utf-8')).hexdigest()
    cur.execute("UPDATE users SET pass = ? WHERE id = ?", (new_hash, user[0]))
    return redirect('/account/?pwd=success')

@app.route('/api/account/update_avatar', methods=['POST'])
@with_session
async def handle_update_avatar(request, session):
    user = get_current_user(session)
    if not user:
        return redirect('/login')
    avatar = request.form.get("avatar")
    if avatar not in AVATARS:
        return redirect('/account/?avatar=invalid')
    cur.execute("UPDATE users SET avatar = ? WHERE id = ?", (avatar, user[0]))
    return redirect('/account/?avatar=success')

@app.route('/api/account/delete', methods=['POST'])
@with_session
async def handle_delete_account(request, session):
    user = get_current_user(session)
    if not user:
        return redirect('/login')
    confirm = request.form.get("confirm_delete")
    pwd = request.form.get("delete_pwd")
    if confirm != "on" or not pwd:
        return redirect('/account/?delete=confirm')
    pwd_hash = hashlib.sha256(pwd.encode('utf-8')).hexdigest()
    if pwd_hash != user[3]:
        return redirect('/account/?delete=wrong')
    cur.execute("DELETE FROM users WHERE id = ?", (user[0],))
    response = redirect('/?account=deleted')
    session.delete()
    return response

@app.route('/api/account/forgot_password', methods=['POST'])
@with_session
async def handle_forgot_password(request, session):
    name = request.form.get("name")
    tel = request.form.get("tel")
    new_pwd = request.form.get("new_pwd")
    new_pwd_confirm = request.form.get("new_pwd_confirm")
    if not name or not tel or not new_pwd or not new_pwd_confirm:
        return redirect('/forgot?status=blank')
    if new_pwd != new_pwd_confirm:
        return redirect('/forgot?status=nomatch')
    cur.execute("SELECT id FROM users WHERE tel = ? AND name = ?", (tel, name))
    user = cur.fetchone()
    if not user:
        return redirect('/forgot?status=notfound')
    new_hash = hashlib.sha256(new_pwd.encode('utf-8')).hexdigest()
    cur.execute("UPDATE users SET pass = ? WHERE id = ?", (new_hash, user[0]))
    return redirect('/login?reset=success')
    
@app.route('/getcookie') 
@with_session
async def get_cookie_page(request, session):
    user_data = get_current_user(session)
    if user_data:
        user_name = user_data[2]
        return f"Имя пользователя в этой сессии: <b>{user_name}</b>", 200, {'Content-Type': 'text/html; charset=utf-8'}
    else:
        return "Cookie не найдены или сессия истекла (перезайдите в аккаунт)", 404, {'Content-Type': 'text/html; charset=utf-8'}



@app.route('/logout')
@with_session
async def logout(request, session):
    response = redirect('/')
    session.delete()
    return response

app.run()
