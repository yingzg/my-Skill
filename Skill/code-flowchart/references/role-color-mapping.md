# 角色 → 颜色映射

流程图节点按「角色桶」着色。映射顺序：先按 `location_type`，再按 `symbol` 命名后缀兜底。

| 角色桶 | location_type | 命名后缀兜底 | mermaid classDef | 颜色语义 |
|---|---|---|---|---|
| entry | controller / route / dubbo_provider | Provider / Controller / Scheduler / Consumer / Listener / Handler / Job / Facade | `classDef entry fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20` | 绿 = 入口 |
| business | service / dubbo_interface | Service / Manager / Processor / Executor / CommandService / DomainService / ApplicationService | `classDef business fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#0d47a1` | 蓝 = 业务 |
| persistence | mapper / sql | Repository / Mapper / Dao | `classDef persistence fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#bf360c` | 橙 = 持久化 |
| other | config / constant / enum / exception / log_statement / test / unknown | （其余） | `classDef other fill:#eceff1,stroke:#607d8b,stroke-width:1px,color:#37474f` | 灰 = 其他 |

判定伪代码：

```text
function roleOf(location):
  if location.location_type in {controller, route, dubbo_provider}: return entry
  if location.location_type in {service, dubbo_interface}: return business
  if location.location_type in {mapper, sql}: return persistence
  # 命名兜底（location_type 缺失或 unknown 时）
  name = location.symbol or ""
  if name matches /(Provider|Controller|Scheduler|Consumer|Listener|Handler|Job|Facade)$/: return entry
  if name matches /(Service|Manager|Processor|Executor)$/: return business
  if name matches /(Repository|Mapper|Dao)$/: return persistence
  return other
```

每个角色桶在 Mermaid 源里生成一条 `classDef`，并把对应节点 id 用 `class n1,n2 entry` 归属。
