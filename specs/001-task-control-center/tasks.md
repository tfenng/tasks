# Tasks: 任务中控系统（Task Control Center）

**Input**: Design documents from `/specs/001-task-control-center/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Implementation Status (2026-10-30)**: Backend MVP + schedules + retry + targets/credentials + SSH/HTTP executors + stats + users/sessions/tokens/audit + Docker/CI + React console implemented. `[X]` marks completed tasks. Full UI polish, comprehensive tests, and validation remain pending.

**Tests**: 本任务清单包含测试任务。项目宪法第 VII 条要求核心业务规则、数据库事务、权限和关键 API
必须有自动化测试，因此测试不是可选项。

**Organization**: 任务按用户故事分组，支持独立实现、独立验证和增量交付。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行执行（不同文件，且不依赖未完成任务）
- **[Story]**: 所属用户故事（US1 ~ US6）
- 每个任务都包含明确文件路径

## Path Conventions

- 后端：`backend/src/task_control/`、`backend/tests/`、`backend/migrations/`
- 前端：`frontend/src/`、`frontend/tests/`
- 部署：`deploy/`
- 设计文档：`specs/001-task-control-center/`

**Constraint source**: 所有表、字段、枚举、长度、CHECK、唯一约束和索引以
`specs/001-task-control-center/data-model.md` 为准；任务描述只摘录关键约束，未逐字复述的字段仍必须
按该文件实现。API 请求/响应以 `contracts/openapi.yaml` 为准。

## Contract & Data Model Mapping

| 契约/数据 | 用户故事 |
|-----------|----------|
| auth/session/CSRF/RBAC、health、audit | Foundational、US6 |
| definitions、runs（立即/local） | US1 |
| users、audit UI、profile、角色导航 | US6 |
| schedules、scheduler | US2 |
| execution-targets、credentials、SSH/HTTP | US3 |
| retry、attempts | US4 |
| stats/runs、stats/attempts、dashboard | US5 |

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 工程骨架、依赖、构建、测试与部署基础设施。

- [X] T001 创建后端工程骨架与依赖声明，包含 FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、psycopg 3、croniter、paramiko、httpx、cryptography、argon2-cffi、jsonschema、loguru，写入 `backend/pyproject.toml`
- [ ] T002 配置 Ruff、mypy、pytest、pytest-cov 与测试路径，写入 `backend/pyproject.toml`
- [ ] T003 [P] 创建 React 18 + TypeScript + Vite 前端工程与依赖（Ant Design 5、TanStack Query 5、React Router 6、RJSF、Recharts、openapi-fetch），写入 `frontend/package.json`
- [ ] T004 [P] 配置 ESLint、Prettier、Vitest、Testing Library 与 Playwright，写入 `frontend/eslint.config.js`、`frontend/vitest.config.ts`、`frontend/playwright.config.ts`（仅创建配置文件，不修改 `frontend/package.json`）
- [X] T005 [P] 创建 Docker Compose（db/api/scheduler/worker/migrate）和环境变量样例，写入 `deploy/docker-compose.yml`、`deploy/.env.example`
- [X] T006 [P] 创建多阶段 Dockerfile（前端构建 + 后端运行时）与可选 Nginx 配置，写入 `deploy/Dockerfile`、`deploy/nginx.conf`
- [X] T007 [P] 配置 Alembic（`task_control` schema、迁移目录、UTC 约定），写入 `backend/alembic.ini`、`backend/migrations/env.py`
- [X] T008 [P] 实现 loguru JSON 日志与 correlation_id 工具，写入 `backend/src/task_control/infrastructure/logging.py`
- [X] T009 [P] 实现 pydantic-settings 配置（`TASK_CONTROL_` 前缀、数据库 URL、密钥 key ring、脚本根、known_hosts、保留期、`TASK_CONTROL_WORKER_CONCURRENCY`），写入 `backend/src/task_control/config.py`
- [ ] T010 [P] 创建 CI 工作流，运行后端 Ruff/mypy/pytest、前端 lint/test/build、Playwright 冒烟，写入 `.github/workflows/ci.yml`
- [X] T011 创建后端测试夹具（testcontainers PostgreSQL、应用工厂、迁移、事务回滚、固定时钟），写入 `backend/tests/conftest.py`
- [ ] T012 [P] 创建前端测试夹具与 API mock 基础，写入 `frontend/tests/setup.ts`、`frontend/tests/mocks/server.ts`
- [ ] T013 [P] 编写后端/前端开发说明与常用命令，写入 `backend/README.md`、`frontend/README.md`
- [ ] T014 [P] 创建验证用示例脚本（hello、flaky、slow、HTTP mock），写入 `backend/scripts/example_tasks/`

**Checkpoint**: 工程可安装、可启动空应用、可运行测试骨架。

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 数据库、认证、错误处理、日志、健康检查、前端壳层等所有用户故事共享的基础。

**⚠️ CRITICAL**: 本阶段完成前，不得开始任何用户故事的实现。

### Database & Domain Foundations

- [X] T015 实现 SQLAlchemy engine/session/Base 与 UTC 约定，写入 `backend/src/task_control/infrastructure/db/session.py`
- [ ] T016 创建 `users`、`sessions`、`api_tokens` 迁移，包含 `role IN ('admin','operator','viewer')`、用户名 3–64 且小写唯一、密码哈希非空，写入 `backend/migrations/versions/0001_identity.py`
- [X] T017 创建 `task_definitions`、`task_definition_versions`、`task_definition_runtime` 迁移，包含 key 正则 `^[a-z][a-z0-9_-]{1,99}$`、版本唯一 `(definition_id, version_no)`、timeout 1–86400、max_concurrency 1–100，写入 `backend/migrations/versions/0002_definitions.py`
- [ ] T018 创建 `execution_targets`、`credentials` 迁移，包含类型枚举 `local/ssh/http`、凭据 `password/ssh_key/http_bearer/http_basic`、密文与 key_version，写入 `backend/migrations/versions/0003_targets.py`
- [ ] T019 创建 `workers`、`schedules`、`runs`、`attempts` 迁移（先建 `workers` 以满足 `runs.worker_id` 外键），包含状态 CHECK、`(schedule_id, scheduled_for)` 部分唯一、`(created_by, idempotency_key)` 部分唯一、`attempt_no` 唯一，写入 `backend/migrations/versions/0004_execution.py`
- [X] T020 创建 `audit_events` 迁移与运行队列/租约/审计索引，写入 `backend/migrations/versions/0005_operations.py`
- [ ] T021 [P] 实现身份/会话/Token ORM 模型，写入 `backend/src/task_control/infrastructure/db/models/identity.py`
- [ ] T022 [P] 实现定义/版本/目标/凭据 ORM 模型，写入 `backend/src/task_control/infrastructure/db/models/definitions.py`
- [ ] T023 [P] 实现调度/运行/尝试/工作器/审计 ORM 模型，写入 `backend/src/task_control/infrastructure/db/models/execution.py`
- [ ] T024 实现仓储基类、Unit of Work 与事务边界辅助，写入 `backend/src/task_control/infrastructure/db/repositories/base.py`
- [ ] T025 定义领域枚举、实体、值对象和领域异常，写入 `backend/src/task_control/domain/enums.py`、`backend/src/task_control/domain/entities.py`、`backend/src/task_control/domain/errors.py`
- [ ] T026 定义仓储、Clock、TaskExecutor、SecretProvider 端口，写入 `backend/src/task_control/domain/ports.py`
- [ ] T027 实现运行/尝试/调度状态机与基础策略骨架，写入 `backend/src/task_control/domain/policies.py`

### Security & Cross-Cutting

- [X] T028 实现 Argon2id 密码哈希与校验，写入 `backend/src/task_control/infrastructure/security/passwords.py`
- [X] T029 实现服务端会话、CSRF token 和会话吊销，写入 `backend/src/task_control/infrastructure/security/sessions.py`
- [ ] T030 实现 API Token 生成、哈希、校验与吊销，写入 `backend/src/task_control/infrastructure/security/tokens.py`
- [X] T031 实现 AES-256-GCM key ring 与敏感值加密/解密，写入 `backend/src/task_control/infrastructure/security/secrets.py`
- [X] T032 实现 RBAC 依赖（admin/operator/viewer）与服务端资源级授权，写入 `backend/src/task_control/api/deps.py`
- [X] T033 实现统一错误响应、异常映射与 correlation_id 中间件，写入 `backend/src/task_control/api/errors.py`
- [ ] T034 实现分页、排序、筛选参数解析与统一响应辅助，写入 `backend/src/task_control/api/pagination.py`
- [ ] T035 实现登录锁定、写操作限流与 429/Retry-After；超限请求写审计，写入 `backend/src/task_control/api/rate_limit.py`
- [X] T036 实现 `/health/live` 与 `/health/ready`，检查数据库和调度器/worker 心跳，写入 `backend/src/task_control/api/v1/health.py`
- [X] T037 实现 append-only 审计仓储与服务，写入 `backend/src/task_control/infrastructure/db/repositories/audit.py`、`backend/src/task_control/application/audit/service.py`
- [ ] T038 创建 FastAPI 应用工厂、路由注册、安全响应头、SPA 静态托管与 SPA fallback，写入 `backend/src/task_control/main.py`

### Frontend Shell

- [ ] T039 由 `contracts/openapi.yaml` 生成 TypeScript 客户端并实现 fetch 包装（CSRF、401、错误解析），写入 `frontend/src/lib/api/client.ts`
- [ ] T040 实现应用 Providers、路由、布局、认证上下文和角色导航，写入 `frontend/src/app/`
- [ ] T041 实现共享 PageState、ConfirmAction、RunStatus、DataTable 组件，写入 `frontend/src/components/`
- [X] T042 实现登录页、退出、会话过期处理和 403 页面，写入 `frontend/src/pages/login/`、`frontend/src/app/guards.tsx`

### Foundational Tests

- [ ] T043 [P] 编写迁移与约束集成测试（唯一键、CHECK、UTC、部分索引），写入 `backend/tests/integration/test_migrations.py`
- [ ] T044 [P] 编写认证/会话/CSRF/RBAC 集成测试，写入 `backend/tests/integration/test_auth.py`
- [ ] T045 [P] 编写密钥加密、错误响应、分页、限流与限流审计单元测试，写入 `backend/tests/unit/test_security.py`、`backend/tests/unit/test_api_helpers.py`
- [ ] T046 [P] 编写前端 auth/layout/API wrapper 测试，写入 `frontend/tests/unit/auth.test.tsx`
- [ ] T047 实现部署引导与维护 CLI（create-admin、reset-password、retention 触发；不是业务 CLI），写入 `backend/src/task_control/cli.py`

**Checkpoint**: 基础认证、数据库、错误处理、健康检查和前端壳层可独立运行。

---

## Phase 3: User Story 1 - 定义任务并立即执行 (Priority: P1) 🎯 MVP

**Goal**: 创建带参数 Schema 的任务定义，提交一次立即运行，由本机脚本执行并记录结果。

**Independent Test**: 创建带必填/可选参数和本地脚本入口的定义；提交合法参数后运行到达终态并
可查看参数快照、退出码和输出；提交非法参数被拒绝且不产生运行。

### Tests for User Story 1

- [ ] T048 [P] [US1] 编写 definitions/runs 契约测试，覆盖请求/响应/错误结构，写入 `backend/tests/contract/test_definitions_runs.py`
- [X] T049 [P] [US1] 编写参数 Schema 单元测试（必填、默认、类型、枚举、嵌套、敏感字段、大小限制），写入 `backend/tests/unit/test_parameters.py`
- [X] T050 [P] [US1] 编写本机执行器单元测试（成功、非零退出、超时、取消、输出截断、脱敏），写入 `backend/tests/unit/test_local_executor.py`
- [ ] T051 [P] [US1] 编写运行状态机与不变量单元测试，写入 `backend/tests/unit/test_run_state_machine.py`
- [ ] T052 [P] [US1] 编写“定义 → 立即运行 → worker 执行 → 终态”集成测试，写入 `backend/tests/integration/test_immediate_run.py`

### Implementation for User Story 1

- [ ] T053 [US1] 实现 TaskDefinition/TaskDefinitionVersion/TaskRun/TaskAttempt 领域实体与校验，写入 `backend/src/task_control/domain/entities.py`
- [X] T054 [US1] 实现定义/版本/运行/尝试仓储，写入 `backend/src/task_control/infrastructure/db/repositories/definitions.py`、`backend/src/task_control/infrastructure/db/repositories/runs.py`
- [ ] T055 [US1] 实现 JSON Schema 2020-12 子集校验、默认值应用、敏感字段标记与 256 KB 限制，写入 `backend/src/task_control/domain/parameters.py`
- [ ] T056 [US1] 实现定义服务：创建、修改生成不可变新版本、列表、启用、禁用、归档；禁用时暂停关联调度并取消未到期 `scheduled` 运行（`DEFINITION_DISABLED`），归档取消未开始运行，写入 `backend/src/task_control/application/definitions/service.py`
- [X] T057 [US1] 实现立即运行提交：校验定义/版本、目标/凭据 active、参数、加密敏感参数、幂等键与 request_hash；目标/凭据禁用返回 `TARGET_DISABLED`；本机执行可基于定义版本生成本地目标快照，显式目标管理在 US3 加入，写入 `backend/src/task_control/application/runs/service.py`
- [X] T058 [P] [US1] 实现 definitions API（列表、创建、详情、更新、启停、归档、版本列表/详情）；PATCH/状态动作要求 `If-Match`，缺失 428、版本冲突 409、响应返回新 `version`，写入 `backend/src/task_control/api/v1/definitions.py`
- [X] T059 [P] [US1] 实现 runs API（提交、列表、详情、取消、参数脱敏、幂等返回），写入 `backend/src/task_control/api/v1/runs.py`
- [X] T060 [US1] 实现 TaskExecutor 注册表、本机脚本执行器（`shell=False`、进程组、超时、输出上限、脱敏），写入 `backend/src/task_control/infrastructure/executors/`
- [X] T061 [US1] 实现 worker 队列认领、runtime 原子计数、尝试创建和租约；同定义按 `queued_at, id` FIFO，跨定义 work-conserving 跳过已达定义并发的运行，全局槽位由 `TASK_CONTROL_WORKER_CONCURRENCY` 控制；每次创建 attempt 时从目标快照的 credential_id 解析当前 active 凭据（不缓存），禁用则失败为 `TARGET_DISABLED`，写入 `backend/src/task_control/worker/loop.py`
- [ ] T062 [US1] 实现 worker 完成/失败/取消写回、运行终态和 runtime 释放，写入 `backend/src/task_control/worker/loop.py`
- [X] T063 [US1] 实现 worker 心跳与 reaper 失联运行对账（`WORKER_LOST`），写入 `backend/src/task_control/worker/heartbeat.py`、`backend/src/task_control/worker/reaper.py`
- [ ] T064 [US1] 为定义创建/修改/启停/归档、运行提交/取消/完成写审计事件，写入 `backend/src/task_control/application/audit/events.py`
- [ ] T065 [US1] 实现定义列表、详情、创建/编辑页与 RJSF 动态本机脚本表单，写入 `frontend/src/pages/definitions/`
- [ ] T066 [US1] 实现运行列表、详情、状态时间线、尝试、脱敏参数和取消操作，写入 `frontend/src/pages/runs/`
- [ ] T067 [US1] 实现 definitions/runs 的 query key、3 秒轮询、空/错/加载状态和表单错误映射，写入 `frontend/src/features/definitions/`、`frontend/src/features/runs/`
- [ ] T068 [US1] 扩展立即运行集成测试：成功、失败、参数非法、取消、reaper 对账、同定义 FIFO、跨定义 work-conserving 和全局并发上限，写入 `backend/tests/integration/test_immediate_run.py`
- [ ] T069 [US1] 按 quickstart 场景 2/3 手动验证本地定义、立即执行、参数校验与输出脱敏，记录结果到 `specs/001-task-control-center/quickstart.md`

**Checkpoint**: US1 可独立交付：管理员/操作员可用 API 或 Web UI 定义任务、立即执行并查看结果。

---

## Phase 4: User Story 6 - 通过 Web 管理界面完成任务运维 (Priority: P1)

**Goal**: 交付控制台基础、用户/审计/个人设置和跨页体验；后续故事补充调度、远程、重试、统计页面。

**Independent Test**: 管理员仅通过 Web UI 创建操作员/观察者、重置密码、查看审计；观察者看不到写
操作且 API 拒绝越权；登录、CSRF、会话过期和 403 页面行为正确。

> 说明：US6 是横切交付目标。本阶段先交付控制台壳层、用户/审计/个人设置和跨页规范；各业务故事
> 阶段补充自己的页面，最终在 Polish 阶段验证完整控制台。

### Tests for User Story 6

- [ ] T070 [P] [US6] 编写 users/audit 契约测试与 UI 路由访问测试，覆盖缺少 `If-Match` 的 428、旧版本 409、正确版本 200、无自助注册入口，写入 `backend/tests/contract/test_users_audit.py`、`frontend/tests/unit/routes.test.tsx`
- [ ] T071 [P] [US6] 编写角色权限、CSRF、会话吊销、未认证访问和无自助注册集成测试，写入 `backend/tests/integration/test_rbac.py`

### Implementation for User Story 6

- [X] T072 [P] [US6] 实现用户管理服务/API：创建、更新显示名/角色/状态、重置密码；更新要求 `If-Match`，缺失 428、版本冲突 409、响应返回新 `version`，写入 `backend/src/task_control/application/auth/users.py`、`backend/src/task_control/api/v1/users.py`
- [X] T073 [P] [US6] 实现审计列表 API 与筛选分页，写入 `backend/src/task_control/api/v1/audit.py`
- [X] T074 [US6] 实现用户管理页（创建、禁用、重置密码、角色分配），写入 `frontend/src/pages/users/`
- [X] T075 [US6] 实现审计页（操作者/动作/资源/时间筛选），写入 `frontend/src/pages/audit/`
- [X] T076 [US6] 实现个人设置页（改密码、会话列表/吊销、API Token 创建/吊销），写入 `frontend/src/pages/profile/`
- [ ] T077 [US6] 完善角色导航、路由守卫、403 页面和服务端越权提示，写入 `frontend/src/app/guards.tsx`、`frontend/src/app/layout/`
- [ ] T078 [US6] 统一加载/空/错误/409/428/429 状态与危险操作确认模式；409/428 保留用户输入并提示刷新，写入 `frontend/src/components/PageState/`、`frontend/src/components/ConfirmAction/`
- [ ] T079 [US6] 完成键盘导航、表单标签、对比度和 375px 响应式检查，写入 `frontend/src/styles/`、`frontend/src/app/layout/`
- [ ] T080 [US6] 编写 Playwright 冒烟：登录、创建操作员、创建定义、立即运行、查看结果，写入 `frontend/tests/e2e/auth-and-run.spec.ts`
- [ ] T081 [US6] 按 quickstart 场景 1/9 验证登录、角色、CSRF、幂等和会话吊销，记录结果到 `specs/001-task-control-center/quickstart.md`

**Checkpoint**: 控制台可登录、可管理用户/审计/个人设置，角色边界和跨页体验一致。

---

## Phase 5: User Story 2 - 配置定时、间隔与一次性调度 (Priority: P2)

**Goal**: 支持一次性、cron 和固定间隔调度，暂停/恢复/取消，重叠与错过处理。

**Independent Test**: 创建一次性/间隔调度，观察触发时间、下一次触发时间、暂停/恢复/取消；服务停止
跨过触发点后验证错过/合并补跑；重叠时按策略跳过或排队。

### Tests for User Story 2

- [ ] T082 [P] [US2] 编写 cron/间隔/一次性/DST/重叠/错过单元测试，使用固定时钟，写入 `backend/tests/unit/test_scheduling.py`
- [ ] T083 [P] [US2] 编写调度 exactly-once、暂停/恢复、禁用定义联动、无自动恢复/补跑、错过/合并集成测试，写入 `backend/tests/integration/test_scheduler.py`
- [ ] T084 [P] [US2] 编写 schedules 契约测试，写入 `backend/tests/contract/test_schedules.py`

### Implementation for User Story 2

- [ ] T085 [US2] 实现 Schedule 领域实体、仓储与状态机，写入 `backend/src/task_control/domain/schedules.py`、`backend/src/task_control/infrastructure/db/repositories/schedules.py`
- [ ] T086 [US2] 实现调度服务：创建/更新/暂停/恢复/取消、`pause_for_definition`，复制目标快照并记录版本/参数；恢复从当前时间计算下一次触发，不补跑，写入 `backend/src/task_control/application/schedules/service.py`
- [ ] T087 [P] [US2] 实现 croniter + zoneinfo 的 next-fire 计算，处理一次性、固定间隔、DST/时钟跳变，写入 `backend/src/task_control/scheduler/cron.py`
- [ ] T088 [US2] 实现调度循环：advisory lock、批量到期查询、`FOR UPDATE SKIP LOCKED`、事务推进；触发时校验目标/凭据 active，禁用则创建 `failed`（`TARGET_DISABLED`）而非 `queued`，写入 `backend/src/task_control/scheduler/loop.py`
- [ ] T089 [US2] 实现 `(schedule_id, scheduled_for)` 唯一触发、重叠 skip/queue、跳过/错过记录和宽限期合并，写入 `backend/src/task_control/scheduler/loop.py`
- [ ] T090 [US2] 实现一次性 `scheduled` 运行提升为 `queued`；提升前校验目标/凭据 active，禁用则标记 `failed`（`TARGET_DISABLED`），写入 `backend/src/task_control/scheduler/loop.py`
- [X] T091 [US2] 实现 schedules API（列表/创建/详情/更新/暂停/恢复/取消）；更新和状态动作要求 `If-Match`，缺失 428、版本冲突 409、响应返回新 `version`，写入 `backend/src/task_control/api/v1/schedules.py`
- [ ] T092 [US2] 实现调度列表、创建/编辑、详情页，包含初始 fire_at/cron/interval、时区和策略；编辑携带 `If-Match` 并处理 409/428，写入 `frontend/src/pages/schedules/`
- [ ] T093 [US2] 实现下一次触发、暂停/恢复/取消、关联运行下钻和状态反馈；状态动作携带 `If-Match` 并处理 409/428，写入 `frontend/src/pages/schedules/`
- [ ] T094 [US2] 扩展调度集成测试：重叠、错过、DST、取消、禁用/归档定义联动，写入 `backend/tests/integration/test_scheduler.py`
- [ ] T095 [US2] 按 quickstart 场景 4/5 验证一次性、间隔、暂停/恢复/取消和重叠/错过，记录结果到 `specs/001-task-control-center/quickstart.md`

**Checkpoint**: US2 可独立交付：调度创建、触发、暂停/恢复/取消、重叠/错过均可用。

---

## Phase 6: User Story 3 - 通过 SSH 和 HTTP 触发远程任务 (Priority: P3)

**Goal**: 管理员登记执行目标/凭据；任务定义可用 SSH 命令或 HTTP 请求执行，安全处理认证、TLS、
主机密钥和失败分类。

**Independent Test**: 注册 SSH/HTTP 任务，使用测试主机/端点提交；成功、认证失败、连接失败、超时和
非预期响应均正确分类；目标白名单生效；凭据不出现在响应/日志。

### Tests for User Story 3

- [ ] T096 [P] [US3] 编写 HTTP 执行器单元测试（2xx/4xx/5xx/429、超时、TLS、重定向、响应条件、脱敏），使用 respx，写入 `backend/tests/unit/test_http_executor.py`
- [ ] T097 [P] [US3] 编写 SSH 执行器单元测试（成功、认证失败、主机密钥变化、超时、取消），使用 fake transport，写入 `backend/tests/unit/test_ssh_executor.py`
- [ ] T098 [P] [US3] 编写 targets/credentials 契约测试，确认响应永不含 secret，写入 `backend/tests/contract/test_targets_credentials.py`
- [ ] T099 [P] [US3] 编写目标类型/凭据类型匹配、禁用目标、白名单和 SSRF 集成测试，写入 `backend/tests/integration/test_targets.py`

### Implementation for User Story 3

- [X] T100 [P] [US3] 实现 ExecutionTarget/Credential 领域实体、仓储与服务，校验目标类型与凭据 kind 匹配，写入 `backend/src/task_control/application/targets/service.py`
- [X] T101 [US3] 实现 targets/credentials API：管理员权限、写-only secret、掩码元数据、禁用语义；禁用时级联失败 queued/retry_wait 运行（`TARGET_DISABLED`），凭据更新递增 version/key_version 并写审计，写入 `backend/src/task_control/api/v1/targets.py`、`backend/src/task_control/api/v1/credentials.py`
- [X] T102 [P] [US3] 实现 HTTP 执行器（httpx、TLS 校验、成功状态集合、响应头/体条件、SSRF 防护），写入 `backend/src/task_control/infrastructure/executors/http.py`
- [X] T103 [P] [US3] 实现 SSH 执行器（paramiko、known_hosts、RejectPolicy、认证/主机密钥错误分类、超时），写入 `backend/src/task_control/infrastructure/executors/ssh.py`
- [X] T104 [US3] 扩展执行器注册表与 executor_config 校验，支持 local/ssh/http 三类目标；仅代码注册，不暴露运行时上传/插件接口，写入 `backend/src/task_control/infrastructure/executors/registry.py`
- [X] T105 [US3] 实现执行目标管理页（创建/编辑/禁用、类型配置、凭据选择），写入 `frontend/src/pages/targets/`
- [X] T106 [US3] 实现凭据管理页（创建/轮换/禁用，永不回显 secret），写入 `frontend/src/pages/credentials/`
- [X] T107 [US3] 扩展任务定义表单以支持 SSH/HTTP 执行器配置和参数 Schema，写入 `frontend/src/features/definitions/ExecutorForm.tsx`
- [ ] T108 [US3] 扩展远程执行集成测试：HTTP mock、SSH 可选容器、凭据禁用、目标移除；验证 queued/retry_wait 运行失败为 `TARGET_DISABLED`、running 允许完成、新提交被拒且无新 attempt，写入 `backend/tests/integration/test_remote_execution.py`
- [ ] T109 [US3] 按 quickstart 场景 7/8/12 验证 HTTP、可选 SSH 和凭据/输出脱敏，记录结果到 `specs/001-task-control-center/quickstart.md`

**Checkpoint**: US3 可独立交付：SSH/HTTP 目标可登记、可执行、可安全失败。

---

## Phase 7: User Story 4 - 失败自动重试并保留原始参数 (Priority: P4)

**Goal**: 可重试失败按退避策略自动重试；每次尝试保留参数/版本/目标快照；耗尽后可手工重试。

**Independent Test**: 前两次失败、第三次成功的任务产生 3 条尝试，参数快照完全一致；耗尽后手工
重试创建 `parent_run_id` 关联的新运行；不可重试错误不自动重试。

### Tests for User Story 4

- [ ] T110 [P] [US4] 编写重试分类、退避上限、退出码白名单、耗尽逻辑单元测试，写入 `backend/tests/unit/test_retry.py`
- [ ] T111 [P] [US4] 编写自动重试参数一致性、不可重试错误、手工重试 lineage 集成测试，写入 `backend/tests/integration/test_retry.py`
- [ ] T112 [P] [US4] 编写 retry/attempts 契约测试，写入 `backend/tests/contract/test_retry_attempts.py`

### Implementation for User Story 4

- [ ] T113 [P] [US4] 实现 RetryPolicy 领域策略与错误分类（timeout/connection/HTTP 429/5xx/worker lost/exit codes），写入 `backend/src/task_control/domain/retry.py`
- [X] T114 [US4] 在 worker 完成路径实现 `retry_wait`、`next_retry_at`、退避计算和 runtime 释放；重试 attempt 由 T061 在创建时重新解析当前凭据，不缓存旧值，写入 `backend/src/task_control/worker/loop.py`
- [X] T115 [US4] 在调度循环中提升到期 `retry_wait` 为 `queued`，写入 `backend/src/task_control/scheduler/loop.py`
- [ ] T116 [US4] 实现 attempts 列表/详情 API，返回每次尝试的错误分类、退出码/HTTP 状态和输出摘要，写入 `backend/src/task_control/api/v1/runs.py`
- [X] T117 [US4] 实现手工重试服务/API：复制参数/版本/目标快照、写 `parent_run_id`、原运行不可变，写入 `backend/src/task_control/application/runs/service.py`
- [ ] T118 [US4] 实现 UI 重试确认、尝试时间线、下一次重试时间和不可重试原因展示，写入 `frontend/src/features/runs/`
- [ ] T119 [US4] 编写重试集成测试：3 次尝试、耗尽、手工重试、取消后不再重试、凭据在 retry_wait 期间轮换/禁用后下一次 attempt 使用新值或失败，写入 `backend/tests/integration/test_retry.py`
- [ ] T120 [US4] 按 quickstart 场景 6 验证自动/手工重试与参数保留，记录结果到 `specs/001-task-control-center/quickstart.md`

**Checkpoint**: US4 可独立交付：失败可按策略重试，参数/版本/目标快照不丢失。

---

## Phase 8: User Story 5 - 查看运行成败统计与失败详情 (Priority: P5)

**Goal**: 按定义/版本/触发/入口/状态/时间统计运行与尝试，展示成功率、耗时、失败详情并支持下钻。

**Independent Test**: 构造成功、失败、取消、跳过、重试运行；统计与运行/尝试明细逐项一致；重试不
重复计运行；筛选、分页、下钻和时区边界正确。

### Tests for User Story 5

- [ ] T121 [P] [US5] 编写成功率分母、计数规则、P95、UTC/时区分桶单元测试，写入 `backend/tests/unit/test_stats.py`
- [ ] T122 [P] [US5] 编写统计与运行/尝试明细对账、筛选、分页、60 秒内新鲜度集成测试，写入 `backend/tests/integration/test_stats.py`
- [ ] T123 [P] [US5] 编写 stats 契约测试，写入 `backend/tests/contract/test_stats.py`

### Implementation for User Story 5

- [X] T124 [US5] 实现运行/尝试统计查询：总数、成功/失败/取消/跳过/错过/重试中、成功率、平均/P95、group_by 和时区；统计查询实时无缓存，写入 `backend/src/task_control/infrastructure/db/repositories/stats.py`
- [X] T125 [US5] 实现 stats API（runs/attempts），支持 from/to/definition/version/trigger/executor/status 筛选，写入 `backend/src/task_control/api/v1/stats.py`
- [ ] T126 [US5] 实现仪表盘卡片、近期失败和活动调度，写入 `frontend/src/pages/dashboard/`
- [ ] T127 [US5] 实现统计页图表、筛选、分组和运行下钻，写入 `frontend/src/pages/stats/`
- [ ] T128 [US5] 实现运行列表完整筛选/排序/分页和统计下钻参数同步，写入 `frontend/src/pages/runs/`
- [ ] T129 [US5] 扩展统计测试并验证 quickstart 场景 10，记录结果到 `specs/001-task-control-center/quickstart.md`

**Checkpoint**: US5 可独立交付：运营人员可查看成败、耗时、失败详情并下钻。

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: 跨故事安全、性能、保留、契约、可访问性和端到端验证。

- [ ] T130 [P] 安全加固复查：CSP/安全头、CSRF、XSS、会话、SSRF、命令注入、凭据脱敏、限流；扫描路由/OpenAPI，确认不存在运行时上传或任意插件入口，写入 `backend/src/task_control/api/security_headers.py`
- [ ] T131 [P] 执行后端负载测试并断言：1,000 定义、10,000 待执行/调度、100 并发；立即运行 p99 启动 ≤10s、调度触发 p99 入队 ≤5s、30 分钟稳态无丢失/重复触发；固定 4 vCPU/8GB 环境，输出 `backend/tests/performance/results.md`
- [X] T132 [P] 实现保留清理任务（运行 13 个月、尝试/输出 90 天、审计 13 个月），写入 `backend/src/task_control/worker/retention.py`
- [ ] T133 [P] 审计覆盖复查：登录、账号、定义、目标、凭据、调度、提交、取消、重试、越权，写入 `backend/tests/integration/test_audit_coverage.py`
- [ ] T134 [P] 运行 OpenAPI/错误码契约一致性检查并修复漂移；若 OpenAPI diff 含 breaking change，必须存在对应的 `docs/api-compatibility.md` 记录；契约中不得出现运行时上传/插件入口，否则测试失败，写入 `backend/tests/contract/test_openapi_conformance.py`
- [ ] T135 [P] 前端可访问性与响应式复查（键盘、标签、对比度、375px），写入 `frontend/tests/e2e/accessibility.spec.ts`
- [ ] T136 [P] 编写完整 Playwright E2E：登录、定义、调度、远程、重试、统计、权限，写入 `frontend/tests/e2e/full-console.spec.ts`
- [ ] T137 [P] 运行 Docker Compose 冒烟：迁移、管理员创建、健康检查、API/UI 可访问，写入 `deploy/smoke.sh`
- [ ] T138 [P] 完整执行 quickstart 场景 1–12 并修复问题，更新 `specs/001-task-control-center/quickstart.md`
- [ ] T139 [P] 编写运行手册：启动顺序、迁移、备份、凭据轮换、故障排查，写入 `docs/operations.md`
- [ ] T140 [P] 执行 Web 控制台可用性测试并产出 `specs/001-task-control-center/usability-report.md`：
  至少 10 名目标操作员完成登录、创建带 5 个参数的任务定义、提交运行、配置调度、定位失败并
  手工重试、查看统计；记录完成率、耗时、阻塞点
- [ ] T141 [P] 执行前端页面性能测试并产出 `frontend/tests/performance/page-performance.spec.ts`：
  使用 10,000 条运行数据，验证任务列表、运行详情、统计首屏 p95 ≤2s；生产构建 + Lighthouse/Playwright
- [ ] T142 [P] 编写跨资源乐观并发集成测试并写入 `backend/tests/integration/test_optimistic_concurrency.py`：
  两个客户端同时更新同一任务定义、调度和用户；缺少 `If-Match` 返回 428，旧 version 返回 409，
  不得静默覆盖；覆盖 SC-017
- [ ] T143 [P] 建立 API 兼容性记录与模板，定义版本、弃用和破坏性变更流程，写入 `docs/api-compatibility.md`
- [ ] T144 最终宪法合规复查（原则 I–VIII、技术约束、质量门禁）并写入 `specs/001-task-control-center/plan.md`：
  检查不兼容 API 变更记录、迁移步骤和 OpenAPI 同步情况
- [ ] T145 清理示例脚手架、确认无明文密钥/调试开关，更新 `backend/README.md`、`frontend/README.md`

**Checkpoint**: 所有故事集成通过；安全、性能、保留、契约、API 兼容性、可访问性、可用性和并发冲突
均满足验收。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖，立即可开始。
- **Foundational (Phase 2)**: 依赖 Setup；阻塞所有用户故事。
- **US1 (Phase 3)**: 依赖 Foundational；交付最小可用任务定义 + 本地立即执行。
- **US6 (Phase 4)**: 依赖 Foundational + US1；交付控制台壳层、用户/审计/个人设置。
- **US2 (Phase 5)**: 依赖 Foundational + US1；调度不依赖 US6。
- **US3 (Phase 6)**: 依赖 Foundational + US1；远程执行不依赖 US2/US4/US5。
- **US4 (Phase 7)**: 依赖 US1 + US2（`retry_wait` 提升由调度循环完成）。
- **US5 (Phase 8)**: 依赖 US1；可在 US2–US4 之后集成完整状态统计。
- **Polish (Phase 9)**: 依赖所有目标用户故事完成。

### User Story Dependencies

```text
Setup -> Foundational -> US1
US1 -> US6
US1 -> US2 -> US4
US1 -> US3
US1 -> US5
US6 + US2 + US3 + US4 + US5 -> Polish
```

### Within Each User Story

- 测试先写并确认失败，再实现。
- 领域实体 → 仓储 → 服务 → API → UI → 集成测试。
- 同一故事内先核心路径，再错误/取消/边界。
- 每个 checkpoint 独立验证后再进入下一优先级。

### Parallel Opportunities

- Phase 1 中标 [P] 的工程/配置任务可并行。
- Phase 2 中 ORM 模型、安全模块、前端壳层可由不同成员并行（注意迁移文件顺序）。
- US2、US3、US5 在 US1 完成后可并行；US4 需 US2 的调度提升。
- 每个故事的测试任务可并行编写；UI 与后端可在契约冻结后并行。
- US6 的页面任务与 US2/US3 的后端任务可并行，但导航/权限改动需协调。
- Polish 阶段 T140 可用性、T141 前端性能、T142 并发测试可并行（依赖同一完成构建）。

---

## Parallel Example: User Story 1

```bash
# 测试并行
Task: "T048 [US1] definitions/runs 契约测试"
Task: "T049 [US1] 参数 Schema 单元测试"
Task: "T050 [US1] 本机执行器单元测试"
Task: "T051 [US1] 运行状态机单元测试"

# API 任务并行；UI 页面在对应 API 可用后进行
Task: "T058 [US1] definitions API"
Task: "T059 [US1] runs API"
```

## Parallel Example: User Story 2

```bash
Task: "T082 [US2] 调度规则单元测试"
Task: "T084 [US2] schedules 契约测试"
Task: "T087 [US2] next-fire 计算"
```

## Parallel Example: User Story 3

```bash
Task: "T096 [US3] HTTP 执行器测试"
Task: "T097 [US3] SSH 执行器测试"
Task: "T100 [US3] 目标/凭据服务"
Task: "T102 [US3] HTTP 执行器"
Task: "T103 [US3] SSH 执行器"
# T105/T106 页面在 T101 API 完成后进行
```

## Parallel Example: User Story 4

```bash
Task: "T110 [US4] 重试分类/退避单元测试"
Task: "T111 [US4] 自动/手工重试集成测试"
Task: "T113 [US4] RetryPolicy 领域策略"
```

## Parallel Example: User Story 5

```bash
Task: "T121 [US5] 成功率/计数/P95 单元测试"
Task: "T122 [US5] 统计对账集成测试"
# T126/T127/T128 页面在 T125 API 完成后进行
```

## Parallel Example: User Story 6

```bash
Task: "T070 [US6] users/audit 契约测试"
Task: "T071 [US6] 角色/CSRF/会话测试"
Task: "T072 [US6] 用户管理 API"
Task: "T073 [US6] 审计 API"
# T074/T075/T076 页面在 T072/T073 API 完成后进行
```

---

## Implementation Strategy

### MVP First

建议 MVP = **Phase 1 + Phase 2 + US1 + US6**：

- 可登录的控制台
- 创建带动态参数 Schema 的任务定义
- 本机脚本立即执行、取消、查看结果/尝试
- 用户/角色、审计、个人设置
- 这是最小可用的“任务中控”闭环

### Incremental Delivery

1. Setup + Foundational → 基础设施就绪。
2. US1 → 本地任务定义/执行闭环（MVP 核心）。
3. US6 → 控制台壳层、用户/审计/个人设置。
4. US2 → 定时/间隔/一次性调度。
5. US3 → SSH/HTTP 远程执行。
6. US4 → 自动/手工重试。
7. US5 → 统计与下钻。
8. Polish → 安全/性能/保留/契约/可访问性/E2E。

### Parallel Team Strategy

- 1 人：按 Phase 顺序串行。
- 2–3 人：Setup/Foundational 共同完成；之后 US1 + US6 一人，US2/US4 一人，US3/US5 一人。
- 前端可在契约冻结后与后端并行；US6 负责跨页一致性，避免各页面风格分裂。

---

## Notes

- [P] 任务必须确认不同文件且无未完成依赖。
- 所有任务遵循宪法：Ruff、类型注解、显式异常、Alembic、UTC、审计、测试。
- 提交前运行 `uv run ruff check .`、`uv run pytest`、`pnpm lint`、`pnpm test`、`pnpm build`。
- 每个故事完成后按 quickstart 对应场景独立验证。
- 不要提前实现 DAG、优先级、SSO/MFA、分布式 worker 或运行时插件上传（明确 out of scope）。
