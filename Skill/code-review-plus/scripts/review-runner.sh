#!/bin/bash
# review-runner.sh — 并行调用外部 AI CLI 做代码审查
# 用法: review-runner.sh <输出目录> <代码文件1> [代码文件2] ...
# 功能: 预拼接 prompt，并行启动所有可用外部 CLI，结果写到输出目录
# 兼容 macOS bash 3.x

set -e

R='\033[0;31m' G='\033[0;32m' Y='\033[1;33m' C='\033[0;36m' NC='\033[0m'

# ─── 参数校验 ───
if [ $# -lt 2 ]; then
  echo -e "${R}用法: review-runner.sh <输出目录> <代码文件1> [代码文件2] ...${NC}"
  exit 1
fi

OUTPUT_DIR="$1"; shift
CODE_FILES=("$@")

mkdir -p "$OUTPUT_DIR"

# 清除旧标记
rm -f "$OUTPUT_DIR/.done" "$OUTPUT_DIR/.tools"

# ─── 检测可用工具 ───
TOOLS=()
for t in codex; do
  command -v "$t" &>/dev/null && TOOLS+=("$t")
done

if [ ${#TOOLS[@]} -eq 0 ]; then
  echo -e "${Y}没有检测到 Codex CLI (codex)${NC}"
  echo "" > "$OUTPUT_DIR/.tools"
  touch "$OUTPUT_DIR/.done"
  exit 0
fi

# 记录可用工具
printf '%s\n' "${TOOLS[@]}" > "$OUTPUT_DIR/.tools"
echo -e "${C}检测到外部工具: ${TOOLS[*]}${NC}"

# ─── 预拼接 prompt 到临时文件（避免 CLI 自己读文件的来回）───
PROMPT_FILE="$OUTPUT_DIR/.prompt.txt"
cat > "$PROMPT_FILE" << 'PROMPT_HEADER'
请审查以下代码，严格按照以下格式输出：

## 代码概述
简要描述代码的功能和结构（2-3句话）

## 问题清单
按严重程度排序（Critical > High > Medium > Low），每项包含：
- **[严重程度]** 问题描述
- 位置：文件名:行号
- 修复建议

## 优点
代码写得好的地方

## 改进建议
具体的重构或优化建议

代码内容：
PROMPT_HEADER

for f in "${CODE_FILES[@]}"; do
  if [ -f "$f" ]; then
    echo "" >> "$PROMPT_FILE"
    echo "=== $(basename "$f") ===" >> "$PROMPT_FILE"
    cat "$f" >> "$PROMPT_FILE"
  else
    echo -e "${R}文件不存在: $f${NC}" >&2
  fi
done

PROMPT_SIZE=$(wc -c < "$PROMPT_FILE")
echo -e "${C}Prompt 大小: ${PROMPT_SIZE} bytes${NC}"

# ─── 超时时长（秒）───
TIMEOUT=${REVIEW_TIMEOUT:-180}

# ─── 单工具调用函数 ───
run_single_tool() {
  local tool="$1"
  local prompt_file="$2"
  local output_file="$3"
  local timeout_sec="$4"

  local prompt
  prompt=$(cat "$prompt_file")

  # 带超时执行（兼容 macOS 无 timeout 命令）
  (
    case "$tool" in
      codex)
        # 优先用 codex exec 非交互模式（需要 --skip-git-repo-check 避免非 git 目录报错）
        codex exec --skip-git-repo-check "$prompt" 2>/dev/null || codex -q --skip-git-repo-check "$prompt" 2>/dev/null
        ;;
    esac
  ) > "$output_file" 2>/dev/null &
  local pid=$!

  # watchdog 超时杀
  ( sleep "$timeout_sec" && kill "$pid" 2>/dev/null ) &
  local watchdog=$!

  wait "$pid" 2>/dev/null
  local ret=$?
  kill "$watchdog" 2>/dev/null 2>&1
  wait "$watchdog" 2>/dev/null 2>&1

  if [ ! -s "$output_file" ]; then
    echo "[${tool}] 审查超时或失败 (timeout=${timeout_sec}s, exit=${ret})" > "$output_file"
  fi

  return $ret
}

# ─── 并行启动所有工具 ───
echo -e "${Y}并行启动 ${#TOOLS[@]} 个外部工具审查（限时 ${TIMEOUT}s 每个）...${NC}"

PIDS=()
for t in "${TOOLS[@]}"; do
  echo -e "${C}  启动 ${t}...${NC}"
  run_single_tool "$t" "$PROMPT_FILE" "$OUTPUT_DIR/${t}-review.md" "$TIMEOUT" &
  PIDS+=($!)
done

# ─── 等待全部完成 ───
FAILED=0
for i in "${!PIDS[@]}"; do
  wait "${PIDS[$i]}" 2>/dev/null || FAILED=$((FAILED + 1))
  t="${TOOLS[$i]}"
  if [ -s "$OUTPUT_DIR/${t}-review.md" ]; then
    SIZE=$(wc -c < "$OUTPUT_DIR/${t}-review.md")
    echo -e "${G}  ${t} 完成 (${SIZE} bytes)${NC}"
  else
    echo -e "${R}  ${t} 无输出${NC}"
  fi
done

# ─── 完成标记 ───
touch "$OUTPUT_DIR/.done"
echo -e "${G}全部外部审查完成 (${#TOOLS[@]} 个工具, ${FAILED} 个失败)${NC}"
