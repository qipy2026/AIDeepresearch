# 摄像头数据源：从 HTTP API 迁移到直读 SQLite — 设计文档

日期：2026-06-25　|　状态：已确认　|　方案：B（直读 SQLite + 本地图片）

## 一、背景与问题

贷后监管综合周报的「视频巡检人数趋势」和「关键时刻快照」数据当前完全依赖 HTTP 调用 search 项目（摄像头 + YOLO）的 API。search 项目未启动时，`_read_camera_snapshots()` 无法获取任何数据，报告中出现「数据不足（无摄像头数据）」的空洞。

search 项目的 SQLite 数据库（`counts.db`）和快照图片均存储在本机磁盘上，本项目完全可以直接读取，无需依赖 search 进程运行。

## 二、方案

完全去掉 HTTP 调用，改为：
- **直读 counts.db**：2 条 SQL 替换原本 2 个 HTTP 请求
- **图片按需复制**：将 search 项目 `snapshot_data/` 目录下的图片复制到本项目本地目录
- **本地静态路由 serve**：新增 `/snapshots/<fname>` 端点 serve 本地图片

```
之前:  reporter ──HTTP──► search:5000 (API + 图片)
之后:  reporter ──SQL──► counts.db (只读)
        reporter ──file copy──► 本地 snapshot_data/
        main.py  ──serve──► /snapshots/<fname>
```

## 三、环境变量

```bash
# 新增 3 个环境变量
CAMERA_DB_PATH=E:\work\code\search\snapshot_data\counts.db  # SQLite 数据库路径
CAMERA_SNAPSHOT_SRC=E:\work\code\search\snapshot_data       # 图片源目录
CAMERA_SNAPSHOT_LOCAL=./snapshot_data                        # 本项目本地缓存目录
```

## 四、详细设计

### 4.1 `_read_camera_snapshots()` 重写

位置：`reporter.py:180-243`

**之前**：通过 `requests.get()` 调用 2 个 HTTP 端点
**之后**：`sqlite3.connect(CAMERA_DB_PATH)` 打开连接（只执行 SELECT，不写入），执行 2 条 SQL：

**SQL 1 — 聚合时序数据**（替代 `GET /api/counts/timeseries?camera_id=1&days=28`）：

```sql
SELECT
  strftime('%Y-%m-%dT%H', recorded_at) AS bucket,
  AVG(person_count) AS avg_count
FROM counts
WHERE camera_id = 1
  AND recorded_at >= datetime('now', '-' || ? || ' days')
  AND person_count IS NOT NULL
GROUP BY bucket
ORDER BY bucket
```

**SQL 2 — 原始快照记录**（替代 `GET /api/counts/timeseries?camera_id=1&bucket=raw&from=...`）：

```sql
SELECT recorded_at AS timestamp, person_count, snapshot_path
FROM counts
WHERE camera_id = 1
  AND recorded_at >= ?
  AND snapshot_path != ''
  AND person_count IS NOT NULL
ORDER BY recorded_at DESC
```

返回格式与当前完全一致（`List[Dict]`），下游方法无需修改：
```python
[
  {"snapshot_date": "2026-06-24T14", "headcount": 8, "snapshot_path": ""},
  ...
]
```

### 4.2 图片同步

新增 `_sync_snapshot_images(snapshots: List[Dict]) -> None`：

- 遍历快照记录的 `snapshot_path` 字段
- 提取文件名（`\` → `/` 统一处理）
- 检查本地 `CAMERA_SNAPSHOT_LOCAL/<fname>` 是否已存在
- 不存在 → `shutil.copy2(src, dst)` 从源目录复制
- 复制失败或源不可达 → `snapshot_path` 置空，`log.warning`
- 更新 `snapshot_path` 为本项目可 serve 的路径

### 4.3 静态图片路由

在 `main.py` 中新增：

```python
_snapshot_dir = Path(os.getenv("CAMERA_SNAPSHOT_LOCAL", "./snapshot_data"))
_snapshot_dir.mkdir(parents=True, exist_ok=True)

@app.get("/snapshots/{filename}")
def serve_snapshot(filename: str):
    """Serve local snapshot images (copied from search project)."""
    file_path = _snapshot_dir / filename
    if not file_path.exists():
        raise HTTPException(404, "Snapshot not found")
    return FileResponse(file_path)
```

### 4.4 错误处理矩阵

| 场景 | 行为 |
|------|------|
| `CAMERA_DB_PATH` 未配置 | `log.warning` → 返回空列表（向后兼容） |
| DB 文件不存在或不可读 | `log.warning` → 返回空列表 |
| DB 被 WAL 锁定 | SQLite 的 WAL 模式自动处理（读写不互斥） |
| 图片源目录不可达 | 跳过图片复制，相关 `snapshot_path` 置空 |
| 单个图片复制失败 | 跳过该图片，不阻塞报告生成 |
| DB 中无数据 | 返回空列表，趋势计算走 `insufficient` 分支 |

### 4.5 连接管理

每次调用 `_read_camera_snapshots()` 时：
1. `sqlite3.connect(db_path)` 打开连接
2. `conn.row_factory = sqlite3.Row` 按列名访问
3. 查询完后 `conn.close()`
4. 使用 context manager（`with closing(conn):`）确保连接关闭，即使查询异常也能释放

不用连接池——调用频率极低（每次生成报告调用 1-2 次），简单 open + close 即可。

## 五、影响范围

| 文件 | 改动量 | 类型 |
|------|--------|------|
| `.env` | +3 行 | 新增环境变量 |
| `.env.example` | +3 行 | 同步模板 |
| `reporter.py` `_read_camera_snapshots()` | ~50 行重写 | 替换 HTTP 为 SQLite |
| `reporter.py` | +25 行 | 新增 `_sync_snapshot_images()` |
| `main.py` | +15 行 | 新增 `/snapshots/<fname>` 路由 |
| `test_weekly_context.py` | ~15 行修改 | Mock 从 HTTP 改为 sqlite3 |
| `test_weekly_report_pipeline.py` | ~10 行修改 | 同上 |
| **总计** | **~120 行** | **集中在 4 个文件** |

## 六、不需要改的部分

- `_compute_headcount_trend()` — 输入格式不变
- `_attach_key_snapshots()` — 输入格式不变
- `_inject_snapshot_images()` — 输入格式不变
- `_format_weekly_context()` — 输入格式不变
- `_build_weekly_data()` — 调用方式不变
- `_build_fallback_report()` — 调用方式不变
- 所有其他测试 — 接口不受影响

## 七、实现步骤

```
Step 1: 新增环境变量配置              — .env + .env.example
Step 2: 重写 _read_camera_snapshots()  — reporter.py (SQL 替换 HTTP)
Step 3: 新增 _sync_snapshot_images()   — reporter.py (图片按需复制)
Step 4: 新增 /snapshots/<fname> 路由   — main.py
Step 5: 移除 HTTP 相关 import          — reporter.py (requests 不再用于摄像头)
Step 6: 更新测试                       — test_weekly_context.py + test_weekly_report_pipeline.py
Step 7: 运行全量测试验证               — pytest
Step 8: 生成完整报告验证               — curl /research 确认人数趋势有数据
```

## 八、测试策略

### 新增测试

| 测试 | 内容 |
|------|------|
| `test_reads_snapshots_from_sqlite` | Mock `sqlite3.connect`，验证返回格式正确 |
| `test_returns_empty_on_db_missing` | DB 路径不存在 → 空列表，不抛异常 |
| `test_returns_empty_on_no_data` | DB 存在但 counts 表为空 → 空列表 |
| `test_sync_images_copies_files` | `_sync_snapshot_images` 正确复制文件 |
| `test_sync_images_skips_on_src_missing` | 源目录不可达 → 图片跳过，不阻塞 |

### 更新现有测试

- `test_headcount_trend_has_correct_structure` — mock 从 `_read_camera_snapshots` 改为 mock DB
- `test_insufficient_trend_produces_fallback_in_context` — 同上
