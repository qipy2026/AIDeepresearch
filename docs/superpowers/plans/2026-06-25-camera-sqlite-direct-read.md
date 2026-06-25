# 摄像头数据源迁移：HTTP API → 直读 SQLite — 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将摄像头快照数据获取从 HTTP API 调用改为直读 search 项目的 SQLite 数据库 + 图片按需复制到本地 serve

**架构：** 直接连接 `counts.db`（只读 SELECT），2 条 SQL 替换 2 个 HTTP 请求；快照图片从 search 项目目录按需复制到本项目本地 `snapshot_data/`，通过 FastAPI 静态路由 serve

**技术栈：** Python 3.x, sqlite3 (stdlib), shutil, FastAPI FileResponse, pytest

**规格文档：** `docs/superpowers/specs/2026-06-25-camera-sqlite-direct-read-design.md`

---

## 文件结构

| 文件 | 职责 | 改动 |
|------|------|------|
| `.env` | 环境变量配置 | +3 行 |
| `.env.example` | 环境变量模板 | +3 行（带注释） |
| `services/reporter.py` | 重写 `_read_camera_snapshots()` + 新增 `_sync_snapshot_images()` | ~75 行 |
| `main.py` | 新增 `/snapshots/<fname>` 路由 | +15 行 |
| `tests/unit/test_video_trend.py` | 视频趋势测试 — mock 从 HTTP 改为 sqlite3 | ~50 行改动 |
| `tests/integration/test_weekly_report_pipeline.py` | 管道集成测试 — 确认 mock 兼容 | ~2 行改动 |

---

### 任务 1：新增环境变量

**文件：**
- 修改：`backend/.env`
- 修改：`backend/.env.example`

- [ ] **步骤 1：在 `.env` 中添加 CAMERA 环境变量**

在 `.env` 中 `# CAMERA_AI_WEBHOOK_SECRET=xxxxx` 行之后新增：

```bash
# 摄像头数据源（直读 search 项目 SQLite + 快照图片）
CAMERA_DB_PATH=E:\work\code\search\snapshot_data\counts.db
CAMERA_SNAPSHOT_SRC=E:\work\code\search\snapshot_data
CAMERA_SNAPSHOT_LOCAL=./snapshot_data
```

- [ ] **步骤 2：在 `.env.example` 末尾添加带注释的模板**

```bash
# -----------------------------------------------------------------------------
# 摄像头数据源（直读 search 项目 SQLite + 快照图片）
# -----------------------------------------------------------------------------
# CAMERA_DB_PATH=/path/to/search/snapshot_data/counts.db
# CAMERA_SNAPSHOT_SRC=/path/to/search/snapshot_data
# CAMERA_SNAPSHOT_LOCAL=./snapshot_data
```

- [ ] **步骤 3：验证环境变量可读取**

```bash
cd backend && python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('CAMERA_DB_PATH') or 'NOT SET')"
```
预期：`E:\work\code\search\snapshot_data\counts.db`

- [ ] **步骤 4：Commit**

```bash
git add backend/.env backend/.env.example
git commit -m "config: add CAMERA_DB_PATH / CAMERA_SNAPSHOT_SRC / CAMERA_SNAPSHOT_LOCAL env vars

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 2：重写 `_read_camera_snapshots()` + 新增 `_sync_snapshot_images()`

**文件：**
- 修改：`backend/src/services/reporter.py:180-243`（重写）
- 修改：`backend/src/services/reporter.py:178`（新增静态方法）
- 修改：`backend/src/tests/unit/test_video_trend.py`

- [ ] **步骤 1：编写失败测试**

在 `test_video_trend.py` 的 `TestReadCameraSnapshots` 类中新增 4 个测试：

```python
def test_reads_snapshots_from_sqlite(self, monkeypatch, tmp_path):
    """验证从 SQLite 读取数据后返回格式与原来 HTTP 版本一致"""
    import sqlite3

    db_path = tmp_path / "test_counts.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS counts (
            id INTEGER PRIMARY KEY,
            camera_id INTEGER NOT NULL,
            recorded_at TEXT NOT NULL,
            person_count INTEGER,
            snapshot_path TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        INSERT INTO counts (camera_id, recorded_at, person_count, snapshot_path, created_at)
        VALUES
        (1, '2026-06-24T14:30:00+00:00', 12, '', '2026-06-24 14:30:00'),
        (1, '2026-06-24T14:45:00+00:00', 8, '', '2026-06-24 14:45:00'),
        (1, '2026-06-24T15:00:00+00:00', NULL, '', '2026-06-24 15:00:00'),
        (2, '2026-06-24T14:00:00+00:00', 100, '', '2026-06-24 14:00:00')
    """)
    conn.commit()
    conn.close()

    monkeypatch.setenv("CAMERA_DB_PATH", str(db_path))
    monkeypatch.setenv("CAMERA_SNAPSHOT_SRC", str(tmp_path))
    monkeypatch.setenv("CAMERA_SNAPSHOT_LOCAL", str(tmp_path / "local_snapshots"))

    result = ReportingService._read_camera_snapshots("测试企业", weeks=4)

    assert len(result) == 2  # camera_id=1, person_count IS NOT NULL
    assert result[0]["snapshot_date"] == "2026-06-24T14"
    assert result[0]["headcount"] == 10  # AVG(12, 8) = 10
    assert result[0]["snapshot_path"] == ""

def test_returns_empty_on_db_missing(self, monkeypatch):
    """DB 路径不存在 → 返回空列表，不抛异常"""
    monkeypatch.setenv("CAMERA_DB_PATH", "/nonexistent/path/counts.db")
    result = ReportingService._read_camera_snapshots("测试企业", weeks=4)
    assert result == []

def test_sync_images_copies_files(self, monkeypatch, tmp_path):
    """图片从源目录复制到本地目录，snapshot_path 更新为文件名"""
    import sqlite3

    src_dir = tmp_path / "src_snapshots"
    src_dir.mkdir()
    img_file = src_dir / "snap_abc.jpg"
    img_file.write_bytes(b"fake jpeg data")

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE counts (
        id INTEGER PRIMARY KEY, camera_id INTEGER, recorded_at TEXT,
        person_count INTEGER, snapshot_path TEXT, created_at TEXT)""")
    conn.execute("""INSERT INTO counts VALUES
        (1, 1, '2026-06-24T14:00:00', 5, 'snapshot_data\\snap_abc.jpg', '2026-06-24 14:00:00')""")
    conn.commit()
    conn.close()

    local_dir = tmp_path / "local_snapshots"

    monkeypatch.setenv("CAMERA_DB_PATH", str(db_path))
    monkeypatch.setenv("CAMERA_SNAPSHOT_SRC", str(src_dir))
    monkeypatch.setenv("CAMERA_SNAPSHOT_LOCAL", str(local_dir))

    result = ReportingService._read_camera_snapshots("test", weeks=4)

    copied = local_dir / "snap_abc.jpg"
    assert copied.exists()
    assert copied.read_bytes() == b"fake jpeg data"
    assert "snap_abc.jpg" in result[0]["snapshot_path"]

def test_sync_images_skips_when_src_missing(self, monkeypatch, tmp_path):
    """源目录不存在时图片跳过，不阻塞报告生成"""
    import sqlite3

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE counts (
        id INTEGER PRIMARY KEY, camera_id INTEGER, recorded_at TEXT,
        person_count INTEGER, snapshot_path TEXT, created_at TEXT)""")
    conn.execute("""INSERT INTO counts VALUES
        (1, 1, '2026-06-24T14:00:00', 5, 'snapshot_data\\snap_missing.jpg', '2026-06-24 14:00:00')""")
    conn.commit()
    conn.close()

    monkeypatch.setenv("CAMERA_DB_PATH", str(db_path))
    monkeypatch.setenv("CAMERA_SNAPSHOT_SRC", "/nonexistent/src_dir")
    monkeypatch.setenv("CAMERA_SNAPSHOT_LOCAL", str(tmp_path / "local"))

    result = ReportingService._read_camera_snapshots("test", weeks=4)
    assert len(result) == 1
    assert result[0]["snapshot_path"] == ""
```

- [ ] **步骤 2：运行新增测试验证失败**

```bash
cd backend && PYTHONPATH=src python -m pytest src/tests/unit/test_video_trend.py::TestReadCameraSnapshots::test_reads_snapshots_from_sqlite src/tests/unit/test_video_trend.py::TestReadCameraSnapshots::test_returns_empty_on_db_missing src/tests/unit/test_video_trend.py::TestReadCameraSnapshots::test_sync_images_copies_files src/tests/unit/test_video_trend.py::TestReadCameraSnapshots::test_sync_images_skips_when_src_missing -v
```
预期：全部 FAIL（`_read_camera_snapshots` 仍用 HTTP，`_sync_snapshot_images` 不存在）

- [ ] **步骤 3a：重写 `_read_camera_snapshots()`**

将 `reporter.py:180-243` 整段替换为：

```python
    @staticmethod
    def _read_camera_snapshots(enterprise: str, weeks: int = 4) -> List[Dict[str, Any]]:
        """读取企业指定周数内的摄像头快照人数数据。

        从 search 项目的 SQLite 数据库（counts.db）直接读取，
        不再依赖 search 项目 HTTP API。DB 不可用或配置缺失时优雅降级，返回空列表。

        enterprise 参数当前未使用——单摄场景下所有企业共享同一摄像头数据。
        保留此参数以便后续多摄像头对应多企业时按 enterprise 筛选 camera_id。
        """
        import sqlite3
        from contextlib import closing

        db_path = os.getenv("CAMERA_DB_PATH", "")
        if not db_path:
            logger.warning("CAMERA_DB_PATH 未配置，摄像头数据不可用")
            return []

        try:
            with closing(sqlite3.connect(db_path)) as conn:
                conn.row_factory = sqlite3.Row

                # 1. 聚合时序数据（替代 /api/counts/timeseries?camera_id=1&days=N）
                rows = conn.execute(
                    """SELECT
                         strftime('%Y-%m-%dT%H', recorded_at) AS bucket,
                         AVG(person_count) AS avg_count
                       FROM counts
                       WHERE camera_id = 1
                         AND recorded_at >= datetime('now', '-' || ? || ' days')
                         AND person_count IS NOT NULL
                       GROUP BY bucket
                       ORDER BY bucket""",
                    (weeks * 7,),
                ).fetchall()

                result = [
                    {
                        "snapshot_date": row["bucket"],
                        "headcount": round(row["avg_count"]),
                        "snapshot_path": "",
                    }
                    for row in rows
                ]

                # 2. 原始快照记录（替代 /api/counts/timeseries?bucket=raw&from=...）
                from datetime import datetime as _dt, timedelta as _td, timezone as _tz
                from_ts = (_dt.now(_tz.utc) - _td(days=weeks * 7)).strftime("%Y-%m-%d")
                raw_rows = conn.execute(
                    """SELECT recorded_at AS timestamp, person_count, snapshot_path
                       FROM counts
                       WHERE camera_id = 1
                         AND recorded_at >= ?
                         AND snapshot_path != ''
                         AND person_count IS NOT NULL
                       ORDER BY recorded_at DESC""",
                    (from_ts,),
                ).fetchall()

                if raw_rows:
                    snapshots = [dict(r) for r in raw_rows]
                    ReportingService._attach_key_snapshots(result, snapshots)

                    # 3. 图片按需同步
                    ReportingService._sync_snapshot_images(result)

                return result
        except (sqlite3.Error, sqlite3.DatabaseError) as _e:
            logger.warning(
                "摄像头 SQLite 数据库读取失败，企业={}，DB={}，错误={}，降级为空数据",
                enterprise, db_path, _e,
            )
            return []
        except FileNotFoundError as _e:
            logger.warning(
                "摄像头 SQLite 数据库文件不存在，企业={}，DB={}，错误={}",
                enterprise, db_path, _e,
            )
            return []
```

- [ ] **步骤 3b：新增 `_sync_snapshot_images()`**

在 `_attach_key_snapshots` 方法之后（约第 178 行），新增：

```python
    @staticmethod
    def _sync_snapshot_images(snapshots: List[Dict[str, Any]]) -> None:
        """将快照图片从 search 项目目录按需复制到本项目本地目录。

        仅复制尚不存在的文件；源不可达或复制失败时清空该记录的 snapshot_path，
        不阻塞报告生成。
        """
        import shutil

        src_dir = os.getenv("CAMERA_SNAPSHOT_SRC", "")
        local_dir = os.getenv("CAMERA_SNAPSHOT_LOCAL", "./snapshot_data")

        if not src_dir:
            logger.warning("CAMERA_SNAPSHOT_SRC 未配置，跳过图片同步")
            for s in snapshots:
                s["snapshot_path"] = ""
            return

        # 确保本地目录存在
        Path(local_dir).mkdir(parents=True, exist_ok=True)

        for s in snapshots:
            sp = s.get("snapshot_path", "")
            if not sp:
                continue

            # 提取文件名（兼容 Windows \ 和 POSIX /）
            fname = sp.replace("\\", "/").split("/")[-1]
            src_path = Path(src_dir) / fname

            if not src_path.exists():
                logger.warning("快照图片源文件不存在: {}，跳过", src_path)
                s["snapshot_path"] = ""
                continue

            dst_path = Path(local_dir) / fname
            if not dst_path.exists():
                try:
                    shutil.copy2(str(src_path), str(dst_path))
                    logger.debug("快照图片已复制: {} -> {}", src_path, dst_path)
                except (OSError, shutil.Error) as _e:
                    logger.warning("快照图片复制失败: {} -> {}, 错误={}", src_path, dst_path, _e)
                    s["snapshot_path"] = ""
                    continue

            # 更新为可 serve 的路径（只要文件名，路由会拼接本地目录）
            s["snapshot_path"] = fname
```

- [ ] **步骤 4：运行新增测试验证通过**

```bash
cd backend && PYTHONPATH=src python -m pytest src/tests/unit/test_video_trend.py::TestReadCameraSnapshots::test_reads_snapshots_from_sqlite src/tests/unit/test_video_trend.py::TestReadCameraSnapshots::test_returns_empty_on_db_missing src/tests/unit/test_video_trend.py::TestReadCameraSnapshots::test_sync_images_copies_files src/tests/unit/test_video_trend.py::TestReadCameraSnapshots::test_sync_images_skips_when_src_missing -v
```
预期：4 PASS

- [ ] **步骤 5：Commit**

```bash
git add backend/src/services/reporter.py backend/src/tests/unit/test_video_trend.py
git commit -m "refactor: rewrite _read_camera_snapshots() to read SQLite directly + add _sync_snapshot_images()

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 3：新增 `/snapshots/<fname>` 静态路由

**文件：**
- 修改：`backend/src/main.py`

- [ ] **步骤 1：在 `main.py` 中添加路由**

在 `create_app()` 函数中，Vue SPA 挂载代码之后（约第 112 行），`@app.on_event("startup")` 之前，插入：

```python
    # 快照图片静态路由（从 search 项目复制到本地的摄像头快照）
    _snapshot_dir = _P(__file__).parent.parent / os.getenv("CAMERA_SNAPSHOT_LOCAL", "snapshot_data")
    _snapshot_dir.mkdir(parents=True, exist_ok=True)

    @app.get("/snapshots/{filename}")
    def serve_snapshot(filename: str):
        """Serve local snapshot images (copied from search project)."""
        from fastapi.responses import FileResponse
        file_path = _snapshot_dir / filename
        if not file_path.exists():
            raise HTTPException(404, f"Snapshot not found: {filename}")
        return FileResponse(str(file_path))
```

- [ ] **步骤 2：验证路由可访问**

```bash
mkdir -p backend/snapshot_data
echo "test" > backend/snapshot_data/test.txt
curl http://localhost:8080/snapshots/test.txt
```
预期：返回 `test`

- [ ] **步骤 3：Commit**

```bash
git add backend/src/main.py
git commit -m "feat: add /snapshots/<fname> route to serve local camera snapshots

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 4：清理 & 更新旧测试

**文件：**
- 修改：`backend/src/services/reporter.py`（移除 `requests` import）
- 修改：`backend/src/tests/unit/test_video_trend.py`（更新 3 个旧测试）

- [ ] **步骤 1：检查 `requests` 是否还用于其他方法**

```bash
cd backend && grep -n "requests\." backend/src/services/reporter.py
```
如无匹配结果（`requests` 仅用于已删除的 HTTP 调用），则移除第 11 行 `import requests`。

- [ ] **步骤 2：更新旧测试 — HTTP mock → sqlite3 mock**

3 个旧测试需要更新或删除：

**删除** `test_graceful_degradation_on_connection_error`（场景已被 `test_returns_empty_on_db_missing` 覆盖）。

**重写** `test_params_passed_correctly` 为：

```python
def test_aggregated_fields_mapped_correctly(self, monkeypatch, tmp_path):
    """验证 SQLite 返回后字段映射正确（bucket → snapshot_date, avg_count → headcount）"""
    import sqlite3

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE counts (
        id INTEGER PRIMARY KEY, camera_id INTEGER, recorded_at TEXT,
        person_count INTEGER, snapshot_path TEXT, created_at TEXT)""")
    conn.execute("""INSERT INTO counts VALUES
        (1, 1, '2026-06-24T14:30:00+00:00', 13, '', '2026-06-24 14:30:00'),
        (2, 1, '2026-06-24T14:45:00+00:00', 12, '', '2026-06-24 14:45:00')""")
    conn.commit()
    conn.close()

    monkeypatch.setenv("CAMERA_DB_PATH", str(db_path))
    monkeypatch.setenv("CAMERA_SNAPSHOT_SRC", str(tmp_path))
    monkeypatch.setenv("CAMERA_SNAPSHOT_LOCAL", str(tmp_path / "local"))

    result = ReportingService._read_camera_snapshots("test", weeks=4)

    assert len(result) == 1
    assert result[0]["snapshot_date"] == "2026-06-24T14"
    assert result[0]["headcount"] == 12  # round(AVG(13, 12)) = round(12.5) = 12
    assert result[0]["snapshot_path"] == ""
```

**删除** `test_null_avg_count_skipped`（场景已被 `test_reads_snapshots_from_sqlite` 中的 NULL 行覆盖）。

- [ ] **步骤 3：运行全量视频趋势测试**

```bash
cd backend && PYTHONPATH=src python -m pytest src/tests/unit/test_video_trend.py -v
```
预期：全部 PASS（新增 4 + 保留 1 + 趋势 7 + 快照 3 + 注入 3 = ~18 个测试）

- [ ] **步骤 4：运行全量单元测试**

```bash
cd backend && PYTHONPATH=src python -m pytest src/tests/unit/ -v
```
预期：全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add backend/src/services/reporter.py backend/src/tests/unit/test_video_trend.py
git commit -m "chore: remove unused requests import, update old video trend tests

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 5：全量验证 + 真实报告测试

- [ ] **步骤 1：运行全量单元测试**

```bash
cd backend && PYTHONPATH=src python -m pytest src/tests/unit/ -v
```
预期：全部 PASS

- [ ] **步骤 2：运行集成测试**

```bash
cd backend && PYTHONPATH=src python -m pytest src/tests/integration/ -v
```
预期：非 skip 测试全部 PASS

- [ ] **步骤 3：生成真实报告验证**

```bash
# 确保服务在运行
curl -s http://localhost:8080/healthz

# 生成报告
python -c "
import urllib.request, json
body = json.dumps({'topic': '成都瑜璟物业服务有限公司 周报'}).encode('utf-8')
req = urllib.request.Request('http://localhost:8080/research', data=body,
    headers={'Content-Type': 'application/json; charset=utf-8'}, method='POST')
resp = urllib.request.urlopen(req)
report = json.loads(resp.read().decode('utf-8'))['report_markdown']
# 关键检查
assert '发放金额：未披露' in report, 'loan_amount display broken'
assert '[甲方名称]' not in report, 'template placeholder still present'
# 摄像头数据：如果 search 项目之前采集过数据，应能看到人数；
# 如果 DB 为空则仍会显示「数据不足」，但不应崩溃
assert '视频巡检' in report, 'missing video inspection section'
print(f'OK: Report {len(report)} chars')
"
```
预期：`OK: Report XXXX chars`

- [ ] **步骤 4：检查报告中的摄像头数据**

```bash
python -c "
import urllib.request, json
body = json.dumps({'topic': '成都瑜璟物业服务有限公司 周报'}).encode('utf-8')
req = urllib.request.Request('http://localhost:8080/research', data=body,
    headers={'Content-Type': 'application/json; charset=utf-8'}, method='POST')
report = json.loads(resp.read().decode('utf-8'))['report_markdown']
if '数据不足' in report and '暂无法生成趋势' in report:
    print('INFO: counts.db 暂无该企业数据（search 项目可能未采集过此企业）')
elif '视频巡检人数' in report and '人' in report:
    print('OK: 人数趋势数据已成功注入报告')
else:
    print('CHECK: 请手动确认报告第四部分内容')
"
```

- [ ] **步骤 5：停止服务 & 最终 Commit**

```bash
# 如有残余变更
git status
git add -A
git commit -m "chore: final cleanup after camera SQLite migration verification

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 验证清单

所有任务完成后，执行最终验证：

```bash
# 全量测试
cd backend && PYTHONPATH=src python -m pytest src/tests/unit/ src/tests/integration/ -v

# 确认 CAMERA_DB_PATH 配置存在
cd backend && grep -n "CAMERA_DB_PATH" .env

# 确认 HTTP 摄像头调用已移除
cd backend && grep -n "CAMERA_API_URL\|localhost:5000" src/services/reporter.py
# 预期：无输出

# 确认 sqlite3 使用存在
cd backend && grep -n "sqlite3.connect" src/services/reporter.py
# 预期：有输出

# 确认 /snapshots 路由存在
cd backend && grep -n "/snapshots" src/main.py
# 预期：有输出
```
