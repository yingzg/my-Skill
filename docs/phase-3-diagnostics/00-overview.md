# Phase 3: 排障诊断 — 学习总览

> 对应 [skill-learning-roadmap.md](../skill-learning-roadmap.md) Phase 3 章节
>
> 📅 生成时间: 2026-07-08

---

## 🎯 学习目标

掌握 4 个线上排障诊断 Skill 的核心设计思想和可复制模式，理解如何脱离公司内部依赖后进行通用化复刻。

---

## 📊 四技能对比矩阵

| 维度 | ticket-troubleshoot-v3 | hera-trace-doctor | code-trace-analyzer | hera-slow-api-analyzer |
|------|----------------------|-------------------|---------------------|----------------------|
| **行数** | 409 | 163 | 227 | 510 |
| **难度** | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **输入** | 用户描述 + 业务ID | 单个 traceId | Java 包路径/类名/方法名 | appName + 时间范围 |
| **数据源** | 数据库 + 代码 | Hera CLI (trace+log) | 本地源码 | Hera Web + 源码 |
| **核心模式** | Pipeline + Contract | Rule Engine | 逐层 AST 遍历 | 2-Phase Automation |
| **输出** | 双层结论(简/详) | 5段诊断报告 | Mermaid 链路 + SQL | Markdown 治理报告 |
| **关键依赖** | zeus-devx-database MCP | hera CLI | feishu MCP | Playwright + Hera |
| **独特设计** | Checkpoint 恢复 / 经验库复用 / Golden Cases | 症状→根因规则映射 | 外部调用识别 / 异常全景图 | API 接口文档作为备选 |

---

## 🥇 推荐学习顺序

```
3.1 ticket-troubleshoot-v3  ──→  最精良，含几乎所有设计模式
         ↓
3.2 hera-trace-doctor       ──→  最轻量，快速建立成就感
         ↓
3.3 code-trace-analyzer     ──→  纯静态分析，脱离依赖最自然
         ↓
3.4 hera-slow-api-analyzer  ──→  最重，平台抽象设计挑战最大
```

**理由**: ticket-troubleshoot-v3 是一把"瑞士军刀"——pipeline、checkpoint、output contract、fail-close、经验库复用、golden cases 回归测试全都在一个 skill 里。先吃透它，后面三个的设计思路你一眼就能认出来。

---

## 🏗️ 贯穿四个 Skill 的核心设计模式

### 1. Pipeline（流水线）
`ticket-troubleshoot-v3` (7步) / `hera-slow-api-analyzer` (8步) / `hera-trace-doctor` (3步)

```text
输入 → 步骤1 → 步骤2 → ... → 步骤N → 结构化输出
```

**关键设计决策**:
- 是否允许步骤间跳跃？（ticket: 是，有快速复用路径）
- 失败后如何恢复？（ticket: checkpoint + 续跑协议）
- 步骤间是否有依赖？（hera-slow: 两阶段严格分离）

### 2. Output Contract（输出契约）
`ticket-troubleshoot-v3` 独有

```yaml
status: success | partial_success | failed  # 强制三态
confidence: high | medium | low
restricted_info: []                          # 显式声明受限信息
```

这是 **形式化验证** 思想在 Prompt Engineering 中的应用——不是"写好一点"的软约束，而是可机器校验的硬约束。

### 3. Rule Engine（规则引擎）
`hera-trace-doctor` 的 `diagnosis-rules.md`

```text
if 症状 == "Broken Pipe"   →  根因 = 客户端先断开
if 症状 == "长耗时+子span短" →  根因 = 未埋点内部逻辑
```

与 Pipeline 互补：Pipeline 控制 **流程**，Rule Engine 控制 **判断逻辑**。

### 4. Evidence-First（证据优先）
所有四个 Skill 的共性要求

- `ticket`: 结论必须绑证据（代码行号 + 查询结果）
- `trace-doctor`: 至少 5 条证据（trace + log + 时间线）
- `code-trace`: 必须读数实际源码，不凭类名猜测
- `hera-slow`: 基于 Hera 页面 + span + 源码的三重验证

---

## 🔌 公司依赖通用化策略

### 核心原则: 依赖倒置（Dependency Inversion）

每个 Skill 不直接依赖具体的 MCP/API，而是定义 **抽象接口**，通过 **适配器** 对接具体平台。

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Skill Core │────→│   Interface   │←────│   Adapter    │
│   (通用逻辑)  │     │  (抽象接口)    │     │  (具体实现)   │
└──────────────┘     └──────────────┘     └──────────────┘
                           ↑                    ↑
                      IDatabaseQuery      ZeusAdapter
                      ITraceAnalyzer      GrafanaAdapter
                      IDocPublisher       MarkdownAdapter
```

### 各 Skill 的抽象层设计

| Skill | 公司依赖 | 抽象接口 | 默认适配器 |
|-------|---------|---------|-----------|
| ticket-troubleshoot | zeus-devx-database MCP | `IDatabaseQuery` | MySQLAdapter (直连) |
| code-trace-analyzer | feishu MCP | `IDocPublisher` | MarkdownAdapter (本地文件) |
| hera-slow-api-analyzer | Hera 平台 | `IAPMPlatform` / `ITraceFetcher` | GrafanaAdapter / 通用 OpenTelemetry |
| hera-trace-doctor | hera CLI | `ITraceFetcher` / `ILogFetcher` | JaegerAdapter / ELKAdapter |

---

## 📏 量化 Skill 质量的维度

脱离公司平台后，如何判断复刻的 Skill 质量是否达标？

### 结构质量（可审计）
| 指标 | 测量方法 | ticket-troubleshoot-v3 基准值 |
|------|---------|-------------------------------|
| Checkpoint 完整率 | 模拟中断后能否续跑 | 100%（7步全部有checkpoint） |
| Contract 符合率 | 输出是否满足 Output Schema | 100%（有自检清单） |
| 中断白名单准确率 | 是否在该中断时中断 | 2个允许中断点（选系统/无描述） |

### 功能质量（可回放）
| 指标 | 测量方法 | 基准 |
|------|---------|------|
| Golden Case 通过率 | 用预置用例回归测试 | ticket: 3个 GC 全部通过 |
| 恢复准确率 | 中断后续跑，结果是否一致 | 应为 100% |

### 泛化质量（可迁移）
| 指标 | 测量方法 |
|------|---------|
| 适配器接口数量 | 数出 Skill 中有多少外部调用 → 每个对应一个接口方法 |
| 平台假设显式化程度 | 有多少"硬编码"的平台 URL/参数 → 应全部抽取为配置 |
| 多平台测试通过率 | 至少 2 个不同平台适配器下 golden case 通过 |

---

## 📁 文档结构

```
phase-3-diagnostics/
├── 00-overview.md                           ← 你在这
├── 01-ticket-troubleshoot-v3/
│   ├── learning.md                          # 深度分析学习文档
│   └── quiz.md                              # 问题验证文档
├── 02-hera-trace-doctor/
│   ├── learning.md
│   └── quiz.md
├── 03-code-trace-analyzer/
│   ├── learning.md
│   └── quiz.md
└── 04-hera-slow-api-analyzer/
    ├── learning.md
    └── quiz.md
```

---

## ⏱️ Phase 3 学习时间规划

| 天 | 内容 | 预估 |
|----|------|------|
| Day 1 | ticket-troubleshoot-v3 学习文档 + 回答问题 | 3h |
| Day 2 | hera-trace-doctor 学习文档 + 回答问题 | 1.5h |
| Day 3 | code-trace-analyzer 学习文档 + 回答问题 | 2.5h |
| Day 4 | hera-slow-api-analyzer 学习文档 + 回答问题 | 3h |
| Day 5 | 复习 + 脱离依赖复刻实战 | 2h |

> 注：文档已为你生成好，时间主要花在理解和回答 quiz 上。
