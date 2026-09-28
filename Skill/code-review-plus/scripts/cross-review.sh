#!/bin/bash
# cross-review.sh — 多模型交叉审查 & 差异对比（并行版）
# 用法: ./cross-review.sh <代码文件路径> [代码文件2] ...
# 兼容 macOS bash 3.x

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
R='\033[0;31m' G='\033[0;32m' B='\033[0;34m' Y='\033[1;33m' C='\033[0;36m' NC='\033[0m'

# ─── 超时函数（兼容 macOS 无 timeout 命令）───
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

if [ -z "$1" ]; then
  echo -e "${R}用法: ./cross-review.sh <代码文件路径> [代码文件2] ...${NC}"
  echo "   示例: ./cross-review.sh src/utils/auth.ts"
  exit 1
fi

CODE_FILES=("$@")
for f in "${CODE_FILES[@]}"; do
  [ ! -f "$f" ] && { echo -e "${R}文件不存在: $f${NC}"; exit 1; }
done

OUTPUT_DIR="/tmp/code-review-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUTPUT_DIR"

# ─── 工具标签（兼容 bash 3.x）───
LABEL_claude="Claude";   COLOR_claude="31"
LABEL_codex="Codex";     COLOR_codex="34"
get_label() { eval echo "\$LABEL_$1"; }
get_color() { eval echo "\$COLOR_$1"; }

# 检测可用工具（仅用于 claude 流程图生成）
FIRST_TOOL=""
for t in claude codex; do
  if [ "$t" = "claude" ] && [ "${CLAUDECODE:-0}" = "1" ]; then
    continue
  fi
  if command -v "$t" &>/dev/null; then
    [ -z "$FIRST_TOOL" ] && FIRST_TOOL="$t"
  fi
done

echo -e "${C}╔══════════════════════════════════════════════╗${NC}"
echo -e "${C}║   CodeReviewPlus 多模型交叉审查（并行版）    ║${NC}"
echo -e "${C}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${B}文件: ${NC}${CODE_FILES[*]}"
echo -e "${B}输出: ${NC}$OUTPUT_DIR"
echo ""

TIMEOUT=180

# ─── Step 1: 并行启动外部工具审查 ───
echo -e "${Y}[1/3] 并行启动外部工具审查...${NC}"
bash "$SCRIPT_DIR/review-runner.sh" "$OUTPUT_DIR" "${CODE_FILES[@]}" &
RUNNER_PID=$!
echo -e "${G}  外部工具后台启动 (PID=$RUNNER_PID)${NC}"
echo ""

# ─── Step 2: 同时用第一个工具生成流程图 ───
if [ -n "$FIRST_TOOL" ]; then
  echo -e "${Y}[2/3] 生成代码流程图 (${FIRST_TOOL})...${NC}"

  FLOW_PROMPT_FILE=$(mktemp)
  cat > "$FLOW_PROMPT_FILE" << 'PROMPT_EOF'
请为以下代码生成 Mermaid 流程图（flowchart TD），包含主要函数调用、条件分支、循环和数据流转。节点用中文，只输出 Mermaid 代码块。

代码内容：
PROMPT_EOF
  for f in "${CODE_FILES[@]}"; do
    echo "=== $(basename "$f") ===" >> "$FLOW_PROMPT_FILE"
    cat "$f" >> "$FLOW_PROMPT_FILE"
  done

  FLOW_PROMPT=$(cat "$FLOW_PROMPT_FILE")
  rm -f "$FLOW_PROMPT_FILE"

  case "$FIRST_TOOL" in
    claude)   run_with_timeout "$TIMEOUT" claude --print "$FLOW_PROMPT" > "$OUTPUT_DIR/flowchart-raw.md" 2>/dev/null ;;
    codex)    run_with_timeout "$TIMEOUT" codex exec --skip-git-repo-check "$FLOW_PROMPT" > "$OUTPUT_DIR/flowchart-raw.md" 2>/dev/null || \
              run_with_timeout "$TIMEOUT" codex -q --skip-git-repo-check "$FLOW_PROMPT" > "$OUTPUT_DIR/flowchart-raw.md" 2>/dev/null ;;
  esac

  sed -n '/```mermaid/,/```/p' "$OUTPUT_DIR/flowchart-raw.md" | sed '1d;$d' > "$OUTPUT_DIR/flowchart.mmd" 2>/dev/null || true
  [ ! -s "$OUTPUT_DIR/flowchart.mmd" ] && cp "$OUTPUT_DIR/flowchart-raw.md" "$OUTPUT_DIR/flowchart.mmd" 2>/dev/null || true

  echo -e "${G}  流程图已生成${NC}"
  echo ""
  echo -e "${C}═══ 代码流程图 ═══════════════════════${NC}"
  cat "$OUTPUT_DIR/flowchart.mmd" 2>/dev/null
  echo ""
  echo -e "${C}═══════════════════════════════════════${NC}"
  echo ""
fi

# ─── Step 3: 等待外部工具完成 + 汇总 ───
echo -e "${Y}[3/3] 等待外部工具完成...${NC}"
wait "$RUNNER_PID" 2>/dev/null || true

# 读取可用工具列表
TOOLS=()
if [ -f "$OUTPUT_DIR/.tools" ]; then
  while IFS= read -r line; do
    [ -n "$line" ] && TOOLS+=("$line")
  done < "$OUTPUT_DIR/.tools"
fi

echo -e "${G}  外部工具全部完成 (${#TOOLS[@]} 个)${NC}"
for t in "${TOOLS[@]}"; do
  if [ -s "$OUTPUT_DIR/${t}-review.md" ]; then
    SIZE=$(wc -c < "$OUTPUT_DIR/${t}-review.md")
    echo -e "  $(get_label "$t"): ${SIZE} bytes"
  fi
done
echo ""

# ─── 差异对比（用第一个工具生成）───
if [ ${#TOOLS[@]} -ge 2 ] && [ -n "$FIRST_TOOL" ]; then
  echo -e "${Y}生成差异对比...${NC}"

  DIFF_PROMPT_FILE=$(mktemp)
  cat > "$DIFF_PROMPT_FILE" << PROMPT_HEADER
以下是 ${#TOOLS[@]} 份代码审查报告，请对比分析。
PROMPT_HEADER

  for t in "${TOOLS[@]}"; do
    echo "--- $(get_label "$t") 审查报告 ---" >> "$DIFF_PROMPT_FILE"
    cat "$OUTPUT_DIR/${t}-review.md" >> "$DIFF_PROMPT_FILE"
    echo "" >> "$DIFF_PROMPT_FILE"
  done

  cat >> "$DIFF_PROMPT_FILE" << 'PROMPT_FOOTER'

请对比所有审查报告，输出：
## 共性问题（多个工具都提到的，可信度最高）
## 差异性问题（仅某工具发现的）
## 综合修复建议（按优先级排序）
PROMPT_FOOTER

  DIFF_PROMPT=$(cat "$DIFF_PROMPT_FILE")
  rm -f "$DIFF_PROMPT_FILE"

  case "$FIRST_TOOL" in
    claude)   run_with_timeout "$TIMEOUT" claude --print "$DIFF_PROMPT" > "$OUTPUT_DIR/diff-report.md" 2>/dev/null ;;
    codex)    run_with_timeout "$TIMEOUT" codex exec --skip-git-repo-check "$DIFF_PROMPT" > "$OUTPUT_DIR/diff-report.md" 2>/dev/null || \
              run_with_timeout "$TIMEOUT" codex -q --skip-git-repo-check "$DIFF_PROMPT" > "$OUTPUT_DIR/diff-report.md" 2>/dev/null ;;
  esac
elif [ ${#TOOLS[@]} -eq 1 ]; then
  cp "$OUTPUT_DIR/${TOOLS[0]}-review.md" "$OUTPUT_DIR/diff-report.md"
fi

# ─── 生成 HTML 报告 ───
cat > "$OUTPUT_DIR/report.html" << 'HTMLEOF'
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CodeReviewPlus 报告</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9;padding:20px;line-height:1.6}
  .container{max-width:1200px;margin:0 auto}
  h1{color:#58a6ff;margin-bottom:8px;font-size:26px}
  h2{color:#79c0ff;margin:32px 0 16px;font-size:20px;border-bottom:1px solid #21262d;padding-bottom:8px}
  .meta{color:#8b949e;margin-bottom:24px;font-size:14px}
  .mermaid{background:#161b22;border-radius:8px;padding:20px;margin:16px 0;overflow-x:auto}
  .tab-bar{display:flex;gap:4px;margin-top:24px;border-bottom:2px solid #21262d}
  .tab{padding:10px 20px;cursor:pointer;color:#8b949e;border-radius:8px 8px 0 0;background:#161b22;border:1px solid #21262d;border-bottom:none;font-size:14px;transition:all .2s}
  .tab:hover{color:#c9d1d9}
  .tab.active{color:#58a6ff;background:#0d1117;border-color:#58a6ff}
  .tab-content{display:none;background:#161b22;border-radius:0 0 8px 8px;padding:24px;border:1px solid #21262d;border-top:none}
  .tab-content.active{display:block}
  .review-content{white-space:pre-wrap;line-height:1.7;font-size:14px}
</style>
</head>
<body>
<div class="container">
  <h1>CodeReviewPlus</h1>
  <div class="meta" id="meta"></div>
  <h2>代码流程图</h2>
  <div class="mermaid" id="flowchart"></div>
  <div class="tab-bar" id="tab-bar"></div>
  <div id="tab-contents"></div>
<script>
mermaid.initialize({theme:'dark',startOnLoad:true});
function switchTab(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('tab-'+name).classList.add('active');
}
</script>
</div>
</body>
</html>
HTMLEOF

# 用 sed 注入实际数据
TOOLS_STR="${TOOLS[*]}"
FILENAMES=""
for f in "${CODE_FILES[@]}"; do FILENAMES="$FILENAMES $(basename "$f")"; done

# 注入 meta
sed -i '' "s|<div class=\"meta\" id=\"meta\"></div>|<div class=\"meta\">${FILENAMES} | $(date '+%Y-%m-%d %H:%M') | ${TOOLS_STR}</div>|" "$OUTPUT_DIR/report.html"

# 注入流程图
if [ -s "$OUTPUT_DIR/flowchart.mmd" ]; then
  # 用 python 安全注入多行内容
  python3 -c "
import sys
flowchart = open('$OUTPUT_DIR/flowchart.mmd').read()
html = open('$OUTPUT_DIR/report.html').read()
html = html.replace('<div class=\"mermaid\" id=\"flowchart\"></div>', '<div class=\"mermaid\">' + flowchart + '</div>')
open('$OUTPUT_DIR/report.html', 'w').write(html)
"
fi

# 注入 tabs
TAB_BAR_HTML=""
TAB_CONTENT_HTML=""
for t in "${TOOLS[@]}"; do
  LABEL=$(get_label "$t")
  TAB_BAR_HTML="$TAB_BAR_HTML<div class=\"tab\" onclick=\"switchTab('$t')\">$LABEL</div>"
  CONTENT=$(cat "$OUTPUT_DIR/${t}-review.md" 2>/dev/null | sed 's/</\&lt;/g; s/>/\&gt;/g' | sed 's/$/\\n/' | tr -d '\n')
  TAB_CONTENT_HTML="$TAB_CONTENT_HTML<div class=\"tab-content\" id=\"tab-$t\"><div class=\"review-content\">$(cat "$OUTPUT_DIR/${t}-review.md" 2>/dev/null | sed 's/</\&lt;/g; s/>/\&gt;/g')</div></div>"
done
TAB_BAR_HTML="$TAB_BAR_HTML<div class=\"tab\" onclick=\"switchTab('diff')\">差异对比</div>"
DIFF_CONTENT=$(cat "$OUTPUT_DIR/diff-report.md" 2>/dev/null | sed 's/</\&lt;/g; s/>/\&gt;/g')
TAB_CONTENT_HTML="$TAB_CONTENT_HTML<div class=\"tab-content\" id=\"tab-diff\"><div class=\"review-content\">$DIFF_CONTENT</div></div>"

python3 -c "
html = open('$OUTPUT_DIR/report.html').read()
html = html.replace('<div class=\"tab-bar\" id=\"tab-bar\"></div>', '''<div class=\"tab-bar\">$TAB_BAR_HTML</div>''')
open('$OUTPUT_DIR/report.html', 'w').write(html)
"

python3 << PYEOF
tabs_html = open("$OUTPUT_DIR/report.html").read()
# Read tab contents from files
import os
contents = ""
tools = "$TOOLS_STR".split()
for t in tools:
    fpath = "$OUTPUT_DIR/" + t + "-review.md"
    if os.path.exists(fpath):
        data = open(fpath).read().replace("<", "&lt;").replace(">", "&gt;")
    else:
        data = t + " 无输出"
    label = {"codex":"Codex","claude":"Claude"}.get(t, t)
    contents += '<div class="tab-content" id="tab-' + t + '"><div class="review-content">' + data + '</div></div>\n'
# diff
diff_path = "$OUTPUT_DIR/diff-report.md"
if os.path.exists(diff_path):
    diff_data = open(diff_path).read().replace("<", "&lt;").replace(">", "&gt;")
else:
    diff_data = "无差异对比报告"
contents += '<div class="tab-content" id="tab-diff"><div class="review-content">' + diff_data + '</div></div>\n'
tabs_html = tabs_html.replace('<div id="tab-contents"></div>', contents)
# activate first tab
tabs_html = tabs_html.replace('class="tab" onclick', 'class="tab active" onclick', 1)
tabs_html = tabs_html.replace('class="tab-content" id', 'class="tab-content active" id', 1)
open("$OUTPUT_DIR/report.html", "w").write(tabs_html)
PYEOF

# ─── 输出结果 ───
echo ""
echo -e "${C}═══════════════════════════════════════════${NC}"
echo -e "${G}审查完成！${NC}"
echo ""
echo -e "${B}文件列表:${NC}"
[ -s "$OUTPUT_DIR/flowchart.mmd" ] && echo -e "  流程图:     $OUTPUT_DIR/flowchart.mmd"
for t in "${TOOLS[@]}"; do
  echo -e "  $(get_label "$t"): $OUTPUT_DIR/${t}-review.md"
done
[ -s "$OUTPUT_DIR/diff-report.md" ] && echo -e "  差异对比:   $OUTPUT_DIR/diff-report.md"
echo -e "  ${Y}可视化报告: $OUTPUT_DIR/report.html${NC}"
echo ""
[ -s "$OUTPUT_DIR/diff-report.md" ] && { echo -e "${C}═══ 差异对比 ══════════════════════════${NC}"; cat "$OUTPUT_DIR/diff-report.md"; echo ""; }
echo -e "${Y}打开报告: open $OUTPUT_DIR/report.html${NC}"
