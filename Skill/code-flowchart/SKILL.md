---
name: code-flowchart
description: 把 Code-intelligence 的 code.explore_symbol 返回的调用链（main_paths）渲染成可视化流程图 + 时序图。Use when 用户想看到某个方法的调用链流程图、需要可视化「入口→锚点→出口」调用链、或需要演示 Code-intelligence 的调用链检索能力。输入一个 symbol 或 ExploreResponse JSON，输出自包含 HTML（简化流程图 + 详细时序图）。
---

# code-flowchart

把 `code.explore_symbol` 返回的 `ExploreResponse.main_paths` 渲染成调用链可视化（自包含 HTML，内联 mermaid.js，单文件多图）。每个 entry 输出**两张互补图**：

1. **简化流程图**（`flowchart`）：只画主线骨架，校验/参数组装/锁/DTO 等非主线细节折叠不显示。
2. **详细时序图**（`sequenceDiagram`）：把折叠细节展开为消息，尽量详细。

## 定位

展示层 SKILL。只消费 `ExploreResponse`，不修改 Code-intelligence 核心，不重新解析代码，不重跑 trace。

## 工作流

1. **拿数据**：用户给 symbol → 调 `code.explore_symbol` 拿 `ExploreResponse`；用户直接给 JSON → 跳过。
2. **读主链路**：读 `main_paths`，按 `entry_symbol` 分组（一 entry 一组图）。
3. **生成简化流程图**：节点/边按 `references/role-color-mapping.md`（着色）+ `references/relation-label-mapping.md`（边标签）生成 Mermaid `flowchart` 源；candidate 边加 `linkStyle ... stroke-dasharray`；**不含 folded_steps**。
4. **生成详细时序图**：按 `references/sequence-diagram-mapping.md` 生成 Mermaid `sequenceDiagram` 源（participants + 主线消息 + folded 细节消息）。
5. **填 config**：按 `templates/flowchart-config.schema.md` 填 `title/coverage/graphs[]`（含 `mermaid_flowchart` + `mermaid_sequence`）。
6. **渲染**：把 config 填入 `templates/flowchart.html`（替换 `window.FLOWCHART_CONFIG`），输出 HTML 文件。

## 诚实展示规则（不可变，来自 schema-contract 8.2）

- `coverage.complete=false` → banner 必须醒目写「候选主流程，非完整运行时调用链」。
- `path_status != verified` → 虚线边 + `candidate` 角标，绝不画成实线（时序图在 header 标徽标）。
- `confidence=low` → 警示徽标。
- `main_paths=[]` → 渲染「无主链路证据」占位 + 透传 `diagnostics`。
- 绝不把 main_paths 当完整调用链；「空」只代表「无证据」，不是「不存在」。

## 文件

- 模板：`templates/flowchart.html`（渲染时替换 `window.FLOWCHART_CONFIG`）
- 契约：`templates/flowchart-config.schema.md`
- 映射：`references/role-color-mapping.md`、`references/relation-label-mapping.md`、`references/sequence-diagram-mapping.md`
- 字段：`references/explore-symbol-fields.md`
- 示例：`examples/precheck-rebate.md`
