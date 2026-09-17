# relation_type → 边标签映射

边标签取 `CodeRelation.relation_type`（归一化类型，见 schema-contract 6.8）。映射如下：

| relation_type | 边标签 | 备注 |
|---|---|---|
| calls | calls | 强（执行链路） |
| method_implements | implements | 强 |
| method_overrides | overrides | 强 |
| maps_to_sql | → SQL | 中强 |
| uses_table | uses table | 中强 |
| handles_route | handles | 中 |
| throws | throws | 中 |
| logs | logs | 中 |
| reads_config | reads config | 中 |
| has_method | has method | 中 |
| has_property | has property | 中 |
| extends | extends | 中 |
| contains | contains | 中 |
| imports | imports | 弱（静态依赖） |
| accesses | accesses | 弱 |
| typed_as | typed as | 弱 |
| references | references | 弱（兜底降级） |

Mermaid 流程图边语法：`A -- "calls" --> B` 或 `A -->|calls| B`。

> 注意：v0.5 已把 `main_path.relations` 精简到 3 种强关系（calls / method_implements / maps_to_sql），
> 主链路流程图绝大多数边都是 `calls`。其余类型仅当 fallback 或审计展开时出现。
