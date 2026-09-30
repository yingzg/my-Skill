---
name: install-skill
description: Skill-Hub skill 安装引导。指导用户将 skill-hub 仓库中的 skill 以软链接方式安装到各 AI 工具的 skills 目录。支持 Claude Code、OpenCode、Gemini CLI 三种工具。触发词：安装skill、install skill、怎么安装skill、软链接skill。
---

# Install Skill — 安装引导

将 skill-hub 中的 skill 软链接到各 AI 工具，使其能识别并调用。

## 执行前必须确认

触发此 skill 后，**先向用户确认以下两项**，再执行任何命令：

1. **skill 来源**：是 skill-hub 仓库内的 skill，还是其他路径？
   - skill-hub 内：`<skill-hub根目录>/skill/<skill-name>`（通过 `git remote -v` 或当前工作目录确认根目录）
   - 其他路径：请用户提供完整路径
2. **目标工具**：安装到哪个 AI 工具？（默认 Claude Code）

确认后，用 `ls` 验证源路径存在，再执行 `ln -s`。

## 各工具 Skills 目录

| 工具 | Skills 目录 |
|------|------------|
| Claude Code | `~/.claude/skills/` |
| OpenCode | `~/.opencode/skills/` |
| Gemini CLI | `~/.gemini/antigravity/skills/` |

## 安装单个 skill

```bash
SKILL_HUB=$(git -C . rev-parse --show-toplevel 2>/dev/null || echo "<skill-hub根目录>")
TARGET_DIR=~/.claude/skills   # 按目标工具替换

ln -s "$SKILL_HUB/skill/<skill-name>" "$TARGET_DIR/<skill-name>"
```

## 批量安装全部 skill

```bash
SKILL_HUB=$(git -C . rev-parse --show-toplevel)
TARGET_DIR=~/.claude/skills   # 按目标工具替换

for d in "$SKILL_HUB/skill/"/*/; do
  name=$(basename "$d")
  target="$TARGET_DIR/$name"
  if [ ! -e "$target" ]; then
    ln -s "$d" "$target"
    echo "✅ $name"
  else
    echo "⏭️  $name (已存在，跳过)"
  fi
done
```

## 验证安装

```bash
ls -la "$TARGET_DIR/<skill-name>"
# 应显示软链接箭头指向 skill-hub/skill/<skill-name>
```
