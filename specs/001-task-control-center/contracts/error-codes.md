# Error Codes

所有错误响应使用同一结构，HTTP 状态码与业务错误码分离：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "参数校验失败",
    "details": [
      {"field": "parameters.count", "code": "minimum", "message": "必须大于等于 1"}
    ],
    "correlation_id": "01J9Z8K6Q3W7Y2V5N4M3B2A1C0"
  }
}
```

- `message` 面向操作员，中文、可读、可行动；不得包含堆栈、SQL、文件路径或密钥。
- `details` 可选，字段级错误用于表单定位。
- `correlation_id` 同时写入日志和审计，便于追踪。
- 未列出的内部错误统一返回 `INTERNAL_ERROR`，服务端记录完整异常。

| Code | HTTP | 场景 | 客户端处理 |
|------|------|------|------------|
| `AUTH_REQUIRED` | 401 | 未登录、会话过期或令牌无效 | 跳转登录/清除本地会话 |
| `AUTH_INVALID_CREDENTIALS` | 401 | 用户名或密码错误 | 提示重新输入，不区分具体原因 |
| `AUTH_LOCKED` | 423 | 连续失败导致账号锁定 | 显示解锁时间（如有） |
| `CSRF_INVALID` | 403 | Cookie 会话缺少/错误 CSRF token | 刷新页面后重试 |
| `FORBIDDEN` | 403 | 角色或资源级权限不足 | 显示无权限，不重试 |
| `NOT_FOUND` | 404 | 资源不存在或已不可见 | 返回列表/刷新 |
| `VALIDATION_ERROR` | 422 | 请求体、查询参数或参数 Schema 校验失败 | 字段级展示 |
| `CONFLICT_VERSION` | 409 | `If-Match` 与当前 `version` 不一致 | 提示刷新并合并 |
| `IDEMPOTENCY_CONFLICT` | 409 | 相同幂等键但请求体不同 | 使用原请求或更换 key |
| `INVALID_STATE` | 409 | 运行/调度当前状态不允许操作 | 刷新状态后重试 |
| `SCHEDULE_CONFLICT` | 409 | 调度版本/定义不可用或已归档 | 选择有效版本 |
| `DEFINITION_ARCHIVED` | 409 | 定义已归档仍尝试提交/调度 | 选择其他定义 |
| `DEFINITION_DISABLED` | 409 | 定义已禁用；未到期的一次性运行被取消 | 启用定义或选择其他定义 |
| `PRECONDITION_REQUIRED` | 428 | 更新缺少 `If-Match` | 读取最新 `version` 后重试 |
| `TARGET_DISABLED` | 409 | 执行目标或凭据已禁用/移除 | 由管理员恢复或改选 |
| `RATE_LIMITED` | 429 | 登录/写操作超过阈值 | 按 `Retry-After` 等待 |
| `PAYLOAD_TOO_LARGE` | 413 | 请求体/参数/输出超过限制 | 缩小请求或调整配置 |
| `UNSUPPORTED_EXECUTOR` | 422 | 执行入口类型未注册/配置无效 | 修正定义或联系管理员 |
| `EXECUTOR_UNAVAILABLE` | 503 | 执行器依赖不可用（如 SSH 库/网络） | 稍后重试；可重试分类 |
| `INTERNAL_ERROR` | 500 | 未预期异常 | 显示关联 ID，联系管理员 |

## Retryability

以下错误分类由执行器写入尝试记录，并由重试策略决定是否自动重试：

| Error class | Retryable by default | Notes |
|-------------|----------------------|-------|
| `TIMEOUT` | yes | 本机/SSH/HTTP 超时 |
| `CONNECTION` | yes | DNS、TCP、TLS 握手等临时连接问题 |
| `SSH_AUTH` | no | 凭据错误，重试无意义 |
| `SSH_HOST_KEY` | no | 主机密钥变化，安全拒绝 |
| `HTTP_408` / `HTTP_429` / `HTTP_5XX` | yes | 客户端超时/限流/服务端错误 |
| `HTTP_4XX` | no | 其他客户端错误 |
| `RESPONSE_MISMATCH` | no | 状态码不在成功集合，或响应头/响应体条件不满足 |
| `EXIT_CODE` | no | 本机/SSH 非零退出，除非定义显式列入 `retry_on_exit_codes` |
| `VALIDATION` | no | 参数/配置错误 |
| `CANCELLED` | no | 主动取消 |
| `WORKER_LOST` | yes | worker 失联，按策略重试 |

## Rate Limit Headers

`429` 响应包含：

```text
Retry-After: 30
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1761811200
```
