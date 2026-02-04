import os, random, string
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, session
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "lms_secret_key"

DATABASE_URL = os.environ.get("postgresql://nikhilgit:qexVCyfv0wlHPndqwdbheBw8EnWw68Ri@dpg-d612jqkoud1c738540hg-a/lms_db_m89x")

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

    all_classes = []
    if session["role"]=="student":
        cur.execute("""
            SELECT classes.id, classes.class_name, users.name AS teacher_name
            FROM classes
            JOIN users ON classes.admin_id = users.id
            WHERE classes.id NOT IN (
                SELECT class_id FROM class_members WHERE user_id=%s
            )
        """,(session["user_id"],))
        all_classes = cur.fetchall()

    conn.close()

    return render_template("dashboard.html",
        classes=classes,
        all_classes=all_classes,
        name=session["name"],
        role=session["role"]
    )


# ---------------- REQUEST JOIN ----------------
@app.route("/request_join/<int:class_id>", methods=["POST"])
def request_join(class_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO join_requests(class_id,student_id,status)
        VALUES(%s,%s,'pending')
        ON CONFLICT DO NOTHING
    """,(class_id, session["user_id"]))
    conn.commit()
    conn.close()
    return redirect("/dashboard")


# ---------------- TEACHER REQUESTS ----------------
@app.route("/requests")
def requests_page():
    if session["role"]!="teacher":
        return redirect("/dashboard")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT join_requests.id, users.name, classes.class_name,
               classes.id as class_id, users.id as student_id
            FROM join_requests
        JOIN users ON join_requests.student_id = users.id
        JOIN classes ON join_requests.class_id = classes.id
        WHERE classes.admin_id=%s AND join_requests.status='pending'
    """,(session["user_id"],))
    requests = cur.fetchall()
    conn.close()

    return render_template("requests.html", requests=requests)


# ---------------- APPROVE REQUEST ----------------
@app.route("/approve_request/<int:req_id>")
def approve_request(req_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM join_requests WHERE id=%s",(req_id,))
    req = cur.fetchone()

    cur.execute("INSERT INTO class_members(class_id,user_id) VALUES(%s,%s)",
                (req["class_id"], req["student_id"]))
    cur.execute("UPDATE join_requests SET status='approved' WHERE id=%s",(req_id,))

    conn.commit()
    conn.close()
    return redirect("/requests")


# ---------------- REJECT REQUEST ----------------
@app.route("/reject_request/<int:req_id>")
def reject_request(req_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE join_requests SET status='rejected' WHERE id=%s",(req_id,))
    conn.commit()
    conn.close()
    return redirect("/requests")


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------- CREATE QUIZ ----------------
@app.route("/create_quiz/<int:class_id>", methods=["POST"])
def create_quiz(class_id):
    if "user_id" not in session:
        return redirect("/")

    conn = get_db()
    cur = conn.cursor()

    # only teacher can create quiz
    cur.execute("SELECT * FROM classes WHERE id=%s", (class_id,))
    class_data = cur.fetchone()

    if class_data["admin_id"] != session["user_id"]:
        return "Access Denied"

    title = request.form["title"]

    cur.execute("""
        INSERT INTO quizzes(class_id, title)
        VALUES (%s, %s)
        RETURNING id
    """, (class_id, title))

    quiz_id = cur.fetchone()["id"]

    conn.commit()
    conn.close()

    return redirect(f"/quiz/{quiz_id}")


# ---------------- QUIZ PAGE (TEACHER ADD QUESTIONS) ----------------
@app.route("/quiz/<int:quiz_id>", methods=["GET","POST"])
def quiz_page(quiz_id):
    if "user_id" not in session:
        return redirect("/")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM quizzes WHERE id=%s", (quiz_id,))
    quiz = cur.fetchone()

    cur.execute("SELECT * FROM classes WHERE id=%s", (quiz["class_id"],))
    class_data = cur.fetchone()

    # student redirected to attempt quiz
    if class_data["admin_id"] != session["user_id"]:
        conn.close()
        return redirect(f"/attempt_quiz/{quiz_id}")

    if request.method == "POST":
        q = request.form["question"]
        o1 = request.form["option1"]
        o2 = request.form["option2"]
        o3 = request.form["option3"]
        o4 = request.form["option4"]
        ans = request.form["answer"]

        cur.execute("""
            INSERT INTO questions(quiz_id,question,option1,option2,option3,option4,answer)
            VALUES(%s,%s,%s,%s,%s,%s,%s)
        """,(quiz_id,q,o1,o2,o3,o4,ans))

        conn.commit()

    cur.execute("SELECT * FROM questions WHERE quiz_id=%s", (quiz_id,))
    questions = cur.fetchall()

    conn.close()

    return render_template("quiz.html", quiz=quiz, questions=questions)


# ---------------- STUDENT ATTEMPT QUIZ ----------------
@app.route("/attempt_quiz/<int:quiz_id>", methods=["GET","POST"])
def attempt_quiz(quiz_id):
    if "user_id" not in session:
        return redirect("/")

    if session["role"] == "teacher":
        return redirect("/dashboard")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM submissions
        WHERE quiz_id=%s AND user_id=%s
    """, (quiz_id, session["user_id"]))

    already = cur.fetchone()

    cur.execute("SELECT * FROM questions WHERE quiz_id=%s", (quiz_id,))
    questions = cur.fetchall()

    if already:
        conn.close()
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
            if user_ans == q["answer"]:
                score += 1

        cur.execute("""
            INSERT INTO submissions(quiz_id,user_id,score)
            VALUES(%s,%s,%s)
        """,(quiz_id, session["user_id"], score))

        conn.commit()
        conn.close()

        return render_template(
            "feedback.html",
            score=score,
            total=len(questions),
            attempted=False
        )

    conn.close()
    return render_template("attempt_quiz.html", questions=questions)

@app.route("/analysis")
def analysis():
    if "user_id" not in session:
        return redirect("/")

    conn = get_db()
    cur = conn.cursor()

    user_id = session["user_id"]
    role = session["role"]

    if role == "teacher":
        cur.execute("""
            SELECT quizzes.id, quizzes.title, classes.class_name
            FROM quizzes
            JOIN classes ON quizzes.class_id = classes.id
            WHERE classes.admin_id=%s
        """,(user_id,))
    else:
        cur.execute("""
            SELECT quizzes.id, quizzes.title, classes.class_name
            FROM submissions
            JOIN quizzes ON submissions.quiz_id = quizzes.id
            JOIN classes ON quizzes.class_id = classes.id
            WHERE submissions.user_id=%s
        """,(user_id,))

    quizzes = cur.fetchall()
    conn.close()

    return render_template("analysis.html", quizzes=quizzes, role=role)


@app.route("/quiz_stats/<int:quiz_id>")
def quiz_stats(quiz_id):
    if "user_id" not in session:
        return redirect("/")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT quizzes.id, quizzes.title, classes.class_name
        FROM quizzes
        JOIN classes ON quizzes.class_id = classes.id
        WHERE quizzes.id=%s
    """,(quiz_id,))
    quiz = cur.fetchone()

    cur.execute("""
        SELECT score FROM submissions
        WHERE quiz_id=%s AND user_id=%s
    """,(quiz_id, session["user_id"]))
    submission = cur.fetchone()

    conn.close()

    my_score = submission["score"] if submission else ""

    return render_template("quiz_stats.html", quiz=quiz, my_score=my_score)

@app.route("/report")
def report():
    if "user_id" not in session:
        return redirect("/")

    conn = get_db()
    cur = conn.cursor()

    user_id = session["user_id"]
    role = session["role"]

    if role == "student":
        cur.execute("""
            SELECT classes.id, classes.class_name
            FROM classes
            JOIN class_members ON classes.id = class_members.class_id
            WHERE class_members.user_id=%s AND classes.status='running'
        """,(user_id,))
        running = cur.fetchall()

        cur.execute("""
            SELECT classes.class_name
            FROM classes
            JOIN class_members ON classes.id = class_members.class_id
            WHERE class_members.user_id=%s AND classes.status='completed'
        """,(user_id,))
        completed = cur.fetchall()

        progress_data = []
        for c in running:
            class_id = c["id"]

            cur.execute("SELECT COUNT(*) AS count FROM quizzes WHERE class_id=%s",(class_id,))
            total_quizzes = cur.fetchone()["count"]

            cur.execute("""
                SELECT COUNT(*) AS count FROM submissions
                WHERE user_id=%s AND quiz_id IN
                (SELECT id FROM quizzes WHERE class_id=%s)
            """,(user_id,class_id))
            attempted_quizzes = cur.fetchone()["count"]

            cur.execute("SELECT COUNT(*) AS count FROM contents WHERE class_id=%s",(class_id,))
            total_contents = cur.fetchone()["count"]

            cur.execute("""
                SELECT COUNT(*) AS count FROM content_progress
                WHERE user_id=%s AND content_id IN
                (SELECT id FROM contents WHERE class_id=%s)
            """,(user_id,class_id))
            completed_contents = cur.fetchone()["count"]

            total = total_quizzes + total_contents
            done = attempted_quizzes + completed_contents
            progress = int((done/total)*100) if total>0 else 0

            progress_data.append({"class_name": c["class_name"], "progress": progress})

        conn.close()
        return render_template("report.html",
            role=role,
            completed=completed,
            running=running,
            progress_data=progress_data
        )

    # -------- TEACHER --------
    else:
        cur.execute("""
            SELECT id, class_name FROM classes
            WHERE admin_id=%s AND status='running'
        """,(user_id,))
        running_classes = cur.fetchall()

        cur.execute("""
            SELECT id, class_name FROM classes
            WHERE admin_id=%s AND status='completed'
        """,(user_id,))
        completed_list = cur.fetchall()

        teacher_data = []
        for c in running_classes:
            class_id = c["id"]

            cur.execute("SELECT COUNT(*) AS count FROM contents WHERE class_id=%s",(class_id,))
            file_count = cur.fetchone()["count"]

            cur.execute("SELECT COUNT(*) AS count FROM videos WHERE class_id=%s",(class_id,))
            video_count = cur.fetchone()["count"]

            cur.execute("SELECT COUNT(*) AS count FROM quizzes WHERE class_id=%s",(class_id,))
            quiz_count = cur.fetchone()["count"]

            teacher_data.append({
                "class_name": c["class_name"],
                "total_uploads": file_count + video_count,
                "total_quizzes": quiz_count
            })

        conn.close()
        return render_template("report.html",
            role=role,
            running=running_classes,
            completed=completed_list,
            teacher_data=teacher_data
        )

@app.route("/upload_video/<int:class_id>", methods=["POST"])
def upload_video(class_id):
    if "user_id" not in session:
        return redirect("/")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM classes WHERE id=%s",(class_id,))
    class_data = cur.fetchone()

    if class_data["admin_id"] != session["user_id"]:
        return "Access Denied"

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
    return redirect(f"/class/{class_id}")


@app.route("/upload_content/<int:class_id>", methods=["POST"])
def upload_content(class_id):
    if "user_id" not in session:
        return redirect("/")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM classes WHERE id=%s",(class_id,))
    class_data = cur.fetchone()

    if class_data["admin_id"] != session["user_id"]:
        return "Access Denied"

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
    return redirect(f"/class/{class_id}")

if __name__=="__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port)