# ---------------- DATABASE (POSTGRESQL) ----------------
import psycopg2
from psycopg2.extras import RealDictCursor
def get_db():
    # Use your specific Neon Connection URL here
    DATABASE_URL = "postgresql://nikhilgit:qexVCyfv0wlHPndqwdbheBw8EnWw68Ri@dpg-d612jqkoud1c738540hg-a/lms_db_m89x"
    conn = psycopg2.connect(DATABASE_URL)
    # This makes the results behave like dictionaries
    return conn
def get_cursor(conn):

    return conn.cursor(cursor_factory=RealDictCursor)
def generate_class_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
# ---------------- IMPORTS ----------------
import os
import random, string, sqlite3
from flask import Flask, render_template, request, redirect, session, url_for, send_from_directory
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import datetime
from flask import send_file
import io
# ---------------- APP INIT ----------------
app = Flask(__name__)
app.secret_key = "lms_secret_key"
# ---------------- UPLOAD CONFIG ----------------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
# ---------------- DATABASE ----------------
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn
def generate_class_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
# ---------------- CREATE TABLES ----------------
with get_db() as db:
    db.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT
    )""")

    db.execute("""
    CREATE TABLE IF NOT EXISTS join_requests(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER,
    student_id INTEGER,
    status TEXT
    )
""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS classes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_name TEXT,
        class_code TEXT UNIQUE,
        admin_id INTEGER
    )""")
    db.execute("""
CREATE TABLE IF NOT EXISTS content_progress(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER,
    user_id INTEGER,
    status TEXT
)
""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS class_members(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER,
        user_id INTEGER
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS quizzes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER,
        title TEXT
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS questions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_id INTEGER,
        question TEXT,
        option1 TEXT,
        option2 TEXT,
        option3 TEXT,
        option4 TEXT,
        answer TEXT
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS submissions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_id INTEGER,
        user_id INTEGER,
        score INTEGER
    )""")
    db.execute("""
CREATE TABLE IF NOT EXISTS videos(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER,
    title TEXT,
    filename TEXT
)
""")

    db.execute("""
    CREATE TABLE IF NOT EXISTS contents(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER,
        title TEXT,
        filename TEXT,
        filetype TEXT
    )
    """)

# ---------------- ANALYSIS PAGE ----------------
@app.route("/analysis")
def analysis():

    if "user_id" not in session:
        return redirect("/")



    db = get_db()
    user_id = session["user_id"]
    role = session["role"]

    if role == "teacher":
        quizzes = db.execute("""
            SELECT quizzes.id, quizzes.title, classes.class_name
            FROM quizzes
            JOIN classes ON quizzes.class_id = classes.id
            WHERE classes.admin_id=?
        """, (user_id,)).fetchall()

    else:
        quizzes = db.execute("""
            SELECT quizzes.id, quizzes.title, classes.class_name
            FROM submissions
            JOIN quizzes ON submissions.quiz_id = quizzes.id
            JOIN classes ON quizzes.class_id = classes.id
            WHERE submissions.user_id=?
        """, (user_id,)).fetchall()
        
    quizzes_list = [{"id": q[0], "title": q[1], "class_name": q[2]} for q in quizzes]
    return render_template("analysis.html", quizzes=quizzes_list, role=role)
# ---------------- QUIZ STATS PAGE ----------------

@app.route("/quiz_stats/<int:quiz_id>")

def quiz_stats(quiz_id):

    if "user_id" not in session:

        return redirect("/")



    db = get_db()

    quiz = db.execute("""

        SELECT quizzes.id, quizzes.title, classes.class_name

        FROM quizzes

        JOIN classes ON quizzes.class_id = classes.id

        WHERE quizzes.id = ?

    """, (quiz_id,)).fetchone()

    if not quiz:

        return "Quiz not found"



    # Get the current student's score for this quiz

    user_id = session["user_id"]

    submission = db.execute("""

        SELECT score FROM submissions WHERE quiz_id = ? AND user_id = ?

    """, (quiz_id, user_id)).fetchone()

    my_score = submission[0] if submission else ""



    return render_template("quiz_stats.html", quiz=quiz, my_score=my_score)

# ---------------- LOGIN ----------------

@app.route("/", methods=["GET","POST"])

def login():

    if request.method == "POST":

        email = request.form["email"]

        password = request.form["password"]



        db = get_db()

        user = db.execute(

            "SELECT * FROM users WHERE email=? AND password=?",

            (email,password)

        ).fetchone()



        if user:

            session["user_id"] = user["id"]

            session["name"] = user["name"]

            session["role"] = user["role"]   # ⭐ important

            return redirect("/dashboard")

        else:

            return "Invalid login"



    return render_template("index.html")

# ---------------- REGISTER ----------------

@app.route("/register", methods=["GET","POST"])

def register():

    if request.method == "POST":

        name = request.form["name"]

        email = request.form["email"]

        password = request.form["password"]

        role = request.form["role"]



        db = get_db()

        db.execute(

            "INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",

            (name,email,password,role)

        )

        db.commit()

        return redirect("/")



    return render_template("register.html")

# ---------------- DASHBOARD ----------------

@app.route("/dashboard", methods=["GET","POST"])

def dashboard():

    if "user_id" not in session:

        return redirect("/")



    db = get_db()



    # ONLY TEACHER CAN CREATE CLASS

    if request.method == "POST":

        if session["role"] != "teacher":

            return "Access Denied"



        class_name = request.form["class_name"]

        code = generate_class_code()

        admin_id = session["user_id"]



        db.execute(

    "INSERT INTO classes(class_name,class_code,admin_id,status) VALUES(?,?,?,?)",

    (class_name, code, admin_id, "running")

)
        db.commit()

        class_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        db.execute(

            "INSERT INTO class_members(class_id,user_id) VALUES(?,?)",

            (class_id,admin_id)

        )

        db.commit()

    if session["role"] == "student":

        all_classes = db.execute("""

        SELECT classes.id, classes.class_name, users.name AS teacher_name

        FROM classes

        JOIN users ON classes.admin_id = users.id

        WHERE classes.id NOT IN (

            SELECT class_id FROM class_members WHERE user_id=?

        )

    """, (session["user_id"],)).fetchall()

    else:

        all_classes = []



    classes = db.execute("""

        SELECT classes.id, classes.class_name, classes.class_code

        FROM classes

        JOIN class_members ON classes.id = class_members.class_id

        WHERE class_members.user_id=?

    """,(session["user_id"],)).fetchall()



    return render_template("dashboard.html",

        classes=classes,

        all_classes=all_classes,

        name=session["name"],

        role=session["role"]

)

# ---------------- JOIN CLASS ----------------

@app.route("/join_class", methods=["POST"])

def join_class():

    if "user_id" not in session:

        return redirect("/")



    code = request.form["class_code"]

    user_id = session["user_id"]



    db = get_db()

    class_data = db.execute(

        "SELECT * FROM classes WHERE class_code=?",(code,)

    ).fetchone()



    if not class_data:

        return "Invalid class code"



    exists = db.execute("""

        SELECT * FROM class_members WHERE class_id=? AND user_id=?

    """,(class_data["id"],user_id)).fetchone()

    if not exists:

        db.execute(

            "INSERT INTO class_members(class_id,user_id) VALUES(?,?)",

            (class_data["id"], user_id)

        )

        db.commit()



    return redirect("/dashboard")

# ---------------- CLASS PAGE ----------------

@app.route("/class/<int:class_id>")

def class_page(class_id):

    if "user_id" not in session:

        return redirect("/")

    db = get_db()

    class_data = db.execute(

        "SELECT * FROM classes WHERE id=?", (class_id,)

    ).fetchone()

    quizzes = db.execute(
        "SELECT * FROM quizzes WHERE class_id=?", (class_id,)
    ).fetchall()

    members = db.execute("""
    SELECT users.id, users.name, users.role
    FROM users
    JOIN class_members
    ON users.id = class_members.user_id
    WHERE class_members.class_id=?
""",(class_id,)).fetchall()
    
    videos = db.execute(
    "SELECT * FROM videos WHERE class_id=?",
    (class_id,)).fetchall()
    
    contents = db.execute(

    "SELECT * FROM contents WHERE class_id=?", (class_id,)).fetchall()

    attempted = db.execute("""

        SELECT quiz_id FROM submissions WHERE user_id=?

    """, (session["user_id"],)).fetchall()
    attempted_ids = [row["quiz_id"] for row in attempted]
    is_admin = class_data["admin_id"] == session["user_id"]
    quiz_completion = {}

    if is_admin:

        for q in quizzes:

            students = db.execute("""

                SELECT users.name FROM submissions

                JOIN users ON submissions.user_id = users.id

                WHERE submissions.quiz_id=?

            """, (q["id"],)).fetchall()

            quiz_completion[q["id"]] = [s["name"] for s in students]



    return render_template(

        "class.html",

        class_data=class_data,

        quizzes=quizzes,

        members=members,

        is_admin=is_admin,

        attempted_ids=attempted_ids,

        videos=videos,

        contents=contents,

        quiz_completion=quiz_completion

    )


@app.route("/request_join/<int:class_id>", methods=["POST"])

def request_join(class_id):

    if "user_id" not in session:

        return redirect("/")



    db = get_db()

    student_id = session["user_id"]



    existing = db.execute("""

        SELECT * FROM join_requests

        WHERE class_id=? AND student_id=?

    """,(class_id, student_id)).fetchone()

    if not existing:

        db.execute("""

            INSERT INTO join_requests(class_id, student_id, status)

            VALUES(?,?,?)

        """,(class_id, student_id, "pending"))

        db.commit()
    return redirect("/dashboard")

@app.route("/requests")

def requests():

    if "user_id" not in session or session["role"]!="teacher":

        return redirect("/")



    db = get_db()

    teacher_id = session["user_id"]

    requests = db.execute("""

        SELECT join_requests.id, users.name, classes.class_name, classes.id as class_id, users.id as student_id

        FROM join_requests

        JOIN users ON join_requests.student_id = users.id

        JOIN classes ON join_requests.class_id = classes.id

        WHERE classes.admin_id=? AND join_requests.status='pending'

    """,(teacher_id,)).fetchall()



    return render_template("requests.html", requests=requests)

@app.route("/browse_classes")

def browse_classes():

    if "user_id" not in session:

        return redirect("/")



    if session["role"] != "student":

        return redirect("/dashboard")



    db = get_db()

    user_id = session["user_id"]



    all_classes = db.execute("""

        SELECT classes.id, classes.class_name, users.name AS teacher_name

        FROM classes

        JOIN users ON classes.admin_id = users.id

        WHERE classes.id NOT IN (

            SELECT class_id FROM class_members WHERE user_id=?

        )

    """, (user_id,)).fetchall()

    return render_template("browse_classes.html", all_classes=all_classes)

@app.route("/student_report")

def student_report():

    db = get_db()

    completed = db.execute("""

        SELECT classes.class_name

        FROM classes

        JOIN class_members ON classes.id = class_members.class_id

        WHERE class_members.user_id=? AND classes.status='completed'

    """,(session["user_id"],)).fetchall()

    running = db.execute("""

        SELECT classes.class_name

        FROM classes

        JOIN class_members ON classes.id = class_members.class_id

        WHERE class_members.user_id=? AND classes.status='running'

    """,(session["user_id"],)).fetchall()

    completed_classes = len(completed)

    active_classes = len(running)

    return render_template("student_report.html",
        completed=completed,
        running=running,
        completed_classes=completed_classes,
        active_classes=active_classes

    )

@app.route("/approve_request/<int:req_id>")
def approve_request(req_id):
    db = get_db()
    req = db.execute("""
    SELECT * FROM join_requests WHERE id=?
    """,(req_id,)).fetchone()

    db.execute("""

        INSERT INTO class_members(class_id, user_id)

        VALUES(?,?)

    """,(req["class_id"], req["student_id"]))

    db.execute("""
        UPDATE join_requests SET status='approved' WHERE id=?
    """,(req_id,))

    db.commit()
    return redirect("/requests")

@app.route("/reject_request/<int:req_id>")
def reject_request(req_id):

    db = get_db()

    db.execute("UPDATE join_requests SET status='rejected' WHERE id=?", (req_id,))

    db.commit()
    return redirect("/requests")

@app.route("/teacher_report")

def teacher_report():

    if "user_id" not in session:

        return redirect("/")

    db = get_db()
    user_id = session["user_id"]

    classes = db.execute("""
        SELECT id, class_name, status
        FROM classes
        WHERE admin_id=?
    """, (user_id,)).fetchall()

    total_classes = len(classes)

    active_classes = sum(1 for c in classes if c["status"] == "running")

    completed_classes = sum(1 for c in classes if c["status"] == "completed")

    return render_template(

        "teacher_report.html",

        classes=classes,

        total_classes=total_classes,

        active_classes=active_classes,

        completed_classes=completed_classes

    )

@app.route("/mark_content/<int:content_id>")

def mark_content(content_id):

    if "user_id" not in session:

        return redirect("/")

    user_id = session["user_id"]

    db = get_db()

    already = db.execute("""
        SELECT * FROM content_progress
        WHERE user_id=? AND content_id=?
    """,(user_id, content_id)).fetchone()

    if not already:
        db.execute("""
            INSERT INTO content_progress(user_id, content_id, status)
            VALUES(?,?,?)
        """,(user_id, content_id, "completed"))

        db.commit()
    return redirect(request.referrer)
@app.route("/complete_class/<int:class_id>", methods=["POST"])

def complete_class(class_id):

    if "user_id" not in session:

        return redirect("/")



    db = get_db()



    class_data = db.execute(

        "SELECT * FROM classes WHERE id=?", (class_id,)

    ).fetchone()



    if class_data["admin_id"] != session["user_id"]:

        return "Access Denied"



    db.execute(

        "UPDATE classes SET status='completed' WHERE id=?",

        (class_id,)

    )

    db.commit()



    return redirect(f"/class/{class_id}")



@app.route("/report/<int:class_id>")

def generate_report(class_id):

    if "user_id" not in session:

        return redirect("/")



    db = get_db()



    class_data = db.execute(

        "SELECT * FROM classes WHERE id=?",

        (class_id,)

    ).fetchone()



    user = db.execute(

        "SELECT * FROM users WHERE id=?",

        (session["user_id"],)

    ).fetchone()



    quizzes = db.execute("""

        SELECT COUNT(*) as total

        FROM quizzes WHERE class_id=?

    """,(class_id,)).fetchone()["total"]



    attempted = db.execute("""

        SELECT COUNT(*) as attempted

        FROM submissions

        WHERE quiz_id IN (SELECT id FROM quizzes WHERE class_id=?)

        AND user_id=?

    """,(class_id, session["user_id"])).fetchone()["attempted"]



    return render_template(

        "gen_rep.html",

        class_data=class_data,

        user=user,

        total_quizzes=quizzes,

        attempted_quizzes=attempted

    )



@app.route("/report")

def report():

    if "user_id" not in session:

        return redirect("/")



    db = get_db()

    user_id = session["user_id"]

    role = session["role"]



    # --- STUDENT LOGIC ---

    if role == "student":

        # FIX: Explicitly select classes.id to avoid ambiguity

        running = db.execute("""

            SELECT classes.id, classes.class_name FROM classes

            JOIN class_members ON classes.id = class_members.class_id

            WHERE class_members.user_id=? AND classes.status='running'

        """, (user_id,)).fetchall()



        completed = db.execute("""

            SELECT classes.class_name FROM classes

            JOIN class_members ON classes.id = class_members.class_id

            WHERE class_members.user_id=? AND classes.status='completed'

        """, (user_id,)).fetchall()



        progress_data = []

        for c in running:

            class_id = c["id"]

            total_quizzes = db.execute("SELECT COUNT(*) as count FROM quizzes WHERE class_id=?", (class_id,)).fetchone()["count"]

            attempted_quizzes = db.execute("SELECT COUNT(*) as count FROM submissions WHERE user_id=? AND quiz_id IN (SELECT id FROM quizzes WHERE class_id=?)", (user_id, class_id)).fetchone()["count"]

            total_contents = db.execute("SELECT COUNT(*) as count FROM contents WHERE class_id=?", (class_id,)).fetchone()["count"]

            completed_contents = db.execute("SELECT COUNT(*) as count FROM content_progress WHERE user_id=? AND content_id IN (SELECT id FROM contents WHERE class_id=?)", (user_id, class_id)).fetchone()["count"]

           

            total = total_quizzes + total_contents

            done = attempted_quizzes + completed_contents

            progress = int((done / total) * 100) if total > 0 else 0



            progress_data.append({"class_name": c["class_name"], "progress": progress})



        return render_template("report.html", role=role, completed=completed, running=running,

                               completed_classes=len(completed), active_classes=len(running), progress_data=progress_data)



    # --- TEACHER LOGIC ---

    else:

        # Teacher logic remains the same

        running_classes = db.execute("SELECT id, class_name FROM classes WHERE admin_id=? AND status='running'", (user_id,)).fetchall()

        completed_list = db.execute("SELECT id, class_name FROM classes WHERE admin_id=? AND status='completed'", (user_id,)).fetchall()



        teacher_data = []

        for c in running_classes:

            class_id = c["id"]

            file_count = db.execute("SELECT COUNT(*) as count FROM contents WHERE class_id=?", (class_id,)).fetchone()["count"]

            video_count = db.execute("SELECT COUNT(*) as count FROM videos WHERE class_id=?", (class_id,)).fetchone()["count"]

            quiz_count = db.execute("SELECT COUNT(*) as count FROM quizzes WHERE class_id=?", (class_id,)).fetchone()["count"]

           

            teacher_data.append({

                "class_name": c["class_name"],

                "total_uploads": file_count + video_count,

                "total_quizzes": quiz_count

            })



        return render_template("report.html", role=role, running=running_classes,

                               completed=completed_list, active_classes=len(running_classes),

                               completed_classes=len(completed_list), teacher_data=teacher_data)



@app.route("/download_report/<int:class_id>")

def download_report(class_id):

    if "user_id" not in session:

        return redirect("/")



    db = get_db()



    class_data = db.execute(

        "SELECT * FROM classes WHERE id=?", (class_id,)

    ).fetchone()



    user = db.execute(

        "SELECT * FROM users WHERE id=?", (session["user_id"],)

    ).fetchone()



    submissions = db.execute("""

        SELECT quizzes.title, submissions.score

        FROM submissions

        JOIN quizzes ON submissions.quiz_id = quizzes.id

        WHERE quizzes.class_id=? AND submissions.user_id=?

    """, (class_id, session["user_id"])).fetchall()



    buffer = io.BytesIO()

    pdf = canvas.Canvas(buffer, pagesize=letter)

    text = pdf.beginText(40, 750)



    text.setFont("Helvetica", 12)

    text.textLine("Learning Management System - Report")

    text.textLine("")

    text.textLine(f"Student Name: {user['name']}")

    text.textLine(f"Class: {class_data['class_name']}")

    text.textLine(f"Status: Completed")

    text.textLine(f"Date: {datetime.now().strftime('%d-%m-%Y')}")

    text.textLine("")

    text.textLine("Quiz Results:")



    for s in submissions:

        text.textLine(f"- {s['title']} : {s['score']}")



    pdf.drawText(text)

    pdf.showPage()

    pdf.save()



    buffer.seek(0)



    return send_file(

        buffer,

        as_attachment=True,

        download_name="report.pdf",

        mimetype="application/pdf"

    )



@app.route("/upload_video/<int:class_id>", methods=["POST"])

def upload_video(class_id):

    if "user_id" not in session:

        return redirect("/")



    db = get_db()

    class_data = db.execute("SELECT * FROM classes WHERE id=?", (class_id,)).fetchone()



    # only teacher can upload

    if class_data["admin_id"] != session["user_id"]:

        return "Access Denied"



    title = request.form["title"]

    video = request.files["video"]



    filename = secure_filename(video.filename)

    video.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))



    db.execute(

        "INSERT INTO videos(class_id,title,filename) VALUES(?,?,?)",

        (class_id, title, filename)

    )

    db.commit()



    return redirect(f"/class/{class_id}")



@app.route("/uploads/<filename>")

def uploaded_file(filename):

    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)



@app.route("/upload_content/<int:class_id>", methods=["POST"])

def upload_content(class_id):

    if "user_id" not in session:

        return redirect("/")



    db = get_db()

    class_data = db.execute(

        "SELECT * FROM classes WHERE id=?", (class_id,)

    ).fetchone()



    # only teacher can upload

    if class_data["admin_id"] != session["user_id"]:

        return "Access Denied"



    title = request.form["title"]

    file = request.files["file"]



    if file.filename == "":

        return redirect(f"/class/{class_id}")



    filename = secure_filename(file.filename)

    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    file.save(filepath)



    filetype = filename.split(".")[-1].lower()



    db.execute("""

        INSERT INTO contents(class_id,title,filename,filetype)

        VALUES(?,?,?,?)

    """, (class_id, title, filename, filetype))

    db.commit()



    return redirect(f"/class/{class_id}")



@app.route("/remove_member/<int:class_id>/<int:user_id>")

def remove_member(class_id, user_id):

    if "user_id" not in session:

        return redirect("/")



    db = get_db()



    # check teacher

    class_data = db.execute(

        "SELECT * FROM classes WHERE id=?", (class_id,)

    ).fetchone()



    if class_data["admin_id"] != session["user_id"]:

        return "Access Denied"



    # prevent removing teacher himself

    if user_id == session["user_id"]:

        return redirect(f"/class/{class_id}")



    db.execute(

        "DELETE FROM class_members WHERE class_id=? AND user_id=?",

        (class_id, user_id)

    )

    db.commit()



    return redirect(f"/class/{class_id}")



 # ---------------- CREATE QUIZ ----------------

@app.route("/create_quiz/<int:class_id>", methods=["POST"])

def create_quiz(class_id):

    if "user_id" not in session:

        return redirect("/")



    # only teacher can create quiz

    db = get_db()

    class_data = db.execute("SELECT * FROM classes WHERE id=?", (class_id,)).fetchone()



    if class_data["admin_id"] != session["user_id"]:

        return "Access Denied"



    title = request.form["title"]



    db.execute(

        "INSERT INTO quizzes(class_id,title) VALUES(?,?)",

        (class_id, title)

    )

    db.commit()



    quiz_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]



    return redirect(f"/quiz/{quiz_id}")



@app.route("/quiz/<int:quiz_id>", methods=["GET","POST"])

def quiz_page(quiz_id):

    if "user_id" not in session:

        return redirect("/")



    db = get_db()

    quiz = db.execute("SELECT * FROM quizzes WHERE id=?", (quiz_id,)).fetchone()

    class_data = db.execute("SELECT * FROM classes WHERE id=?", (quiz["class_id"],)).fetchone()



    if class_data["admin_id"] != session["user_id"]:

        return redirect(f"/attempt_quiz/{quiz_id}")



    if request.method == "POST":

        q = request.form["question"]

        o1 = request.form["option1"]

        o2 = request.form["option2"]

        o3 = request.form["option3"]

        o4 = request.form["option4"]

        ans = request.form["answer"]



        db.execute("""

            INSERT INTO questions(quiz_id,question,option1,option2,option3,option4,answer)

            VALUES(?,?,?,?,?,?,?)

        """,(quiz_id,q,o1,o2,o3,o4,ans))

        db.commit()



    questions = db.execute("SELECT * FROM questions WHERE quiz_id=?", (quiz_id,)).fetchall()

    return render_template("quiz.html", quiz=quiz, questions=questions)





# ---------------- STUDENT ATTEMPT QUIZ ----------------

@app.route("/attempt_quiz/<int:quiz_id>", methods=["GET","POST"])

def attempt_quiz(quiz_id):

    if "user_id" not in session:

        return redirect("/")



    # 🚫 block teacher

    if session["role"] == "teacher":

        return redirect("/dashboard")



    db = get_db()



    # check if already attempted

    already = db.execute(

        "SELECT * FROM submissions WHERE quiz_id=? AND user_id=?",

        (quiz_id, session["user_id"])

    ).fetchone()



    questions = db.execute(

        "SELECT * FROM questions WHERE quiz_id=?", (quiz_id,)

    ).fetchall()



    if already:

        return render_template(

            "feedback.html",

            score=already["score"],

            total=len(questions),

            attempted=True

        )



    if request.method == "POST":

        score = 0



        for q in questions:

            user_ans = request.form.get(str(q["id"]))

            correct_ans = q["answer"].strip()



            if user_ans == correct_ans:

                score += 1



        # ✅ SAVE RESULT HERE

        db.execute(

            "INSERT INTO submissions(quiz_id,user_id,score) VALUES(?,?,?)",

            (quiz_id, session["user_id"], score)

        )

        db.commit()

        return render_template(

            "feedback.html",

            score=score,

            total=len(questions),

            attempted=False

        )

    return render_template("attempt_quiz.html", questions=questions)

# ---------------- LOGOUT ----------------

@app.route("/logout")

def logout():

    session.clear()

    return redirect("/")

if __name__ == "__main__":

    # Use the port assigned by the deployment platform

    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port)