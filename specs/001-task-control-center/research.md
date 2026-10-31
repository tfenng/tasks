# Phase 0 Research: 任务中控系统

**Feature**: `001-task-control-center` | **Date**: 2026-10-30

所有技术未知项已在本文件收敛；实现阶段只需按 `uv.lock` / `pnpm-lock.yaml` 固定精确补丁版本。
本文件不替代规格，产品行为以 [spec.md](spec.md) 为准。

## R-01 后端工程边界与依赖版本

**Decision**: 在 `backend/` 新建独立 Python 3.12 工程，使用 FastAPI 0.115+、Pydantic 2.9+、
pydantic-settings、SQLAlchemy 2.0、Alembic、psycopg 3.2、uvicorn、croniter、paramiko、httpx、
cryptography、argon2-cffi、jsonschema、loguru。使用 `uv` 管理依赖并提交 `uv.lock`。

**Rationale**: 现有根目录服务使用 Pydantic 1.10 和旧版 FastAPI，且依赖的 `dao` 包不在当前检出中。
新系统需要 Pydantic 2 的 JSON Schema/类型能力，若与遗留服务共用环境会造成不可控升级。独立工程
可以独立测试、构建和部署，同时保留遗留服务不变。

**Alternatives considered**:
- 复用根目录 Pydantic 1 环境：会限制新代码的类型和 Schema 能力，并受遗留依赖缺失影响。
- 在同一环境混用 Pydantic 1/2：Python 包冲突，不可行。
- 升级整个仓库到 Pydantic 2：超出本特性范围，且会破坏遗留代码。

## R-02 架构风格

**Decision**: 模块化单体，同一代码库拆成 `api`、`scheduler`、`worker` 三个进程；按领域分层为
`domain`、`application`、`infrastructure`、`api`。

**Rationale**: 任务量级和团队规模不需要微服务；拆分进程可以获得故障隔离和独立扩缩容，同时保留
单一代码库、单一数据库和简单部署。领域层不依赖 Web 框架，满足宪法第 II 条。

**Alternatives considered**:
- 单进程同时跑 API/调度/执行：部署最简单，但任务执行会拖慢 API，重启会中断所有角色。
- 微服务拆分 API/调度/执行器：网络边界、消息契约和运维复杂度超出 v1 需要。
- Serverless 函数：长任务、SSH 连接和本地脚本不适合。

## R-03 队列与并发控制

**Decision**: 使用 PostgreSQL 作为任务队列：`SELECT ... FOR UPDATE SKIP LOCKED` 认领 `queued`
运行；`task_definition_runtime` 原子计数限制单定义并发；worker 线程数限制全局并发。

**Rationale**: 已有 PostgreSQL，避免新增 Redis/Celery；`SKIP LOCKED` 天然支持多 worker 竞争，
事务内完成“认领 + 建尝试 + 计数”可保证一致性。符合 KISS/YAGNI 和“无明确收益不引入消息队列”。

**Alternatives considered**:
- Redis + Celery/RQ：成熟，但引入额外中间件、序列化契约和运维面；v1 不需要。
- RabbitMQ/Kafka：过重，且不解决调度状态持久化。
- 数据库轮询但不加锁：多 worker 会重复认领。

## R-04 调度器实现

**Decision**: 自建调度循环，每秒轮询 `schedules.next_fire_at`，使用 croniter + zoneinfo 计算下一次
触发；使用 PostgreSQL advisory lock 保证单调度领导者；一次性运行由同一循环提升。

**Rationale**: 调度规则、重叠/错过策略和运行创建需要与业务表在同一事务内完成；APScheduler 的
job store 会与自有 `schedules` 表形成双写。自建循环代码量小、可测试、可观测。

**Alternatives considered**:
- APScheduler：功能全，但持久化 job 与业务调度重复，错过/重叠语义难统一。
- Celery Beat：需要 Celery/Redis，且 beat 与 worker 的失败语义分离。
- 系统 cron：无法表达业务状态、重试和审计。

## R-05 调度 exactly-once

**Decision**: `runs` 表对 `(schedule_id, scheduled_for)` 建部分唯一索引；调度事务插入运行并推进
`next_fire_at`，冲突即视为该触发点已处理。错过/跳过也写入运行记录，状态分别为 `missed`/`skipped`。

**Rationale**: 唯一约束是数据库层的最终防线，不依赖调度器单实例；运行记录同时服务统计和审计。
调度器用 advisory lock 降低冲突，但正确性由唯一约束保证。

**Alternatives considered**:
- 仅靠单实例：故障切换/误启动多实例时会重复。
- 单独 occurrence 表：更规范，但增加一张表和连接；v1 用运行表承载足够。
- 内存去重：重启丢失。

## R-06 前端框架

**Decision**: React 18.3 + TypeScript + Vite 6 + Ant Design 5 + TanStack Query 5 + React Router 6 +
`@rjsf/core`/`@rjsf/antd` + Recharts 2；使用 pnpm 和 `pnpm-lock.yaml`。

**Rationale**: 管理控制台需要成熟表格、表单、弹窗、统计组件；Ant Design 覆盖完整。RJSF 能直接
消费后端 JSON Schema 生成动态参数表单，避免手写每个任务的表单。TanStack Query 适合轮询和缓存。
OpenAPI 生成 TypeScript 客户端可降低契约漂移。

**Alternatives considered**:
- Vue 3 + Element Plus：同样成熟，但团队/生态选择无额外收益；React 的 OpenAPI/RJSF 组合更直接。
- 服务端渲染 Jinja2 + HTMX：实现简单，但动态参数表单、统计图表和复杂交互成本更高。
- Next.js：SSR 对内部控制台无必要，增加构建/部署复杂度。

## R-07 本地账号与会话

**Decision**: 本地账号 + Argon2id 密码哈希 + 服务端会话表 + HttpOnly/Secure/SameSite=Lax Cookie +
CSRF token；API 使用可撤销的个人访问令牌（Bearer），令牌只存哈希。

**Rationale**: 用户明确选择本地账号；服务端会话支持立即吊销和审计，避免 JWT 无法撤销的问题。
Argon2id 是当前推荐的密码哈希。PAT 解决 API 自动化无法交互登录的问题；v1 不交付独立运维 CLI。

**Alternatives considered**:
- JWT 无状态会话：扩展方便，但吊销、会话列表和“退出所有设备”复杂。
- Flask-Login/Django auth：引入另一套框架，不符合 FastAPI 结构。
- SSO/OIDC：用户明确排除于 v1。

## R-08 参数模型与动态表单

**Decision**: 任务定义参数使用 JSON Schema 2020-12 子集存储；后端用 `jsonschema` 校验；前端用
RJSF + AJV 根据同一 Schema 渲染表单；敏感字段用 `x-secret: true` + `writeOnly: true` 标记。

**Rationale**: 一份 Schema 同时驱动 API 校验、数据库快照和前端表单，避免三处重复。JSON Schema
支持嵌套对象/数组、枚举、默认值和格式约束，足够覆盖任务参数。

**Alternatives considered**:
- 每个任务写 Pydantic 模型：类型强，但新增任务需要改代码/发版，违背“注册各式任务”的目标。
- 自定义字段 DSL：需要自己实现校验和表单渲染，重复造轮子。
- 纯键值对无类型：无法做字段级校验和动态表单。

## R-09 执行器实现

**Decision**: 统一 `TaskExecutor` Protocol；本机脚本用 `subprocess`（`shell=False`），SSH 用
paramiko，HTTP 用 httpx；注册表按 `executor_type` 创建实例。

**Rationale**: 三类入口都是同步阻塞 I/O，放在 worker 线程中简单可控。paramiko 避免依赖系统 ssh
和交互式 known_hosts；httpx 提供 TLS、超时和连接池；subprocess 可精确控制 argv、进程组和超时。

**Alternatives considered**:
- 系统 `ssh` 命令：依赖主机 ssh 配置和 known_hosts，输出解析脆弱。
- `requests`：成熟，但 httpx 的超时/HTTP2/测试适配更现代。
- Ansible：过重，且引入 playbook 语义。
- 异步执行器：会增加 async SQLAlchemy/取消传播复杂度，v1 无必要。

## R-10 凭据与敏感参数存储

**Decision**: 凭据和敏感参数使用 AES-256-GCM 加密；密钥从 `TASK_CONTROL_SECRET_KEYS` key ring
加载，密文带 `key_version`；展示层使用 `parameters_redacted` 和掩码元数据。

**Rationale**: 不引入 Vault 等外部服务即可满足“加密存储/受保护存储”；key ring 支持轮换。
解密只发生在 worker 执行瞬间，API 不返回明文。

**Alternatives considered**:
- 仅环境变量引用：安全但管理员无法在 UI 中维护多个凭据。
- 外部 Vault：更安全，但增加部署依赖；设计保留 `SecretProvider` 端口以便后续接入。
- 明文数据库：违反宪法和规格。

## R-11 授权模型

**Decision**: 固定三角色：管理员、操作员、只读观察者；服务端在用例层执行资源级授权；前端只做
入口显隐。管理员管理用户/目标/凭据/全局配置；操作员管理定义/调度/运行；观察者只读。

**Rationale**: 满足单工作区内部系统的最小权限模型；固定角色避免自定义角色的权限组合爆炸。
所有写操作仍以服务端校验为准。

**Alternatives considered**:
- 自定义角色/权限矩阵：灵活但 v1 无明确需求，增加 UI 和测试复杂度。
- 仅按用户隔离：与单工作区共享任务视图冲突。
- 仅前端限制：不安全。

## R-12 测试策略

**Decision**: pytest + testcontainers PostgreSQL + respx + time-machine + httpx；前端 Vitest +
Testing Library + Playwright。单元测试覆盖领域规则；集成测试覆盖事务、唯一约束、队列、调度、
reaper；契约测试校验 OpenAPI；E2E 覆盖关键运维流程。

**Rationale**: 调度、重试、并发和事务必须用真实 PostgreSQL 验证；testcontainers 提供隔离且可
重复的数据库。time-machine 让 cron/退避/租约测试确定性。Playwright 覆盖 UI 与权限。

**Alternatives considered**:
- SQLite 内存库：不支持 `SKIP LOCKED`、部分索引、`timestamptz` 语义，无法验证核心逻辑。
- 仅 mock 仓储：测不到唯一约束和事务竞态。
- 仅手工测试：无法满足回归要求。

## R-13 部署与运行

**Decision**: Docker Compose 部署 `db`、`api`、`scheduler`、`worker`、一次性 `migrate`；前端构建
产物由 FastAPI 静态托管；生产可在前面加 Nginx/Traefik 做 TLS。开发和测试用独立数据库。

**Rationale**: 单控制面、单数据库，Compose 足够；多阶段 Dockerfile 将 Node 构建和 Python 运行时
合并，减少镜像和跨域配置。Alembic 在启动前独立执行，避免多进程同时迁移。

**Alternatives considered**:
- Kubernetes：v1 规模不需要，增加清单和运维复杂度。
- 独立 Nginx 托管前端：多一个容器和 CORS/路由配置；FastAPI 静态托管更简单。
- 直接把前端放 CDN：内部系统无必要。

## R-14 时间、时区与 DST

**Decision**: 数据库统一 `timestamptz` 存 UTC；调度计划保存 IANA 时区；cron 用 croniter +
zoneinfo 计算；固定间隔按 UTC 秒数推进。所有 API 时间为 ISO 8601 UTC，查询接受调用方时区。

**Rationale**: UTC 存储避免跨时区歧义；按计划时区计算符合用户直觉；croniter 支持时区感知。
固定间隔不随时区/DST 跳变，语义稳定。

**Alternatives considered**:
- 本地时间存储：DST 回拨会重复/歧义。
- 全部按 UTC 计算 cron：用户在本地时区的“每天 9 点”会漂移。
- 自己实现 cron：容易在月末/DST 出错。

## R-15 数据保留与统计

**Decision**: 运行主记录保留 13 个月；尝试、输出摘要和响应摘要保留 90 天；审计保留 13 个月。
统计从运行表聚合；尝试级统计只覆盖保留期内的尝试。每日维护任务执行清理并记录删除数量。

**Rationale**: 运行行较小，保留 13 个月可支持同比/长期统计；大字段（输出）只保留 90 天控制成本。
避免引入 rollup 表和近似 P95 的复杂性。

**Alternatives considered**:
- 全部保留 13 个月：输出可能占大量存储。
- 运行只保留 90 天：无法满足聚合 13 个月。
- 预聚合/分区：数据量达到更高量级再引入。

## R-16 限流与滥用防护

**Decision**: 登录失败由数据库 `failed_login_count/locked_until` 控制；API 写操作使用进程内令牌桶，
返回 429 + `Retry-After`；登录接口同时按用户名和来源 IP 限制。

**Rationale**: 单控制面、API 进程数有限，进程内限流足够防止常见滥用；登录锁定是持久化的，跨进程
有效。避免引入 Redis。

**Alternatives considered**:
- Redis 限流：全局精确，但增加中间件。
- 数据库计数每次请求写库：成本高。
- 不限流：违反规格 FR-062。

## R-17 可观测性

**Decision**: loguru JSON 日志 + 审计表 + 健康/就绪检查；日志带 `correlation_id`、`run_id`、
`attempt_id`、`actor_id`；不引入 Prometheus/OpenTelemetry。

**Rationale**: v1 的运营需求是定位失败运行和审计操作；结构化日志 + 运行/尝试表已足够。集中式
指标/追踪明确在规格中排除。

**Alternatives considered**:
- Prometheus + Grafana：后续需要容量/延迟趋势时再加。
- OpenTelemetry：跨服务追踪在单控制面中收益有限。
- 仅文本日志：难以按 run_id 过滤。

## R-18 乐观并发与幂等

**Decision**: 可编辑资源带 `version` 字段；更新要求 `If-Match`，不匹配返回 409。运行提交支持
`Idempotency-Key`，相同用户 + key + 相同请求哈希返回已有运行；不同哈希返回 409。

**Rationale**: 防止两个操作员静默覆盖；防止客户端超时重发造成重复执行。数据库唯一约束兜底。

**Alternatives considered**:
- 最后写入获胜：会覆盖他人修改。
- 悲观锁长时间持有：UI 体验差。
- 仅前端防重复：不可靠。

## R-19 前端数据刷新

**Decision**: TanStack Query 轮询：活动运行/仪表盘 3 秒，调度 30 秒，定义/统计 60 秒；页面隐藏时
暂停轮询；使用 `refetchIntervalInBackground: false`。不使用 WebSocket/SSE。

**Rationale**: 轮询实现简单、可缓存、易排障；3 秒满足运维感知，不需要实时推送。SSE/WebSocket 会
增加连接管理、代理和重连复杂度。

**Alternatives considered**:
- WebSocket：实时性更好，但 v1 无硬需求。
- SSE：比 WebSocket 简单，但仍有连接和代理问题。
- 手动刷新：体验差。

## R-20 构建、质量与依赖锁定

**Decision**: 后端 `uv` + `pyproject.toml` + `uv.lock`；前端 `pnpm` + `pnpm-lock.yaml`；Ruff 负责
Python lint/format；ESLint + Prettier 负责前端；CI 执行后端 lint/typecheck/test、前端
lint/test/build、Playwright 关键流程。

**Rationale**: 锁定可复现环境；Ruff 满足宪法；前后端各自使用生态标准工具。CI 门禁与规格的
“测试通过才认定完成”一致。

**Alternatives considered**:
- pip + requirements.txt：可用，但解析/锁定体验不如 uv；现有遗留 requirements 不适用于新工程。
- npm/yarn：pnpm 的锁文件和安装速度更适合 monorepo。
- 不设 CI：无法保证回归。

## Resolved Unknowns

- 无剩余待澄清项。
- 所有第三方依赖均在 `pyproject.toml` / `package.json` 声明，精确版本由锁文件固定。
- 外部依赖仅 PostgreSQL、SSH 目标、HTTP 目标和宿主机脚本目录；无 Redis、消息队列或外部 IdP。
