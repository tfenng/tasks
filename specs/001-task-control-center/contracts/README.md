# API & Interface Contracts

本目录是任务中控系统的接口契约，供后端实现、前端生成客户端和集成测试共同使用。

| 文件 | 内容 |
|------|------|
| [openapi.yaml](openapi.yaml) | REST API 3.1 契约（`/api/v1`） |
| [error-codes.md](error-codes.md) | 统一错误码与 HTTP 状态映射 |
| [executor-interface.md](executor-interface.md) | 执行器扩展点（内部 Python Protocol） |
| [ui-routes.md](ui-routes.md) | Web 控制台路由、角色与页面数据契约 |

## Conventions

- 基础路径：`/api/v1`；OpenAPI 文档：`/api/docs`；健康检查不带版本前缀，见契约中的 `/health/*`。
- 认证：Web 使用 `tc_session` HttpOnly Cookie；API/自动化使用 `Authorization: Bearer <token>`。
- CSRF：Cookie 认证的 `POST/PUT/PATCH/DELETE` 必须带 `X-CSRF-Token`，值来自登录响应/可读
  `tc_csrf` Cookie。Bearer 认证不需要 CSRF。
- 时间：ISO 8601 UTC，例如 `2026-10-30T08:00:00Z`；查询可带 `timezone` 用于统计分桶。
- 分页：`page`（默认 1）、`page_size`（默认 20，最大 100）；响应包含 `page/page_size/total/total_pages`。
- 排序：`sort=-created_at`、`sort=queued_at`；仅允许契约声明的字段。
- 幂等：`POST /runs` 支持 `Idempotency-Key`；相同用户 + key + 相同请求哈希返回已有运行。
- 并发：可编辑资源返回 `version`；更新带 `If-Match: "<version>"`；缺失返回 428，冲突返回 409。
- 错误：统一为 `{"error": {...}}`，详见 [error-codes.md](error-codes.md)。
- 敏感信息：响应永不返回密码、会话令牌、凭据明文或敏感参数明文。
- 兼容性：新增字段为向后兼容；删除/重命名字段或改变语义属于不兼容变更，必须记录在
  `docs/api-compatibility.md`，包含影响、迁移和回滚方案。
