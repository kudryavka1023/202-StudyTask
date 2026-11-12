import re
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from db import close_db, get_db, init_db

PRIORITIES = ("高", "中", "低")
STATUSES = ("待完成", "进行中", "已完成")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DUE_SOON_DAYS = 3


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY="studytask-local-development-key",
        DATABASE=str(Path(app.instance_path) / "studytask.sqlite3"),
    )
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)

    with app.app_context():
        init_db()

    register_routes(app)
    register_error_handlers(app)
    return app


def validate_task_form(form, *, allow_status, fallback_status="待完成"):
    """Validate and normalize submitted task fields."""
    data = {
        "name": (form.get("name") or "").strip(),
        "course": (form.get("course") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "due_date": (form.get("due_date") or "").strip(),
        "priority": (form.get("priority") or "中").strip(),
        "status": "待完成",
    }
    if allow_status:
        data["status"] = (form.get("status") or fallback_status).strip()

    errors = {}

    if not data["name"]:
        errors["name"] = "请输入任务名称。"
    elif len(data["name"]) > 100:
        errors["name"] = "任务名称不能超过 100 个字符。"

    if not data["course"]:
        errors["course"] = "请输入所属课程。"
    elif len(data["course"]) > 60:
        errors["course"] = "所属课程不能超过 60 个字符。"

    if len(data["description"]) > 1000:
        errors["description"] = "任务描述不能超过 1000 个字符。"

    if not data["due_date"]:
        errors["due_date"] = "请选择截止日期。"
    elif not DATE_PATTERN.fullmatch(data["due_date"]):
        errors["due_date"] = "截止日期格式必须为 YYYY-MM-DD。"
    else:
        try:
            date.fromisoformat(data["due_date"])
        except ValueError:
            errors["due_date"] = "截止日期不是有效日期。"

    if data["priority"] not in PRIORITIES:
        errors["priority"] = "优先级必须为高、中或低。"

    if allow_status and data["status"] not in STATUSES:
        errors["status"] = "任务状态必须为待完成、进行中或已完成。"

    return data, errors


def decorate_task(row, today=None):
    """Convert a DB row to a dict and add reminder flags."""
    task = dict(row)
    today = today or date.today()
    due = date.fromisoformat(task["due_date"])
    unfinished = task["status"] != "已完成"
    task["is_overdue"] = unfinished and due < today
    task["is_due_soon"] = (
        unfinished and today <= due <= today + timedelta(days=DUE_SOON_DAYS)
    )
    return task


def get_stats(db):
    row = db.execute(
        """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN status = '已完成' THEN 1 ELSE 0 END), 0)
                   AS completed
        FROM tasks
        """
    ).fetchone()
    total = row["total"]
    completed = row["completed"]
    if total == 0:
        rate = "0"
    else:
        rate = f"{completed * 100 / total:.1f}".rstrip("0").rstrip(".")
    return {"total": total, "completed": completed, "rate": rate}


def register_routes(app):
    def get_task_or_404(task_id):
        task = get_db().execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if task is None:
            abort(404)
        return task

    def new_task_form_data():
        return {
            "name": "",
            "course": "",
            "description": "",
            "due_date": "",
            "priority": "中",
            "status": "待完成",
        }

    @app.get("/")
    def index():
        filters = {
            "course": (request.args.get("course") or "").strip(),
            "status": (request.args.get("status") or "").strip(),
            "priority": (request.args.get("priority") or "").strip(),
        }

        conditions = []
        params = []
        if filters["course"]:
            conditions.append("course = ?")
            params.append(filters["course"])
        if filters["status"]:
            conditions.append("status = ?")
            params.append(filters["status"])
        if filters["priority"]:
            conditions.append("priority = ?")
            params.append(filters["priority"])

        sql = "SELECT * FROM tasks"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY due_date ASC, id ASC"

        db = get_db()
        rows = db.execute(sql, params).fetchall()
        today = date.today()
        tasks = [decorate_task(row, today) for row in rows]
        courses = [
            row["course"]
            for row in db.execute(
                "SELECT DISTINCT course FROM tasks ORDER BY course ASC"
            ).fetchall()
        ]

        return render_template(
            "index.html",
            tasks=tasks,
            courses=courses,
            filters=filters,
            stats=get_stats(db),
            statuses=STATUSES,
            priorities=PRIORITIES,
        )

    @app.get("/tasks/new")
    def new_task():
        return render_template(
            "task_form.html",
            form_data=new_task_form_data(),
            errors={},
            is_edit=False,
            task=None,
            priorities=PRIORITIES,
            statuses=STATUSES,
        )

    @app.post("/tasks")
    def create_task():
        data, errors = validate_task_form(request.form, allow_status=False)
        if errors:
            return (
                render_template(
                    "task_form.html",
                    form_data=data,
                    errors=errors,
                    is_edit=False,
                    task=None,
                    priorities=PRIORITIES,
                    statuses=STATUSES,
                ),
                400,
            )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db = get_db()
        cursor = db.execute(
            """
            INSERT INTO tasks
                (name, course, description, due_date, priority, status,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["name"],
                data["course"],
                data["description"],
                data["due_date"],
                data["priority"],
                "待完成",
                now,
                now,
            ),
        )
        db.commit()
        flash("任务已创建。", "success")
        return redirect(url_for("task_detail", task_id=cursor.lastrowid))

    @app.get("/tasks/<int:task_id>")
    def task_detail(task_id):
        task = decorate_task(get_task_or_404(task_id))
        return render_template("task_detail.html", task=task, statuses=STATUSES)

    @app.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
    def edit_task(task_id):
        task = get_task_or_404(task_id)

        if request.method == "GET":
            return render_template(
                "task_form.html",
                form_data=dict(task),
                errors={},
                is_edit=True,
                task=task,
                priorities=PRIORITIES,
                statuses=STATUSES,
            )

        data, errors = validate_task_form(
            request.form, allow_status=True, fallback_status=task["status"]
        )
        if errors:
            return (
                render_template(
                    "task_form.html",
                    form_data=data,
                    errors=errors,
                    is_edit=True,
                    task=task,
                    priorities=PRIORITIES,
                    statuses=STATUSES,
                ),
                400,
            )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db = get_db()
        db.execute(
            """
            UPDATE tasks
            SET name = ?, course = ?, description = ?, due_date = ?,
                priority = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                data["name"],
                data["course"],
                data["description"],
                data["due_date"],
                data["priority"],
                data["status"],
                now,
                task_id,
            ),
        )
        db.commit()
        flash("任务已更新。", "success")
        return redirect(url_for("task_detail", task_id=task_id))

    @app.post("/tasks/<int:task_id>/status")
    def update_task_status(task_id):
        get_task_or_404(task_id)
        status = (request.form.get("status") or "").strip()
        if status not in STATUSES:
            flash("任务状态无效，未做修改。", "error")
            return redirect(url_for("task_detail", task_id=task_id))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db = get_db()
        db.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, task_id),
        )
        db.commit()
        flash(f"任务状态已更新为“{status}”。", "success")
        return redirect(url_for("task_detail", task_id=task_id))

    @app.route("/tasks/<int:task_id>/delete", methods=["GET", "POST"])
    def delete_task(task_id):
        task = get_task_or_404(task_id)

        if request.method == "POST":
            db = get_db()
            db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            db.commit()
            flash("任务已删除。", "success")
            return redirect(url_for("index"))

        return render_template(
            "confirm_delete.html", task=decorate_task(task)
        )


def register_error_handlers(app):
    @app.errorhandler(404)
    def not_found(error):
        return render_template("404.html"), 404


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)