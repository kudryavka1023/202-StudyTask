import re
from datetime import date, timedelta

import pytest

from app import create_app


def table_row(html, task_name):
    """Return the table row containing the given task name."""
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S):
        if task_name in row:
            return row
    raise AssertionError(f"未在页面中找到任务行：{task_name}")


def test_empty_home_shows_zero_statistics(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "任务总数" in body
    assert "0%" in body
    assert "当前条件下没有任务" in body


def test_create_task_is_saved_and_visible(client, make_task, query_db):
    due_date = (date.today() + timedelta(days=2)).isoformat()
    response = make_task(
        name="数据结构作业",
        course="数据结构",
        description="完成链表实验",
        due_date=due_date,
        priority="高",
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "任务已创建" in body
    assert "数据结构作业" in body
    assert "完成链表实验" in body

    rows = query_db("SELECT * FROM tasks")
    assert len(rows) == 1
    task = rows[0]
    assert task["name"] == "数据结构作业"
    assert task["course"] == "数据结构"
    assert task["description"] == "完成链表实验"
    assert task["due_date"] == due_date
    assert task["priority"] == "高"
    assert task["status"] == "待完成"
    assert task["created_at"]
    assert task["updated_at"]

    index_body = client.get("/").get_data(as_text=True)
    assert "数据结构作业" in index_body
    assert "数据结构" in index_body
    assert due_date in index_body


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": "   "}, "请输入任务名称"),
        ({"course": ""}, "请输入所属课程"),
        ({"due_date": ""}, "请选择截止日期"),
    ],
)
def test_required_fields_are_rejected(client, overrides, message, query_db):
    data = {
        "name": "有效任务",
        "course": "软件工程",
        "description": "",
        "due_date": (date.today() + timedelta(days=1)).isoformat(),
        "priority": "中",
    }
    data.update(overrides)

    response = client.post("/tasks", data=data)

    assert response.status_code == 400
    assert message in response.get_data(as_text=True)
    assert query_db("SELECT * FROM tasks") == []


@pytest.mark.parametrize(
    "invalid_date",
    ["2026-02-30", "2026/11/13", "not-a-date", "2026-13-01"],
)
def test_invalid_due_dates_are_rejected(client, invalid_date, query_db):
    response = client.post(
        "/tasks",
        data={
            "name": "无效日期任务",
            "course": "软件工程",
            "description": "",
            "due_date": invalid_date,
            "priority": "中",
        },
    )

    assert response.status_code == 400
    assert "截止日期" in response.get_data(as_text=True)
    assert query_db("SELECT * FROM tasks") == []


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": "任" * 101}, "100"),
        ({"course": "课" * 61}, "60"),
        ({"description": "描" * 1001}, "1000"),
    ],
)
def test_length_limits_are_rejected(client, overrides, message, query_db):
    data = {
        "name": "长度校验任务",
        "course": "软件工程",
        "description": "",
        "due_date": (date.today() + timedelta(days=1)).isoformat(),
        "priority": "中",
    }
    data.update(overrides)

    response = client.post("/tasks", data=data)

    assert response.status_code == 400
    assert message in response.get_data(as_text=True)
    assert query_db("SELECT * FROM tasks") == []


def test_maximum_lengths_are_accepted(client, make_task, query_db):
    response = make_task(
        name="任" * 100,
        course="课" * 60,
        description="描" * 1000,
    )

    assert response.status_code == 200
    assert len(query_db("SELECT * FROM tasks")) == 1


def test_edit_updates_all_fields_and_persists(
    client, make_task, query_db, fetch_task
):
    make_task(
        name="待修改任务",
        course="旧课程",
        description="旧描述",
        priority="中",
    )
    task_id = query_db("SELECT id FROM tasks")[0]["id"]
    new_due_date = (date.today() + timedelta(days=5)).isoformat()

    response = client.post(
        f"/tasks/{task_id}/edit",
        data={
            "name": "修改后的任务",
            "course": "新课程",
            "description": "新的任务描述",
            "due_date": new_due_date,
            "priority": "低",
            "status": "进行中",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "任务已更新" in body
    assert "修改后的任务" in body
    assert "新的任务描述" in body
    assert "进行中" in body

    task = fetch_task(task_id)
    assert task["name"] == "修改后的任务"
    assert task["course"] == "新课程"
    assert task["description"] == "新的任务描述"
    assert task["due_date"] == new_due_date
    assert task["priority"] == "低"
    assert task["status"] == "进行中"

    detail_body = client.get(f"/tasks/{task_id}").get_data(as_text=True)
    assert "新的任务描述" in detail_body
    assert "新课程" in detail_body


def test_status_transitions_are_persisted(client, make_task, query_db, fetch_task):
    make_task(name="状态流转任务")
    task_id = query_db("SELECT id FROM tasks")[0]["id"]

    for status in ("进行中", "已完成", "待完成"):
        response = client.post(
            f"/tasks/{task_id}/status",
            data={"status": status},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert f"任务状态已更新为“{status}”" in response.get_data(as_text=True)
        assert fetch_task(task_id)["status"] == status


def test_invalid_status_is_rejected(client, make_task, query_db, fetch_task):
    make_task(name="状态校验任务")
    task_id = query_db("SELECT id FROM tasks")[0]["id"]

    response = client.post(
        f"/tasks/{task_id}/status",
        data={"status": "已归档"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "任务状态无效" in response.get_data(as_text=True)
    assert fetch_task(task_id)["status"] == "待完成"


def test_filters_by_course_status_priority_and_combination(
    client, make_task, query_db
):
    make_task(name="数据结构作业A", course="数据结构", priority="高")
    make_task(name="数据结构复习B", course="数据结构", priority="低")
    make_task(name="数据库作业C", course="数据库原理", priority="高")

    task_b_id = query_db(
        "SELECT id FROM tasks WHERE name = ?", ("数据结构复习B",)
    )[0]["id"]
    client.post(
        f"/tasks/{task_b_id}/status",
        data={"status": "已完成"},
        follow_redirects=True,
    )

    course_body = client.get(
        "/", query_string={"course": "数据结构"}
    ).get_data(as_text=True)
    assert "数据结构作业A" in course_body
    assert "数据结构复习B" in course_body
    assert "数据库作业C" not in course_body

    status_body = client.get(
        "/", query_string={"status": "已完成"}
    ).get_data(as_text=True)
    assert "数据结构复习B" in status_body
    assert "数据结构作业A" not in status_body
    assert "数据库作业C" not in status_body

    priority_body = client.get(
        "/", query_string={"priority": "高"}
    ).get_data(as_text=True)
    assert "数据结构作业A" in priority_body
    assert "数据库作业C" in priority_body
    assert "数据结构复习B" not in priority_body

    combined_body = client.get(
        "/",
        query_string={
            "course": "数据结构",
            "status": "待完成",
            "priority": "高",
        },
    ).get_data(as_text=True)
    assert "数据结构作业A" in combined_body
    assert "数据结构复习B" not in combined_body
    assert "数据库作业C" not in combined_body


def test_overdue_and_due_soon_reminders(client, make_task, query_db):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    today = date.today().isoformat()
    in_three_days = (date.today() + timedelta(days=3)).isoformat()
    in_four_days = (date.today() + timedelta(days=4)).isoformat()

    make_task(name="逾期任务", due_date=yesterday)
    make_task(name="今日到期任务", due_date=today)
    make_task(name="三天内到期任务", due_date=in_three_days)
    make_task(name="四天后到期任务", due_date=in_four_days)
    make_task(name="已完成旧任务", due_date=yesterday)

    completed_id = query_db(
        "SELECT id FROM tasks WHERE name = ?", ("已完成旧任务",)
    )[0]["id"]
    client.post(
        f"/tasks/{completed_id}/status",
        data={"status": "已完成"},
        follow_redirects=True,
    )

    body = client.get("/").get_data(as_text=True)

    overdue_row = table_row(body, "逾期任务")
    assert "逾期" in overdue_row

    today_row = table_row(body, "今日到期任务")
    assert "即将到期" in today_row

    three_day_row = table_row(body, "三天内到期任务")
    assert "即将到期" in three_day_row

    four_day_row = table_row(body, "四天后到期任务")
    assert "即将到期" not in four_day_row

    completed_row = table_row(body, "已完成旧任务")
    assert "逾期" not in completed_row
    assert "即将到期" not in completed_row


def test_statistics_total_completed_and_rate(client, make_task, query_db):
    for index in range(5):
        make_task(name=f"统计任务{index + 1}")

    task_ids = [row["id"] for row in query_db("SELECT id FROM tasks ORDER BY id")]
    for task_id in task_ids[:2]:
        client.post(
            f"/tasks/{task_id}/status",
            data={"status": "已完成"},
            follow_redirects=True,
        )

    body = client.get("/").get_data(as_text=True)

    assert re.search(
        r'<span class="stat-label">任务总数</span>\s*<strong>5</strong>', body
    )
    assert re.search(
        r'<span class="stat-label">已完成</span>\s*<strong>2</strong>', body
    )
    assert "40%" in body


def test_delete_requires_confirmation_and_cancel_keeps_task(
    client, make_task, query_db
):
    make_task(name="待删除任务")
    task_id = query_db("SELECT id FROM tasks")[0]["id"]

    confirmation = client.get(f"/tasks/{task_id}/delete")
    confirmation_body = confirmation.get_data(as_text=True)

    assert confirmation.status_code == 200
    assert "确认删除" in confirmation_body
    assert "待删除任务" in confirmation_body
    assert "取消" in confirmation_body
    assert len(query_db("SELECT * FROM tasks")) == 1

    cancel_response = client.get(f"/tasks/{task_id}")
    assert cancel_response.status_code == 200
    assert len(query_db("SELECT * FROM tasks")) == 1

    delete_response = client.post(
        f"/tasks/{task_id}/delete", follow_redirects=True
    )
    assert delete_response.status_code == 200
    assert "任务已删除" in delete_response.get_data(as_text=True)
    assert query_db("SELECT * FROM tasks") == []
    assert client.get(f"/tasks/{task_id}").status_code == 404


def test_missing_task_returns_404(client):
    for path in (
        "/tasks/999",
        "/tasks/999/edit",
        "/tasks/999/delete",
    ):
        response = client.get(path)
        assert response.status_code == 404
        assert "未找到该任务或页面" in response.get_data(as_text=True)


def test_data_persists_after_application_restart(tmp_path):
    database = str(tmp_path / "persistent.sqlite3")
    config = {
        "TESTING": True,
        "SECRET_KEY": "restart-test",
        "DATABASE": database,
    }

    first_app = create_app(config)
    with first_app.test_client() as first_client:
        response = first_client.post(
            "/tasks",
            data={
                "name": "重启后仍存在",
                "course": "软件工程",
                "description": "验证 SQLite 持久化",
                "due_date": (date.today() + timedelta(days=1)).isoformat(),
                "priority": "中",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

    second_app = create_app(config)
    with second_app.test_client() as second_client:
        body = second_client.get("/").get_data(as_text=True)
        detail_body = second_client.get("/tasks/1").get_data(as_text=True)

    assert "重启后仍存在" in body
    assert "验证 SQLite 持久化" in detail_body


def test_user_content_is_html_escaped(client, make_task):
    make_task(name='<script>alert("x")</script>', description="<b>描述</b>")

    body = client.get("/").get_data(as_text=True)

    assert "<script>alert" not in body
    assert "&lt;script&gt;alert" in body
    assert "<b>描述</b>" not in body