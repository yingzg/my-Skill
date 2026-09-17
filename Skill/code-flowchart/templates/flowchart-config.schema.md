# flowchart config JSON 契约

Agent 填入 `templates/flowchart.html` 的配置对象，运行时替换模板里的 `window.FLOWCHART_CONFIG`。

```json
{
  "title": "preCheckRebate 调用链",
  "project": "intl-scheme",
  "query": "preCheckRebate",
  "coverage": {
    "complete": false,
    "reason": "relation_budget_reached",
    "note": "候选主流程，非完整运行时调用链"
  },
  "graphs": [
    {
      "entry_symbol": "SettlementBillCommandProviderImpl.preCheckRebate",
      "exit_symbol": "SettlementAndRebateServiceImpl.executePreCheckRebate",
      "path_status": "verified",
      "confidence": "medium",
      "mermaid_flowchart": "flowchart LR\n  n1[...] -->|calls| n2[...] ...",
      "mermaid_sequence": "sequenceDiagram\n  participant P as ...\n  P->>C: preCheckRebate ...",
      "folded": [
        { "parent": "SettlementAndRebateServiceImpl.preCheckRebate", "items": ["checkPreCheckParam (校验)", "buildPreCheckRebateParam (参数组装)", "BizException (异常构造)"] }
      ]
    }
  ]
}
```

## 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | 是 | 页面标题 |
| `project` | string | 是 | 项目名 |
| `query` | string | 是 | 原始 query |
| `coverage.complete` | boolean | 是 | 决定 banner 颜色（true=绿，false=红黄警示） |
| `coverage.reason` | string | 否 | 不完整原因（relation_budget_reached / depth_limit_reached / fanout_limit_reached） |
| `coverage.note` | string | 是 | banner 主文案（complete=false 时固定为「候选主流程，非完整运行时调用链」） |
| `graphs[]` | array | 是 | 每个 entry_symbol 一组图 |
| `graphs[].entry_symbol` | string | 是 | `▶ Entry:` 徽标文案 |
| `graphs[].exit_symbol` | string | 否 | `■ Exit:` 徽标文案 |
| `graphs[].path_status` | string | 是 | `verified` 或 `candidate` |
| `graphs[].confidence` | string | 是 | high/medium/low |
| `graphs[].mermaid_flowchart` | string | 是 | 简化流程图 Mermaid 源（节点/边/classDef/linkStyle 已编码在内） |
| `graphs[].mermaid_sequence` | string | 是 | 详细时序图 Mermaid 源（participant/消息已编码在内） |
| `graphs[].folded[]` | array | 否 | 折叠细节，每项含 `parent` + `items[]` |

## mermaid_flowchart 编码约定（Agent 生成时遵守）

- 节点：`n1["ClassSimpleName.methodName"]`（标签带类名，无裸方法名）。
- 边：`n1 -->|calls| n2`。
- 角色着色：`classDef entry ...` + `class n1,n2 entry`。
- candidate 虚线：`linkStyle 0 stroke:#9e9e9e,stroke-width:2px,stroke-dasharray:5 5`。
- 方向：`flowchart LR`（左到右，适配演示）。
- **不包含 folded_steps**（折叠细节只进时序图）。

## mermaid_sequence 编码约定

- 见 `references/sequence-diagram-mapping.md`。
- 含主线消息 + folded 细节消息，尽量详细。
