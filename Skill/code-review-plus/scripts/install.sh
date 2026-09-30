#!/bin/bash
# install.sh — 一键安装 code-review-plus 为 Claude Code Skill
# 运行: bash scripts/install.sh
# 支持 macOS / Linux / Windows (Git Bash / WSL)

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SKILL_NAME="code-review-plus"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
SOURCE_DIR="$(dirname "$SCRIPT_DIR")"
TARGET_DIR="$HOME/.claude/skills/$SKILL_NAME"

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  CodeReviewPlus Skill Installer${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "${BLUE}Source:${NC} $SOURCE_DIR"
echo -e "${BLUE}Target:${NC} $TARGET_DIR"
echo ""

# ─── 检测 AI CLI 工具 ───
echo -e "${YELLOW}Detecting AI CLI tools...${NC}"

TOOL_LABELS_codex="Codex"
get_label() { eval echo "\$TOOL_LABELS_$1"; }

AVAILABLE=()
for cmd in codex; do
  label=$(get_label "$cmd")
  if command -v "$cmd" &> /dev/null; then
    ver=$($cmd --version 2>/dev/null | head -1 || echo "installed")
    echo -e "   ${GREEN}+ $label ($cmd) — $ver${NC}"
    AVAILABLE+=("$cmd")
  else
    echo -e "   ${RED}- $label ($cmd) — not found${NC}"
  fi
done

echo ""
if [ ${#AVAILABLE[@]} -eq 0 ]; then
  echo -e "${YELLOW}Warning: Codex CLI not detected.${NC}"
  echo -e "${YELLOW}The skill will still install, but code review requires Codex:${NC}"
  echo ""
  echo -e "  ${CYAN}npm install -g @openai/codex${NC}"
  echo ""
else
  echo -e "${GREEN}Found ${#AVAILABLE[@]} tool(s)${NC}"
fi
echo ""

# ─── 检查源文件 ───
if [ ! -f "$SOURCE_DIR/SKILL.md" ]; then
  echo -e "${RED}Error: SKILL.md not found in $SOURCE_DIR${NC}"
  echo -e "${RED}Please run this script from the extracted zip directory: bash scripts/install.sh${NC}"
  exit 1
fi

# ─── 安装到 ~/.claude/skills/ ───
echo -e "${YELLOW}Installing skill...${NC}"

# 如果已存在，备份
if [ -d "$TARGET_DIR" ]; then
  echo -e "${YELLOW}Existing installation found, updating...${NC}"
  rm -rf "$TARGET_DIR"
fi

mkdir -p "$TARGET_DIR/scripts"

# 复制 SKILL.md
cp "$SOURCE_DIR/SKILL.md" "$TARGET_DIR/"

# 复制脚本
for script in cross-review.sh review-runner.sh live-review.sh; do
  if [ -f "$SOURCE_DIR/scripts/$script" ]; then
    cp "$SOURCE_DIR/scripts/$script" "$TARGET_DIR/scripts/"
    chmod +x "$TARGET_DIR/scripts/$script"
  fi
done

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Installation complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Installed to:${NC} $TARGET_DIR"
echo ""
echo -e "Usage:"
echo -e "  1. Start a new Claude Code conversation (or restart current one)"
echo -e "  2. The skill will be auto-detected"
echo -e "  3. Say ${CYAN}\"code review\"${NC} or ${CYAN}\"/code-review-plus\"${NC} to invoke"
echo ""
