# Task Control Center

基于 **FastAPI + PostgreSQL + React** 的任务调度控制中心，用于管理任务定义、定时调度、执行器、运行记录和审计日志。

当前主线代码位于 `backend/` 与 `frontend/`，通过 `deploy/docker-compose.yml` 一键部署。根目录的 `main.py` / `server.py` 是旧版全景与点云任务服务，详见文末[旧版服务](#旧版服务)。

## 功能

- 任务定义与不可变版本，支持 JSON Schema 参数校验
- 即时运行、interval / cron / once 调度，支持暂停、恢复、取消
- 本机脚本、SSH、HTTP 执行器，凭据加密存储
- Worker 认领任务、租约续期、超时终止、失败重试与退避
- 运行 stdout / stderr 实时输出与历史输出查看
- 运行、尝试、成功率、P95 等统计
- 用户、角色、会话、API Token、审计日志
- 登录限流、安全响应头、数据保留策略
- React + Ant Design 管理控制台
- Docker Compose 部署，包含数据库迁移、API、Worker、Scheduler

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.12、FastAPI、SQLAlchemy 2、Alembic、Pydantic 2 |
| 数据库 | PostgreSQL 16 |
| 前端 | React 18、TypeScript、Vite 6、Ant Design 5 |
| 部署 | Docker Compose、PostgreSQL 官方镜像 |
| 测试与检查 | pytest、ruff、pnpm lint |

## 目录结构

```text
.
├── backend/                 # FastAPI API、worker、scheduler、迁移与测试
│   ├── src/task_control/
│   ├── migrations/
│   └── tests/
├── frontend/                # React 控制台
│   ├── src/
│   └── dist/                # pnpm build 产物（构建后生成），由 FastAPI 托管
├── deploy/
│   ├── Dockerfile           # 前端构建 + 后端运行时镜像
│   ├── docker-compose.yml   # db / migrate / api / worker / scheduler
│   ├── .env.example
│   └── task-scripts/        # 挂载到容器的 /opt/task-scripts
├── specs/                   # 需求、设计、数据模型与快速验证文档
├── main.py, server.py       # 旧版服务入口（非当前主线）
├── services/                # 旧版服务代码
└── utils/                   # 旧版服务工具
```

## 快速开始（Docker Compose）

### 1. 准备环境

- Docker 24+
- Docker Compose v2
- 可用端口：`8000`（API / Web UI），以及 `5432` 或自定义的 PostgreSQL 端口

### 2. 配置环境变量

```sh
cd deploy
cp .env.example .env
```

生成 32 字节的 base64 密钥：

```sh
python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
```

编辑 `deploy/.env`，把占位符替换成真实密钥：

```dotenv
TASK_CONTROL_SECRET_KEYS={"1":"<上一步生成的密钥>"}
TASK_CONTROL_SECRET_ACTIVE_VERSION=1
TASK_CONTROL_COOKIE_SECURE=false
```

> 密钥必须是解码后正好 32 字节的 base64。保留占位符 `REPLACE_WITH_32_BYTE_BASE64` 会导致迁移和 API 启动失败。

如果本机 `5432` 已被 PostgreSQL 占用，在 `deploy/.env` 中增加：

```dotenv
POSTGRES_PORT=5433
```

### 3. 启动

```sh
cd deploy
docker compose up -d --build
```

Compose 会依次完成：

1. 启动 `db` 并等待健康检查通过
2. 运行一次性 `migrate` 容器执行 `alembic upgrade head`
3. 启动 `api`、`worker`、`scheduler`

`migrate` 执行成功后会退出，这是正常状态；`docker compose ps -a` 中显示 `Exited (0)`。

### 4. 创建管理员

首次启动后创建管理员：

```sh
cd deploy
docker compose exec api python -m task_control.cli create-admin --username admin
```

按提示输入密码（至少 12 位）。如果管理员已存在，可重置密码：

```sh
docker compose exec api python -m task_control.cli reset-password --username admin
```

重置后首次登录会要求修改密码。

### 5. 访问

| 入口 | 地址 |
| --- | --- |
| Web UI | <http://localhost:8000> |
| API 文档 | <http://localhost:8000/api/docs> |
| OpenAPI | <http://localhost:8000/api/openapi.json> |
| 存活检查 | <http://localhost:8000/api/v1/health/live> |
| 就绪检查 | <http://localhost:8000/api/v1/health/ready> |

如需修改宿主机端口：

```dotenv
TASK_CONTROL_API_PORT=8080
```

修改后重新执行 `docker compose up -d`。

### 常用命令

```sh
cd deploy

docker compose ps -a                      # 查看全部服务，包括已退出的 migrate
docker compose logs -f api worker scheduler
docker compose restart api worker scheduler
docker compose up -d --build              # 代码变更后重建
docker compose down                       # 停止服务，保留数据卷
docker compose down -v                    # 停止并删除数据卷（会清空数据库和输出）
```

## 本地开发

### 后端

需要 Python 3.12、[uv](https://docs.astral.sh/uv/) 和可用的 PostgreSQL。

```sh
# 方式一：只用容器启动数据库
# 如果还没有 deploy/.env，请先按“快速开始”第 2 步创建并设置密钥
docker compose -f deploy/docker-compose.yml up -d db

# 方式二：使用本机 PostgreSQL
createdb task_control

cd backend
uv sync --python 3.12 --group dev
cp .env.example .env
```

编辑 `backend/.env`，至少设置：

```dotenv
TASK_CONTROL_DATABASE_URL=postgresql+psycopg://localhost:5432/task_control
TASK_CONTROL_SCRIPT_ROOT=/tmp/task-control-scripts
TASK_CONTROL_OUTPUT_ROOT=/tmp/task-control-output
TASK_CONTROL_SECRET_KEYS={"1":"<32 字节 base64>"}
TASK_CONTROL_COOKIE_SECURE=false
```

如果使用 Compose 的数据库且宿主机端口设为 `5433`，请把连接串改为 `localhost:5433`。

执行迁移并创建管理员：

```sh
uv run alembic upgrade head
uv run python -m task_control.cli create-admin --username admin
```

修改数据库模型后生成并应用迁移：

```sh
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

启动 API：

```sh
uv run uvicorn task_control.main:app --reload --port 8000
```

另开终端启动 Worker 和 Scheduler：

```sh
cd backend
uv run python -m task_control.worker.loop
uv run python -m task_control.scheduler.loop
```

> API、Worker、Scheduler 必须分别运行。只启动 API 时，任务会停留在 `queued` 状态。

### 前端

需要 Node.js 22 和 pnpm 10.32.1（已通过 `packageManager` 固定）。

```sh
cd frontend
pnpm install
pnpm dev        # http://localhost:5173，/api 代理到 127.0.0.1:8000
```

生产构建：

```sh
pnpm build
```

构建产物位于 `frontend/dist`。FastAPI 启动时如果检测到该目录，会直接在 `/` 提供控制台。

## 配置

### 应用环境变量

所有后端变量使用 `TASK_CONTROL_` 前缀，可写入 `backend/.env` 或 `deploy/.env`。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `TASK_CONTROL_DATABASE_URL` | `postgresql+psycopg://localhost:5432/task_control` | SQLAlchemy 数据库连接串；Compose 中自动指向 `db` |
| `TASK_CONTROL_SECRET_KEYS` | 内置开发密钥 | JSON 对象，版本号到 32 字节 base64 密钥的映射；生产必须替换 |
| `TASK_CONTROL_SECRET_ACTIVE_VERSION` | `1` | 当前用于加密的密钥版本，便于轮换 |
| `TASK_CONTROL_COOKIE_SECURE` | `false` | HTTPS 环境应设为 `true` |
| `TASK_CONTROL_SESSION_IDLE_MINUTES` | `30` | 普通会话空闲有效期 |
| `TASK_CONTROL_SESSION_REMEMBER_DAYS` | `7` | “记住我”会话有效期 |
| `TASK_CONTROL_SCRIPT_ROOT` | `/tmp/task-control-scripts` | 本机脚本执行根目录；Compose 中为 `/opt/task-scripts` |
| `TASK_CONTROL_OUTPUT_ROOT` | `/tmp/task-control-output` | 运行输出目录；API 与 Worker 必须共享 |
| `TASK_CONTROL_KNOWN_HOSTS_PATH` | 空 | SSH 执行器的 known_hosts 文件 |
| `TASK_CONTROL_WORKER_CONCURRENCY` | `4` | Worker 并发数 |
| `TASK_CONTROL_WORKER_POLL_SECONDS` | `1` | Worker 轮询间隔 |
| `TASK_CONTROL_LEASE_SECONDS` | `60` | 执行租约时长 |
| `TASK_CONTROL_OUTPUT_LIMIT_BYTES` | `1048576` | 单次尝试保留的输出上限 |
| `TASK_CONTROL_RETENTION_DAYS` | `395` | 运行记录保留天数 |
| `TASK_CONTROL_ATTEMPT_RETENTION_DAYS` | `90` | 尝试记录保留天数 |
| `TASK_CONTROL_CORS_ORIGINS` | `http://localhost:5173` | 允许的跨域来源，逗号分隔 |
| `TASK_CONTROL_LOG_LEVEL` | `INFO` | 日志级别 |

### Compose 变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `POSTGRES_DB` | `task_control` | 数据库名 |
| `POSTGRES_USER` | `task_control` | 数据库用户 |
| `POSTGRES_PASSWORD` | `task_control` | 数据库密码，生产环境必须修改 |
| `POSTGRES_PORT` | `5432` | 数据库映射到宿主机的端口，冲突时改为 `5433` 等 |
| `TASK_CONTROL_API_PORT` | `8000` | API 与 Web UI 的宿主机端口 |

## API 概览

所有业务接口位于 `/api/v1` 下，使用 Cookie 会话 + CSRF 校验；也可以创建 API Token 调用。

| 前缀 | 说明 |
| --- | --- |
| `/api/v1/auth` | 登录、登出、当前用户、修改密码、会话与 Token 管理 |
| `/api/v1/task-definitions` | 任务定义、版本、归档与删除 |
| `/api/v1/runs` | 提交运行、列表、详情、取消、重试、实时输出 |
| `/api/v1/schedules` | 调度创建、暂停、恢复、取消、删除 |
| `/api/v1/execution-targets` | 执行目标管理 |
| `/api/v1/stats` | 运行统计 |
| `/api/v1/users` | 用户管理（管理员） |
| `/api/v1/audit-events` | 审计日志（管理员） |
| `/api/v1/scripts` | 脚本目录浏览 |
| `/api/v1/health` | 存活与就绪检查 |

## 测试与检查

后端：

```sh
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

测试默认连接 `task_control_test` 数据库，并在每个用例前后创建、删除表；请先确保本机 PostgreSQL 已启动并存在该数据库：

```sh
createdb task_control_test
```

前端：

```sh
cd frontend
pnpm lint
pnpm build
```

## 数据与运维

### 数据卷

Compose 使用两个命名卷：

- `task-control_task_control_pg`：PostgreSQL 数据
- `task-control_task_control_output`：运行输出文件，挂载到 API 与 Worker

脚本目录 `deploy/task-scripts` 以只读方式挂载到容器的 `/opt/task-scripts`。把脚本放入该目录后，任务定义中的命令可直接引用，例如：

```text
python /opt/task-scripts/hello.py --name ${name}
```

### 备份

```sh
cd deploy
docker compose exec -T db pg_dump -U task_control task_control > task_control_backup.sql
```

恢复前请确认目标数据库为空或已备份。

### 保留策略

历史数据通过保留任务清理，按 `TASK_CONTROL_RETENTION_DAYS` 和 `TASK_CONTROL_ATTEMPT_RETENTION_DAYS` 删除运行、尝试、审计、会话与输出文件。当前不会自动定时执行，可以手动运行：

```sh
cd deploy
docker compose exec api python -m task_control.worker.retention
```

也可以把该命令配置为宿主机的 cron / systemd timer。

## 常见问题

### 启动时报 `secret_keys ... is not valid base64`

`deploy/.env` 中还是示例占位符。重新生成密钥并替换：

```sh
python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
```

### 启动时报 `ports are not available: 127.0.0.1:5432`

本机 PostgreSQL 已占用 5432。编辑 `deploy/.env`：

```dotenv
POSTGRES_PORT=5433
```

然后重新执行 `docker compose up -d`。容器内部仍然使用 5432，只有宿主机映射端口变化。

### `ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION`

`frontend/package.json` 已通过 `packageManager` 固定 pnpm 10.32.1。请勿直接改用更新的大版本 pnpm；如果需要升级，先重新生成并验证 `pnpm-lock.yaml`。

### 忘记管理员密码

```sh
cd deploy
docker compose exec api python -m task_control.cli reset-password --username admin
```

### `/health/ready` 显示 worker `degraded`

当前 Worker 只在启动时登记心跳，运行超过约 90 秒后就绪检查可能显示 `degraded`，但 Worker 进程仍会正常认领和执行任务。可通过 `docker compose logs worker` 和运行记录确认实际状态。

## 安全建议

- 不要提交 `deploy/.env` 或 `backend/.env`，两者已被 `.gitignore` 忽略
- 生产环境修改默认数据库密码，并通过 HTTPS 部署
- HTTPS 环境设置 `TASK_CONTROL_COOKIE_SECURE=true`
- 限制 API 端口暴露范围，必要时放在反向代理之后
- 定期轮换 `TASK_CONTROL_SECRET_KEYS`，通过 `TASK_CONTROL_SECRET_ACTIVE_VERSION` 切换新版本

## 旧版服务

根目录的 `main.py`、`server.py`、`services/`、`utils/` 是旧版全景影像与点云任务服务：

- 使用 Python 3.12 + pydantic v1，默认监听 `8080`
- 入口为 `server.py`，Docker 文件为根目录的 `Dockerfile` / `Dockerfile-rt`
- 依赖的 `dao` 包不在当前仓库中，直接 `import main` 会失败
- 新功能与部署请使用 `backend/` + `frontend/` + `deploy/`

旧版服务仅作为历史代码保留，不建议与新控制中心混用同一数据库或容器。
