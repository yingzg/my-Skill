# Shell 型 Skill Prompt 设计指南

> 适用场景：`SKILL.md` 控制流程，`scripts/*.sh` 负责确定性执行，例如 `code-review-plus` 的 `review-runner.sh`。

## 一句话原则

写 Shell 型 Skill 的 prompt 时，不要只说“帮我写个脚本”。要把 **流程协议、文件协议、进程协议、失败策略、输出契约** 都说清楚。

Shell 脚本适合做确定性的事情：

- 参数校验
- 文件读写
- 目录创建
- 工具探测
- prompt 拼接
- 子进程启动
- PID 管理
- 超时控制
- 结果文件落盘
- 完成标记

LLM 适合做语义判断：

- 理解代码
- 审查风险
- 归纳共性问题
- 判断严重程度
- 生成修复建议
- 汇总多模型结果

因此，好的 prompt 要明确区分：哪些交给 Shell 保证稳定，哪些交给 AI 做判断。

## Prompt 结构模板

可以用下面这个结构提示 AI 生成 Shell 型 Skill。

```markdown
我要设计一个 Shell 型 Skill，采用 SKILL.md 编排流程、scripts/*.sh 实现确定性逻辑。

## 目标
这个 Skill 要完成什么任务：
- 输入是什么
- 输出是什么
- 完成标准是什么

## 分层要求
- SKILL.md 只写触发条件、整体流程、人工确认点、输出格式
- Shell 脚本负责参数校验、工具探测、文件协议、子进程、超时、结果落盘
- 不要把复杂 Shell 逻辑全部写进 SKILL.md

## 文件协议
请设计固定的工作目录和中间文件：
- `.prompt.txt`：给外部 AI CLI 的完整 prompt
- `<tool>-result.md`：每个外部工具的输出
- `.tools`：检测到的可用工具列表
- `.done`：全部后台任务完成标记
- `report.html` 或 `report.md`：最终报告

## 进程协议
请实现：
- 主 Agent 先启动 runner 脚本到后台
- runner 脚本拼接 prompt
- runner 脚本并行启动外部 CLI
- 每个外部 CLI 输出到独立文件
- runner 等待所有子进程结束
- runner 写 `.done`
- 主 Agent 再读取结果文件并汇总

## Shell 可靠性要求
- 所有变量引用使用双引号
- 参数不足时打印 usage 并退出
- 输出目录使用 `mkdir -p`
- 外部命令使用 `command -v` 检测
- 后台任务保存 PID
- 使用 `wait` 等待子进程
- 使用 watchdog 或 timeout 防止卡死
- 外部工具失败时写入失败说明，不要让下游读空文件
- 不要把 token、密钥打印到日志

## Prompt 拼接要求
外部 AI CLI 不能自动共享当前 Agent 上下文，所以必须把任务说明和输入材料显式写入 `.prompt.txt`。
`.prompt.txt` 至少包含：
- 任务目标
- 输出格式
- 严重程度或分类标准
- 输入文件名
- 输入文件内容

## 输出要求
请输出：
- Skill 目录结构
- SKILL.md 草案
- scripts/runner.sh
- 每个 Shell 片段的作用说明
- 使用示例
```

## 为什么要强调文件协议

多进程协作时，不能假设不同 AI 工具共享上下文。

例如 `code-review-plus` 中，Claude 和 Codex 之间不是直接共享记忆，而是通过文件通信：

```text
Claude 当前会话
  ├─ 启动 review-runner.sh 到后台
  ├─ 自己阅读代码并审查
  └─ 等待 runner 写出结果

review-runner.sh
  ├─ 生成 .prompt.txt
  ├─ 调用 codex exec ".prompt.txt 的内容"
  ├─ 写 codex-review.md
  └─ touch .done
```

这里真正的上下文传递方式是：

```text
代码文件 + 任务说明 + 输出格式
        ↓
    .prompt.txt
        ↓
    codex exec
        ↓
    codex-review.md
```

所以实现时一定要先设计中间文件，而不是先写复杂命令。

## 关键提示词：让 AI 不容易写偏

### 1. 约束 SKILL.md 和脚本边界

差的提示：

```text
帮我写一个代码审查 Skill，用 Shell 调 Codex。
```

好的提示：

```text
帮我设计一个代码审查 Skill。SKILL.md 只负责触发条件、5 步流程和最终报告格式；复杂实现放到 scripts/review-runner.sh。runner.sh 负责检测 codex、拼接 .prompt.txt、后台启动 codex、超时控制、写 codex-review.md 和 .done。不要把长 Shell 逻辑写进 SKILL.md。
```

### 2. 明确上下文不能自动共享

差的提示：

```text
让 Codex 帮忙审查当前代码。
```

好的提示：

```text
Codex 子进程不能自动获得当前 Agent 对话上下文。请在 runner.sh 中显式生成 .prompt.txt，把审查目标、输出格式、文件名和文件内容全部写进去，然后将 .prompt.txt 的内容作为 codex exec 的参数。
```

### 3. 明确失败降级

差的提示：

```text
调用 Codex 失败就报错。
```

好的提示：

```text
调用 Codex 超时或失败时，不要让整个 Skill 崩溃。请写入 codex-review.md，内容说明失败原因；仍然 touch .done，让主 Agent 可以继续汇总 Claude 自身审查结果。
```

### 4. 明确进程管理

差的提示：

```text
后台跑一下 Codex。
```

好的提示：

```text
请使用 `cmd &` 启动后台任务，用 `$!` 保存 PID，用 `wait "$pid"` 等待结束。为每个外部工具启动 watchdog：`sleep "$timeout_sec" && kill "$pid"`，防止命令长时间卡住。
```

### 5. 明确输出契约

差的提示：

```text
生成审查报告。
```

好的提示：

```text
每个外部工具必须输出到 `$OUTPUT_DIR/<tool>-review.md`。runner 完成后必须写 `$OUTPUT_DIR/.done`。主 Agent 只读取这些文件，不从终端日志解析结果。
```

## Shell 型 Skill 的设计顺序

不要从命令开始。按这个顺序设计：

1. 定义用户输入：文件路径、目录、分支、MR URL、配置文件。
2. 定义最终输出：Markdown 报告、HTML 报告、评论 JSON、补丁文件。
3. 定义工作目录：所有中间文件放在哪里。
4. 定义文件协议：哪些文件表示输入、结果、状态、错误。
5. 定义进程协议：谁启动谁，谁等待谁，谁写完成标记。
6. 定义失败策略：工具不存在、文件不存在、超时、空输出怎么处理。
7. 最后再生成 Shell 命令。

## 先写脚本规格说明，再翻译成 Bash

如果不熟 Shell，不要直接要求 AI 写 Bash。先用自然语言写“脚本规格说明”，确认行为正确后，再让 AI 翻译成 Bash。

例如 `code-review-plus` 的 runner 可以先写成：

```text
这个 runner 脚本是一个外部 AI 调度器。

它接收一个输出目录和若干代码文件。

它先检查 Codex 是否存在。
如果不存在，就写空工具列表和完成标记，然后正常退出。

如果 Codex 存在，就把审查任务说明、输出格式要求、所有代码文件内容拼成一个 prompt 文件。

然后它启动 Codex 子进程，把 prompt 文件内容传给 Codex。
Codex 的标准输出必须写入 codex-review.md。
Codex 的错误输出不展示给用户。

为了防止 Codex 卡住，脚本同时启动一个 watchdog 子进程。
watchdog 等待指定秒数后杀掉 Codex 进程。
如果 Codex 提前结束，脚本就杀掉 watchdog。

脚本等待 Codex 完成后，检查输出文件是否为空。
如果为空，就写入“审查超时或失败”的说明，保证主 Agent 总能读到结果。

最后脚本写 .done 文件，告诉主 Agent 外部审查已经结束。
```

然后再追加一句：

```text
请先指出这份脚本规格说明是否缺少输入校验、失败处理、兼容性、安全性或清理逻辑；补全规格后，再翻译成 Bash。
```

这个方式比“直接写 Shell”更稳定，因为 AI 会先理解行为协议，再选择命令实现。

## 通用 Prompt 公式

复杂 Shell 脚本可以用这个公式提示 AI：

```markdown
请写一个 Bash 函数/脚本，实现【一句话目标】。

## 输入参数
- 参数1：...
- 参数2：...

## 输出文件协议
- 文件1：...
- 文件2：...

## 执行步骤
1. ...
2. ...
3. ...

## 失败处理
- 情况1：...
- 情况2：...

## 进程要求
- 是否后台运行
- 是否保存 PID
- 是否 wait
- 是否 timeout/watchdog
- 完成标记是什么

## 安全/兼容要求
- 变量加双引号
- 不使用 eval
- 兼容 macOS Bash 3.x
- 不泄露敏感信息

请先解释设计，再输出代码。
```

这个公式的重点不是记住每个 Shell 命令，而是把“脚本应该遵守的协议”说清楚。

## 不熟 Shell 时，如何让 AI 主动补齐可靠性要求

有些校验和兼容性问题确实需要熟悉 Shell 才能想到，例如变量加双引号、PID 清理、macOS Bash 兼容、禁用 `eval`、输出为空时兜底。此时不要假装自己知道所有细节，应该显式要求 AI 做“脚本可靠性设计审查”。

可以这样提示：

```markdown
我不熟 Shell。请你作为资深 Shell 脚本工程师，先不要直接写代码。

请先根据我的脚本目标，主动补齐我可能遗漏的可靠性要求，至少覆盖：
- 参数校验
- 文件和目录是否存在
- 命令是否安装
- 路径中包含空格时是否安全
- 变量是否需要双引号
- 是否需要临时目录或工作目录
- 子进程是否需要保存 PID
- 是否需要超时和 watchdog
- 子进程失败时是否要降级
- 是否需要完成标记文件
- 输出文件为空时怎么处理
- 是否可能泄露 token、prompt 或敏感内容
- 是否兼容 macOS Bash 3.x 和 Linux Bash
- 是否使用了危险命令或危险写法，例如 `eval`、宽泛 `rm -rf`
- 脚本被重复运行时，旧状态文件怎么处理

请先输出：
1. 你补齐后的脚本行为规格
2. 可靠性风险清单
3. 你准备采用的 Shell 实现策略

等规格清楚后，再输出 Bash 代码。
```

如果已经生成了脚本，还可以要求 AI 做二次审查：

```markdown
请审查下面这个 Shell 脚本，不要改业务目标，只检查可靠性和可移植性。

重点检查：
- 未加双引号的变量
- 未处理的空参数
- 命令不存在时的行为
- 后台进程是否可能泄漏
- `wait` 和退出码是否正确处理
- 输出文件是否可能为空
- `.done` 是否在所有结束路径都会写入
- 是否有不必要的敏感信息输出
- 是否兼容 macOS Bash 3.x
- 是否存在危险删除或路径拼接风险

请按“问题 / 风险 / 建议修改”输出。
```

这种写法的本质是把“不懂 Shell 的风险”转化为 AI 的审查任务。你不需要提前知道所有 Shell 细节，但必须要求 AI 在写代码前先做可靠性补全，在写完后再做可靠性审查。

## 常用 Shell 意图表

| 意图 | 常用写法 |
|---|---|
| 检测命令是否存在 | `command -v codex` |
| 忽略错误输出 | `2>/dev/null` |
| 忽略全部输出 | `&>/dev/null` |
| 成功后执行 | `cmd && next` |
| 失败后执行 | `cmd || fallback` |
| 定义变量 | `NAME="value"` |
| 使用变量 | `"$NAME"` |
| 执行命令并取结果 | `$(date +%Y%m%d)` |
| 后台执行 | `cmd &` |
| 获取后台 PID | `$!` |
| 等待后台进程 | `wait "$pid"` |
| 杀掉进程 | `kill "$pid"` |
| 创建目录 | `mkdir -p "$dir"` |
| 判断文件存在 | `[ -f "$file" ]` |
| 判断文件非空 | `[ -s "$file" ]` |
| 写入文件 | `echo "text" > "$file"` |
| 追加文件 | `echo "text" >> "$file"` |
| 读取文件 | `cat "$file"` |
| 多行写入文件 | `cat > "$file" << 'EOF' ... EOF` |
| 遍历数组 | `for x in "${arr[@]}"; do ... done` |
| 数组长度 | `${#arr[@]}` |
| 所有脚本参数 | `"$@"` |
| 第一个参数 | `$1` |
| 丢弃第一个参数 | `shift` |

## code-review-plus 的设计提示词示例

```markdown
请帮我设计一个 `code-review-plus-lite` Skill。

目标：对用户指定的代码文件做双视角审查：当前 Agent 自己审查，同时后台调用 Codex CLI 审查，最后合并成 Markdown 报告。

目录结构：
- SKILL.md
- scripts/review-runner.sh

SKILL.md 要求：
- frontmatter 包含 name 和 description
- description 写清触发词：代码审查、code review、交叉审查、帮我 review
- 正文只保留 5 步流程：
  1. 确定审查目标
  2. 后台启动 scripts/review-runner.sh
  3. 当前 Agent 自己审查
  4. 读取 `$OUTPUT_DIR/codex-review.md`
  5. 输出共性问题、差异问题、修复建议

review-runner.sh 要求：
- 参数：`review-runner.sh <输出目录> <代码文件1> [代码文件2] ...`
- 参数不足时打印 usage 并 exit 1
- 使用 `mkdir -p "$OUTPUT_DIR"`
- 清理旧 `.done` 和 `.tools`
- 使用 `command -v codex` 检测 Codex
- 生成 `$OUTPUT_DIR/.prompt.txt`
- 把任务说明、输出格式、每个代码文件名和内容写入 `.prompt.txt`
- 使用 `codex exec --skip-git-repo-check "$prompt"` 调用 Codex
- Codex 输出写入 `$OUTPUT_DIR/codex-review.md`
- 后台进程使用 `$!` 保存 PID
- watchdog 超时默认 180 秒，支持 `REVIEW_TIMEOUT` 环境变量覆盖
- Codex 失败或输出为空时，写入失败说明
- 完成后必须 `touch "$OUTPUT_DIR/.done"`

请先输出设计说明，再输出完整文件内容。
```

## 检查清单

生成 Shell 型 Skill 后，用这个清单检查：

- [ ] SKILL.md 是否只保留流程，不塞大段复杂 Shell？
- [ ] description 是否包含明确触发词？
- [ ] 脚本是否有 usage 和参数校验？
- [ ] 所有变量引用是否加了双引号？
- [ ] 是否定义了固定输出目录？
- [ ] 是否有 `.prompt.txt` 显式传递上下文？
- [ ] 是否有 `.done` 表示后台任务完成？
- [ ] 外部工具输出是否写入文件，而不是只打印到终端？
- [ ] 外部工具失败时是否能降级？
- [ ] 是否避免泄露 token、密钥、内部配置？
- [ ] 是否能在没有外部工具时正常结束？
- [ ] 主 Agent 是否只依赖文件协议读取结果？

## 最重要的记忆点

不需要背 Shell 命令。实现这类 Skill 时，只要记住一句话：

> 先写协议，再写命令。文件协议解决上下文传递，进程协议解决并行协作，Shell 命令只是协议的落地方式。
