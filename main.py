from microdot import Microdot, send_file, redirect
from jinja2 import Environment, PackageLoader, select_autoescape
import hashlib
import bcrypt
import sqlite3
db = sqlite3.connect('database.db', autocommit=True)
cur = db.cursor()
import uuid

# todo: rate limiting на post запросы

env = Environment(
    loader=PackageLoader("main"),
    autoescape=select_autoescape()
)

page_index = env.get_template("index.tmpl")
page_login = env.get_template("login.tmpl")
page_register = env.get_template("register.tmpl")
page_tutorial = env.get_template("tutorial.tmpl")

app = Microdot()

SESSIONS = {}

def create_session(username):
    # Generate a random unique string
    token = str(uuid.uuid4())
    SESSIONS[token] = username
    return token

def get_current_user(request):
    # Retrieve the cookie
    token = request.cookies.get('session_id')
    # Look up the token in our dictionary
    if token and token in SESSIONS:
        return SESSIONS[token]
    return None

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
                PRIMARY KEY(id AUTOINCREMENT)
            )
        ''')
    else:
        print("Table 'users' found.")

# Run the check on startup
init_db()

# -- PAGES

# index
@app.route('/')
async def index(request):
    login_status = ""
    if request.args.get("reg"):
        if request.args.get("reg") == "success":
            login_status = "ты удачно зарегал акк, заходи в меню входа в акк"
        else:
            login_status = "акк не зареган, попробуй ещё раз"
    return page_index.render(test=login_status), 200, {'Content-Type': 'text/html'}

# login
@app.route('/login')
async def index(request):
    return page_login.render(test="test"), 200, {'Content-Type': 'text/html'}

# login
@app.route('/register')
async def index(request):
    return page_register.render(test="test"), 200, {'Content-Type': 'text/html'}

# static
@app.route('/static/<path:path>')
async def static(request, path):
    if '..' in path:
        return 'Not found', 404
    return send_file('static/' + path)


# tutorial
@app.route('/tutorials')
async def index(request):
    return page_tutorial.render(test="test"), 200, {'Content-Type': 'text/html'}


# @app.route('/db/<path:path>')
# async def dbdownload(request, path):
#     if '..' in path:
#         return 'Not found', 404
        
#     return send_file('db/' + path)

# register route
@app.route('/api/account/register', methods=['POST'])
async def handle_reg(request):
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
async def handle_login(request):
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
        token = create_session(user)
        response = redirect('/?login=success')
        
        # 3. Set the cookie (HttpOnly helps security)
        # response.set_cookie('session_id', token, http_only=True, max_age=3600)
        response.set_cookie('session_id', token, http_only=True, max_age=3600, path='/')
        return response
    else:
        return redirect('/?login=fail')
    
@app.route('/getcookie') 
async def get_cookie_page(request):
    
    token_value = request.cookies.get('session_id')
    if token_value and token_value in SESSIONS:
        user_data = SESSIONS[token_value]
        user_name = user_data[2]
        loged = True
        return f"Имя пользователя в этой сессии: <b>{user_name}</b>", 200, {'Content-Type': 'text/html; charset=utf-8'}
    else:
        loged = False
        return "Cookie не найдены или сессия истекла (перезайдите в аккаунт)", 404, {'Content-Type': 'text/html; charset=utf-8'}



@app.route('/logout')
async def logout(request):
    token = request.cookies.get('session_id')
    if token and token in SESSIONS:
        del SESSIONS[token]
    response = redirect('/')
    response.delete_cookie('session_id', path='/')
    return response

app.run()