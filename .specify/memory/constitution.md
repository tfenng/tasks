# Tasks Service Constitution

<!--
Sync Impact Report
- Version change: none → 1.0.0 (initial adoption)
- Ratification date: 2026-10-30
- Modified principles: none (initial adoption)
- Added principles: I. Simplicity First; II. Modular Architecture; III. Python Code Quality;
  IV. Data Integrity; V. API Consistency; VI. Security by Default;
  VII. Testing and Reliability; VIII. User Experience Consistency
- Added sections: Technical Constraints; Development Workflow & Quality Gates; Governance
- Removed sections: none
- Deferred TODOs: TODO(CONSTRAINT) — 用户输入在“MUST 提供明确的”处截断，需补充完整约束后再修订。
-->

## Core Principles

### I. Simplicity First（简单优先）

- MUST 优先采用简单、清晰、易于维护的实现方案。
- MUST 遵循 KISS、DRY 和 YAGNI 原则。
- MUST 避免为尚未出现的需求提前构建复杂抽象。
- SHOULD 优先使用成熟的 Python 标准库及主流开源组件。
- MUST NOT 在没有明确需求和收益的情况下引入微服务、消息队列或复杂设计模式。
- MUST 保持代码可读性，禁止为了简短而牺牲可维护性。

**Rationale**: 项目的主要目标是快速、可靠地交付任务管理功能，而非追求架构复杂度。

### II. Modular Architecture（模块化架构）

- MUST 采用模块化单体架构作为默认架构。
- MUST 按业务领域组织模块，而不是仅按文件类型组织全部代码。
- MUST 分离 Web/API 层、业务逻辑层和数据访问层。
- MUST NOT 在路由处理函数中实现复杂业务逻辑。
- MUST NOT 让业务逻辑依赖 HTTP 请求对象或具体 Web 框架。
- SHOULD 使用明确的模块接口减少循环依赖。
- SHOULD 优先采用同步、直接的函数调用，仅在明确存在异步 I/O 需求时使用异步方案。

**Rationale**: 保证代码能够持续演进，并使 AI Agent 可以独立修改单个模块而不破坏其他功能。

### III. Python Code Quality（Python 代码质量）

- MUST 遵循 PEP 8 和现代 Python 编码惯例。
- MUST 为公共函数、方法及关键业务数据结构提供类型注解。
- MUST 使用 Ruff 进行代码检查和格式化，除非项目已经确定等效工具。
- MUST 使用明确的异常类型处理预期业务错误。
- MUST NOT 静默吞掉异常。
- MUST NOT 在业务代码中使用裸 `except:`。
- MUST 避免不必要的全局可变状态。
- SHOULD 使用 Pydantic、dataclass 或等效机制表达结构化数据。
- SHOULD 保持函数职责单一，避免过长、过度嵌套的函数。
- MUST 为新增第三方依赖提供明确用途，避免重复功能的依赖。

**Rationale**: 提升可读性、静态检查能力和 AI 自动修改代码的可靠性。

### IV. Data Integrity（数据完整性）

- MUST 使用数据库迁移机制管理数据库 Schema 变更。
- MUST NOT 通过直接修改生产数据库结构代替版本化迁移。
- MUST 保证涉及多个关联数据写入的业务操作具有事务一致性。
- MUST 在数据库层建立必要的唯一约束、外键约束及索引。
- MUST 使用参数化查询或 ORM 安全机制，防止 SQL 注入。
- MUST 使用带时区的时间数据，统一采用 UTC 存储时间点。
- MUST 明确区分任务状态、优先级、截止时间和完成时间等业务概念。
- MUST 保证任务状态变更符合定义的业务规则。
- SHOULD 避免无意覆盖用户已有数据。
- SHOULD 优先使用可回滚的数据迁移方案。

**Rationale**: 任务管理系统依赖长期保存、查询和更新任务数据，数据完整性优先于实现便利性。

### V. API Consistency（API 一致性）

- MUST 为 API 定义一致的请求、响应和错误处理规范。
- MUST 对所有外部输入进行验证。
- MUST 使用合适的 HTTP 方法和状态码。
- MUST 对分页、排序、过滤采用一致的参数约定。
- MUST 避免将数据库内部实现直接暴露为 API 契约。
- MUST 对 API 的不兼容修改明确记录影响。
- SHOULD 为公开 API 提供 OpenAPI 文档。
- SHOULD 对可重复提交的业务操作考虑幂等性。
- MUST 不向客户端暴露敏感的内部异常堆栈。

**Rationale**: 统一接口规范可以降低前后端协作成本，并减少新增功能带来的不一致。

### VI. Security by Default（默认安全）

- MUST 对需要登录的资源实施身份认证。
- MUST 在服务端执行资源级权限校验，不能仅依赖前端限制。
- MUST 防止用户未经授权读取或修改其他用户的数据。
- MUST 使用安全的密码哈希算法；不得存储明文密码。
- MUST NOT 将密码、Token、密钥或其他敏感信息提交到代码仓库。
- MUST 从环境变量或安全配置服务加载敏感配置。
- MUST 针对适用的认证方式采取 CSRF、XSS 和会话安全防护。
- MUST 对用户输入和上传内容进行必要的安全验证。
- SHOULD 对重要操作记录可追踪的审计信息。

**Rationale**: 多用户任务管理应用需要严格的数据隔离和访问控制。

### VII. Testing and Reliability（测试与可靠性）

- MUST 使用 pytest 或项目现有的等效框架执行自动化测试。
- MUST 为核心业务规则编写单元测试。
- MUST 为数据库事务、权限控制及关键 API 编写集成测试。
- MUST 为修复的 Bug 增加能够复现原问题的回归测试。
- MUST 确保相关自动化测试通过后才认定功能完成。
- MUST 使用独立测试数据库或隔离的测试环境。
- SHOULD 使用固定、可重复的测试数据。
- SHOULD 优先测试业务行为及结果，而不是内部实现细节。
- MUST NOT 为了通过测试而删除有效的测试用例或弱化断言。

**Rationale**: 保证 AI Agent 多次迭代后，既有功能不会被意外破坏。

### VIII. User Experience Consistency（用户体验一致性）

- MUST 保持页面布局、导航、表单和交互反馈的一致性。
- MUST 为数据加载、空状态、操作成功和操作失败提供明确反馈。
- MUST 为关键数据删除或不可逆操作提供适当保护。
- MUST 对任务创建、编辑、状态变更等常用操作保持合理的响应速度。
- SHOULD 支持常见桌面及移动设备屏幕尺寸。
- SHOULD 遵守基本的 Web 无障碍设计要求。
- MUST 避免因页面刷新、重复提交或网络错误造成数据丢失。

**Rationale**: 任务管理应用属于高频使用工具，清晰、稳定的交互比过度复杂的视觉效果更重要。

## Technical Constraints

- 后端开发语言为 Python。
- Web 框架、ORM、数据库及前端框架由技术规划阶段确定。
- 优先使用稳定、长期维护的依赖版本。
- 使用明确的依赖管理和锁定机制，保证环境可复现。
- 区分开发、测试和生产环境配置。
- 应用运行时配置与用户业务配置必须分离。
- 用户在应用中修改并持久化到数据库的业务配置，不应自动写回 `.env`。
- TODO(CONSTRAINT): 用户输入在“MUST 提供明确的”处截断，需补充完整要求后再纳入正式约束。

## Development Workflow & Quality Gates

- 每个变更必须先明确规格、验收标准与影响范围，再进入实现；修复缺陷必须先有可复现用例。
- 提交前必须通过 Ruff 检查与格式化，以及相关 pytest 测试；未通过不得合并。
- 数据库 Schema 变更必须附带版本化迁移、回滚方案及测试环境验证结果。
- 不兼容 API 变更必须记录影响范围、迁移步骤，并同步更新 OpenAPI 文档。
- 涉及认证、授权、数据隔离或敏感信息的变更必须经过安全评审。
- 代码评审必须检查本宪法合规性；任何复杂度例外必须在评审中说明收益与替代方案。

## Governance

本宪法是项目治理的最高约束，优先于其他开发实践与约定。`AGENTS.md` 提供运行时开发指引；若两者冲突，以本宪法为准。

### 修订程序

- 任何修订必须以 Issue/PR 形式提出，说明动机、影响范围、迁移方案与版本变更类型。
- 修订需经项目维护者评审批准后生效；不兼容修订必须提供迁移计划。
- 生效时必须同步更新版本号、批准日期与最后修订日期。

### 版本策略

采用语义化版本：

- MAJOR：删除、重定义原则或引入不兼容治理变更。
- MINOR：新增原则/章节或实质性扩展现有指导。
- PATCH：澄清措辞、修正笔误或非语义调整。

### 合规审查

- 所有 PR 与代码评审必须验证是否符合本宪法；违反项必须记录例外理由、整改责任人与期限。
- 测试、迁移、API 契约与安全检查是合并前的强制门禁。
- 新依赖必须说明用途，并确认不存在重复能力或更简单的替代方案。

**Version**: 1.0.0 | **Ratified**: 2026-10-30 | **Last Amended**: 2026-10-30
