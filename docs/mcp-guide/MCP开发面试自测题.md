# MCP 开发面试自测题

> 生成时间：2026-06-02  
> 用途：模拟面试官提问，检查你是否真正掌握 MCP 开发的核心知识点、工程实践和生产化边界。  
> 使用方式：建议你先独立回答，不要翻代码；答完后再对照学习计划、项目 README、tool/resource/prompt contract 和源码复盘。

## 1. 当前学习上下文总结

你已经按一周学习路线完成了 MCP 开发的主要学习内容，学习路径大致是：

1. 从 MCP 基础概念入门，理解 Host、Client、Server、Transport、Tools、Resources、Prompts。
2. 用 stdio transport 实现天气 MCP，掌握 Tool 注册、参数 schema、环境变量、外部 API 调用、错误处理和调试。
3. 给 stdio 天气 MCP 补充测试、调试手册和常见故障排查，理解 JSON-RPC 生命周期。
4. 将天气 MCP 升级为 Streamable HTTP MCP，掌握 `/mcp` endpoint、`/health`、Bearer Token、结构化日志、`callId`、外部依赖诊断。
5. 实现 `mcp-java-insight-http`，把 Day 5 的 Java 代码库只读 MCP 和 Day 6 的业务 MCP 知识点合并，重点学习：
   - 代码库只读访问
   - workspace 白名单
   - 敏感文件过滤
   - 返回结果限长
   - Tools / Resources / Prompts 的边界
   - mock 业务查询
   - 脱敏
   - 审计意识
   - 为什么写操作 MCP 必须谨慎设计
6. 当前项目的业务逻辑不是重点，重点是借这些项目理解 MCP Server 的设计、开发、调试、测试和生产化边界。

当前主要项目包括：

| 项目 | 目录 | 学习重点 |
|---|---|---|
| stdio 天气 MCP | `/mnt/d/个人项目/mcpStartedGuide/mcp_weather-stdio-server` | stdio transport、Tool 基础、外部 API、调试 |
| HTTP 天气 MCP | `/mnt/d/个人项目/mcpStartedGuide/mcp-weather-http-server` | Streamable HTTP、鉴权、health、callId、日志、网络诊断 |
| Java Insight HTTP MCP | `/mnt/d/个人项目/mcpStartedGuide/mcp-java-insight-http` | 只读代码库 MCP、Resources、Prompts、安全边界、mock 业务 MCP |

## 2. 自测规则

建议按下面方式答题：

- 每题先口头回答 1-3 分钟。
- 遇到设计题，先画调用链或列模块边界，再讲取舍。
- 遇到生产化题，必须覆盖安全、可观测、错误处理、测试。
- 不要求背 TypeScript 语法，但要能说清楚代码结构和职责分层。
- 如果回答只停留在“能调用成功”，说明掌握还不完整；生产级 MCP 要能解释边界和失败场景。

评分建议：

| 分数 | 表现 |
|---|---|
| 0 分 | 说不清概念，或回答与 MCP 无关 |
| 1 分 | 知道名词，但说不清作用和调用链 |
| 2 分 | 能解释基本概念，能结合项目举例 |
| 3 分 | 能解释工程实现、风险边界、故障处理和取舍 |

## 3. 第一组：MCP 核心概念

### Q1：请用 3 分钟解释 MCP 是什么，它解决了什么问题？

考察点：

- MCP 与普通 HTTP API 的区别
- MCP 与插件、函数调用、Agent 工具调用的关系
- 为什么需要统一协议
- MCP Server 在 AI 应用中的位置

你的回答：

```text

```

### Q2：请解释 Host、MCP Client、MCP Server 三者的关系。

追问：

- Claude Desktop、Cursor、VS Code 插件分别更接近哪个角色？
- 你自己开发 MCP 时，通常开发的是哪一部分？
- 一个 Host 是否可以连接多个 MCP Server？

你的回答：

```text

```

### Q3：Tools、Resources、Prompts 分别是什么？边界是什么？

追问：

- 为什么 Tool 是动作，Resource 是上下文，Prompt 是任务模板？
- 哪些场景应该做 Tool，哪些场景应该做 Resource？
- Prompt 被调用后会不会自动执行 Tool？

你的回答：

```text

```

### Q4：MCP 的一次典型 Tool 调用链路是什么？

请从用户输入一直讲到 Tool handler 执行，再讲到结果返回。

追问：

- `tools/list` 和 `tools/call` 分别发生在什么时候？
- Tool 的 `description` 是写给谁看的？
- Tool 的 input schema 有什么作用？

你的回答：

```text

```

### Q5：为什么说 MCP Server 不是普通后端 Controller？

考察点：

- 面向模型的工具描述
- schema 约束
- Host/Client 管理连接
- Tool 调用是模型选择出来的
- 返回内容要适合模型继续推理

你的回答：

```text

```

## 4. 第二组：stdio MCP

### Q6：stdio transport 的工作方式是什么？

追问：

- stdin、stdout、stderr 分别承担什么职责？
- 为什么 stdio MCP 里不能随便 `console.log()`？
- 如果 stdout 被日志污染，会发生什么？

你的回答：

```text

```

### Q7：stdio MCP 适合什么场景？不适合什么场景？

考察点：

- 本地工具
- 个人桌面客户端
- 单用户子进程
- 团队共享限制
- 部署和鉴权限制

你的回答：

```text

```

### Q8：你的 stdio 天气 MCP 里，`get-current-weather` 和 `get-forecast` 分别覆盖了哪些 MCP 开发基本功？

追问：

- 参数校验怎么做？
- OpenWeather API Key 怎么传入？
- 城市不存在、API key 错误、网络错误应该怎么返回？
- 预报数据为什么需要聚合？

你的回答：

```text

```

### Q9：如果 stdio MCP 在客户端里连不上，你会按什么顺序排查？

考察点：

- 客户端配置路径
- build 输出路径
- Node 版本
- env 是否传入
- stdout 日志污染
- Inspector 调试
- schema 与入参不匹配

你的回答：

```text

```

## 5. 第三组：Streamable HTTP MCP

### Q10：stdio MCP 和 Streamable HTTP MCP 的核心区别是什么？

追问：

- transport 形态有什么不同？
- 集成方式有什么不同？
- 团队共享时为什么更适合 HTTP？
- HTTP MCP 会引入哪些额外安全问题？

你的回答：

```text

```

### Q11：HTTP MCP 为什么需要 `/mcp` endpoint 和 `/health` endpoint？

追问：

- `/mcp` 承载什么协议交互？
- `/health` 给谁用？
- health check 里适合返回哪些信息？不适合返回哪些信息？

你的回答：

```text

```

### Q12：HTTP MCP 为什么必须做鉴权？

追问：

- Bearer Token 的最小实现是什么？
- 为什么生产环境不能使用默认开发 token？
- 鉴权失败应该返回什么？
- token 是否应该写入日志？

你的回答：

```text

```

### Q13：HTTP MCP 为什么要做 Host 校验、CORS 或类似边界？

考察点：

- 远程暴露的服务风险
- 浏览器环境访问
- 内网服务保护
- 防止非预期来源调用

你的回答：

```text

```

### Q14：你的 HTTP 天气 MCP 为什么新增了 `diagnose-weather-network`？

追问：

- 它解决的是业务问题还是运维排障问题？
- 生产环境中外部 API 依赖应该如何诊断？
- 诊断工具返回信息时要注意什么安全边界？

你的回答：

```text

```

## 6. 第四组：Tool 设计

### Q15：设计一个 MCP Tool 时，你会从哪些维度定义它？

考察点：

- name
- title
- description
- input schema
- output shape
- annotations
- readOnlyHint
- 错误处理
- 返回限制
- 安全边界

你的回答：

```text

```

### Q16：Tool 的 description 为什么很重要？

追问：

- 它是写给最终用户看的，还是写给模型看的？
- 如果 description 写得太模糊，会带来什么问题？
- 如何在 description 里表达“什么时候该用，什么时候不该用”？

你的回答：

```text

```

### Q17：为什么 input schema 不能只靠 TypeScript 类型？

追问：

- 运行时校验和编译期类型的区别是什么？
- zod 在 MCP Tool 里承担什么职责？
- schema 里如何表达默认值、范围、枚举、可选字段？

你的回答：

```text

```

### Q18：Tool 返回结果应该怎么设计，才更适合模型继续使用？

考察点：

- 结构化 JSON
- 简洁文本
- `callId`
- 不返回过长内容
- 不返回敏感信息
- 错误结果可定位

你的回答：

```text

```

### Q19：为什么不建议把 Tool 设计成 `execute-sql`、`read-any-file`、`call-any-api` 这种泛能力？

追问：

- 泛能力 Tool 的安全风险是什么？
- 什么是“窄业务动作”？
- 生产级 MCP 应该如何限制模型的操作空间？

你的回答：

```text

```

### Q20：如果一个 Tool 需要调用外部 HTTP API，你会加哪些保护？

考察点：

- 超时
- 错误包装
- 重试边界
- 代理配置
- 敏感字段脱敏
- 日志不要记录 token
- 返回大小限制

你的回答：

```text

```

## 7. 第五组：Resources 和 Prompts

### Q21：Resource 在 MCP 里的作用是什么？

追问：

- 它和 Tool 的最大区别是什么？
- Resource 适合暴露哪些稳定上下文？
- 为什么 Java 代码库 MCP 里适合有 `project://summary`？

你的回答：

```text

```

### Q22：请解释 `project://security-policy` 这类 Resource 的价值。

考察点：

- 向客户端说明服务边界
- 让模型知道哪些路径可访问
- 解释只读限制和敏感文件规则
- 减少误调用

你的回答：

```text

```

### Q23：Prompt 在 MCP 里的作用是什么？

追问：

- Prompt 是不是工具？
- Prompt 返回的是什么？
- 为什么 `analyze-java-method` 适合做 Prompt？
- Prompt 如何引导模型组合调用多个 Tool？

你的回答：

```text

```

### Q24：客户端使用 Resource 和 Prompt 的方式分别是什么？

追问：

- `listResources` / `readResource` 做什么？
- `listPrompts` / `getPrompt` 做什么？
- 客户端拿到 Prompt 后，下一步通常会发生什么？

你的回答：

```text

```

## 8. 第六组：Java 代码库只读 MCP

### Q25：为什么 Java 代码库 MCP 要设计成只读？

追问：

- 代码库读取和代码库修改风险有什么区别？
- 如果允许写文件，会引入哪些额外安全要求？
- 只读 MCP 仍然有哪些风险？

你的回答：

```text

```

### Q26：`search-code`、`read-source-file`、`find-java-class`、`find-mapper-sql` 的能力边界分别是什么？

考察点：

- 搜索代码
- 读取指定片段
- 定位 Java 类型
- 定位 Mapper XML 或注解 SQL
- 为什么不直接一次性返回整个项目

你的回答：

```text

```

### Q27：路径白名单为什么重要？你会如何实现？

追问：

- 什么是 workspace root？
- 如何防止 `../` 路径穿越？
- 为什么要用规范化后的绝对路径判断？
- Windows / Linux 路径差异会带来什么问题？

你的回答：

```text

```

### Q28：敏感文件过滤应该覆盖哪些类型？

考察点：

- `.env`
- 私钥
- token
- cookie
- 证书
- 构建产物
- 大文件
- `.git`
- 依赖目录

你的回答：

```text

```

### Q29：为什么读取源码要限制行数和结果数量？

追问：

- 对模型上下文有什么影响？
- 对服务性能有什么影响？
- 对数据泄露风险有什么影响？
- `maxResults`、`MAX_READ_LINES` 这类配置有什么价值？

你的回答：

```text

```

### Q30：如果用户要求读取 workspace 外的文件，MCP Server 应该怎么处理？

考察点：

- 拒绝请求
- 返回明确错误
- 带 `callId`
- 日志记录完整信息
- 不泄露敏感路径细节

你的回答：

```text

```

### Q31：Java 代码库 MCP 如何帮助分析一个接口实现链路？

请结合 Controller、Service、Mapper、SQL 讲调用流程。

你的回答：

```text

```

## 9. 第七组：Mock 业务 MCP 与写操作安全

### Q32：`MockBusinessClient` 在项目中的作用是什么？

追问：

- 它是真实业务系统吗？
- 为什么学习阶段用本地 JSON mock 数据？
- 它和 `BusinessCaseService` 的职责区别是什么？

你的回答：

```text

```

### Q33：`query-business-case` 这个 Tool 主要演示了哪些业务 MCP 设计点？

考察点：

- 业务查询类 Tool
- mock 数据源
- 脱敏
- limit
- 只读 note
- `callId`
- 业务症状到代码关键词的连接

你的回答：

```text

```

### Q34：为什么当前项目没有真正实现写操作 Tool？

追问：

- 学习阶段直接做写操作有什么风险？
- 写操作 MCP 的价值依赖什么前提？
- 为什么保留 `safe-update-design-review` Prompt？

你的回答：

```text

```

### Q35：如果未来要实现 `update-order-status`，必须具备哪些安全条件？

考察点：

- operator token
- confirm=true
- reason
- idempotencyKey
- auditId
- before/after snapshot
- 权限校验
- 审计日志
- 幂等处理
- 禁止任意 SQL

你的回答：

```text

```

### Q36：为什么写操作 Tool 应该是“窄业务动作”，而不是“通用更新能力”？

追问：

- `update-order-status` 和 `execute-sql` 的风险差异是什么？
- 服务端应该负责哪些校验？
- LLM 在写操作里不应该决定什么？

你的回答：

```text

```

## 10. 第八组：生产化工程规范

### Q37：一个生产级 MCP Server 应该有哪些基本模块？

考察点：

- server / transport
- tools
- services
- clients
- domain
- lib
- config
- logger
- tests
- docs

你的回答：

```text

```

### Q38：为什么要做 tool 层、service 层、client 层分离？

追问：

- tool 层应该做什么？
- service 层应该做什么？
- client 层应该做什么？
- 如果所有逻辑都写在 tool handler 里，会有什么问题？

你的回答：

```text

```

### Q39：`callId` 的作用是什么？

追问：

- 它和 traceId 有什么关系？
- 为什么错误返回要带 `callId`？
- 日志里应该如何使用 `callId`？
- 用户反馈问题时如何用 `callId` 排查？

你的回答：

```text

```

### Q40：结构化日志应该记录哪些字段？不应该记录哪些字段？

考察点：

- time
- level
- callId
- tool
- operation
- elapsedMs
- status
- errorName
- userId / tenantId
- 不记录 token、密码、手机号、完整敏感参数

你的回答：

```text

```

### Q41：MCP Server 的错误处理应该怎么设计？

追问：

- 参数错误、业务错误、外部依赖错误怎么区分？
- 用户可见错误和服务端日志有什么区别？
- 为什么服务端日志可以有 stack，但返回给用户不能过度暴露内部信息？

你的回答：

```text

```

### Q42：配置文件和环境变量读取需要注意什么？

追问：

- `.env.example` 和 `.env` 的区别是什么？
- 为什么不能把 secret 写进代码？
- 为什么生产环境必须显式配置 token？
- 如果只通过 `process.env` 读取，但没有加载 `.env`，会发生什么？

你的回答：

```text

```

### Q43：为什么要提供 smoke client 或 MCP Inspector 调试方式？

考察点：

- 验证 MCP endpoint
- 验证鉴权
- 验证 list tools/resources/prompts
- 验证 tool call
- 复现客户端问题

你的回答：

```text

```

### Q44：你会为 MCP 写哪些测试？

追问：

- 单元测试测什么？
- 集成测试测什么？
- smoke test 测什么？
- 外部 API 真实调用为什么要显式开启？

你的回答：

```text

```

## 11. 第九组：安全与风险

### Q45：只读 MCP 是否就一定安全？

追问：

- 只读文件访问有什么泄露风险？
- 业务查询有什么隐私风险？
- 搜索代码可能泄露什么？
- 如何降低这些风险？

你的回答：

```text

```

### Q46：远程 HTTP MCP 上线前，你会做哪些安全检查？

考察点：

- HTTPS
- 鉴权
- token 管理
- RBAC / ABAC
- userId / tenantId
- CORS / Host
- rate limit
- audit log
- secret 脱敏
- 错误信息控制
- 路径白名单

你的回答：

```text

```

### Q47：为什么生产级 MCP 不应该相信 LLM 的判断？

追问：

- LLM 可以建议什么？
- 服务端必须自己校验什么？
- 在写操作中，LLM 的角色边界是什么？

你的回答：

```text

```

### Q48：如何防止 MCP 返回内容过大或泄露上下文？

考察点：

- limit
- max lines
- max file size
- snippet
- 分页或截断
- 敏感字段 mask
- 拒绝高风险文件

你的回答：

```text

```

### Q49：如果 MCP 接入真实数据库，你会如何设计只读查询？

追问：

- 是否允许任意 SQL？
- 是否使用查询模板或白名单？
- 如何限制表、字段、行数？
- 如何做权限和审计？
- 如何防止敏感字段泄露？

你的回答：

```text

```

## 12. 第十组：场景设计题

### Q50：现在要为团队做一个“Java 接口排障 MCP”，你会如何设计？

请说明：

- Tools
- Resources
- Prompts
- 数据来源
- 安全边界
- 日志审计
- 测试方案

你的回答：

```text

```

### Q51：现在要把你的 HTTP 天气 MCP 部署给团队共享，你会补哪些生产能力？

考察点：

- HTTPS / 网关
- OAuth 或企业 SSO
- 限流
- OpenTelemetry
- 外部化日志
- 配置管理
- 健康检查
- 监控告警
- 多环境配置

你的回答：

```text

```

### Q52：如果面试官要求你现场设计一个“订单查询 MCP”，你会如何回答？

请覆盖：

- Tool 列表
- 参数设计
- 返回结构
- 脱敏
- 权限
- callId
- 错误处理
- 是否支持写操作

你的回答：

```text

```

### Q53：如果业务方要求做一个“AI 可以帮我更新订单状态”的 MCP，你会如何说服他先做安全设计？

追问：

- 你会问业务方哪些问题？
- 你会拒绝哪些不安全需求？
- 你会给出怎样的最小可控方案？

你的回答：

```text

```

### Q54：请设计一个 MCP 上线检查清单。

至少覆盖：

- 协议
- 鉴权
- 权限
- 日志
- 错误
- 测试
- 安全
- 文档
- 运维

你的回答：

```text

```

## 13. 第十一组：代码理解题

### Q55：在 `mcp-java-insight-http` 中，MCP Server 是在哪里装配 Tools、Resources、Prompts 的？

追问：

- 你会优先读哪个文件？
- 你如何从这个文件看出项目整体结构？

你的回答：

```text

```

### Q56：`business-tools.ts`、`business-case-service.ts`、`mock-business-client.ts` 三者的职责怎么区分？

考察点：

- Tool 注册层
- 业务编排层
- mock 数据读取层
- 为什么这样分层

你的回答：

```text

```

### Q57：`filesystem-client.ts` 和 `path-security.ts` 分别负责什么？

追问：

- 文件读取和路径安全为什么不应该混在一起？
- 什么时候应该拒绝读取？
- 为什么先做路径安全，再做文件操作？

你的回答：

```text

```

### Q58：`limit.ts` 这类小工具文件在生产级 MCP 里有什么价值？

追问：

- 参数边界集中管理有什么好处？
- 如果没有 limit，会有哪些风险？

你的回答：

```text

```

### Q59：`tool-utils.ts` 这类统一包装 Tool 调用的代码解决了什么问题？

考察点：

- callId
- 统一日志
- 统一错误处理
- 统一返回结构
- 减少重复代码

你的回答：

```text

```

## 14. 第十二组：故障排查题

### Q60：HTTP MCP 的 `/health` 正常，但 Inspector 调用 `/mcp` 失败，你会怎么排查？

可能方向：

- URL 是否正确
- Authorization header
- CORS / Host
- transport 初始化
- JSON-RPC 请求格式
- 服务端日志

你的回答：

```text

```

### Q61：Tool 在 list 里能看到，但调用时报参数错误，你会怎么排查？

可能方向：

- input schema
- 客户端传参 JSON
- 必填字段
- 类型错误
- enum / min / max
- 默认值

你的回答：

```text

```

### Q62：`read-source-file` 被正常拒绝了，但用户认为这是 bug，你会怎么解释？

考察点：

- workspace 白名单
- 敏感文件过滤
- 只读安全边界
- 拒绝也是正确行为
- 如何从 `callId` 查日志

你的回答：

```text

```

### Q63：`find-java-class` 在大仓库里很慢，你会如何优化？

可能方向：

- 达到 maxResults 后停止遍历
- 忽略 node_modules、target、build、.git
- 缓存项目索引
- 限制文件类型
- 后续接入 ripgrep
- 异步超时

你的回答：

```text

```

### Q64：天气 MCP 调用外部 API 超时，你会如何定位？

可能方向：

- API key
- 代理
- DNS
- 超时配置
- OpenWeather 服务状态
- `diagnose-weather-network`
- 日志 callId

你的回答：

```text

```

## 15. 第十三组：面试表达题

### Q65：请用 3 分钟介绍你做过的 MCP 项目。

要求：

- 不要陷入业务细节
- 重点讲学习目标
- 讲清 stdio 到 HTTP 的升级
- 讲清生产化边界
- 讲清 Java 代码库 MCP 的价值

你的回答：

```text

```

### Q66：请用 5 分钟讲清楚你认为生产级 MCP 最关键的 5 个点。

建议覆盖：

- 协议边界
- 鉴权权限
- 安全限制
- 可观测性
- 测试和文档

你的回答：

```text

```

### Q67：如果面试官问“你只是写了几个 demo，怎么证明你掌握了 MCP？”你怎么回答？

考察点：

- 从 demo 到生产化的设计意识
- HTTP transport
- 安全边界
- 调试和测试
- 文档契约
- 真实 Java 项目接入

你的回答：

```text

```

### Q68：你认为 MCP 开发最容易被忽略的风险是什么？

候选方向：

- 过度信任 LLM
- 工具权限过大
- 写操作无审计
- 文件读取无边界
- 返回敏感信息
- 没有 callId
- stdio stdout 被污染

你的回答：

```text

```

## 16. 加分追问题

### Q69：MCP 与 OpenAPI / REST API 的关系是什么？

你的回答：

```text

```

### Q70：MCP 与 function calling 的区别是什么？

你的回答：

```text

```

### Q71：如果要把 MCP 接入企业内部网关，你会关注哪些点？

你的回答：

```text

```

### Q72：如果一个 MCP 同时服务多个团队或租户，你会如何设计 tenant 隔离？

你的回答：

```text

```

### Q73：如何判断一个能力应该做成 MCP Tool，而不是直接放进 Prompt？

你的回答：

```text

```

### Q74：如何判断一个上下文应该做成 Resource，而不是每次都由 Tool 查询？

你的回答：

```text

```

### Q75：如果 MCP Server 要支持高并发，你会关注哪些工程问题？

你的回答：

```text

```

## 17. 最终自评表

完成答题后，按下面清单自评：

| 能力项 | 是否掌握 | 备注 |
|---|---|---|
| 能解释 MCP Host / Client / Server |  |  |
| 能解释 Tools / Resources / Prompts |  |  |
| 能解释 stdio transport |  |  |
| 能解释 Streamable HTTP transport |  |  |
| 能设计 Tool schema 和返回结构 |  |  |
| 能说明 stdio 日志为什么走 stderr |  |  |
| 能说明 HTTP MCP 为什么要鉴权 |  |  |
| 能设计 `/health` 和 smoke test |  |  |
| 能设计 callId 和结构化日志 |  |  |
| 能做路径白名单和敏感文件过滤 |  |  |
| 能说明只读 MCP 的风险 |  |  |
| 能说明写操作 MCP 的安全要求 |  |  |
| 能说明 Prompt 不会自动执行 Tool |  |  |
| 能说明 Resource 的稳定上下文价值 |  |  |
| 能排查 MCP 客户端连接失败 |  |  |
| 能排查 Tool 参数错误 |  |  |
| 能讲清自己的 MCP 项目 |  |  |

## 18. 建议答题顺序

如果你想用最短时间验证掌握程度，建议先答这些核心题：

```text
Q1, Q2, Q3, Q4,
Q6, Q10, Q12,
Q15, Q17, Q18, Q19,
Q21, Q23,
Q25, Q27, Q29,
Q35, Q36,
Q38, Q39, Q41,
Q45, Q46,
Q50, Q65, Q67
```

如果这些题能答清楚，说明你已经掌握了 MCP 开发的主干知识。

如果要进一步达到面试稳定表达，建议再重点练：

```text
Q53, Q54, Q60, Q61, Q63, Q66, Q68
```

