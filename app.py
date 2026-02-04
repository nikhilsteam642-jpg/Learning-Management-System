import os, random, string
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, session
from werkzeug.utils import secure_filename

app = Flask(__name__)

# ---------------- CONFIG ----------------
app.secret_key = os.environ.get("SECRET_KEY", "fallback_secret")

DATABASE_URL = os.environ.get("DATABASE_URL")

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ---------------- DB ----------------
def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def generate_class_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


# ---------------- CREATE TABLES ----------------
def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS classes(
        id SERIAL PRIMARY KEY,
        class_name TEXT,
        class_code TEXT UNIQUE,
        admin_id INTEGER REFERENCES users(id),
        status TEXT DEFAULT 'running'
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS class_members(
        id SERIAL PRIMARY KEY,
        class_id INTEGER,
        user_id INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS join_requests(
        id SERIAL PRIMARY KEY,
        class_id INTEGER,
        student_id INTEGER,
        status TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS quizzes(
        id SERIAL PRIMARY KEY,
        class_id INTEGER,
        title TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS questions(
        id SERIAL PRIMARY KEY,
        quiz_id INTEGER,
        question TEXT,
        option1 TEXT,
        option2 TEXT,
        option3 TEXT,
        option4 TEXT,
        answer TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS submissions(
        id SERIAL PRIMARY KEY,
        quiz_id INTEGER,
        user_id INTEGER,
        score INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS contents(
        id SERIAL PRIMARY KEY,
        class_id INTEGER,
        title TEXT,
        filename TEXT,
        filetype TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS videos(
        id SERIAL PRIMARY KEY,
        class_id INTEGER,
        title TEXT,
        filename TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS content_progress(
        id SERIAL PRIMARY KEY,
        user_id INTEGER,
        content_id INTEGER
    )
    """)

    conn.commit()
    conn.close()

init_db()


# ---------------- LOGIN ----------------
@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=%s AND password=%s", (email,password))
        user = cur.fetchone()
        conn.close()

        if user:
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            return redirect("/dashboard")

        return "Invalid login"

    return render_template("index.html")


# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users(name,email,password,role)
            VALUES(%s,%s,%s,%s)
        """, (
            request.form["name"],
            request.form["email"],
            request.form["password"],
            request.form["role"]
        ))
        conn.commit()
        conn.close()
        return redirect("/")
    return render_template("register.html")


# ---------------- DASHBOARD ----------------
@app.route("/dashboard", methods=["GET","POST"])
def dashboard():
    if "user_id" not in session:
        return redirect("/")

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST" and session["role"] == "teacher":
        code = generate_class_code()
        cur.execute("""
            INSERT INTO classes(class_name,class_code,admin_id,status)
            VALUES(%s,%s,%s,'running') RETURNING id
        """,(request.form["class_name"],code,session["user_id"]))
        class_id = cur.fetchone()["id"]

        cur.execute("INSERT INTO class_members(class_id,user_id) VALUES(%s,%s)",
                    (class_id, session["user_id"]))
        conn.commit()

    cur.execute("""
        SELECT classes.id, classes.class_name, classes.class_code
        FROM classes
        JOIN class_members ON classes.id = class_members.class_id
        WHERE class_members.user_id=%s
    """,(session["user_id"],))
    classes = cur.fetchall()

    conn.close()

    return render_template("dashboard.html",
        classes=classes,
        name=session["name"],
        role=session["role"]
    )


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------------- UPLOAD VIDEO ----------------
@app.route("/upload_video/<int:class_id>", methods=["POST"])
def upload_video(class_id):
    if "user_id" not in session:
        return redirect("/")

    conn = get_db()
    cur = conn.cursor()

    title = request.form["title"]
    video = request.files["video"]

    filename = secure_filename(video.filename)
    video.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    cur.execute("""
        INSERT INTO videos(class_id,title,filename)
        VALUES (%s,%s,%s)
    """,(class_id,title,filename))

    conn.commit()
    conn.close()
    return redirect("/dashboard")


# ---------------- UPLOAD CONTENT ----------------
@app.route("/upload_content/<int:class_id>", methods=["POST"])
def upload_content(class_id):
    if "user_id" not in session:
        return redirect("/")

    conn = get_db()
    cur = conn.cursor()

    title = request.form["title"]
    file = request.files["file"]

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    filetype = filename.split(".")[-1].lower()

    cur.execute("""
        INSERT INTO contents(class_id,title,filename,filetype)
        VALUES (%s,%s,%s,%s)
    """,(class_id,title,filename,filetype))

    conn.commit()
    conn.close()
    return redirect("/dashboard")


# ---------------- MAIN ----------------
if __name__=="__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port)
