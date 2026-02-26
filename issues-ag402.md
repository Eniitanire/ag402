# ag402 库问题报告

> 版本: ag402-core 0.1.6, ag402-mcp 0.1.6
> 测试环境: Docker (python:3.12-slim), Ubuntu 22.04
> 报告日期: 2026-02-25

---

## BUG-1 [高] `ag402 serve` 硬编码 host=127.0.0.1，Docker 容器化部署不可用

### 描述

`ag402_core/cli.py` 的 `_cmd_serve()` 函数中，`uvicorn.run()` 硬编码了 `host="127.0.0.1"`：

```python
# ag402_core/cli.py, _cmd_serve() 函数末尾
uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
```

在 Docker 容器中，`127.0.0.1` 仅对容器自身可见。Docker 的 `-p 8001:8001` 端口映射连接的是容器的网卡接口（通常为 `eth0` / `172.x.x.x`），而 uvicorn 只监听 loopback，外部请求到达容器后无法路由到 uvicorn 进程。

### 复现步骤

```bash
# 使用官方推荐的 docker-compose.yml
docker compose up -d
curl http://localhost:8001/health
# 结果: curl: (52) Empty reply from server
```

### 影响范围

- Docker 部署完全不可用
- Kubernetes 部署完全不可用
- 任何容器化环境均受影响

### 建议修复

`_cmd_serve()` 函数应增加 `--host` 参数，默认值改为 `0.0.0.0`：

```python
# 在 argparse 定义中添加
serve_p.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")

# _cmd_serve() 中使用
uvicorn.run(app, host=args.host if hasattr(args, 'host') else "0.0.0.0", port=port, ...)
```

注意: `ag402_mcp/gateway.py` 的 `cli_main()` 已经有 `--host` 参数且默认 `127.0.0.1`，但 `_cmd_serve()` 完全不使用它。建议统一。

### 当前 workaround

编写 `gateway_wrapper.py` 绕过 `ag402 serve`，直接构造 `X402Gateway` + `uvicorn.run(host="0.0.0.0", ...)`。

---

## BUG-2 [高] aiosqlite 后台线程与多事件循环冲突导致 crash loop

### 描述

`ag402 serve` 启动流程中存在多个事件循环生命周期冲突：

1. `_cmd_serve()` 在同步上下文中运行，内部可能触发 `asyncio.run()`（如 env 加载、钱包初始化），创建并关闭第一个 event loop
2. 然后 `uvicorn.run()` 创建第二个 event loop
3. uvicorn lifespan 中 `await gateway._persistent_guard.init_db()` 调用 `aiosqlite.connect()`
4. aiosqlite 的后台 `_connection_worker_thread` 持有的是旧 loop 的引用
5. 线程调用 `future.get_loop().call_soon_threadsafe()` → 旧 loop 已关闭 → `RuntimeError: Event loop is closed`

### 报错堆栈

```
Exception in thread Thread-1 (_connection_worker_thread):
  File "aiosqlite/core.py", line 66, in _connection_worker_thread
    future.get_loop().call_soon_threadsafe(set_result, future, result)
  File "uvloop/loop.pyx", line 1290, in uvloop.loop.Loop.call_soon_threadsafe
  File "uvloop/loop.pyx", line 705, in uvloop.loop.Loop._check_closed
RuntimeError: Event loop is closed
```

### 影响范围

- 使用 `uvicorn[standard]`（含 uvloop）时 100% 复现
- 移除 uvloop 后仍可能出现（取决于 CLI 入口是否触发过 `asyncio.run()`）

### 建议修复

方案 A（推荐）：`_cmd_serve()` 中不使用 `uvicorn.run()`（它会创建新 loop），而是在同一个 `asyncio.run()` 中同时初始化和运行：

```python
async def _serve_async(args):
    # 所有异步初始化和 uvicorn 在同一个 loop 中
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    await server.serve()

def _cmd_serve(args):
    asyncio.run(_serve_async(args))
```

方案 B：在 `_cmd_serve()` 入口确保之前没有任何 `asyncio.run()` 被调用过（包括 `load_config()`、`load_dotenv()` 等路径）。

方案 C（权宜之计）：在 `PersistentReplayGuard` 中使用 `asyncio.get_running_loop()` 替代线程绑定的 loop 引用。

### 当前 workaround

1. `pip uninstall uvloop`（消除严格检查）
2. 使用 `gateway_wrapper.py` 确保只有一个事件循环

---

## BUG-3 [中] `PersistentReplayGuard.init_db()` 权限检查缺失

### 描述

`ag402_core/security/replay_guard.py` 的 `init_db()` 方法：

```python
async def init_db(self) -> None:
    db_dir = os.path.dirname(self.db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    self._db = await aiosqlite.connect(self.db_path, timeout=10.0)
```

当目录存在但当前用户无写权限时，`aiosqlite.connect()` 抛出 `sqlite3.OperationalError: unable to open database file`，错误信息不直观，缺乏权限提示。

### 建议修复

```python
async def init_db(self) -> None:
    db_dir = os.path.dirname(self.db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    if db_dir and not os.access(db_dir, os.W_OK):
        raise PermissionError(
            f"Cannot write to {db_dir} — check directory permissions. "
            f"Current user: {os.getuid()}, dir owner: {os.stat(db_dir).st_uid}"
        )
    self._db = await aiosqlite.connect(self.db_path, timeout=10.0)
```

---

## 建议-1 [低] `ag402 serve` 缺少 `--host` CLI 参数

`_cmd_serve()` 的 argparse 定义中没有 `--host` 参数。对比 `ag402_mcp/gateway.py` 的 `cli_main()` 已有该参数。建议统一。

## 建议-2 [低] 配置路径分散，文档不清晰

ag402 的配置分散在三处，用户容易混淆：
1. 项目 `.env`（通过 `env_file` 传入容器）
2. `~/.ag402/.env`（ag402 内部配置）
3. CLI 参数（`--price`, `--address` 等）

优先级不明确，建议在文档中说明加载顺序和覆盖关系。

## 建议-3 [低] `ag402 doctor` 不检查 gateway 运行环境

`ag402 doctor` 检查了 Python、依赖、钱包等，但不检查：
- 端口是否可绑定
- 目标后端 URL 是否可达
- SQLite 数据库目录是否可写

建议增加这些检查项。
