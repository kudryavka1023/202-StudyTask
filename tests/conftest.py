from datetime import date, timedelta

import pytest

from app import create_app
from db import get_db


@pytest.fixture
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE": str(tmp_path / "studytask-test.sqlite3"),
        }
    )
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_task(client):
    def _make_task(**overrides):
        data = {
            "name": "完成数据结构实验",
            "course": "数据结构",
            "description": "完成链表实验报告",
            "due_date": (date.today() + timedelta(days=1)).isoformat(),
            "priority": "高",
        }
        data.update(overrides)
        return client.post("/tasks", data=data, follow_redirects=True)

    return _make_task


@pytest.fixture
def query_db(app):
    def _query(sql, params=()):
        with app.app_context():
            rows = get_db().execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    return _query


@pytest.fixture
def fetch_task(query_db):
    def _fetch_task(task_id):
        rows = query_db("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return rows[0] if rows else None

    return _fetch_task