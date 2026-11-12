"""
实验一最低验收用例 T1–T10 及补充验收用例 AC-01–AC-05。

运行：
    .venv\\Scripts\\python.exe -m pytest tests/test_acceptance.py -v
"""

import re
from datetime import date, timedelta

from app import create_app


def day(offset):
    return (date.today() + timedelta(days=offset)).isoformat()


def valid_payload(**overrides):
    data = {
        "name": "验收任务",
        "course": "软件工程",
        "description": "验收测试描述",
        "due_date": day(1),
        "priority": "中",
    }
    data.update(overrides)
    return data


def table_row(html, task_name):
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S):
        if task_name in row:
            return row
    raise AssertionError(f"未在页面中找到任务行：{task_name}")


def test_t01_create_task_and_show_in_list(client, make_task, query_db):
    """T1：新建课程“数据结构”、明天截止、高优先级任务，列表显示新增任务。"""
    response = make_task(
        name="T1 数据结构作业",
        course="数据结构",
        description="链表实验报告",
        due_date=day(1),
        priority="高",
    )

    assert response.status_code == 200
    detail_body = response.get_data(as_text=True)
    assert "任务已创建" in detail_body
    assert "T1 数据结构作业" in detail_body

    rows = query_db("SELECT * FROM tasks")
    assert len(rows) == 1
    task = rows[0]
    assert task["course"] == "数据结构"
    assert task["due_date"] == day(1)
    assert task["priority"] == "高"
    assert task["status"] == "待完成"

    list_body = client.get("/").get_data(as_text=True)
    assert "T1 数据结构作业" in list_body
    assert "数据结构" in list_body
    assert day(1) in list_body


def test_t02_empty_name_rejected_without_dirty_data(client, query_db):
    """T2：名称为空提交新任务，提示错误且不产生脏数据。"""
    response = client.post("/tasks", data=valid_payload(name="   "))

    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "请输入任务名称" in body
    assert query_db("SELECT * FROM tasks") == []


def test_t03_edit_description_and_priority_persist(
    client, make_task, query_db, fetch_task
):
    """T3：修改任务描述与优先级，修改成功且刷新后保留。"""
    make_task(name="T3 待修改任务", description="旧描述", priority="中")
    task_id = query_db("SELECT id FROM tasks")[0]["id"]

    response = client.post(
        f"/tasks/{task_id}/edit",
        data={
            "name": "T3 待修改任务",
            "course": "数据结构",
            "description": "T3 新描述",
            "due_date": day(2),
            "priority": "低",
            "status": "待完成",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "任务已更新" in response.get_data(as_text=True)

    task = fetch_task(task_id)
    assert task["description"] == "T3 新描述"
    assert task["priority"] == "低"

    refreshed_body = client.get(f"/tasks/{task_id}").get_data(as_text=True)
    assert "T3 新描述" in refreshed_body
    assert "低" in refreshed_body


def test_t04_status_transitions_are_saved(client, make_task, query_db, fetch_task):
    """T4：待完成 → 进行中 → 已完成，状态逐次正确更新。"""
    make_task(name="T4 状态流转任务")
    task_id = query_db("SELECT id FROM tasks")[0]["id"]
    assert fetch_task(task_id)["status"] == "待完成"

    for status in ("进行中", "已完成"):
        response = client.post(
            f"/tasks/{task_id}/status",
            data={"status": status},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert f"任务状态已更新为“{status}”" in response.get_data(as_text=True)
        assert fetch_task(task_id)["status"] == status


def test_t05_filters_by_course_status_and_priority(
    client, make_task, query_db
):
    """T5：分别按课程、状态和优先级筛选，结果只包含匹配任务。"""
    make_task(name="T5 数据结构待完成", course="数据结构", priority="高")
    make_task(name="T5 数据结构已完成", course="数据结构", priority="低")
    make_task(name="T5 数据库待完成", course="数据库原理", priority="高")

    completed_id = query_db(
        "SELECT id FROM tasks WHERE name = ?", ("T5 数据结构已完成",)
    )[0]["id"]
    client.post(
        f"/tasks/{completed_id}/status",
        data={"status": "已完成"},
        follow_redirects=True,
    )

    course_body = client.get(
        "/", query_string={"course": "数据结构"}
    ).get_data(as_text=True)
    assert "T5 数据结构待完成" in course_body
    assert "T5 数据结构已完成" in course_body
    assert "T5 数据库待完成" not in course_body

    status_body = client.get(
        "/", query_string={"status": "已完成"}
    ).get_data(as_text=True)
    assert "T5 数据结构已完成" in status_body
    assert "T5 数据结构待完成" not in status_body
    assert "T5 数据库待完成" not in status_body

    priority_body = client.get(
        "/", query_string={"priority": "高"}
    ).get_data(as_text=True)
    assert "T5 数据结构待完成" in priority_body
    assert "T5 数据库待完成" in priority_body
    assert "T5 数据结构已完成" not in priority_body


def test_t06_yesterday_due_unfinished_is_overdue(client, make_task):
    """T6：新增昨日到期且未完成的任务，显示逾期标识。"""
    make_task(name="T6 昨日到期任务", due_date=day(-1), priority="中")

    body = client.get("/").get_data(as_text=True)
    row = table_row(body, "T6 昨日到期任务")
    assert "逾期" in row


def test_t07_tomorrow_due_unfinished_is_due_soon(client, make_task):
    """T7：新增明日到期且未完成的任务，显示即将到期标识。"""
    make_task(name="T7 明日到期任务", due_date=day(1), priority="中")

    body = client.get("/").get_data(as_text=True)
    row = table_row(body, "T7 明日到期任务")
    assert "即将到期" in row


def test_t08_statistics_total_completed_and_rate(
    client, make_task, query_db
):
    """T8：创建 5 项、完成 2 项，显示总数 5、完成数 2、完成率 40%。"""
    for index in range(1, 6):
        make_task(name=f"T8 统计任务{index}")

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
    assert re.search(
        r'<span class="stat-label">完成率</span>\s*<strong>40%</strong>', body
    )


def test_t09_delete_cancel_and_confirm(client, make_task, query_db):
    """T9：删除一项任务并取消/确认操作，取消不删除、确认后删除。"""
    make_task(name="T9 待删除任务")
    task_id = query_db("SELECT id FROM tasks")[0]["id"]

    confirmation = client.get(f"/tasks/{task_id}/delete")
    assert confirmation.status_code == 200
    assert "确认删除" in confirmation.get_data(as_text=True)
    assert len(query_db("SELECT * FROM tasks")) == 1

    # 取消：返回详情页，不执行删除。
    cancel = client.get(f"/tasks/{task_id}")
    assert cancel.status_code == 200
    assert len(query_db("SELECT * FROM tasks")) == 1

    # 确认：提交删除表单，任务从数据库移除。
    deleted = client.post(f"/tasks/{task_id}/delete", follow_redirects=True)
    assert deleted.status_code == 200
    assert "任务已删除" in deleted.get_data(as_text=True)
    assert query_db("SELECT * FROM tasks") == []
    assert client.get(f"/tasks/{task_id}").status_code == 404


def test_t10_data_persists_after_restart(tmp_path):
    """T10：关闭并重新启动系统，已保存数据仍可查询。"""
    database = str(tmp_path / "t10-persistence.sqlite3")
    config = {
        "TESTING": True,
        "SECRET_KEY": "t10-test",
        "DATABASE": database,
    }

    first_app = create_app(config)
    with first_app.test_client() as first_client:
        response = first_client.post(
            "/tasks",
            data=valid_payload(
                name="T10 重启保留任务",
                description="重启后仍可查询",
            ),
            follow_redirects=True,
        )
        assert response.status_code == 200

    second_app = create_app(config)
    with second_app.test_client() as second_client:
        list_body = second_client.get("/").get_data(as_text=True)
        detail_body = second_client.get("/tasks/1").get_data(as_text=True)

    assert "T10 重启保留任务" in list_body
    assert "重启后仍可查询" in detail_body


def test_ac01_length_boundaries_and_invalid_dates(client, query_db):
    """AC-01：长度边界与非法日期校验，不合规输入不写库。"""
    max_length = client.post(
        "/tasks",
        data=valid_payload(
            name="名" * 100,
            course="课" * 60,
            description="描" * 1000,
        ),
        follow_redirects=True,
    )
    assert max_length.status_code == 200
    assert "任务已创建" in max_length.get_data(as_text=True)
    assert len(query_db("SELECT * FROM tasks")) == 1

    invalid_cases = [
        ({"name": "名" * 101}, "100"),
        ({"course": "课" * 61}, "60"),
        ({"description": "描" * 1001}, "1000"),
        ({"due_date": "2026-02-30"}, "截止日期"),
        ({"due_date": "2026/11/13"}, "截止日期"),
    ]
    for overrides, message in invalid_cases:
        response = client.post("/tasks", data=valid_payload(**overrides))
        assert response.status_code == 400
        assert message in response.get_data(as_text=True)

    assert len(query_db("SELECT * FROM tasks")) == 1


def test_ac02_defaults_and_optional_description(client, query_db):
    """AC-02：描述可选；优先级默认中；新建状态默认待完成；时间戳自动生成。"""
    payload = {
        "name": "AC-02 默认值任务",
        "course": "软件工程",
        "due_date": day(1),
    }
    response = client.post("/tasks", data=payload, follow_redirects=True)

    assert response.status_code == 200
    task = query_db("SELECT * FROM tasks")[0]
    assert task["description"] == ""
    assert task["priority"] == "中"
    assert task["status"] == "待完成"
    assert task["created_at"]
    assert task["updated_at"]


def test_ac03_completed_task_has_no_reminder_and_due_soon_boundary(
    client, make_task, query_db
):
    """AC-03：已完成任务不显示提醒；+3 天提示，+4 天不提示。"""
    make_task(name="AC-03 已完成旧任务", due_date=day(-1))
    make_task(name="AC-03 三天内任务", due_date=day(3))
    make_task(name="AC-03 四天后任务", due_date=day(4))

    completed_id = query_db(
        "SELECT id FROM tasks WHERE name = ?", ("AC-03 已完成旧任务",)
    )[0]["id"]
    client.post(
        f"/tasks/{completed_id}/status",
        data={"status": "已完成"},
        follow_redirects=True,
    )

    body = client.get("/").get_data(as_text=True)

    completed_row = table_row(body, "AC-03 已完成旧任务")
    assert "逾期" not in completed_row
    assert "即将到期" not in completed_row

    three_day_row = table_row(body, "AC-03 三天内任务")
    assert "即将到期" in three_day_row

    four_day_row = table_row(body, "AC-03 四天后任务")
    assert "即将到期" not in four_day_row


def test_ac04_combined_filters_are_accurate(client, make_task, query_db):
    """AC-04：课程 + 状态 + 优先级组合筛选准确。"""
    make_task(name="AC-04 目标任务", course="软件工程", priority="高")
    make_task(name="AC-04 状态不符", course="软件工程", priority="高")
    make_task(name="AC-04 课程不符", course="数据库原理", priority="高")
    make_task(name="AC-04 优先级不符", course="软件工程", priority="低")

    completed_id = query_db(
        "SELECT id FROM tasks WHERE name = ?", ("AC-04 状态不符",)
    )[0]["id"]
    client.post(
        f"/tasks/{completed_id}/status",
        data={"status": "已完成"},
        follow_redirects=True,
    )

    body = client.get(
        "/",
        query_string={
            "course": "软件工程",
            "status": "待完成",
            "priority": "高",
        },
    ).get_data(as_text=True)

    assert "AC-04 目标任务" in body
    assert "AC-04 状态不符" not in body
    assert "AC-04 课程不符" not in body
    assert "AC-04 优先级不符" not in body


def test_ac05_invalid_edit_does_not_overwrite_existing_data(
    client, make_task, query_db, fetch_task
):
    """AC-05：编辑提交非法数据时提示错误，原有数据保持完整。"""
    make_task(
        name="AC-05 原任务",
        course="软件工程",
        description="原描述",
        due_date=day(2),
        priority="高",
    )
    task_id = query_db("SELECT id FROM tasks")[0]["id"]

    response = client.post(
        f"/tasks/{task_id}/edit",
        data={
            "name": "",
            "course": "被覆盖课程",
            "description": "被覆盖描述",
            "due_date": day(5),
            "priority": "低",
            "status": "已完成",
        },
    )

    assert response.status_code == 400
    assert "请输入任务名称" in response.get_data(as_text=True)

    task = fetch_task(task_id)
    assert task["name"] == "AC-05 原任务"
    assert task["course"] == "软件工程"
    assert task["description"] == "原描述"
    assert task["due_date"] == day(2)
    assert task["priority"] == "高"
    assert task["status"] == "待完成"