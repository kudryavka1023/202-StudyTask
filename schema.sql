CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    course TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    due_date TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT '中'
        CHECK (priority IN ('高', '中', '低')),
    status TEXT NOT NULL DEFAULT '待完成'
        CHECK (status IN ('待完成', '进行中', '已完成')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (length(name) BETWEEN 1 AND 100),
    CHECK (length(course) BETWEEN 1 AND 60),
    CHECK (length(description) <= 1000),
    CHECK (due_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]')
);
