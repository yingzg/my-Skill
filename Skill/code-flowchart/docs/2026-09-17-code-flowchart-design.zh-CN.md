# code-flowchart 设计规格

> 日期：2026-09-17
> 定位：Code-intelligence 的上游展示层 SKILL，把 `code.explore_symbol` 返回的调用链渲染成可视化流程图。
> 用途：演示 Code-intelligence 的调用链检索能力，同时作为面试展示作品的一部分。

---

## 1. 背景与定位

Code-intelligence 是一个面向 AI Agent 的本地 Java 代码情报底座。它的核心能力之一，是从一个 symbol（方法名/错误码/接口路径）出发，用 GitNexus trace 分段验证，得到「入口 → 锚点 → 出口」的完整调用链（`main_paths`）。

`code-flowchart` 是它的**上游展示层**：输入一个 symbol，调用 `code.explore_symbol` 拿到 `ExploreResponse`，把 `main_paths` 渲染成流程图，让用户一眼看到「这个方法从哪个 Controller/Provider 进来，经过哪些 Service，落到哪个 Mapper/SQL」。

**一句话定义**：只消费 `ExploreResponse.main_paths`（nodes + relations + entry/exit + coverage）的渲染型 SKILL，输出可视化流程图，并诚实标注可信度信号。

---

## 2. 目标

- 输入一个 symbol（或线索），输出一张（或多张）调用链流程图。
- 图上直观呈现：入口 → 业务节点 → 持久化落点。
- 诚实展示 verified/candidate、confidence、coverage 等可信度信号，不粉饰。

## 3. 非目标 / 硬边界

`code-flowchart` 是**展示层**，以下事项**不做**：

1. **不修改** Code-intelligence 核心逻辑（只读消费 `explore_symbol` 返回）。
2. **不重新解析代码**（那是 Code-intelligence 的职责，本 SKILL 只用 `main_paths` 的 nodes/relations）。
3. **不重跑 trace / 不做任何关系探索**。
4. **不粉饰**：`coverage.complete=false` 或 `confidence=low` 时图上必须标注。

---

## 4. 输出格式决策

| 决策项 | 结论 | 理由 |
|---|---|---|
| 渲染载体 | Mermaid 定义 + 自包含 HTML 模板 | Agent 只产出 Mermaid + config JSON，不手写前端；兼顾生成稳定性与演示效果 |
| mermaid.js 引入 | **内联**进模板 | 单文件、离线可开、面试不依赖网络；代价是模板约 2MB |
| 多 entry 打包 | **单文件多图**（顶部 tab 或顺序滚动） | 双击即看全部，演示体验最顺 |

Agent 运行时只产出两样东西：

```text
1. 每个 entry_symbol 两份 Mermaid 定义：
   - flowchart（简化主线流程图，只画 main_path 骨架）
   - sequenceDiagram（详细时序图，含 folded 细节）
2. config JSON（节点角色着色、verified/candidate 标注、coverage 文案、folded 分组、entry/exit 徽标）
```

HTML/CSS/JS 全部来自预置模板，运行时零手写前端。

### 4.1 两种输出形式

每个 `entry_symbol` 输出**两张互补的图**：

| 图 | 类型 | 内容 | 目的 |
|---|---|---|---|
| 简化流程图 | `flowchart` | 只含 `main_path.nodes`（主线）+ `relations`（主线边）；非主线细节（校验/参数组装/锁/DTO）**不显示** | 一眼看懂「入口 → 业务 → 持久化」结构 |
| 详细时序图 | `sequenceDiagram` | 主线调用 + `folded_steps` **展开为细节消息**（校验/组装/锁/异常等） | 展示完整时序，演示 Code-intelligence 折叠细节可回溯的能力 |

两者互补：流程图强调「结构拓扑」，时序图强调「时序细节」。

---

## 5. 数据流

```text
ExploreResponse (main_paths[])
  → 归一化映射（节点/边标签、角色着色、verified/candidate 判定）
  → 按 entry_symbol 分组，每个 entry 两份 Mermaid 定义 + 一份 config JSON：
      · mermaid_flowchart：主线骨架流程图（nodes + relations，折叠细节不显示）
      · mermaid_sequence：详细时序图（nodes + relations + folded_steps 展开为细节消息）
  → 填入预置 HTML 模板（内联 mermaid.js + 固定 UI chrome）
  → 输出自包含 HTML（+ 可选原始 .mmd 供版本化/嵌入）
```

消费顺序遵循 `schema-contract` 8 节约定：

```text
summary → main_paths（优先 high/medium）→ coverage（判断能否说完整）→ diagnostics（决定是否二次 explore）
需要展开细节时才读 folded_steps / side_relations；需要审计时才读 relations / candidate_paths。
```

---

## 6. 可视化规则

### 6.1 节点标签

- 标签 = `ClassSimpleName.methodName`（从 `CodeLocation.symbol` 剥包前缀）。
- `symbol` 缺失时回退 `file:line`。
- **绝不用裸方法名**——v0.3.2 专门修过 `preCheckRebate --calls--> preCheckRebate` 的同名歧义，流程图上重蹈会毁掉演示可信度。

### 6.2 节点角色着色（4 桶，复用 role-classifier 语义）

| 角色桶 | 匹配（LocationType / 命名） | 颜色 |
|---|---|---|
| `entry` | controller / route / dubbo_provider / Provider / Scheduler / Consumer / Listener / Handler | 绿 |
| `business` | service / dubbo_interface / Service / Manager / Processor / Executor | 蓝 |
| `persistence` | mapper / repository / sql / Dao | 橙 |
| `other` | config / constant / enum / exception / test / unknown | 灰 |

不做 `LocationType` 全部 14 值的逐一映射（过度设计且图会变花）。

### 6.3 边标签（归一化 relation_type → 人话）

| relation_type | 边标签 |
|---|---|
| `calls` | calls |
| `method_implements` | implements |
| `method_overrides` | overrides |
| `maps_to_sql` | → SQL |
| `handles_route` | handles |
| 其他 | 回退 relation_type 原文 |

v0.5 已把 `main_path` 关系精简到 3 种强关系（calls / method_implements / maps_to_sql），边标签天然干净。

### 6.4 verified vs candidate（不可妥协）

| 状态 | 视觉 |
|---|---|
| `verified` | 实线边 + 实心节点 + `✓` 徽标 |
| `candidate`（fallback） | **虚线边** + 图上角标「候选链路（未 trace 验证）」 |
| `confidence=low` | 额外警示徽标 + tooltip |

对应 `schema-contract` 8.2 硬规则二「候选不等于验证」。candidate 画得和 verified 一样实，等于视觉上撒谎。

### 6.5 coverage 诚实声明（不可妥协）

- 每张图顶部**恒定**渲染 coverage banner。
- `coverage.complete=true`：banner「已完整探索（预算内）」，仍附「建议结合代码证据确认」的温和提示。
- `coverage.complete=false`：醒目红/黄 banner「**候选主流程，非完整运行时调用链**（原因：relation_budget / depth / fanout）」。

### 6.6 entry/exit 标注

- `entry_symbol` → 首节点 + `▶ Entry:` 徽标（独立形状/描边色）。
- `exit_symbol` → 末节点 + `■ Exit:` 徽标。

### 6.7 folded_steps

- 简化流程图：只画主链路骨架，折叠项**不铺开**，父节点旁标 `+N folded` 徽标（点击展开）。
- 详细时序图：折叠项**展开为细节消息**（见 6.9），让时序图尽量详细。
- 折叠是 v0.4 的卖点：流程图默认折叠保持简洁，时序图展开保持详细，两者互补。

### 6.8 多链路处理

- 按 `entry_symbol` 分组，一个 entry 一组图（流程图 + 时序图，单文件内 tab 切换）。
- 若只有 1 条 `main_path`，自然是一组图。
- 可选的「总览合并图」作为开关，合并时仍需区分各链路 verified/candidate 状态。

### 6.9 时序图映射（sequenceDiagram，详细）

每个 entry 的时序图把折叠细节展开，形成完整时序。映射规则：

**participants**：`main_path.nodes` 的类名去重 + `folded_steps` 的目标类名去重（按首次出现顺序）。

**主线消息**：对每条 relation（from→to），发 `FromClass ->> ToClass: calledMethod`（calledMethod = to 节点的简单方法名）。

**折叠细节消息**：对每个有 folded_steps 的主节点，在它发出下一条主线消息前，按 folded_steps 顺序发消息：

- 同类折叠：`Parent ->> Parent: method (reason标签)`
- 跨类折叠：`Parent ->> FoldedClass: method (reason标签)`

**reason 标签映射**：`validation=校验` / `parameter_assembly=参数组装` / `lock=锁` / `exception=异常构造` / `dto_accessor=DTO访问` / `utility=工具` / `test=测试` / `low_priority_detail=细节`。

**代码位置**：可选 `Note right of X: file:line` 标注。

**side_relations 不进时序图**：imports / test_noise 等是噪声，不是调用链细节（「详细」= 展开 folded_steps，不等于引入噪声）。

**时序图不区分 verified/candidate 线型**（sequenceDiagram 无虚线语义），但在图 header 保留 `✓ verified` / `○ candidate` 徽标。

---

## 7. SKILL 文件结构

对齐 `api-flow` / `online-troubleshoot` 既有约定：

```text
Skill/code-flowchart/
├── SKILL.md                              # frontmatter(name/description) + 工作流
├── templates/
│   ├── flowchart.html                    # 自包含 HTML 模板（内联 mermaid.js + UI chrome）
│   └── flowchart-config.schema.md        # config JSON 字段说明
├── references/
│   ├── role-color-mapping.md             # 角色→颜色
│   ├── relation-label-mapping.md         # relation_type→边标签
│   ├── sequence-diagram-mapping.md       # folded_steps→时序图消息映射
│   └── explore-symbol-fields.md          # 引用 schema-contract 关键字段
├── examples/
│   └── precheck-rebate.md                # 真实 eval case 输入→输出
└── docs/
    └── 2026-09-17-code-flowchart-design.zh-CN.md
```

---

## 8. 降级处理（不隐藏任何 signal）

- `main_paths=[]`：渲染「无主链路证据」占位图 + 透传 `diagnostics`（尤其 `MAIN_PATH_NO_STRONG_RELATION_CHAIN` / `ANCHOR_AMBIGUOUS`），提示二次 explore（缩小 query / 提高 relation_budget）。
- `diagnostics` 始终作为图下方可折叠清单呈现（一等公民，见 schema-contract 2.2）。
- 有 `main_paths` 但 `relations=[]`：渲染单节点序列。
- `index_status.state` 非 `ready`：图上方标出索引状态 + 建议命令。

---

## 9. 测试策略

### 9.1 golden case

基准输入：`preCheckRebate` eval case。

```text
SettlementBillCommandProviderImpl.preCheckRebate
  → SettlementBillCommandServiceImpl.preCheckRebate
  → SettlementAndRebateServiceImpl.preCheckRebate
  → SettlementAndRebateServiceImpl.executePreCheckRebate
```

断言：

- 节点顺序正确。
- entry/exit 徽标正确。
- verified（实线）/candidate（虚线）区分正确。
- coverage banner 文案正确。
- `+N folded` 徽标出现。
- 节点标签含类名（无裸方法名）。

### 9.2 边界 case

- 空 `main_paths` → 占位图 + diagnostics 透传。
- 单节点 → 单节点渲染不崩。
- `confidence=low` → 警示徽标。
- `coverage.complete=false` → 醒目 banner。

---

## 10. 验收标准

- 输入 `ExploreResponse`，输出自包含 HTML（单文件，离线可开）。
- 每个 entry 输出两张图：简化流程图（主线骨架）+ 详细时序图（含 folded 细节）。
- 图上正确区分 verified / candidate / low confidence。
- `coverage.complete=false` 时 banner 醒目，不粉饰。
- entry/exit 徽标、4 桶着色均正确；简化流程图不含校验等非主线细节，时序图展开这些细节。
- golden case + 边界 case 全部通过。

---

## 11. 后续

本设计确认后，进入 `writing-plans` 生成实现计划。实现顺序建议：

1. SKILL.md 骨架 + frontmatter。
2. `references/` 映射表（角色颜色、边标签、字段引用）。
3. `templates/flowchart.html`（内联 mermaid.js + UI chrome）。
4. `templates/flowchart-config.schema.md`。
5. `examples/precheck-rebate.md` golden case。
6. 边界 case 验证。
