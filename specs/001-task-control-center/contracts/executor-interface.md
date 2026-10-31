# Executor Interface Contract

执行器是任务中控系统与外部执行入口之间的唯一扩展点。新增入口类型只需实现本契约并注册工厂，
不得修改调度、队列、重试、统计或权限逻辑（FR-005、FR-050）。

## Python Protocol

```python
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


class ExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class ErrorClass(StrEnum):
    NONE = "NONE"
    TIMEOUT = "TIMEOUT"
    CONNECTION = "CONNECTION"
    SSH_AUTH = "SSH_AUTH"
    SSH_HOST_KEY = "SSH_HOST_KEY"
    HTTP_408 = "HTTP_408"
    HTTP_429 = "HTTP_429"
    HTTP_4XX = "HTTP_4XX"
    HTTP_5XX = "HTTP_5XX"
    RESPONSE_MISMATCH = "RESPONSE_MISMATCH"
    EXIT_CODE = "EXIT_CODE"
    VALIDATION = "VALIDATION"
    CANCELLED = "CANCELLED"
    WORKER_LOST = "WORKER_LOST"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ExecutionContext:
    run_id: str
    attempt_no: int
    executor_type: str
    parameters: dict[str, Any]          # 已解密，仅执行期存在
    target: dict[str, Any]              # 目标配置
    credential: dict[str, Any] | None   # 已解密，仅执行期存在
    timeout_seconds: int
    output_limit_bytes: int
    correlation_id: str
    cancel_requested: "Callable[[], bool]"


@dataclass(frozen=True)
class ExecutionResult:
    status: ExecutionStatus
    error_class: ErrorClass
    error_message: str | None
    exit_code: int | None
    http_status: int | None
    stdout_excerpt: str | None
    stderr_excerpt: str | None
    response_excerpt: str | None
    duration_ms: int
    truncated: bool
    metadata: dict[str, Any]


class TaskExecutor(Protocol):
    executor_type: str

    def execute(self, ctx: ExecutionContext) -> ExecutionResult:
        """执行一次尝试；不得抛出未分类异常。"""
```

## Registry Contract

```python
ExecutorFactory = Callable[[ExecutorDeps], TaskExecutor]

def register_executor(executor_type: str, factory: ExecutorFactory) -> None: ...
def create_executor(executor_type: str, deps: ExecutorDeps) -> TaskExecutor: ...
```

- 注册只发生在应用启动时，由代码显式调用；不支持运行时上传或动态导入用户代码。
- 未注册类型在保存定义时返回 `UNSUPPORTED_EXECUTOR`，而不是等到运行时失败。
- 工厂依赖（HTTP client、SSH known_hosts、脚本根目录、时钟、脱敏器）通过 `ExecutorDeps` 注入，
  便于测试。

## Rules

1. **不得抛出未分类异常**：所有异常必须映射为 `ExecutionResult`，至少带 `ErrorClass.UNKNOWN`。
2. **不得记录明文凭据**：执行器不得把 `credential`、敏感参数写入日志/异常/输出。
3. **必须尊重超时**：`timeout_seconds` 是硬上限；超时返回 `TIMED_OUT` + `ErrorClass.TIMEOUT`。
4. **必须尊重取消**：周期性检查 `ctx.cancel_requested()`；取消返回 `CANCELLED`。
5. **输出限额**：stdout/stderr/response 各最多 `output_limit_bytes`；超限截断并置 `truncated=True`。
6. **不得修改运行状态**：执行器只返回结果；状态迁移由 worker 在事务中完成。
7. **不得访问数据库**：执行器只依赖传入上下文和注入的客户端。
8. **幂等无关**：执行器不负责去重；幂等由提交层处理。
9. **安全默认**：TLS 校验、SSH 主机密钥校验默认开启；不得提供“忽略证书/主机密钥”的隐式开关。
10. **可测试**：HTTP/SSH 依赖必须可注入 fake transport；本机脚本使用临时目录和固定退出码测试。

## Built-in Executors

### LocalScriptExecutor

- config: `interpreter`（可选）、`argv`（字符串数组，支持 `${param}` 整值替换）、`cwd`、
  `env`、`retry_on_exit_codes`。
- 使用 `subprocess.Popen(shell=False, start_new_session=True)`；超时杀进程组。
- 参数以 argv 元素、`TASK_PARAM_<NAME>` 环境变量和 `TASK_PARAMS_JSON` 提供。
- 工作目录必须位于配置的 `script_root` 内；拒绝 `..` 和绝对路径逃逸。

### SshExecutor

- config: `host`、`port`、`user`、`command`、`known_hosts_path`（可选）、`connect_timeout_seconds`。
- credential: `password` 或 `private_key`（含 passphrase）。
- 使用 paramiko；`RejectPolicy` + known_hosts；认证失败映射 `SSH_AUTH`，主机密钥变化映射
  `SSH_HOST_KEY`。
- 远程命令通过 `exec_command`；捕获退出状态、stdout/stderr 摘要；超时/取消关闭 channel。

### HttpExecutor

- config: `method`、`url`（或 target base_url + path）、`headers`、`body_template`、
  `success_status_codes`、`response_header_regex`、`response_body_regex`、`follow_redirects`。
- credential: `bearer` 或 `basic`。
- 使用 httpx.Client；TLS 校验默认开启；默认仅 2xx 成功；超时/连接错误分类。
- 响应摘要只保留配置的头部和截断后的 body；不得回显 `Authorization`。

## Test Contract

每个执行器至少覆盖：

- 成功结果字段完整；
- 超时/取消返回正确状态；
- 输出截断与脱敏；
- 认证/连接/协议错误分类；
- 不泄露凭据；
- 配置校验失败在建定义时被拒绝。
