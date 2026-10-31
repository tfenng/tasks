# Quickstart & Validation Guide

**Feature**: `001-task-control-center` | **Date**: 2026-10-30

本指南用于在本地或测试环境验证端到端行为，不包含实现代码或完整迁移脚本。接口细节见
[contracts/openapi.yaml](contracts/openapi.yaml)，表结构见 [data-model.md](data-model.md)。

## Prerequisites

- Docker 24+ 与 Docker Compose v2
- Python 3.12 与 [uv](https://docs.astral.sh/uv/)
- Node.js 22 LTS 与 pnpm 9
- 可选：一个可 SSH 登录的测试主机（验证 SSH 执行器）
- 可选：Playwright 浏览器（`pnpm exec playwright install chromium`）

## Environment

```sh
cp deploy/.env.example deploy/.env
```

至少设置：

```text
TASK_CONTROL_DATABASE_URL=postgresql+psycopg://task_control:task_control@localhost:5432/task_control
TASK_CONTROL_SECRET_KEYS={"1":"<32-byte-base64>"}
TASK_CONTROL_SECRET_ACTIVE_VERSION=1
TASK_CONTROL_SCRIPT_ROOT=/opt/task-scripts
TASK_CONTROL_KNOWN_HOSTS=/etc/task-control/known_hosts
TASK_CONTROL_COOKIE_SECURE=false          # 本地 HTTP 开发
TASK_CONTROL_ALLOWED_HOSTS=localhost,127.0.0.1
```

生产环境必须使用 HTTPS，并设置 `TASK_CONTROL_COOKIE_SECURE=true`。不要提交 `.env` 或密钥。

## Run the Full Stack

```sh
docker compose -f deploy/docker-compose.yml up --build
```

- Web UI: `http://localhost:8080`
- API docs: `http://localhost:8080/api/docs`
- 健康检查: `http://localhost:8080/api/v1/health/ready`

首次启动先执行迁移，再创建管理员：

```sh
docker compose -f deploy/docker-compose.yml run --rm migrate
docker compose -f deploy/docker-compose.yml run --rm api \
  python -m task_control.cli create-admin --username admin
```

## Run Locally

```sh
# 1. 数据库
docker compose -f deploy/docker-compose.yml up -d db

# 2. 后端
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run python -m task_control.cli create-admin --username admin
uv run uvicorn task_control.main:app --reload --port 8000

# 3. 另开终端：调度器与执行器
cd backend
uv run python -m task_control.scheduler
uv run python -m task_control.worker

# 4. 前端
cd frontend
pnpm install
pnpm dev        # http://localhost:5173，/api 代理到 8000
```

调度器和 worker 必须分别运行；只启动 API 时，运行会停留在 `queued`。

## Validation Scenarios

### 1. Health & Login

```sh
curl -s http://localhost:8000/api/v1/health/live
curl -s http://localhost:8000/api/v1/health/ready
```

预期：`live` 返回 `{"status":"ok"}`；`ready` 的 `checks.database` 和进程心跳为 `ok`。用管理员登录
Web UI，确认导航包含任务定义、调度、运行、统计、目标、凭据、用户、审计。

### 2. Create a Local Script Task

通过 UI 创建任务定义：

- key: `demo-hello`
- 执行入口: 本机脚本
- 参数 Schema: `name`（string，必填）、`count`（integer，默认 1，最小 1）、`token`（string，
  `x-secret: true`）
- 命令: `python /opt/task-scripts/hello.py --name ${name} --count ${count}`
- 超时: 60 秒；最大尝试: 1；并发: 1

提交参数 `{"name":"alice","count":2,"token":"secret"}`，预期：

- 运行从 `queued` 进入 `running`，最终 `succeeded`
- 运行详情显示参数 `name=alice`、`count=2`、`token=***`
- 尝试记录包含退出码 0、耗时和 stdout 摘要
- 审计出现 `definition.create`、`run.create`、`run.succeeded`

### 3. Parameter Validation

提交缺失 `name` 或 `count=0`，预期 HTTP 422 / UI 字段级错误，且运行列表不新增记录。

### 4. One-Time Schedule

为 `demo-hello` 创建一次性调度，`fire_at` 设为 1 分钟后。预期：

- 调度状态 `active`，显示 `next_fire_at`
- 到点后出现一次运行，调度变为 `completed`
- 再次查询不会出现重复运行

### 5. Interval, Pause, Resume, Overlap

创建间隔 60 秒的调度，参数指向一个运行 90 秒的慢任务。预期：

- 第一次运行进入 `running`
- 下一次触发按默认 `skip` 生成 `skipped` 运行并记录原因，不产生并发执行
- 暂停后 `next_fire_at` 不再推进；恢复后从下一个到期点继续；取消后不再产生运行
- 禁用任务定义后，关联调度变为 `paused`，未到期的 `scheduled` 运行被取消并记录
  `DEFINITION_DISABLED`；重新启用后调度仍为 `paused`，必须显式恢复，且不补跑禁用期间的触发

### 6. Retry & Parameter Preservation

创建一个前两次失败、第三次成功的示例脚本任务（`backend/scripts/example_tasks/flaky.py`），
最大尝试 3、初始退避 5 秒。预期：

- 运行依次产生 3 条尝试，前两次 `failed`，运行进入 `retry_wait`
- 第三次 `succeeded`，运行最终成功
- 三次尝试的参数快照和定义版本完全一致
- 手工重试最终失败的运行会创建带 `parent_run_id` 的新运行，并复制原参数

### 7. HTTP Executor

登记 HTTP 目标 `http://localhost:8000`，创建 GET `/api/v1/health/live`、成功状态码 200 的任务。
提交后预期 `succeeded`，尝试记录包含 HTTP 200 和响应摘要。将成功状态码改为 201 再提交，预期
`failed`，错误分类为 `RESPONSE_MISMATCH`，且不自动重试。

### 8. SSH Executor (Optional)

登记测试 SSH 主机和凭据，known_hosts 包含该主机密钥，远程命令 `echo ok`。预期 `succeeded`，
stdout 摘要含 `ok`。将 known_hosts 替换为错误密钥，预期 `failed` 且错误分类为 `SSH_HOST_KEY`，
不自动重试。

### 9. Authorization, CSRF, Idempotency, Concurrency

- 只读用户调用 `POST /runs`：预期 403；UI 不显示提交按钮。
- 管理员创建/禁用用户、重置密码：预期 UI 与 API 一致，旧会话被吊销。
- 缺少 `X-CSRF-Token` 的 Cookie 写请求：预期 403 `CSRF_INVALID`。
- 同一 `Idempotency-Key` 重复提交相同运行：预期只产生一个运行，第二次返回已有运行。
- 更新请求缺少 `If-Match`：预期 428 `PRECONDITION_REQUIRED`。
- 两个浏览器同时编辑同一任务定义：后提交者带旧 `If-Match`，预期 409 `CONFLICT_VERSION`，
  界面保留输入并提示刷新；调度和用户更新同样适用。

### 10. Stats

构造成功、失败、取消、跳过和重试运行，打开统计页或调用：

```sh
curl -s 'http://localhost:8000/api/v1/stats/runs?from=2026-10-01T00:00:00Z&to=2026-11-01T00:00:00Z&group_by=day'
```

预期：运行总数与运行列表一致；重试不重复计入运行数；成功率分母只含成功+失败；可从统计下钻到
对应运行；尝试统计单独展示；运行结束后 60 秒内统计可见且与明细一致（统计查询无缓存）。

### 11. Worker Restart Reconciliation

启动一个 120 秒的慢任务，运行中杀掉 worker 进程，等待租约过期后重启 worker/reaper。预期：

- 失联运行在 5 分钟内被对账，不会永久停留在 `running`
- 当前尝试标记失败（`WORKER_LOST`），按重试策略进入 `retry_wait` 或最终失败
- 运行时并发计数被释放，后续运行可继续

### 12. Secret & Credential Safety

- 创建凭据后查询 `GET /credentials`：只返回名称、kind、掩码元数据，无 secret。
- 在参数/输出中放入测试 token：运行详情、统计、审计和日志均显示 `***`。
- 检查浏览器网络面板：登录后响应不含密码/会话令牌明文。
- 禁用目标/凭据后：新提交返回 `TARGET_DISABLED`；已有 `queued/retry_wait` 运行失败，`running`
  允许完成，且不再产生新 attempt。
- 在 retry_wait 期间轮换 HTTP token/SSH 凭据；下一次 attempt 使用新凭据，参数快照和定义版本不变。

## Automated Verification

```sh
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run pytest tests/integration -q

cd ../frontend
pnpm lint
pnpm test
pnpm build
pnpm exec playwright test
pnpm exec playwright test tests/performance/page-performance.spec.ts
```

性能测试需在固定 4 vCPU/8 GB 环境运行后端负载与前端页面性能，分别产出
`backend/tests/performance/results.md` 和前端性能报告。可用性测试 T140 需至少 10 名目标操作员参与，
结果写入 `specs/001-task-control-center/usability-report.md`；未达到 SC-010/011 不得标记发布完成。

预期：Ruff 无错误；后端单元/集成/契约测试通过；前端 lint/test/build 通过；Playwright 覆盖登录、
创建定义、立即运行、调度、重试、统计和越权场景。

## Troubleshooting

| Symptom | Check |
|---------|-------|
| 运行一直 `queued` | worker 是否启动；`task_definition_runtime.running_count` 是否达到上限 |
| 调度不触发 | scheduler 是否持有 advisory lock；`next_fire_at` 与时钟/时区是否正确 |
| `ready` 返回 503 | 数据库连接、迁移是否完成、scheduler/worker 心跳是否过期 |
| SSH 失败 `SSH_HOST_KEY` | known_hosts 是否包含目标主机当前密钥；管理员是否显式更新信任 |
| HTTP 失败 `HTTP_4XX` | 成功状态码配置、目标 URL 是否在允许列表、TLS 证书是否有效 |
| 403 `CSRF_INVALID` | 写请求是否带 `X-CSRF-Token`；Cookie 是否被浏览器拦截 |
| 409 `CONFLICT_VERSION` | 是否使用最新 `version` 作为 `If-Match`；刷新后重试 |
| 428 `PRECONDITION_REQUIRED` | 更新/状态动作是否带 `If-Match`；先读取最新 `version` |
| 429 | 等待 `Retry-After`；检查登录失败次数/锁定时间 |
| 凭据不可用 | 管理员是否禁用目标/凭据；key ring 版本是否匹配 |
