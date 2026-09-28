---
name: code-review-plus
description: |
  Claude + Codex 代码审查工具。Claude 自身作为审查者之一，同时调用本地 Codex CLI 生成外部审查视角，
  最终对比整理问题并生成 HTML 可视化报告。
  触发场景：用户提到"代码审查"、"交叉审查"、"多模型审查"、"code review"、"帮我review"。
  支持 macOS 和 Windows。
---

# CodeReviewPlus — Claude + Codex 代码审查

## 执行流程

当用户触发此 skill 时，严格按以下步骤执行。核心原则：**外部 CLI 后台先跑，Claude 同时审查，最后汇总**。

### Step 0: 确定审查目标 + 检测平台

- 如果用户指定了文件路径，直接使用
- 如果用户说"审查当前改动"，用 `git diff` 获取变更内容
- 如果用户说"审查 XX 模块"，先搜索定位核心文件
- 如果不明确，询问用户

**检测平台**：执行以下命令判断当前环境：

```bash
uname -s 2>/dev/null || echo "Windows"
```

- 输出包含 `Darwin` → macOS
- 输出包含 `Linux` 或 `MINGW` 或 `MSYS` → Linux / Git Bash
- 输出 `Windows` 或命令失败 → Windows PowerShell

后续步骤根据平台选择对应语法。

### Step 1: 检测可用外部工具 + 后台启动审查

**macOS / Linux / Git Bash 环境：**

```bash
# 检测可用工具
command -v codex &>/dev/null && echo "codex: available" || echo "codex: not found"

# 创建输出目录并后台启动
OUTPUT_DIR="/tmp/code-review-$(date +%Y%m%d-%H%M%S)"
SKILL_DIR="$HOME/.claude/skills/code-review-plus"
bash "$SKILL_DIR/scripts/review-runner.sh" "$OUTPUT_DIR" <文件1> [文件2] ... &
```

**Windows PowerShell 环境：**

```powershell
# 检测可用工具
if (Get-Command codex -ErrorAction SilentlyContinue) { Write-Output "codex: available" } else { Write-Output "codex: not found" }

# 创建输出目录
$OUTPUT_DIR = "$env:TEMP\code-review-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
New-Item -ItemType Directory -Path $OUTPUT_DIR -Force | Out-Null

# 如果有 Git Bash，优先用 review-runner.sh
$SKILL_DIR = Join-Path $env:USERPROFILE ".claude\skills\code-review-plus"
$gitBash = Get-Command bash -ErrorAction SilentlyContinue
if ($gitBash) {
    $runner = "$SKILL_DIR/scripts/review-runner.sh" -replace '\\','/'
    Start-Job -ScriptBlock { bash $using:runner $using:OUTPUT_DIR <文件路径> }
}
```

如果没有 Git Bash，对每个可用工具直接启动后台审查任务：

```powershell
# 预生成 prompt 到临时文件
$PROMPT_FILE = "$OUTPUT_DIR\.prompt.txt"
@"
请审查以下代码，按严重程度排序输出问题清单（Critical > High > Medium > Low），每项包含：严重程度、问题描述、位置（文件名:行号）、修复建议。同时列出代码优点和改进建议。

代码内容：
"@ | Set-Content -Path $PROMPT_FILE
Get-Content <代码文件路径> | Add-Content -Path $PROMPT_FILE

# 后台调用 codex（示例）
Start-Job -ScriptBlock { codex exec (Get-Content $using:PROMPT_FILE -Raw) 2>$null | Set-Content "$using:OUTPUT_DIR\codex-review.md" }

```

等待后台任务完成：

```powershell
Get-Job | Wait-Job -Timeout 180
# 写完成标记
"done" | Set-Content "$OUTPUT_DIR\.done"
```

> 注意：**不要调用 `claude`**，因为你自己就是 Claude，嵌套调用会导致死锁。

### Step 2: Claude 自身审查（与 Step 1 并行）

在外部 CLI 后台运行的同时，Claude 直接阅读代码完成自己的审查。按以下格式组织（暂存不展示）：

```
## 代码概述
简要描述代码功能和结构（2-3句话）

## 问题清单
按严重程度排序（Critical > High > Medium > Low），每项包含：
- **[严重程度]** 问题描述
- 位置：文件名:行号
- 修复建议

## 优点
代码写得好的地方

## 改进建议
具体的重构或优化建议
```

### Step 3: 读取外部 CLI 结果
 
等待后台任务完成，然后读取各工具的审查输出。

**macOS / Linux / Git Bash：**
```bash
test -f "$OUTPUT_DIR/.done" && echo "done" || echo "running"
cat "$OUTPUT_DIR/codex-review.md" 2>/dev/null
```

**Windows PowerShell：**
```powershell
Test-Path "$OUTPUT_DIR\.done"
Get-Content "$OUTPUT_DIR\codex-review.md" -ErrorAction SilentlyContinue
```

如果某个工具超时或失败，其输出文件会包含失败提示或不存在，正常处理即可。

### Step 4: 交叉对比报告

收集所有审查结果后（Claude + 外部工具），对比分析，按以下格式输出：

```markdown
# CodeReviewPlus 交叉审查报告

**文件**: <文件名>
**参与模型**: Claude, Codex
**时间**: <当前时间>

---

## 共性问题（多个模型都发现的）

> 可信度最高，应优先修复

| # | 严重程度 | 问题描述 | 位置 | 发现者 |
|---|---------|---------|------|--------|

## 差异性问题（仅某个模型发现的）

> 需要人工判断是否有效

| # | 严重程度 | 问题描述 | 位置 | 发现者 |
|---|---------|---------|------|--------|

## 优点

## 综合修复建议

按优先级排序的修复清单（P0/P1/P2/P3）
```

### Step 5: 生成 HTML 可视化报告

**每次审查都必须生成 HTML 报告**。用审查数据填充 HTML 模板写入文件，然后打开。

HTML 报告要求：
- 暗色主题（GitHub Dark 风格，背景 #0d1117）
- 顶部统计卡片：Critical / High / Medium / Low 计数 + 共性/差异数量
- Tab 切换面板：共性问题 | 差异性问题 | 优点 | 修复建议 | 各模型详情
- 表格展示问题清单，badge 标注严重程度和发现者
- 修复建议按 P0-P3 分级，用不同颜色标注

打开报告：
- **macOS**: `open "$OUTPUT_DIR/report.html"`
- **Windows PowerShell**: `Start-Process "$OUTPUT_DIR\report.html"`
- **Linux**: `xdg-open "$OUTPUT_DIR/report.html"`

---

## 终端独立使用（需要 bash 环境）

macOS / Linux / Git Bash 用户也可以直接在终端运行脚本：

```bash
# macOS / Linux / Git Bash:
SKILL_DIR="$HOME/.claude/skills/code-review-plus"

# 交叉审查（并行模式）+ HTML 报告
bash "$SKILL_DIR/scripts/cross-review.sh" <代码文件>

# 仅启动外部工具并行审查（不含 Claude）
bash "$SKILL_DIR/scripts/review-runner.sh" <输出目录> <代码文件>
```

> Windows 用户请通过 Git Bash 或 WSL 运行脚本。

## 支持的外部工具

| 工具 | CLI 命令 | 安装方式 | 自动检测 |
|------|---------|---------|---------|
| Codex | `codex` | `npm install -g @openai/codex` | ✅ |

Claude 自身始终作为审查者参与，无需额外安装。只需安装 Codex 即可运行。
