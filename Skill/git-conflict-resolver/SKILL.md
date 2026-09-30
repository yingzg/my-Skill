---
name: git-conflict-resolver
description: Git 合并冲突解决技能。自动检测当前分支的合并冲突文件，分析冲突原因（cherry-pick 重复、并行开发、分支漂移等），判断冲突双方是否有逻辑差异，给出解决策略并自动修复冲突。当用户遇到 git 合并冲突、merge conflict、需要解决冲突时使用此技能。触发词：解决冲突、合并冲突、merge conflict、冲突分析、conflict resolve。
---

# Git 合并冲突解决

## 适用场景

- `git merge` / `git rebase` / `git cherry-pick` 产生冲突
- 用户需要分析冲突原因
- 用户需要自动解决冲突

## 核心工作流

### Step 1: 检测冲突文件

运行 `git status` 查找所有处于未合并（unmerged）状态的文件，列出冲突文件清单。常见冲突状态码：

| 状态码 | 含义 |
|--------|------|
| `UU` | both modified，双方都修改 |
| `AA` | both added，双方都新增 |
| `DD` | both deleted，双方都删除 |
| `AU` | added by us，我方新增 |
| `UA` | added by them，对方新增 |
| `DU` | deleted by us，我方删除、对方修改 |
| `UD` | deleted by them，对方删除、我方修改 |

```bash
git status --short | grep "^UU\|^AA\|^DD\|^AU\|^UA\|^DU\|^UD"
```

### Step 2: 读取冲突内容

逐一读取冲突文件，定位所有 `<<<<<<<` / `=======` / `>>>>>>>` 冲突标记，提取：
- **HEAD 侧代码**（当前分支）
- **Incoming 侧代码**（被合并分支）
- **冲突所在位置**（import 区域 / 方法体 / 新增方法等）

### Step 3: 分析冲突原因

通过 git 历史追溯冲突根因：

```bash
# 1. 从冲突标记获取两个分支名
#    <<<<<<< HEAD  和  >>>>>>> <branch-name>

# 2. 查看两个分支对冲突文件的修改历史
git log --oneline HEAD -- <conflict-file>
git log --oneline <incoming-branch> -- <conflict-file>

# 3. 查找是否有 cherry-pick 重复提交（同 message 不同 SHA）
git log --oneline --all | grep "<关键 commit message>"

# 4. 对比关键提交的改动范围
git show <commit-sha> --stat
```

**常见冲突原因分类：**

| 原因 | 特征 | 解决策略 |
|------|------|---------|
| cherry-pick 重复 | 两个分支有同 message 不同 SHA 的提交，其中一个分支又做了追加修改 | 保留追加修改的一侧（通常是 incoming） |
| 并行开发同一区域 | 两侧都有实质性不同的代码改动 | 需要手动合并两侧逻辑 |
| 纯新增 vs 空 | 一侧为空，另一侧是纯新增代码 | 直接接受新增侧 |
| import 冲突 | 仅 import 区域冲突，方法体无冲突 | 合并两侧 import（去重） |
| 重构 vs 功能修改 | 一侧重命名/移动代码，另一侧修改逻辑 | 需要在重构后的结构上应用功能修改 |

**如何区分「重构」与「功能修改」：**

| 信号 | 重构特征 | 功能修改特征 |
|------|---------|-------------|
| diff 形态 | 大量移动/重命名，净增删行数少 | 局部小范围增删改（改逻辑、加分支、改公式） |
| commit message | 含 `refactor`/`重构`/`extract`/`rename`/`move` 等词 | 含 `fix`/`feat`/`修改`/`新增` 等词 |
| 改动实质 | 逻辑不变，仅结构变化 | 逻辑本身改变 |

判断命令：

```bash
# 1. 看某一侧相对 merge-base 的改动性质（--find-renames 会标注 R=重命名/移动）
git diff --find-renames <merge-base> <branch> -- <file>

# 2. 看该侧的提交历史，从 message 推断意图
git log --oneline <merge-base>..<branch> -- <file>
```

若仍无法确定，按「注意事项」第三条原则：向用户展示两侧差异并请求确认，不要擅自决定。

### Step 4: 判断逻辑差异

对每处冲突判断：

1. **无逻辑冲突**：HEAD 侧为空或与 incoming 侧逻辑一致（如 cherry-pick 重复）→ 直接采用 incoming
2. **单侧新增**：一侧无改动，另一侧纯新增 → 接受新增侧
3. **有逻辑冲突**：两侧都有不同的业务逻辑 → 需要用户确认合并方式

**向用户报告判断结果：**
- 列出每处冲突的位置、双方差异摘要
- 明确告知是否存在逻辑冲突
- 如果全部无逻辑冲突，说明可以安全自动解决

### Step 5: 解决冲突

根据判断结果：

**自动解决（无逻辑冲突时）：**
- 移除所有冲突标记（`<<<<<<<`、`=======`、`>>>>>>>`）
- 保留正确的一侧代码
- 使用 Write 工具写入解决后的完整文件

**需要用户介入（有逻辑冲突时）：**
- 展示两侧代码差异
- 给出合并建议
- 等用户确认后再修改

### Step 6: 验证与收尾

```bash
# 提示用户 git add 标记冲突已解决
git add <resolved-file>

# 检查是否还有未解决的冲突
git status --short | grep "^UU\|^AA\|^DD\|^AU\|^UA\|^DU\|^UD"
```

## 冲突原因分析报告模板

解决完冲突后，向用户输出结构化的原因分析：

```
## 冲突原因分析

**冲突文件：** <file-path>
**冲突双方：** <HEAD branch> vs <incoming branch>

### 时间线
| 时间 | 分支 | 提交 | 内容 |
|------|------|------|------|
| ... | ... | ... | ... |

### 根本原因
<一句话总结>

### 冲突点（共 N 处）
| # | 位置 | HEAD 侧 | Incoming 侧 | 有逻辑冲突 | 解决方式 |
|---|------|---------|-------------|-----------|---------|
| 1 | import 区域 | 无改动 | 新增 XxxImport | 否 | 接受 incoming |
| 2 | xxx 方法 | 基础版 | 增强版 | 否 | 接受 incoming |

### 解决结果
全部采用 incoming 侧代码 / 手动合并两侧逻辑
```

## 注意事项

- 解决冲突前**必须先完整读取冲突文件**，不能只看冲突标记附近
- 如果冲突文件较多，按文件逐个处理，每处理完一个向用户报告
- 对于不确定的逻辑冲突，**宁可多问用户，不要擅自决定**
- 解决后提醒用户 `git add`，但**不要自动 commit**
