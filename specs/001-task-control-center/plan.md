# Implementation Plan: 任务中控系统（Task Control Center）

**Branch**: `001-task-control-center` | **Date**: 2026-10-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-task-control-center/spec.md`

## Summary

构建一个独立的任务中控系统：用任务定义描述参数和执行入口，用运行实例承载一次提交，支持立即、
一次性定时、固定间隔和日历规则触发；通过本机脚本、SSH 和 HTTP 三类执行器触发外部任务；完整保存
参数快照、每次尝试和结果；对可重试失败按策略自动重试；提供运行成败统计和完整运维 Web 控制台。

技术路线采用**模块化单体 + 进程拆分**：同一 Python 代码库提供 API、调度器和执行器三个进程，
PostgreSQL 同时承担持久化、调度队列和并发控制，不引入 Redis、Celery 或消息队列。后端使用
FastAPI + Pydantic 2 + SQLAlchemy 2 + Alembic + psycopg 3；前端使用 React + TypeScript + Vite +
Ant Design 5。新系统放在独立的 `backend/` 与 `frontend/` 目录，不修改现有根目录的全景/点云任务服务。

## Technical Context

**Language/Version**: Python 3.12（后端）；TypeScript 5.x / Node.js 22 LTS（前端）

**Primary Dependencies**:
- 后端：FastAPI 0.115+、Pydantic 2.9+、pydantic-settings、SQLAlchemy 2.0、Alembic、psycopg 3.2、
  uvicorn、croniter、paramiko、httpx、cryptography、argon2-cffi、jsonschema、loguru、PyYAML
- 前端：React 18.3、Ant Design 5、TanStack Query 5、React Router 6、@rjsf/core + @rjsf/antd、
  Recharts 2、Vite 6、pnpm、openapi-typescript + openapi-fetch
- 测试：pytest 8、pytest-cov、testcontainers、respx、time-machine、httpx；Vitest、Testing Library、
  Playwright

**Storage**: PostgreSQL 16，独立 schema `task_control`；数据库同时作为任务队列（`FOR UPDATE SKIP
LOCKED`）和调度状态存储；不引入 Redis/Celery。

**Testing**: pytest（单元/集成/契约）、testcontainers PostgreSQL、respx（HTTP 执行器）、
time-machine（调度与重试时钟）、Vitest + Testing Library（组件）、Playwright（关键端到端流程）。

**Target Platform**: Linux 容器（amd64/arm64）；现代浏览器最近两个主要版本；响应式支持 375px
及以上宽度。

**Project Type**: Web application（后端 API + SPA + 调度器 + 执行器进程）

**Performance Goals**:
- 立即触发运行 p99 在 10 秒内开始执行（容量充足时）
- 调度触发点 p99 在 5 秒内完成入队
- 常用页面首屏可用内容 p95 在 2 秒内
- 支持 1,000 个任务定义、10,000 个待执行/已调度运行、100 个并发执行

**Constraints**:
- 单控制面部署；不包含分布式执行器集群、跨区域多活、DAG/工作流、优先级抢占
- 本机脚本、SSH、HTTP 三类执行入口；新增入口通过代码扩展，不支持运行时上传
- 输出单次保留上限 1 MB；运行明细保留 13 个月，尝试/输出明细保留 90 天
- 本地账号认证；不使用 SSO/OIDC/MFA
- 所有时间以 UTC 存储，调度按计划时区计算
- 后端优先同步 I/O；不引入异步 SQLAlchemy 或消息队列

**Scale/Scope**: 3 个角色（管理员/操作员/只读观察者）；约 10 个主要 Web 页面；63 条功能需求、
19 条成功标准；单工作区，任务数据不按个人隔离。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则/约束 | 结论 | 设计证据 |
|-----------|------|----------|
| I. Simplicity First | PASS | 模块化单体；PostgreSQL 作队列；不用 Redis/Celery；同步 I/O；仅拆分 API/调度器/执行器三个进程 |
| II. Modular Architecture | PASS | `domain` 不依赖 FastAPI/SQLAlchemy；`application` 编排用例；`infrastructure` 实现仓储/执行器/安全；API 仅做协议转换 |
| III. Python Code Quality | PASS | Python 3.12、类型注解、Ruff、显式领域异常、禁止裸 `except`、Pydantic 2 数据结构 |
| IV. Data Integrity | PASS | Alembic 迁移；外键/唯一/检查约束；UTC `timestamptz`；运行/尝试状态机；事务边界明确；参数快照不可变 |
| V. API Consistency | PASS | OpenAPI 3.1；统一错误结构；分页/排序/筛选约定；幂等键；`If-Match` 乐观并发；不暴露内部异常 |
| VI. Security by Default | PASS | 本地账号 + Argon2id；服务端会话 + CSRF；RBAC；凭据 AES-GCM 加密；目标白名单；防命令注入/SSRF；审计 |
| VII. Testing and Reliability | PASS | pytest 单元/集成/契约；独立测试数据库；重试/调度/权限/事务回归测试；Playwright 关键流程 |
| VIII. User Experience Consistency | PASS | Ant Design 统一布局/表单/反馈；加载/空/错误状态；危险操作确认；响应式与基础无障碍；3 秒轮询活动运行 |
| Technical Constraints | PASS | Python 后端；依赖锁定（uv.lock / pnpm-lock.yaml）；开发/测试/生产配置分离；业务配置存数据库，不写回 `.env` |
| Development Workflow | PASS | 规格 → 计划 → 任务 → 实现；Ruff + pytest + 前端检查作为合并门禁；迁移与 OpenAPI 同步评审 |

**Post-Design Re-check**: Phase 1 设计未引入违反项。唯一结构性决策是新系统使用独立后端工程与
Pydantic 2，而现有根目录遗留服务使用 Pydantic 1；两者通过独立虚拟环境/容器隔离，避免破坏遗留服务。

## Project Structure

### Documentation (this feature)

```text
specs/001-task-control-center/
├── plan.md              # 本文件
├── research.md          # Phase 0 技术决策
├── data-model.md        # Phase 1 数据模型与状态机
├── quickstart.md        # Phase 1 端到端验证指南
├── usability-report.md  # Phase 9 可用性测试记录（T140）
├── contracts/           # Phase 1 接口契约
│   ├── README.md
│   ├── openapi.yaml
│   ├── error-codes.md
│   ├── executor-interface.md
│   └── ui-routes.md
└── tasks.md             # Phase 2 输出（本命令不创建）
```

### Source Code (repository root)

```text
.github/
└── workflows/ci.yml

backend/
├── pyproject.toml
├── uv.lock
├── alembic.ini
├── migrations/
│   ├── env.py
│   └── versions/
├── src/task_control/
│   ├── __init__.py
│   ├── main.py                     # FastAPI 应用工厂与 SPA 静态托管
│   ├── cli.py                      # 部署引导与维护命令（非业务 CLI）
│   ├── config.py                   # pydantic-settings 环境配置
│   ├── api/
│   │   ├── deps.py                 # 会话、CSRF、RBAC、分页依赖
│   │   ├── errors.py               # 统一错误响应与异常映射
│   │   └── v1/
│   │       ├── auth.py
│   │       ├── users.py
│   │       ├── definitions.py
│   │       ├── schedules.py
│   │       ├── runs.py
│   │       ├── stats.py
│   │       ├── targets.py
│   │       ├── credentials.py
│   │       ├── audit.py
│   │       └── health.py
│   ├── application/
│   │   ├── auth/
│   │   ├── definitions/
│   │   ├── schedules/
│   │   ├── runs/
│   │   ├── stats/
│   │   ├── targets/
│   │   └── audit/
│   ├── domain/
│   │   ├── entities.py
│   │   ├── enums.py
│   │   ├── errors.py
│   │   ├── policies.py             # 状态机、重试分类、重叠/错过策略
│   │   ├── parameters.py           # JSON Schema 校验与默认值
│   │   └── ports.py                # 仓储/执行器/时钟/密钥端口
│   ├── infrastructure/
│   │   ├── db/
│   │   │   ├── models.py           # SQLAlchemy ORM
│   │   │   ├── session.py
│   │   │   └── repositories/
│   │   ├── security/
│   │   │   ├── passwords.py        # Argon2id
│   │   │   ├── sessions.py         # 服务端会话 + CSRF
│   │   │   ├── tokens.py           # API Token
│   │   │   └── secrets.py          # AES-GCM + key ring
│   │   ├── executors/
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   ├── local.py
│   │   │   ├── ssh.py
│   │   │   └── http.py
│   │   ├── logging.py
│   │   └── clock.py
│   ├── scheduler/
│   │   ├── __main__.py
│   │   ├── loop.py                 # 到期调度、错过/重叠、重试提升
│   │   └── cron.py                 # croniter + zoneinfo
│   └── worker/
│       ├── __main__.py
│       ├── loop.py                 # 队列认领、执行、完成
│       ├── heartbeat.py
│       └── reaper.py               # 失联运行对账
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── performance/                # 后端负载测试与结果
└── scripts/
    └── example_tasks/              # 验证用示例脚本

frontend/
├── package.json
├── pnpm-lock.yaml
├── vite.config.ts
├── tsconfig.json
├── src/
│   ├── main.tsx
│   ├── app/
│   │   ├── router.tsx
│   │   ├── providers.tsx
│   │   └── layout/
│   ├── pages/
│   │   ├── login/
│   │   ├── dashboard/
│   │   ├── definitions/
│   │   ├── schedules/
│   │   ├── runs/
│   │   ├── stats/
│   │   ├── targets/
│   │   ├── credentials/
│   │   ├── users/
│   │   ├── audit/
│   │   └── profile/
│   ├── features/
│   │   ├── auth/
│   │   ├── definitions/
│   │   ├── schedules/
│   │   ├── runs/
│   │   ├── stats/
│   │   └── admin/
│   ├── components/
│   │   ├── ParameterForm/
│   │   ├── RunStatus/
│   │   ├── PageState/
│   │   └── ConfirmAction/
│   ├── lib/
│   │   ├── api/                    # openapi-typescript 生成客户端
│   │   ├── auth/
│   │   └── query/
│   └── styles/
└── tests/
    ├── unit/
    ├── e2e/
    └── performance/                # 页面性能与 Lighthouse/Playwright

deploy/
├── docker-compose.yml
├── Dockerfile                      # 多阶段：前端构建 + 后端运行时
├── .env.example
├── smoke.sh                        # 容器冒烟
└── nginx.conf                      # 可选：生产 TLS/反代

docs/
├── operations.md                   # 运行手册
└── api-compatibility.md            # API 版本、弃用与不兼容变更记录

specs/001-task-control-center/      # 设计文档
```

**Structure Decision**: 选择“Web application”结构。新系统作为独立有界上下文放在 `backend/` 与
`frontend/`，现有根目录 `main.py`、`services/`、`utils/`、`dao` 相关遗留代码不修改。新后端使用
Pydantic 2 和 `pyproject.toml` + `uv.lock`，与根目录遗留服务的 Pydantic 1 依赖隔离；两者可分别
构建、测试和部署。

## Detailed Design

### 1. Runtime Topology

三个进程共享同一个 Python 包和数据库：

- **api**：FastAPI，服务 `/api/v1` 和构建后的 SPA；同步端点，数据库操作使用短事务。
- **scheduler**：单实例领导者，使用 PostgreSQL advisory lock 保证同一时刻只有一个调度循环；
  负责到期调度、一次性运行提升、错过/重叠处理、`retry_wait` 到期提升。
- **worker**：可配置线程数的执行进程；从 `runs` 队列认领任务，调用执行器，写回尝试和运行结果；
  心跳续租，reaper 对账失联运行。

API 不执行任务；调度器不执行任务；worker 不修改调度规则。三者通过数据库状态和事务边界解耦。

### 2. Module Boundaries

依赖方向严格为：

```text
api -> application -> domain
infrastructure -> domain/ports
scheduler/worker -> application + infrastructure
```

- `domain` 只包含实体、值对象、状态机、策略和端口协议，不导入 FastAPI、SQLAlchemy、httpx、paramiko。
- `application` 编排用例和事务，不依赖 HTTP 请求对象。
- `api` 只做认证、输入解析、调用用例、序列化响应和错误映射。
- `infrastructure` 实现仓储、执行器、密码/会话/加密、时钟和日志适配器。

### 3. Scheduling Algorithm

调度循环每 1 秒执行一轮，批量最多 100 条：

1. 用 `pg_try_advisory_lock` 获取调度领导者锁；失去锁的进程自动退出循环。
2. 查询 `schedules WHERE status='active' AND next_fire_at <= now()`，按 `next_fire_at` 排序，
   `FOR UPDATE SKIP LOCKED`。
3. 对每个调度计算本次 `scheduled_for`，用唯一约束 `(schedule_id, scheduled_for)` 保证同一触发点
   最多创建一个运行。
4. 判断重叠：若同一调度存在 `queued/running/retry_wait` 运行，按 `overlap_policy` 创建 `skipped`
   运行或 `queued` 运行；`skipped` 记录原因。
5. 判断错过：若 `now - scheduled_for > misfire_grace_seconds`，创建 `missed` 运行；宽限期内最多
   合并补跑一次，并在运行元数据中记录被合并的触发点。
6. 计算下一次 `next_fire_at`：一次性调度置 `completed`；日历规则用 croniter + zoneinfo；
   固定间隔按 UTC 时间加 interval。
7. 同一事务内插入运行、更新调度 `last_fire_at/next_fire_at`，提交后由 worker 认领。

调度触发器类型：

- `immediate`：提交时直接创建 `queued` 运行。
- `once`：创建 `scheduled` 运行，调度器到点提升为 `queued`。
- `cron`：按 cron 表达式在指定时区重复。
- `interval`：按固定秒数重复，最小 10 秒。

### 4. Queue and Worker Algorithm

1. worker 在事务中查询可认领运行：
   `status='queued' AND queued_at <= now()`，关联
   `task_definition_runtime.running_count < max_concurrency`，按 `queued_at, id` 排序，
   `FOR UPDATE OF runs SKIP LOCKED LIMIT 1`。
2. 原子增加 `task_definition_runtime.running_count`；若并发条件不再满足则回滚重试。
3. 将运行置为 `running`，写 `worker_id`、`lease_expires_at`，创建 `attempt_no = attempt_count + 1`
   的尝试记录，`attempt_count` 加一。
4. 调用执行器；执行期间每 15 秒续租一次。
5. 完成时在同一事务写尝试结果、运行终态或 `retry_wait`、递减 `running_count`。
6. 失败且可重试时设置 `retry_wait` 和 `next_retry_at`；调度器将到期 `retry_wait` 提升为 `queued`。
7. reaper 扫描 `running` 且 `lease_expires_at < now()` 的运行，标记当前尝试为 `failed`（错误分类
   `WORKER_LOST`），按重试策略处理，并递减运行时计数。
8. 定义禁用时暂停其所有 `active` 调度，取消未到期 `scheduled` 运行（`DEFINITION_DISABLED`）；
   `queued/running/retry_wait` 继续。重新启用不自动恢复调度，必须由操作员显式恢复且不补跑。
9. 目标/凭据禁用时，在同一事务中把该目标的 `queued/retry_wait` 运行标记失败（`TARGET_DISABLED`），
   `running` 允许完成；worker 认领前再次校验目标/凭据 active。

全局并发由 worker 线程数（`TASK_CONTROL_WORKER_CONCURRENCY`）限制；单定义并发由
`task_definition_runtime` 原子计数限制。同一任务定义内按 `queued_at, id` FIFO；跨定义采用
work-conserving 选择，跳过已达定义并发上限的运行，避免单一定义阻塞全局。

### 5. Retry State Machine

- 可重试：超时、连接失败、DNS/TLS 临时错误、SSH 连接中断、HTTP 408/429/5xx、worker 失联。
- 不可重试：参数校验、认证/权限、主动取消、其他 HTTP 4xx、配置错误、目标/凭据被禁用。
- 本机脚本和 SSH 的非零退出码默认不可重试；任务定义可通过 `retry_on_exit_codes` 显式列入。
- 退避：`delay = min(initial_backoff * multiplier^(attempt-1), max_backoff)`，默认 30s、2x、10m。
- 运行级 `attempt_count` 与 `max_attempts` 控制；尝试表保存每次参数快照引用、错误分类和输出摘要。
- 手工重试创建新运行，复制原运行参数快照和定义版本，写 `parent_run_id`；原运行不可变。

### 6. Executor Design

统一 Python Protocol：

```python
class TaskExecutor(Protocol):
    def execute(self, ctx: ExecutionContext) -> ExecutionResult: ...
```

`ExecutionContext` 包含定义版本、解析后参数、目标配置、解密后的凭据、超时、输出上限和取消事件。
运行和调度在创建时保存 `target_snapshot`（目标配置 + 凭据引用，不含密钥），重试和调度触发复用
该快照，避免目标后续修改静默改变已有工作。
`ExecutionResult` 包含状态、退出码/HTTP 状态、错误分类、stdout/stderr/响应摘要、耗时。

- **LocalScriptExecutor**：`subprocess.Popen`，`shell=False`，argv 模板按结构化参数替换；工作目录
  限制在配置的脚本根目录；`start_new_session=True`，超时杀进程组；读取线程限量并持续排空管道。
- **SshExecutor**：paramiko；严格 known_hosts 校验；密码/私钥凭据仅在内存解密；连接/执行超时；
  捕获退出状态和输出摘要；主机密钥变化默认拒绝。
- **HttpExecutor**：httpx.Client；TLS 校验；可配置重定向；支持方法/头/体/凭据引用；成功条件为
  状态码集合 + 可选响应头/响应体正则；捕获状态码、响应头和响应体摘要。
- **Registry**：`executor_type -> factory` 的显式注册表；新增类型通过代码和部署完成，不接受运行时
  上传（FR-050）。

所有执行器在返回前调用 `redact()`，用敏感参数值和凭据值做精确替换，并过滤常见 Token 格式。

### 7. Parameter Schema and Secret Handling

- 参数结构使用 JSON Schema 2020-12 子集，支持 string/integer/number/boolean/date-time/enum/array/
  object；敏感字段标记 `x-secret: true` 和 `writeOnly: true`。
- 后端用 `jsonschema` 校验：禁止远程 `$ref`、限制递归深度和总大小、校验 key 命名和默认值。
- 提交时应用默认值，生成规范化参数快照；敏感值用 AES-256-GCM 加密后存入 `parameters`，同时生成
  `parameters_redacted` 用于列表和 UI 展示。
- 重试、手工重试、调度触发均复用同一份参数快照；凭据引用在每次尝试时解析当前有效凭据，
  不缓存解密值；凭据轮换后的下一次 attempt 使用新值，凭据禁用时按 `TARGET_DISABLED` 失败。
- UI 通过 RJSF + Ant Design 根据同一份 JSON Schema 生成表单；敏感字段使用密码控件且永不回显。

### 8. Authentication and Security

- 本地账号；Argon2id 密码哈希；用户名唯一（大小写归一化）。
- 登录成功后创建服务端会话：HttpOnly/Secure/SameSite=Lax Cookie + 会话表；CSRF token 存于
  可读 Cookie 并通过 `X-CSRF-Token` 回传，服务端比对哈希。
- 连续 5 次失败锁定 15 分钟；会话空闲 30 分钟、绝对 8 小时过期；支持退出、单会话吊销和全部吊销。
- API 使用可撤销的个人访问令牌（Bearer），令牌只存哈希，创建时仅显示一次。运维自动化通过 API/
  脚本完成，不交付独立运维 CLI；`cli.py` 只用于部署引导和维护命令。
- RBAC：管理员管理用户/目标/凭据/全局配置；操作员管理定义/调度/运行；观察者只读；服务端强制。
- 凭据用 AES-256-GCM 加密，密钥从环境变量 key ring 加载；支持 key_version 轮换。
- 防命令注入：不拼接 shell；本地脚本参数作为 argv/env 传递。
- 防 SSRF：目标必须由管理员登记；HTTP 默认阻止云元数据地址和回环/链路本地地址，除非目标显式允许。
- 登录和写操作限流；超限返回 429 + `Retry-After`；登录失败同时受数据库锁定。
- 安全响应头：CSP（`frame-ancestors 'none'`、`default-src 'self'`，Ant Design 内联样式使用受限
  `style-src`）、`X-Content-Type-Options: nosniff`、`Referrer-Policy: same-origin`；HTTPS 下启用 HSTS。
- 审计记录登录、账号、定义、目标、凭据、调度、提交、取消、重试、越权和配置变更。

### 9. API Design

- 基础路径 `/api/v1`；OpenAPI 3.1；Swagger UI 在 `/api/docs`。
- 统一错误结构、分页结构和过滤约定，详见 [contracts/openapi.yaml](contracts/openapi.yaml) 与
  [contracts/error-codes.md](contracts/error-codes.md)。
- 运行提交支持 `Idempotency-Key`；更新使用 `If-Match` + `version` 乐观并发；缺失返回 428，
  版本不匹配返回 409。不兼容 API 变更记录在 `docs/api-compatibility.md`，包含影响、迁移和回滚。
- 时间为 ISO 8601 UTC；列表支持 `page/page_size/sort` 和领域筛选。
- 不返回密码、会话令牌、凭据明文或内部异常堆栈；错误带 `correlation_id`。

### 10. Frontend Design

- React 18 + TypeScript + Vite + Ant Design 5；TanStack Query 管理服务端状态；React Router 6 路由。
- 页面：登录、仪表盘、任务定义、调度、运行、统计、目标、凭据、用户、审计、个人设置。
- 动态参数表单：`@rjsf/core` + `@rjsf/antd` + AJV，自定义 `secret` 控件；提交前后端双重校验。
- 运行详情：状态时间线、每次尝试、参数（脱敏）、输出摘要、取消/重试操作。
- 并发编辑：更新请求携带 `If-Match: "<version>"`；缺失返回 428，版本不匹配返回 409，界面保留
  用户输入并提示刷新。
- 统计：成功率、运行数、平均/P95 耗时、按定义/触发方式/执行入口分组；Recharts 图表 + Ant Design
  Table 下钻。
- 轮询：活动运行/仪表盘 3 秒，调度 30 秒，定义/统计 60 秒；请求失败显示重试和最后更新时间。
- 状态：Skeleton 加载、Empty 空态、Result 错误页、全局错误边界；危险操作 Modal 确认；409 冲突
  提示刷新；429 显示等待时间。
- 权限：按角色生成导航和操作；隐藏入口不等于授权，所有写操作仍由服务端校验。
- 响应式：Ant Design Grid + 表格在窄屏切换卡片；中文界面；键盘焦点、表单标签、对比度满足基本无障碍。
- 生产构建由 FastAPI 托管 `frontend/dist`；开发时 Vite 代理 `/api` 到后端。

### 11. Observability, Retention, and Operations

- 结构化 JSON 日志：`timestamp`、`level`、`component`、`correlation_id`、`run_id`、`attempt_id`、
  `actor_id`、`message`；敏感值脱敏。
- 审计表 append-only；管理员可查询；保留 13 个月。
- 健康检查 `/api/v1/health/live`（进程存活）和 `/api/v1/health/ready`（数据库、调度器/worker 心跳）。
- 运行保留 13 个月；尝试和输出明细保留 90 天；保留任务每日执行一次，删除前记录计数。
- 迁移由 Alembic 管理；部署时先跑 `alembic upgrade head`，再启动进程。
- 单控制面；调度器用 advisory lock 保证单领导者；worker 可多线程，但 v1 不跨主机分布式部署。

### 12. Testing Strategy

- 单元：状态机、重试分类、退避、cron/间隔/DST、参数校验、脱敏、权限策略、幂等/并发冲突。
- 集成：testcontainers PostgreSQL，验证迁移、唯一约束、`SKIP LOCKED` 认领、并发计数、事务回滚、
  调度 exactly-once、reaper 对账。
- 契约：OpenAPI 响应/错误码校验；前端生成客户端编译检查。
- 执行器：本机脚本真实子进程；HTTP 用 respx；SSH 用 fake transport + 可选容器化 sshd 集成。
- API：httpx + ASGI，覆盖认证、CSRF、RBAC、分页、幂等、429、409、428、错误结构。
- 前端：Vitest + Testing Library 覆盖表单/状态；Playwright 覆盖登录、创建定义、提交、调度、
  重试、统计、越权。
- 性能：后端负载测试断言 SC-002/003/007，前端页面性能断言 SC-012；固定 4 vCPU/8 GB 环境，
  发布前运行，结果写入 `backend/tests/performance/` 与 `frontend/tests/performance/`。
- 可用性：Polish 阶段至少 10 名目标操作员参与，验证 SC-010/011，记录到
  `usability-report.md`；未达标不得勾选 SC。
- 所有测试使用独立数据库/事务回滚；固定时钟和固定随机种子；CI 门禁为 Ruff + pytest + 前端 lint/test/build。

### 13. Delivery Phases

1. **Foundation**：项目骨架、配置、数据库迁移、用户/会话/CSRF/RBAC、审计、健康检查。
2. **Definitions & Targets**：任务定义/版本、JSON Schema 参数、执行目标、凭据加密、管理员页面。
3. **Execution Core**：本机脚本执行器、运行队列、worker、尝试记录、取消、reaper。
4. **Remote Executors**：SSH 和 HTTP 执行器、目标白名单、凭据轮换、失败分类。
5. **Scheduling & Retry**：一次性/cron/间隔、重叠/错过、重试退避、手工重试、调度页面。
6. **Stats & UI Polish**：统计聚合、下钻、仪表盘、轮询、响应式/无障碍、审计页面。
7. **Hardening**：限流、并发冲突、性能测试、Playwright 端到端、部署与运行手册。

### 14. Risks and Mitigations

| 风险 | 影响 | 缓解 |
|------|------|------|
| 调度器多实例重复触发 | 重复执行 | advisory lock + `(schedule_id, scheduled_for)` 唯一约束 + 幂等 |
| worker 崩溃导致运行卡住 | 运行永久 running | 租约/心跳 + reaper + `WORKER_LOST` 重试 |
| 本机脚本输出过大 | 内存/存储压力 | 读取线程限量 + 持续排空 + 1 MB 截断 |
| SSH 主机密钥变化 | 中间人风险 | 严格 known_hosts + 默认拒绝 + 管理员显式更新 |
| HTTP 目标 SSRF | 内网探测/元数据泄露 | 管理员目标白名单 + 默认阻止元数据/回环地址 |
| 参数/凭据泄露 | 安全事件 | AES-GCM + 脱敏 + 永不回显 + 审计 |
| 并发编辑覆盖 | 数据丢失 | `If-Match` 乐观并发 + 428 缺失/409 冲突提示 |
| 统计与明细不一致 | 运营误判 | 同一事务写运行/尝试；统计从运行表聚合；对账测试 |
| 前端轮询造成负载 | API 压力 | 活动页面 3 秒、非活动 30/60 秒；ETag/缓存；分页 |

### 15. Requirements Traceability

| 需求范围 | 设计落点 |
|----------|----------|
| FR-001 ~ FR-010 任务定义/版本/目标 | `domain/entities.py`、`application/definitions`、`task_definitions`/`task_definition_versions` |
| FR-011 ~ FR-019 提交/队列/取消 | `application/runs`、`runs` 表、worker claim、`task_definition_runtime` |
| FR-020 ~ FR-025 调度 | `scheduler/loop.py`、`scheduler/cron.py`、`schedules` 表、唯一约束 |
| FR-026 ~ FR-032 执行 | `infrastructure/executors/*`、`attempts` 表、租约/reaper |
| FR-033 ~ FR-038 重试 | `domain/policies.py`、`retry_wait/next_retry_at`、`parent_run_id` |
| FR-039 ~ FR-043 统计 | `application/stats`、运行/尝试聚合查询、UTC 时间边界 |
| FR-044 ~ FR-050 安全/审计/接口 | `infrastructure/security/*`、`audit_events`、`api/errors.py`、OpenAPI |
| FR-051 ~ FR-057 Web 控制台 | `frontend/*`、RJSF 动态表单、角色导航、脱敏展示 |
| FR-058 ~ FR-060 本地账号/会话/审计 | `users`/`sessions`/`api_tokens`、Argon2id、CSRF、审计 |
| FR-061 ~ FR-062 并发/限流 | `If-Match`、`version`、登录锁定、写操作限流 |
| FR-063 健康检查 | `/api/v1/health/live`、`/api/v1/health/ready` |

## Complexity Tracking

> 无宪法违规项，无需例外说明。

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| 无 | — | — |

## Phase 0 / Phase 1 Outputs

- [research.md](research.md)：技术选型、调度/队列/认证/执行器/前端/测试/部署决策与替代方案。
- [data-model.md](data-model.md)：表结构、约束、索引、状态机、事务边界、加密与保留策略。
- [contracts/openapi.yaml](contracts/openapi.yaml)：REST API 契约。
- [contracts/error-codes.md](contracts/error-codes.md)：统一错误码。
- [contracts/executor-interface.md](contracts/executor-interface.md)：执行器扩展契约。
- [contracts/ui-routes.md](contracts/ui-routes.md)：前端路由、角色和页面数据契约。
- [quickstart.md](quickstart.md)：本地/容器启动与端到端验证场景。
