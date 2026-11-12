# StudyTask 个人学习任务管理系统

StudyTask 是一个单用户 Web 学习任务管理系统，用于记录课程作业、实验和考试准备等事项，可在本地运行，也可按课程要求临时部署到云服务器。功能范围严格对应《StudyTask 需求规格说明书》附录 A，不包含账号、多人协作、邮件/短信、日历同步或移动端 App。

**在线演示：<http://193.112.133.193:18080/>**

## 技术栈

- Python 3.11+（本机验证版本：Python 3.14.3）
- Flask 3.1.3
- SQLite（Python 标准库 `sqlite3`，无需安装数据库服务）
- pytest 9.2.0

## 功能范围

- 任务新建、列表、详情、编辑、删除（删除前有独立确认页面）
- 任务状态：待完成 / 进行中 / 已完成
- 按课程、状态、优先级单独或组合筛选
- 未完成任务逾期与即将到期提示
- 首页任务总数、已完成数、完成率统计
- SQLite 本地持久化，重启后数据保留
- 中文界面、字段级错误提示、输入长度与日期格式校验

## 实验一交付物

- [实验一报告（4 页）](docs/实验一报告.docx)
- [实验一演示 PPT（10 页）](docs/StudyTask-实验一演示.pptx)
- [需求验收表](docs/acceptance-checklist.md)
- [AI 开发过程记录](AI_DEV_LOG.md)
- 运行页面截图：[`docs/images/`](docs/images/)

## 云端访问

- 在线地址：<http://193.112.133.193:18080/>
- 服务器项目目录：`/opt/202-StudyTask`
- 监听端口：`18080`
- 访问验证：首页 `HTTP 200`，响应头 `Server: gunicorn`；`/static/style.css` 返回 `HTTP 200`，`/tasks/new` 返回 `HTTP 200`

该部署用于课程演示。系统没有登录和 CSRF 防护，演示结束后应停止服务，不能作为长期公网服务。

## 从零开始安装与启动

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

浏览器打开：<http://127.0.0.1:5000/>

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

数据库会在首次启动时自动创建于 `instance/studytask.sqlite3`，不需要手工执行建表命令，也不会写入演示数据。

如需重置本地数据：停止服务，删除 `instance/studytask.sqlite3`，再次启动即可。

也可以使用 Flask CLI 启动（不启用调试模式）：

```powershell
.venv\Scripts\flask.exe --app app run --port 5000
```

## 测试命令

仅执行 T1–T10 与补充验收用例 AC-01–AC-05：

```powershell
.venv\Scripts\python.exe -m pytest tests/test_acceptance.py -v
```

预期结果：`15 passed`。

执行全部验收与回归测试：

```powershell
.venv\Scripts\python.exe -m pytest -q
```

预期结果：`38 passed`。

测试使用 pytest 临时数据库，不会修改 `instance/studytask.sqlite3`。

## 验收清单与自动测试映射

| 编号 | 验收项 | 自动测试 | 结果 |
|---|---|---|---|
| T1 | 新建任务并显示在列表 | `test_acceptance.py::test_t01_create_task_and_show_in_list` | 通过 |
| T2 | 名称为空提交不产生脏数据 | `test_acceptance.py::test_t02_empty_name_rejected_without_dirty_data` | 通过 |
| T3 | 编辑描述与优先级后持久保存 | `test_acceptance.py::test_t03_edit_description_and_priority_persist` | 通过 |
| T4 | 待完成 → 进行中 → 已完成 | `test_acceptance.py::test_t04_status_transitions_are_saved` | 通过 |
| T5 | 课程、状态、优先级筛选 | `test_acceptance.py::test_t05_filters_by_course_status_and_priority` | 通过 |
| T6 | 昨日到期且未完成显示“逾期” | `test_acceptance.py::test_t06_yesterday_due_unfinished_is_overdue` | 通过 |
| T7 | 明日到期且未完成显示“即将到期” | `test_acceptance.py::test_t07_tomorrow_due_unfinished_is_due_soon` | 通过 |
| T8 | 5 项完成 2 项，总数 5、完成率 40% | `test_acceptance.py::test_t08_statistics_total_completed_and_rate` | 通过 |
| T9 | 删除取消不删除、确认后删除 | `test_acceptance.py::test_t09_delete_cancel_and_confirm` | 通过 |
| T10 | 重启应用后数据仍存在 | `test_acceptance.py::test_t10_data_persists_after_restart` | 通过 |

补充验收：AC-01 长度边界与非法日期；AC-02 默认值与可选描述；AC-03 已完成任务无提醒及 +3/+4 天边界；AC-04 三条件组合筛选；AC-05 非法编辑不覆盖原数据。

其他回归测试覆盖：必填字段、非法状态、404、HTML 转义等。

详细验收记录（输入、预期、实际结果和证据）见 [`docs/acceptance-checklist.md`](docs/acceptance-checklist.md)。

## 关键业务规则

- 名称必填，1–100 字；课程必填，1–60 字；描述可选，最多 1000 字。
- 截止日期必填，服务端严格校验 `YYYY-MM-DD` 且必须是真实日期。
- 优先级为高/中/低，默认中；新建任务状态固定为待完成。
- 未完成且截止日期早于今天：显示“逾期”。
- 未完成且截止日期在**今天至今天 +3 天（含首尾）**：显示“即将到期”。
- 已完成任务不显示逾期或即将到期提示；逾期提示优先于即将到期提示。
- 首页统计按**全部任务**计算，不随筛选条件变化。
- 删除必须进入确认页面，确认后使用 POST 删除；取消则保留任务。

## 目录结构

```text
StudyTask/
├─ app.py                     # 应用工厂、路由、校验与提醒逻辑
├─ db.py                      # SQLite 连接与初始化
├─ schema.sql                 # tasks 表结构与数据库约束
├─ templates/                 # 中文服务端渲染页面
├─ static/style.css           # 本地样式，无外部资源
├─ tests/                     # pytest 自动测试
│  ├─ test_acceptance.py      # T1–T10 与 AC-01–AC-05 验收测试
│  └─ test_studytask.py       # 其他回归测试
├─ docs/
│  ├─ acceptance-checklist.md # 需求验收表
│  ├─ 实验一报告.docx          # 实验报告（4 页）
│  ├─ StudyTask-实验一演示.pptx # 演示 PPT（10 页）
│  └─ images/                 # 真实运行截图
├─ requirements.txt
├─ pytest.ini
├─ README.md
└─ AI_DEV_LOG.md
```

## 已知限制

1. **单用户应用**：没有登录、权限和多用户数据隔离，符合 SRS A.5 范围外约定；课程演示可临时部署，但不能作为长期公网服务。
2. **无 CSRF Token**：本地无认证单用户场景未加入 CSRF 防护；如改为公网部署，需要同时补充认证、CSRF、HTTPS 等安全措施。
3. **日期规则**：仅处理日期，不含时间与时区；“即将到期”按服务器本地日期计算，范围为当天至未来第 3 天（含）。
4. **统计口径**：首页统计始终为全部任务，筛选后数字不变；筛选结果数量单独显示在列表下方。
5. **SQLite 与分页**：单文件数据库适合本地单用户和约 200 条任务；未实现分页，任务量极大时列表性能会下降。
6. **无数据导入/导出/云备份**：仅提供本地 SQLite 文件；备份需自行复制 `instance/studytask.sqlite3`。
7. **测试范围**：自动测试覆盖 HTTP 行为与页面内容；未引入真实浏览器端视觉回归测试，界面通过本地启动冒烟检查验证。
8. **删除不可恢复**：确认删除后直接物理删除，没有回收站或软删除。