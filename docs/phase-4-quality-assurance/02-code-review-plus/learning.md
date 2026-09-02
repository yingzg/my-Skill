# code-review-plus — 深度学习文档

> 对应 SKILL.md: `/mnt/d/测试项目/mi-claw-skills/code-review-plus/SKILL.md` (209行)
>
> 原实现仓库: `/mnt/d/测试项目/mi-claw-skills/code-review-plus/`

---

## 一、功能全景

### 一句话定位

**双模型交叉代码审查引擎** — Claude 自身作为审查者之一，同时调用本地 Codex CLI 生成外部审查视角，对比差异后生成 HTML 可视化报告。

### 核心流程

```
用户触发审查请求
    ↓
[Step 0] 确定审查目标 + 检测平台 (macOS/Windows/Linux)
    ↓
┌─────────────────────────────────────────────────────┐  
│              并行执行（两条审查流水线）                  │
│                                                       │
│  [Step 1] 启动 Codex CLI 审查         [Step 2] Claude 自身审查 │
│    ├─ 检测 codex 是否可用               ├─ 阅读代码            │
│    ├─ 预拼接 prompt                     ├─ 按标准格式分析      │
│    ├─ 后台异步运行 (review-runner.sh)   ├─ 问题清单 (C/H/M/L) │
│    └─ 超时 180s，写入结果文件            └─ 暂存不展示         │
│                                                       │
└─────────────────────────────────────────────────────┘
    ↓
[Step 3] 等待外部 CLI 完成，读取审查输出
    ↓
[Step 4] 交叉对比报告
    ├─ 共性问题（多模型都发现 → 高可信度）
    ├─ 差异性问题（仅某模型发现 → 需人工判读）
    └─ 综合修复建议 (P0/P1/P2/P3)
    ↓
[Step 5] 生成 HTML 可视化报告 + 自动打开浏览器
    ├─ 暗色主题 (GitHub Dark #0d1117)
    ├─ 统计卡片 (Critical/High/Medium/Low 计数)
    ├─ Tab 切换面板 (共性问题/差异性问题/优点/修复建议/各模型详情)
    └─ P0-P3 分级修复建议
```

### 与 cr-engineer 的差异化定位

| 维度 | code-review-plus | cr-engineer |
|------|-----------------|-------------|
| 审查对象 | 本地代码文件 / git diff 变更 | GitLab MR (Merge Request) |
| 审查方式 | Claude + Codex 双模型并行 | Claude + 团队历史 review 模式 |
| 输出格式 | HTML 可视化报告 | GitLab MR 评论 |
| 核心创新 | 多模型共识/差异对比 | 团队评论模式学习 |
| 适用场景 | 本地开发、预提交检查 | MR 门禁、CI 流水线 |
| 平台依赖 | Codex CLI (npm) | GitLab API |

---

## 二、架构设计分析

### 2.1 文件分层架构

```
code-review-plus/
├── SKILL.md                    # 主控文件：5步执行流程 + 平台适配 + HTML规范
└── scripts/
    ├── review-runner.sh        # 并行审查引擎：检测工具 + 启动外部CLI + 超时管理
    ├── cross-review.sh         # 全流程编排：并行启动 + 流程图生成 + 差异对比 + HTML生成
    ├── live-review.sh          # 实时并排审查：边跑边输出，支持直播场景
    ├── install.sh              # macOS/Linux 安装脚本
    └── install.ps1             # Windows PowerShell 安装脚本
```

**设计思想**: SKILL.md 定义"做什么"和"为什么"，shell 脚本定义"怎么做"。5 个脚本各司其职，职责边界清晰。这种分层让 SKILL.md 保持 209 行的可读性，同时脚本可以独立测试和演进。

### 2.2 双模型并行执行架构

```
        SKILL.md (编排层)
             │
     ┌───────┴────────┐
     │                │
  Claude 审查      review-runner.sh
  (同步执行)       (异步后台上报)
     │                │
     │          ┌──────┴──────┐
     │          │  检测可用工具   │
     │          │  codex CLI    │
     │          └──────┬──────┘
     │                 │
     │          ┌──────┴──────┐
     │          │  预拼接 prompt  │
     │          │  + 代码内容    │
     │          └──────┬──────┘
     │                 │
     │          ┌──────┴──────┐
     │          │  run_single_tool  │
     │          │  后台异步执行     │
     │          │  PID + watchdog   │
     │          └──────┬──────┘
     │                 │
     └────────┬────────┘
              │
        结果收集 layer
     ┌────────┴────────┐
     │  codex-review.md │
     │  .done 标记文件   │
     └────────┬────────┘
              │
        差异对比 layer
     ┌────────┴────────┐
     │  cross-review.sh │
     │  共性问题 / 差异  │
     │  P0-P3 修复建议  │
     └────────┬────────┘
              │
        可视化 layer
     ┌────────┴────────┐
     │  report.html     │
     │  Mermaid 流程图   │
     │  Tab 切换面板     │
     └─────────────────┘
```

**关键设计决策**: Claude 审查与 Codex CLI 审查是**真并行**的 — Claude 在 Step 2 做审查的同时，Step 1 的 review-runner.sh 已在后台运行 Codex CLI。不是"先跑一个再跑另一个"的串行模式。

### 2.3 并行执行引擎 — review-runner.sh 深度解析

review-runner.sh 是整个多模型审查的核心引擎，巧妙解决了"如何在 shell 中实现真正并行"的问题。

```bash
# 核心并行模式（简化伪代码）
TOOLS=(codex)                          # 检测到的外部工具列表

for t in "${TOOLS[@]}"; do
  run_single_tool "$t" &              # 关键：& 使得每个工具在子进程并行启动
  PIDS+=($!)                          # 记录子进程 PID
done

for i in "${!PIDS[@]}"; do
  wait "${PIDS[$i]}"                  # 等待全部子进程完成
done

touch "$OUTPUT_DIR/.done"             # 统一完成标记
```

**并行机制详解**:

1. **子进程并行**: `run_single_tool "$t" &` 将审查任务放到后台子进程，不阻塞后续工具启动
2. **PID 追踪**: `PIDS+=($!)` 记录每个后台子进程的 PID，后续用于等待和超时管理
3. **统一等待**: 第二个 `for` 循环调用 `wait` 等待所有子进程完成
4. **完成标记**: `.done` 文件作为"所有审查完成"的原子信号，供跨进程协作

**run_single_tool 函数的精妙实现**:

```bash
run_single_tool() {
  local tool="$1"

  # 1. 启动审查子进程，输出重定向到文件
  (codex exec --skip-git-repo-check "$prompt" 2>/dev/null) > "$output_file" 2>/dev/null &
  local pid=$!

  # 2. 启动 watchdog 超时监控子进程
  (sleep "$timeout_sec" && kill "$pid" 2>/dev/null) &
  local watchdog=$!

  # 3. 等待审查子进程完成
  wait "$pid" 2>/dev/null
  local ret=$?

  # 4. 清理 watchdog
  kill "$watchdog" 2>/dev/null 2>&1
  wait "$watchdog" 2>/dev/null 2>&1

  # 5. 无输出时写失败标记
  if [ ! -s "$output_file" ]; then
    echo "[${tool}] 审查超时或失败 (timeout=${timeout_sec}s, exit=${ret})" > "$output_file"
  fi
}
```

这是一个经典的 **PID + watchdog 超时模式**:

- 审查子进程 (pid) 和 watchdog 超时进程 (watchdog) 各自独立运行
- watchdog 在 sleep 后 `kill $pid`，触发超时终止
- 主进程 `wait $pid` 等待审查完成（可能是正常完成或被杀）
- 清理 watchdog 避免僵尸进程
- 结果文件为空时自动写入失败日志，确保下游读取时不会遇到空文件

### 2.4 全流程编排 — cross-review.sh 深度解析

cross-review.sh 是独立终端使用的完整编排脚本，相当于 SKILL.md Step 1-5 的合体。

```
cross-review.sh 执行流程:

  ┌─────────────────────────────────────────────┐
  │ [1/3] 并行启动外部工具审查                     │
  │   bash review-runner.sh "$OUTPUT_DIR" &       │
  │   RUNNER_PID=$!                              │
  └──────────────┬──────────────────────────────┘
                 │
  ┌──────────────┴──────────────────────────────┐
  │ [2/3] 生成代码流程图（与审查并行）              │
  │   run_with_timeout $TIMEOUT codex exec ...   │
  │   → flowchart.mmd (Mermaid 格式)             │
  └──────────────┬──────────────────────────────┘
                 │
  ┌──────────────┴──────────────────────────────┐
  │ [3/3] 等待外部工具完成 + 汇总                  │
  │   wait "$RUNNER_PID"                        │
  │   读取 .tools 获取可用工具列表                  │
  │   读取 ${tool}-review.md 获取各工具审查结果      │
  └──────────────┬──────────────────────────────┘
                 │
  ┌──────────────┴──────────────────────────────┐
  │ 差异对比（如果有 ≥2 个工具）                    │
  │   拼接各审查报告 → 调用 AI 生成 diff-report.md   │
  │   格式: 共性问题 / 差异性问题 / 综合修复建议       │
  └──────────────┬──────────────────────────────┘
                 │
  ┌──────────────┴──────────────────────────────┐
  │ 生成 HTML 报告                               │
  │   注入 meta 信息、流程图、Tab 内容、差异对比      │
  │   用 python3 安全注入多行内容                   │
  └─────────────────────────────────────────────┘
```

**关键设计点**:

1. **三步并行编排**: [1/3] 启动外部审查到后台，[2/3] 同时生成流程图（充分利用等待时间），[3/3] 等待完成并汇总
2. **流程图前置**: 先生成 Mermaid 流程图有助于审查者理解代码结构，且与审查并行不增加总时延
3. **差异对比是二次 AI 调用**: 需要将多份审查报告拼接成 prompt，再调用 AI 做对比分析 — 这是一个"元审查"过程
4. **HTML 注入的安全方案**: 使用 `python3` 做多行内容注入，避免 shell 字符串拼接的安全风险

### 2.5 外部 CLI 集成模式

code-review-plus 设计了一套可扩展的外部 CLI 集成框架:

```
检测层:  command -v codex &>/dev/null     → .tools 记录可用工具
  │
调用层:  codex exec --skip-git-repo-check "$prompt"     # 非交互模式
         codex -q --skip-git-repo-check "$prompt"       # 静默模式（降级）
  │
输入层:  预拼接 .prompt.txt (系统 prompt + 代码内容)
         → 避免 CLI 自行读文件的 I/O 开销
  │
超时层:  watchdog pid + sleep + kill       # 兼容 macOS 无 timeout 命令
  │
输出层:  ${tool}-review.md                 # 标准化输出路径
  │
错误层:  空输出 → 自动写失败日志
         exit code ≠ 0 → 记录但不中断流程
```

**Codex CLI 的特殊处理**:

- `codex exec`: 非交互模式，直接执行 prompt 返回结果
- `--skip-git-repo-check`: 跳过 git 仓库检查，避免在非 git 目录下报错
- `-q` 静默模式作为降级: 部分 Codex 版本可能不支持 `exec` 子命令
- `2>/dev/null`: 抑制 stderr，避免噪音混入审查结果

**可扩展性设计**: `review-runner.sh` 中的 `for t in codex` 循环是为多工具并行设计的。当前只有 Codex，但新增一个工具只需在 `case "$tool" in` 中添加一个分支。

### 2.6 平台适配策略

code-review-plus 是三套独立的平台路径:

```
        用户触发
           │
    uname -s 检测平台
    ┌──────┼──────┐
    │      │       │
  Darwin  Linux   Windows
  (macOS) (bash)  (PowerShell)
    │      │       │
    ├─ bash 脚本   ├─ bash 脚本    ├─ PowerShell 原生命令
    ├─ open 命令   ├─ xdg-open     ├─ Start-Process
    ├─ /tmp/       ├─ /tmp/       ├─ $env:TEMP
    └─ 直接调用     └─ 直接调用     └─ Start-Job 后台任务
```

**macOS 特殊性处理**:

- bash 3.x 兼容 (macOS 默认是 bash 3): 不使用 `declare -A` (关联数组), 改用 `eval` 模拟
- 无 `timeout` 命令: 自实现 `run_with_timeout` 函数 (PID + watchdog 模式)
- sed `-i ''` 语法: macOS sed 的 `-i` 需要空字符串参数

**Windows 特殊性处理**:

- 优先检测 Git Bash: 如果有 Git Bash，优先用 bash 脚本
- 无 Git Bash 时: 使用 PowerShell 原生的 `Start-Job` 做后台任务
- Prompt 写临时文件: PowerShell 的字符串转义复杂，通过临时文件传递大文本

**Linux 特殊性处理**:

- 跟在 macOS 路径 (bash 脚本 + `/tmp/` 目录)
- `xdg-open` 打开浏览器 (代替 macOS 的 `open`)

### 2.7 HTML 报告生成架构

HTML 报告不是简单的数据展示，而是**代码审查的可视化分析工具**。

```
HTML 报告组件树:

├── 顶部 Banner
│   ├── 标题 "CodeReviewPlus"
│   └── meta 信息 (文件名 | 时间 | 参与模型)
│
├── 代码流程图 (Mermaid)
│   └── 主要函数调用、条件分支、数据流转
│
├── Tab 切换面板
│   ├── Tab 1: Codex 审查详情
│   │   └── 完整审查输出的格式化展示
│   ├── Tab 2: Claude 审查详情
│   │   └── 完整审查输出的格式化展示
│   ├── Tab 3: 差异对比
│   │   ├── 共性问题（两模型一致发现）
│   │   └── 差异性问题（单一模型发现）
│   └── Tab N: 其他参与模型...
│
└── 样式系统 (GitHub Dark Theme)
    ├── 背景 #0d1117, 文字 #c9d1d9
    ├── 标题 #58a6ff (蓝色系)
    ├── Tab 选中态 #58a6ff 高亮
    ├── Mermaid 暗色主题集成
    └── 响应式布局 (max-width: 1200px)
```

**HTML 生成的技术难点**:

1. **多行内容注入**: 用 `python3` 而非 `sed` 处理多行内容注入，避免 shell 转义问题
2. **HTML 转义**: `sed 's/</\\&lt;/g; s/>/\\&gt;/g'` 处理审查输出中的 `<` 和 `>`
3. **Tab 激活**: 通过 `sed` 替换第一个 `class="tab"` 为 `class="tab active"`，让第一个 Tab 默认激活
4. **Mermaid 集成**: 通过 CDN 加载 `mermaid@11`，初始化 `{theme:'dark'}`，流程图直接嵌入 HTML

### 2.8 live-review.sh — 实时审查模式

live-review.sh 是面向开发者直播/教学场景的实时审查工具:

```
实时并排审查流程:

  [Step 1] 生成 Mermaid 流程图
      ↓
  [Step 2] 并行启动所有工具
      ├─ Claude 输出 ──→ 终端实时流式展示 (红色前缀)
      └─ Codex 输出  ──→ 终端实时流式展示 (蓝色前缀)
         ↓
     两者同时输出到终端，开发者实时看到两个模型的分析
         ↓
     同时写入 ${tool}-review.md 留存
```

**关键差异**: live-review.sh 使用 `tee` 将输出同时写文件和终端，各工具输出用不同颜色前缀区分 (`\033[31m[Claude]\033[0m` vs `\033[34m[Codex]\033[0m`)，真正实现"实时并排审查"体验。

---

## 三、设计模式深度分析

### 3.1 多模型共识模式 (Multi-Model Consensus Pattern)

这是 code-review-plus 最核心的设计创新，也是 Phase 4 所有 Skill 中独有的模式:

```
          ┌─────────┐          ┌─────────┐
          │ Claude  │          │  Codex  │
          │ 审查视角  │          │ 审查视角  │
          └────┬────┘          └────┬────┘
               │                    │
               └────────┬───────────┘
                        │
                   ┌────┴────┐
                   │ 差异对比  │
                   └────┬────┘
                        │
          ┌─────────────┼─────────────┐
          │             │             │
     ┌────┴────┐   ┌────┴────┐   ┌────┴────┐
     │ 共性问题  │   │ 差异问题  │   │ 矛盾结果  │
     │ 高可信度  │   │ 中可信度  │   │ 需人裁决  │
     └─────────┘   └─────────┘   └─────────┘
```

**共识等级机制**:

| 等级 | 条件 | 可信度 | 处理策略 |
|------|------|--------|---------|
| 共识 | 两个模型都发现了同一问题 | 高 | 优先修复，P0/P1 |
| 差异 | 仅一个模型发现 | 中 | 标记"需人工判读" |
| 矛盾 | 两个模型给出相反结论 | 低 | 标注"需人工裁决" |
| 独有 | 某个模型独有的分析视角 | 参考 | 作为补充信息 |

**为什么多模型共识有效**:

1. **独立盲区不同**: 每个模型训练数据、微调方式、推理偏好不同，盲区不重叠
2. **交叉验证**: 两个模型同时发现的问题，大概率是真正的代码缺陷
3. **互补发现**: 一个模型可能关注逻辑问题，另一个关注安全问题
4. **置信度量化**: 不是简单的"通过/不通过"，而是给出问题置信度

### 3.2 并行执行模式 (Parallel Execution Pattern)

review-runner.sh 中的并行模式有三个关键特征:

```
时间线:

0s ──────────────────────────── 180s
│                                   │
├─ run_single_tool codex &  ────────┤ (Codex 审查)
│                                   │
└─ (同时 Claude 审查)  ─────────────┤
                                    │
                            .done 标记生成
```

**并行 vs 串行的总时延对比**:

| 模式 | Claude 耗时 | Codex 耗时 | 总耗时 | 对比 |
|------|-------------|------------|--------|------|
| 串行 | 60s | 90s | 150s | 基准 |
| 并行 | 60s | 90s | max(60,90) = 90s | 快 40% |

**并行实现的 Shell 技巧**:

```bash
# 技巧 1: 用 & 实现子进程并行
run_single_tool "$t" &      # & 使得函数在子进程中异步运行

# 技巧 2: 用 $! 捕获 PID
PIDS+=($!)                  # $! 是上一个后台命令的 PID

# 技巧 3: 用 wait 同步
wait "${PIDS[$i]}"          # 阻塞直到指定 PID 完成

# 技巧 4: 用 .done 文件做完成信号
touch "$OUTPUT_DIR/.done"   # 原子性的完成标记
```

### 3.3 适配器模式 (Adapter Pattern)

Codex CLI 的输出格式并非标准格式，需要适配器将其转换为统一的审查格式:

```
Codex 原始输出
     │
     ▼
┌──────────────┐
│  格式适配器   │  ← 通过 prompt 约束输出格式
└──────┬───────┘
       │
       ▼
  标准化审查格式:
  ● 代码概述
  ● 问题清单 (C/H/M/L)
  ● 优点
  ● 改进建议
```

**适配不是 post-processing，而是 prompt-engineering**:

review-runner.sh 在调用 Codex 前，预拼接了标准格式的 prompt:

```
请审查以下代码，严格按照以下格式输出：

## 代码概述
## 问题清单
按严重程度排序（Critical > High > Medium > Low）
- **[严重程度]** 问题描述
- 位置：文件名:行号
- 修复建议
## 优点
## 改进建议
```

这样 Codex 的输出直接就是标准格式，无需后期格式转换。这是一种"前置适配"策略。

### 3.4 外观模式 (Facade Pattern)

Shell 脚本作为复杂多步骤编排的外观:

```
外部调用者 (SKILL.md / 终端用户)
           │
    ┌──────┴──────┐
    │ cross-review.sh │  ← 外观：一行命令完成全部编排
    └──────┬──────┘
           │
    ┌──────┼──────┬──────────┐
    │      │      │          │
  review  flowchart   diff    HTML
  runner   生成       对比    生成
```

cross-review.sh 的 `bash "$SCRIPT_DIR/review-runner.sh" "$OUTPUT_DIR" "${CODE_FILES[@]}" &` 就是外观模式 — 隐藏了工具检测、prompt 拼接、超时管理、结果收集等内部复杂性。

---

## 四、核心设计决策

### 4.1 为什么用两个模型而不是同一模型跑两次？

这是最常见的问题。答案分层：

**技术层面**:
- 同一模型跑两次（如 Claude 跑两次），差异主要来自采样随机性 (temperature)，而非系统性差异
- 两个不同模型（Claude + Codex）的差异来源于：训练语料不同、架构设计不同、推理链偏好不同、指令遵循能力不同

**实证层面**:
- 自动化测试中，多模型一致的发现确实比单模型重复两次的发现更有价值
- 单一模型容易产生系统性的"盲区"（如忽略某类安全问题）

**业务层面**:
- "多模型审查"本身就是差异化价值主张
- 交叉验证的结果有更强的说服力

### 4.2 为什么用 Shell 脚本而不是 Python 编排？

| 维度 | Shell 脚本 | Python 脚本 |
|------|-----------|------------|
| 零依赖 | ✅ 仅需 bash (系统自带) | ❌ 需 Python 解释器 |
| 子进程管理 | `&` + `$!` + `wait` 原生支持 | `subprocess.Popen` + 复杂回调 |
| Prompt 拼接 | `cat >>` + heredoc 直观 | 需要多行字符串 + f-string |
| macOS 兼容 | bash 3.x 兼容写法 | 需确定 Python 版本 |
| 维护成本 | 低 (短小精悍) | 中 (需管理依赖和异常) |

**核心原因**: Shell 脚本对"并行启动子进程 + 等待完成"这一核心需求的表达力远超 Python，且零额外依赖。

### 4.3 为什么用 HTML 报告而不是 Markdown？

| 维度 | HTML 报告 | Markdown 终端输出 |
|------|----------|-----------------|
| 可读性 | Tab 切换、颜色标注、统计卡片 | 线性文本，难以表达多维结构 |
| 交互性 | Tab 切换、流程图渲染、悬停提示 | 纯静态文本 |
| 交付性 | 可分享链接、可存档、可二次加工 | 终端输出一次性 |
| 表达力 | CSS 暗色主题、badge、颜色分级 | 有限 |
| 复杂度 | 需要 HTML/CSS/JS 知识 | 零成本 |

**核心原因**: 双模型审查结果是一个**多维数据集** — 问题来源(哪个模型)、严重程度(C/H/M/L)、共识程度(共有/差异)、修复优先级(P0-P3)。HTML 是最适合展现多维数据的形式。

### 4.4 为什么选 Codex 而不是其他 LLM？

| 候选 | CLI 成熟度 | 非交互模式 | prompt 传递 | 生态 |
|------|-----------|-----------|------------|------|
| Codex | ✅ `codex exec` | ✅ | ✅ 直接传递 | OpenAI 官方 |
| Claude CLI | ✅ | ⚠️ 需 `--print` | ✅ | 但嵌套调用死锁 |
| Gemini CLI | ⚠️ | ⚠️ | ⚠️ | 生态未成熟 |
| Ollama | ⚠️ 本地模型 | ⚠️ | ⚠️ 质量不稳定 | 开源 |

**核心原因**: Codex CLI 有最成熟的非交互模式 (`codex exec`)、直接 prompt 传递、无需额外配置。同时 Claude 已作为主审查者运行，不能再嵌套调用自己（SKILL.md 明确警告：`不要调用 claude，因为你自己就是 Claude，嵌套调用会导致死锁`）。

### 4.5 为什么流程图放在 Step 2（与审查并行）而非 Step 0（前置）？

```
错误方案:                         正确方案:
Step 0: 生成流程图 (60s)          Step 1: 启动 Codex 审查 (后台)
Step 1: Codex 审查 (90s)          Step 2: 生成流程图 + Claude 审查 (并行)
Step 2: Claude 审查 (60s)                           ↓
────────────────────────          ────────────────────────
总耗时: 60 + max(90,60) = 150s    总耗时: max(90, max(60,60)) = 90s
```

**核心原因**: 流程图生成和审查任务可以并行，而流程图前置会拖延审查启动。将流程图放到审查并行时段，不增加总时延。

---

## 五、设计权衡与限制

### 5.1 成本：双倍 API 成本

- Claude 审查：消耗当前会话的 token（通常是用户的 Claude 配额）
- Codex 审查：消耗 Codex/OpenAI 的 API 配额
- 总成本约为单模型审查的 2 倍

**权衡**: 对于关键基础设施代码、安全敏感模块，双模型审查的成本是合理的。对于简单改动的代码，单模型审查即可。

### 5.2 时延：短板模型决定总时间

```
Claude 审查: 60s
Codex 审查: 120s (慢)
─────────────────────
总耗时: max(60, 120) = 120s  ← 慢的模型决定总时间
```

即使并行，最终仍需等待最慢的模型完成。差异对比步骤还会增加额外的 AI 调用时延。

### 5.3 Codex 依赖风险

- 如果 Codex CLI 未安装：只能使用 Claude 单一审查，退化为普通审查
- 如果 Codex 服务不可用：review-runner.sh 在超时 180s 后写失败日志，不阻塞流程
- 如果 Codex CLI 行为变更：`exec`/`-q` 子命令可能在未来版本中变化

**当前的处理**: `review-runner.sh` 中如果没有检测到任何外部工具，直接 `touch "$OUTPUT_DIR/.done"` 并退出，不报错。这是一种优雅降级。

### 5.4 审查一致性：模型可能根本性分歧

两个模型可能对同一段代码给出完全相反的结论：
- Claude 认为某写法是安全的，Codex 认为有注入风险
- Claude 建议重构方向 A，Codex 建议方向 B
- **当前无仲裁机制**: 差异对比报告仅标记"需人工判读"，没有自动仲裁

### 5.5 平台锁入

- **macOS**: 完全支持 (bash 脚本 + `open` 命令)
- **Windows**: 需要 Git Bash 或 WSL；PowerShell 原生路径功能不完整
- **Linux**: 未在文档中明确声明支持，但 bash 脚本天然兼容

### 5.6 无持久化存储

- 审查结果写入 `/tmp/`，系统重启后丢失
- 没有历史审查记录查询
- 没有审查质量趋势分析

---

## 六、实践要点

### 6.1 多模型共识作为质量提升模式

在需要高可靠性的场景（安全审计、核心算法、合规检查），多模型共识可以显著降低单一模型的盲区风险。这不是只适用于代码审查，也可以推广到文档审查、合同分析、医学影像判读等领域。

### 6.2 Shell 脚本如何设计并行执行

```bash
# 模板: Shell 并行执行模式
PARALLEL_TASKS=5
PIDS=()

for i in $(seq 1 $PARALLEL_TASKS); do
  do_task "$i" > "output_$i.txt" &
  PIDS+=($!)
done

for pid in "${PIDS[@]}"; do
  wait "$pid" || FAILED=$((FAILED + 1))
done
```

### 6.3 Shell 脚本的 watchdog 超时模式

这是不依赖 `timeout` 命令 (macOS 不可用) 的通用超时实现:

```bash
run_with_timeout() {
  local secs="$1"; shift
  "$@" &
  local pid=$!
  (sleep "$secs" && kill "$pid" 2>/dev/null) &
  local watchdog=$!
  wait "$pid" 2>/dev/null
  local ret=$?
  kill "$watchdog" 2>/dev/null 2>&1
  wait "$watchdog" 2>/dev/null 2>&1
  return $ret
}
```

### 6.4 HTML 报告作为复杂分析的输出

对于需要表达多维数据的分析结果，HTML 报告比 Markdown 或终端输出更适合：
- Tab 切换解决信息过载
- 颜色编码解决优先级传达
- 流程图解决结构可视化
- 暗色主题解决长时间阅读疲劳

### 6.5 prompt 前置约束 vs 后置解析

相比"让 AI 自由输出然后解析"，"用 prompt 约束输出格式"是一种更高效的适配模式。review-runner.sh 在调用 Codex 前将输出格式要求注入 prompt，避免了复杂的后置解析。

### 6.6 优雅降级设计

```bash
# 工具不可用时静默降级，不阻塞流程
if [ ${#TOOLS[@]} -eq 0 ]; then
  echo "没有检测到 Codex CLI (codex)"
  touch "$OUTPUT_DIR/.done"    # ← 不报错，正常标记完成
  exit 0
fi
```

这是一种"尽力而为"的设计哲学 — 系统不应该因为外部依赖缺失而崩溃。

---

## 七、复刻要点 Checklist

- [ ] 理解双模型并行审查的完整流程 (Step 0-5)
- [ ] 理解 review-runner.sh 的并行引擎：`&` + `$!` + `wait` + `.done` 标记
- [ ] 理解 watchdog 超时模式：审查 pid + sleep pid 的协作
- [ ] 理解 cross-review.sh 的三步编排：[1/3] 启动审查、[2/3] 生成流程图、[3/3] 汇总
- [ ] 理解差异对比的三级分类：共识/差异/矛盾
- [ ] 理解 HTML 报告的 Tab 设计 + 暗色主题
- [ ] 理解适配器模式的前置实现：prompt 约束输出格式
- [ ] 理解平台适配的三条路径：macOS / Linux bash / Windows PowerShell
- [ ] 理解为什么选择 Shell 脚本而非 Python
- [ ] 理解为什么选择 Codex 而非其他 LLM
- [ ] 理解优雅降级设计：工具不可用时静默退出而非报错
- [ ] 能设计新增一个外部审查工具（如 Gemini CLI）的集成方案

(End of file - total 496 lines)
