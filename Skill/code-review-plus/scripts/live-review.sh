#!/bin/bash
# live-review.sh — 实时并排查看多模型审查
# 用法: ./live-review.sh <代码文件路径>
# 兼容 macOS bash 3.x

set -e

R='\033[0;31m' G='\033[0;32m' C='\033[0;36m' Y='\033[1;33m' B='\033[0;34m' NC='\033[0m'

[ -z "$1" ] && { echo -e "${R}❌ 用法: ./live-review.sh <代码文件路径>${NC}"; exit 1; }
CODE_FILE="$1"
[ ! -f "$CODE_FILE" ] && { echo -e "${R}❌ 文件不存在: $CODE_FILE${NC}"; exit 1; }

OUTPUT_DIR="/tmp/code-review-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUTPUT_DIR"

# ─── 兼容 bash 3.x（不使用 declare -A）───
LABEL_claude="Claude";     COLOR_claude="31"
LABEL_codex="Codex";       COLOR_codex="34"

get_label() { eval echo "\$LABEL_$1"; }
get_color() { eval echo "\$COLOR_$1"; }

# ─── 超时时长（秒）───
TIMEOUT=180

TOOLS=()
for t in claude codex; do
  # 跳过嵌套 Claude 调用
  if [ "$t" = "claude" ] && [ "${CLAUDECODE:-0}" = "1" ]; then
    echo -e "${Y}⚠️  检测到 Claude Code 会话，跳过嵌套 claude 调用${NC}"
    continue
  fi
  command -v "$t" &>/dev/null && TOOLS+=("$t")
done

[ ${#TOOLS[@]} -eq 0 ] && { echo -e "${R}❌ 没有可用的 AI CLI${NC}"; exit 1; }

echo -e "${C}╔══════════════════════════════════════════╗${NC}"
echo -e "${C}║    ⚡ CodeReviewPlus 实时并排审查        ║${NC}"
echo -e "${C}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "📄 $CODE_FILE | 🛠️ ${TOOLS[*]}"
echo ""

# ─── Step 1: 先生成流程图 ───
FIRST_TOOL="${TOOLS[0]}"

echo -e "${Y}📊 生成代码流程图...${NC}"
echo ""

FLOW_PROMPT_FILE=$(mktemp)
cat > "$FLOW_PROMPT_FILE" << 'PROMPT_EOF'
请为以下代码生成 Mermaid 流程图（flowchart TD），包含主要函数调用、条件分支、循环和数据流转。节点用中文，只输出 Mermaid 代码块。

代码内容：
PROMPT_EOF
cat "$CODE_FILE" >> "$FLOW_PROMPT_FILE"

FLOWCHART_FILE="$OUTPUT_DIR/flowchart.mmd"
FLOW_PROMPT=$(cat "$FLOW_PROMPT_FILE")

# 超时函数
run_with_timeout() {
  local secs="$1"; shift
  "$@" &
  local pid=$!
  ( sleep "$secs" && kill "$pid" 2>/dev/null ) &
  local watchdog=$!
  wait "$pid" 2>/dev/null
  local ret=$?
  kill "$watchdog" 2>/dev/null 2>&1
  wait "$watchdog" 2>/dev/null 2>&1
  return $ret
}

case "$FIRST_TOOL" in
  claude)   run_with_timeout "$TIMEOUT" claude --print "$FLOW_PROMPT" > "$OUTPUT_DIR/flowchart-raw.md" 2>/dev/null ;;
  codex)    run_with_timeout "$TIMEOUT" codex exec --skip-git-repo-check "$FLOW_PROMPT" > "$OUTPUT_DIR/flowchart-raw.md" 2>/dev/null || \
            run_with_timeout "$TIMEOUT" codex -q --skip-git-repo-check "$FLOW_PROMPT" > "$OUTPUT_DIR/flowchart-raw.md" 2>/dev/null ;;
esac
rm -f "$FLOW_PROMPT_FILE"

sed -n '/```mermaid/,/```/p' "$OUTPUT_DIR/flowchart-raw.md" | sed '1d;$d' > "$FLOWCHART_FILE" 2>/dev/null || true
[ ! -s "$FLOWCHART_FILE" ] && cp "$OUTPUT_DIR/flowchart-raw.md" "$FLOWCHART_FILE"

echo -e "${C}═══ 📊 代码流程图 ═══════════════════════${NC}"
cat "$FLOWCHART_FILE"
echo ""
echo -e "${C}═══════════════════════════════════════════${NC}"
echo -e "${Y}💡 粘贴到 https://mermaid.live 可视化查看${NC}"
echo ""

# ─── Step 2: 实时并排审查 ───
echo -e "${Y}🔍 启动多模型实时审查（每个限时 ${TIMEOUT}s）...${NC}"
echo ""

FLOWCHART_CONTEXT=""
if [ -s "$FLOWCHART_FILE" ]; then
  FLOWCHART_CONTEXT="代码流程图：
\`\`\`mermaid
$(cat "$FLOWCHART_FILE")
\`\`\`

基于以上流程图理解，请审查以下代码，指出问题、风险和改进建议，并标注问题对应流程图中的哪个环节。

"
fi

# 构造审查 prompt 到临时文件
REVIEW_PROMPT_FILE=$(mktemp)
cat > "$REVIEW_PROMPT_FILE" << PROMPT_EOF
${FLOWCHART_CONTEXT}代码内容：
$(cat "$CODE_FILE")
PROMPT_EOF
REVIEW_PROMPT=$(cat "$REVIEW_PROMPT_FILE")
rm -f "$REVIEW_PROMPT_FILE"

cleanup() { kill $(jobs -p) 2>/dev/null || true; wait 2>/dev/null; }
trap cleanup EXIT

for t in "${TOOLS[@]}"; do
  (
    OUTPUT_FILE="$OUTPUT_DIR/${t}-review.md"
    COLOR_CODE=$(get_color "$t")
    TOOL_LABEL=$(get_label "$t")

    review_and_prefix() {
      case "$t" in
        claude)   claude --print "$REVIEW_PROMPT" 2>/dev/null ;;
        codex)    codex exec --skip-git-repo-check "$REVIEW_PROMPT" 2>/dev/null || codex -q --skip-git-repo-check "$REVIEW_PROMPT" 2>/dev/null ;;
      esac | tee "$OUTPUT_FILE" | while IFS= read -r line; do
        echo -e "\033[${COLOR_CODE}m[${TOOL_LABEL}]${NC} $line"
      done
    }

    # 带超时执行
    review_and_prefix &
    local_pid=$!
    ( sleep "$TIMEOUT" && kill "$local_pid" 2>/dev/null && echo -e "\033[${COLOR_CODE}m[${TOOL_LABEL}]${NC} ⚠️ 超时 (${TIMEOUT}s)" ) &
    local_watchdog=$!
    wait "$local_pid" 2>/dev/null
    kill "$local_watchdog" 2>/dev/null 2>&1
    wait "$local_watchdog" 2>/dev/null 2>&1
  ) &
done

wait

echo ""
echo -e "${C}═══════════════════════════════════════════${NC}"
echo -e "${G}所有审查完成！${NC}"
echo ""
echo -e "${B}📄 报告: ${NC}$OUTPUT_DIR/"
echo -e "   流程图: $OUTPUT_DIR/flowchart.mmd"
for t in "${TOOLS[@]}"; do
  echo -e "   $(get_label "$t"): $OUTPUT_DIR/${t}-review.md"
done
