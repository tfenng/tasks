# Web UI Route Contract

前端为中文单页应用，使用 Ant Design 5 布局；所有路由在未认证时重定向 `/login`，无权限时显示
403 页面。导航按角色生成，但服务端仍是最终授权边界。

## Routes

| Path | Page | Roles | Primary data | Actions |
|------|------|-------|--------------|---------|
| `/login` | 登录 | 匿名 | `POST /auth/login` | 登录、显示锁定/限流 |
| `/` | 仪表盘 | 全部 | `GET /stats/runs`、`GET /runs?status=failed&page_size=5`、`GET /schedules?status=active` | 跳转运行/调度 |
| `/definitions` | 任务定义列表 | 全部 | `GET /task-definitions` | 搜索、筛选、创建（管理员/操作员） |
| `/definitions/new` | 新建定义 | 管理员/操作员 | 执行目标列表 | 动态参数 Schema、执行器配置、重试/并发 |
| `/definitions/:id` | 定义详情 | 全部 | `GET /task-definitions/{id}`、`GET .../versions` | 编辑新版本、启用/禁用/归档、查看调度/运行 |
| `/schedules` | 调度列表 | 全部 | `GET /schedules` | 创建、暂停/恢复/取消、查看下一次触发 |
| `/schedules/new` | 新建调度 | 管理员/操作员 | 定义版本、参数表单 | 一次性/cron/间隔、时区、重叠/错过策略 |
| `/schedules/:id` | 调度详情 | 全部 | `GET /schedules/{id}`、关联运行 | 编辑、暂停/恢复/取消、下钻运行 |
| `/runs` | 运行列表 | 全部 | `GET /runs` | 筛选定义/状态/触发/入口/时间、取消/重试 |
| `/runs/:id` | 运行详情 | 全部 | `GET /runs/{id}`、`GET .../attempts` | 取消、重试、查看尝试/输出/参数（脱敏） |
| `/stats` | 统计 | 全部 | `GET /stats/runs`、`GET /stats/attempts` | 时间/定义/版本/触发/入口筛选、图表、下钻 |
| `/targets` | 执行目标 | 管理员 | `GET /execution-targets` | 创建/编辑/禁用 |
| `/credentials` | 凭据 | 管理员 | `GET /credentials` | 创建/更新/禁用；永不显示明文 |
| `/users` | 用户与角色 | 管理员 | `GET /users` | 创建、禁用、重置密码、分配角色 |
| `/audit` | 审计 | 管理员 | `GET /audit-events` | 按操作者/动作/资源/时间筛选 |
| `/profile` | 个人设置 | 全部 | `GET /auth/me`、`GET /auth/sessions`、`GET /auth/tokens` | 改密码、吊销会话、管理 API Token |
| `*` | 404 | 全部 | — | 返回首页 |

## Layout

- 顶部：产品名、当前工作区、环境标识（开发/测试/生产）、用户菜单（个人设置/退出）。
- 左侧：仪表盘、任务定义、调度、运行、统计；管理员额外显示目标、凭据、用户、审计。
- 内容区：页面标题 + 面包屑 + 主操作按钮；列表页统一“筛选栏 + 表格 + 分页”。
- 全局：`App` 级错误边界、Ant Design `message`/`notification`、登录过期拦截。

## Page States

每个数据页面必须实现：

- **Loading**：Skeleton/Table loading，不显示空白闪烁。
- **Empty**：Ant Design Empty + 明确的创建/清除筛选动作。
- **Error**：Result status="error" + 关联 ID + 重试按钮。
- **Success**：操作后 message/notification，必要时刷新列表/详情。
- **Conflict**：409 时提示“数据已被他人修改”，提供刷新并保留用户输入。
- **Rate limit**：429 时显示剩余等待时间，禁用提交按钮直到可重试。
- **Forbidden**：403 页面，不显示敏感资源详情。

## Forms

- 任务定义参数表单由后端 `parameter_schema` 通过 RJSF 生成；自定义 `secret` 控件为密码输入，
  编辑时不回显原值。
- 执行器配置按类型切换：本机脚本（解释器/argv/工作目录/环境变量）、SSH（目标/命令/超时）、
  HTTP（方法/URL/头/体/成功条件）。
- 重试策略：最大尝试、初始退避、倍数、最大退避、可重试分类、非零退出码白名单。
- 调度：一次性时间、cron 表达式、间隔秒数、时区、重叠策略、错过宽限。
- 客户端校验使用同一 JSON Schema/AJV；服务端错误按字段映射到表单。
- 危险操作（归档、取消、禁用、重置密码、吊销令牌）使用 `Modal.confirm`，说明不可逆影响。

## Data Fetching

- TanStack Query；query key 以资源 + 筛选参数构造，变更后 invalidate 相关列表/详情。
- 轮询：运行列表/详情和仪表盘 3 秒；调度 30 秒；定义/统计 60 秒；页面隐藏时暂停。
- 运行详情展示状态时间线：创建 → 排队 → 开始 → 尝试 → 重试等待 → 终态。
- 运行主记录超过尝试明细保留期时，详情显示“尝试明细已过保留期”，但状态、时间和统计仍可用。
- 统计图表使用 Recharts；表格与图表共享筛选；点击图表/表格行跳转运行列表并带筛选。
- 请求带 `X-CSRF-Token`（Cookie 会话）；401 清理本地状态并跳转登录；403/404 不重试。

## Accessibility & Responsive

- 所有表单控件有关联 label；错误信息通过 `aria-describedby` 关联；键盘可完成主要流程。
- 颜色对比满足 WCAG AA 基本要求；状态不只依赖颜色，配合文本/图标。
- 桌面使用侧边栏 + 表格；窄屏（<768px）侧边栏折叠，表格切换为卡片列表。
- 中文文案；时间按用户时区展示，API 仍传 UTC。
