# code.explore_symbol 字段引用

本 SKILL 只消费 `ExploreResponse` 的以下字段（完整契约见 Code-intelligence `docs/schema-contract.zh-CN.md`）。

## 消费顺序（v0.4 契约，不可变）

```text
summary → main_paths（优先 high/medium）→ coverage → diagnostics
需要展开细节时读 folded_steps / side_relations；审计时读 relations / candidate_paths
```

## 主链路 MainPath（核心消费对象）

| 字段 | 类型 | 用途 |
|---|---|---|
| `entry_symbol` | string? | 入口符号，图上 `▶ Entry:` 徽标 + 分组键 |
| `exit_symbol` | string? | 出口符号，图上 `■ Exit:` 徽标 |
| `path_status` | string | verified=candidate 判定（verified=实线，其余=虚线） |
| `confidence` | high/medium/low | low 时加警示徽标 |
| `nodes[]` | CodeLocation[] | 有序节点 → 流程图节点 + 时序图 participant |
| `relations[]` | CodeRelation[] | 有序边 → 流程图边 + 时序图主线消息 |
| `folded_steps[]` | FoldedStep[] | 折叠细节 → 时序图细节消息（详见 sequence-diagram-mapping.md） |
| `summary` | string | 图标题副文案 |

## CodeLocation（节点）

| 字段 | 用途 |
|---|---|
| `symbol` | 节点标签（剥包前缀取 `ClassSimpleName.methodName`） |
| `location_type` | 角色着色主依据 |
| `file` / `start_line` | tooltip / Note 标注 |

## CodeRelation（边）

| 字段 | 用途 |
|---|---|
| `from` / `to` | 节点 id 连接 |
| `relation_type` | 边标签（见 relation-label-mapping.md） |

## coverage

| 字段 | 用途 |
|---|---|
| `complete` | false 时 banner 必须醒目标注「候选主流程，非完整运行时调用链」 |

## diagnostics

始终作为图下方可折叠清单透传（不隐藏）。尤其关注：
`MAIN_PATH_NO_STRONG_RELATION_CHAIN` / `ANCHOR_AMBIGUOUS` / `MAIN_PATH_COVERAGE_PARTIAL`。

## 硬规则（来自 schema-contract 8.2）

1. 空不等于无：`main_paths=[]` 只代表「当前无证据」。
2. 候选不等于验证：candidate 永不画成 verified。
3. 预算内不等于全量：`relations` 是预算内子集。
