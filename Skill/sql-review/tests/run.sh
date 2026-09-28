#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

PASS=0
FAIL=0

compare_json() {
    jq --sort-keys 'if type == "array" then . else del(.generated_at, .run_id, .context.branch) end' "$1" > /tmp/jq_expected.json
    jq --sort-keys 'if type == "array" then . else del(.generated_at, .run_id, .context.branch) end' "$2" > /tmp/jq_actual.json
    diff -u /tmp/jq_expected.json /tmp/jq_actual.json
}

compare_json_fields() {
    local filter="$3"
    jq --sort-keys "$filter" "$1" > /tmp/jq_expected.json
    jq --sort-keys "$filter" "$2" > /tmp/jq_actual.json
    diff -u /tmp/jq_expected.json /tmp/jq_actual.json
}

run_test() {
    local name="$1"; local expected="$2"; local actual="$3"; local cmd="$4"
    echo -n "TEST: $name ... "
    if eval "$cmd" 2>/tmp/test_stderr.log > "$actual"; then
        if compare_json "$expected" "$actual"; then
            echo -e "${GREEN}PASS${NC}"; PASS=$((PASS + 1)); rm -f "$actual"
        else
            echo -e "${RED}FAIL${NC} (output differs)"; FAIL=$((FAIL + 1))
        fi
    else
        echo -e "${RED}FAIL${NC} (script error)"; FAIL=$((FAIL + 1)); cat /tmp/test_stderr.log
    fi
}

run_test_subset() {
    local name="$1"; local expected="$2"; local actual="$3"; local cmd="$4"; local filter="$5"
    echo -n "TEST: $name ... "
    if eval "$cmd" 2>/tmp/test_stderr.log > "$actual"; then
        if compare_json_fields "$expected" "$actual" "$filter"; then
            echo -e "${GREEN}PASS${NC}"; PASS=$((PASS + 1)); rm -f "$actual"
        else
            echo -e "${RED}FAIL${NC} (output differs)"; FAIL=$((FAIL + 1))
        fi
    else
        echo -e "${RED}FAIL${NC} (script error)"; FAIL=$((FAIL + 1)); cat /tmp/test_stderr.log
    fi
}

cd "$PROJECT_DIR"
TMP_ACTUAL=$(mktemp)
trap "rm -f $TMP_ACTUAL" EXIT

# Test 1: parse_mapper.py
run_test "parse_mapper" \
    "$SCRIPT_DIR/expected/parse-output.json" \
    "$TMP_ACTUAL" \
    "python3 scripts/parse_mapper.py --file tests/fixtures/mappers.xml 2>/dev/null"

# Test 2: match_rules.py
run_test "match_rules" \
    "$SCRIPT_DIR/expected/rules-output.json" \
    "$TMP_ACTUAL" \
    "python3 scripts/match_rules.py --input '$SCRIPT_DIR/expected/parse-output.json' 2>/dev/null"

# Test 3: discover_datasource.py
run_test "discover_datasource" \
    "$SCRIPT_DIR/expected/discover-output.json" \
    "$TMP_ACTUAL" \
    "python3 scripts/discover_datasource.py --project-root tests/fixtures 2>/dev/null"

# Test 4: extract_changes.py (git repo required — compare only files+count)
GIT_REPO="/tmp/git-test-repo"
if [ ! -d "$GIT_REPO/.git" ]; then
    rm -rf "$GIT_REPO" && mkdir -p "$GIT_REPO"
    git init "$GIT_REPO" --quiet
    git -C "$GIT_REPO" config user.email "test@test"
    git -C "$GIT_REPO" config user.name "test"
    mkdir -p "$GIT_REPO/src/main/java/com/example/mapper"
    mkdir -p "$GIT_REPO/src/main/java/com/example/dao"
    echo "base" > "$GIT_REPO/base.txt"
    git -C "$GIT_REPO" add . && git -C "$GIT_REPO" commit -m "initial" --quiet
    git -C "$GIT_REPO" branch base-branch
    echo "<!-- Order -->" > "$GIT_REPO/src/main/java/com/example/mapper/OrderMapper.xml"
    echo "<!-- User -->" > "$GIT_REPO/src/main/java/com/example/mapper/UserMapper.xml"
    echo "<!-- NotXml -->" > "$GIT_REPO/src/main/java/com/example/dao/NotMapped.xml"
    git -C "$GIT_REPO" add . && git -C "$GIT_REPO" commit -m "add mappers" --quiet
    echo "<!-- changed -->" >> "$GIT_REPO/src/main/java/com/example/mapper/OrderMapper.xml"
    git -C "$GIT_REPO" add . && git -C "$GIT_REPO" commit -m "update" --quiet
fi

run_test_subset "extract_changes" \
    "$SCRIPT_DIR/expected/extract-output.json" \
    "$TMP_ACTUAL" \
    "python3 scripts/extract_changes.py --base base-branch --repo '$GIT_REPO' 2>/dev/null" \
    '{files, total_count}'

# Test 5: trace_callchain.py
run_test "trace_callchain" \
    "$SCRIPT_DIR/expected/trace-output.json" \
    "$TMP_ACTUAL" \
    "python3 scripts/trace_callchain.py --methods '[\"com.example.mapper.OrderMapper.findById\",\"com.example.mapper.OrderMapper.findByOrderNo\",\"com.example.mapper.OrderMapper.updateStatus\",\"com.example.mapper.OrderMapper.findByCondition\"]' --project-root tests/fixtures --project-src java 2>/dev/null"

# Test 6: resolve_dynamic_sql.py (NDJSON)
echo -n "TEST: resolve_dynamic_sql ... "
if python3 scripts/parse_mapper.py --file tests/fixtures/mappers.xml 2>/dev/null | \
   python3 scripts/resolve_dynamic_sql.py 2>/dev/null | \
   jq -s 'sort_by(.sql_id)' > "$TMP_ACTUAL" 2>/dev/null; then
    jq -s 'sort_by(.sql_id)' "$SCRIPT_DIR/expected/resolve-output.jsonl" > /tmp/jq_expected.json
    if diff -u /tmp/jq_expected.json "$TMP_ACTUAL"; then
        echo -e "${GREEN}PASS${NC}"; PASS=$((PASS + 1)); rm -f "$TMP_ACTUAL"
    else
        echo -e "${RED}FAIL${NC} (output differs)"; FAIL=$((FAIL + 1))
    fi
else
    echo -e "${RED}FAIL${NC} (script error)"; FAIL=$((FAIL + 1))
fi

# Test 7: extract_tables.py (NDJSON)
echo -n "TEST: extract_tables ... "
if cat "$SCRIPT_DIR/expected/resolve-output.jsonl" | \
   python3 scripts/extract_tables.py 2>/dev/null | \
   jq -s 'sort_by(.sql_id)' > "$TMP_ACTUAL" 2>/dev/null; then
    jq -s 'sort_by(.sql_id)' "$SCRIPT_DIR/expected/tables-output.jsonl" > /tmp/jq_expected.json
    if diff -u /tmp/jq_expected.json "$TMP_ACTUAL"; then
        echo -e "${GREEN}PASS${NC}"; PASS=$((PASS + 1)); rm -f "$TMP_ACTUAL"
    else
        echo -e "${RED}FAIL${NC} (output differs)"; FAIL=$((FAIL + 1))
    fi
else
    echo -e "${RED}FAIL${NC} (script error)"; FAIL=$((FAIL + 1))
fi

# Test 8: dml_to_select_proxy.py (NDJSON)
echo -n "TEST: dml_to_select_proxy ... "
if cat "$SCRIPT_DIR/expected/resolve-output.jsonl" | \
   python3 scripts/dml_to_select_proxy.py 2>/dev/null | \
   jq -s 'sort_by(.sql_id)' > "$TMP_ACTUAL" 2>/dev/null; then
    jq -s 'sort_by(.sql_id)' "$SCRIPT_DIR/expected/proxy-output.jsonl" > /tmp/jq_expected.json
    if diff -u /tmp/jq_expected.json "$TMP_ACTUAL"; then
        echo -e "${GREEN}PASS${NC}"; PASS=$((PASS + 1)); rm -f "$TMP_ACTUAL"
    else
        echo -e "${RED}FAIL${NC} (output differs)"; FAIL=$((FAIL + 1))
    fi
else
    echo -e "${RED}FAIL${NC} (script error)"; FAIL=$((FAIL + 1))
fi

# Test 9: execute_explain.py (dry-run, single JSON)
run_test "execute_explain" \
    "$SCRIPT_DIR/expected/explain-output.json" \
    "$TMP_ACTUAL" \
    "cat $SCRIPT_DIR/expected/proxy-output.jsonl | python3 scripts/execute_explain.py --dry-run 2>/dev/null > $TMP_ACTUAL"

# Test 10: build_report.py (aggregates rules + explain + risk → gate)
run_test "build_report" \
    "$SCRIPT_DIR/expected/report-output.json" \
    "$TMP_ACTUAL" \
    "python3 scripts/build_report.py --run-id golden --rules-file tests/expected/rules-output.json --explain-file tests/expected/explain-output.json --risk-file tests/fixtures/mock-risk.json --base-branch origin/master --mode local 2>/dev/null > $TMP_ACTUAL"

# Test 10b: build_report.py output must satisfy final report schema fields
echo -n "TEST: build_report schema ... "
if python3 scripts/build_report.py --run-id golden --rules-file tests/expected/rules-output.json --explain-file tests/expected/explain-output.json --risk-file tests/fixtures/mock-risk.json --base-branch origin/master --mode local 2>/dev/null > "$TMP_ACTUAL"; then
    if jq -e '
      .report_id and
      .context and
      .context.mode == "local" and
      .gate.conclusion and
      (.gate.statistics.total | type == "number") and
      (.review_checklist | type == "array") and
      (.degradation_notes | type == "array") and
      ([.findings[].risk_level] | all(. != "UNCERTAIN"))
    ' "$TMP_ACTUAL" >/dev/null; then
        echo -e "${GREEN}PASS${NC}"; PASS=$((PASS + 1)); rm -f "$TMP_ACTUAL"
    else
        echo -e "${RED}FAIL${NC} (schema mismatch)"; FAIL=$((FAIL + 1))
    fi
else
    echo -e "${RED}FAIL${NC} (script error)"; FAIL=$((FAIL + 1)); cat /tmp/test_stderr.log
fi

# Test 10c: run_review.py end-to-end dry run using demo-scheme-style Mapper XML fixture
echo -n "TEST: run_review dry-run e2e ... "
E2E_WORK_DIR="/tmp/sql-review-e2e-test"
rm -rf "$E2E_WORK_DIR"
if python3 scripts/run_review.py \
    --files "[\"$SCRIPT_DIR/fixtures/e2e/DemoCommonMapper.xml\"]" \
    --project-root "$SCRIPT_DIR/fixtures/e2e" \
    --project-src java \
    --base-branch origin/master \
    --run-id e2e \
    --work-dir "$E2E_WORK_DIR" \
    --dry-run \
    --output "$TMP_ACTUAL" 2>/tmp/test_stderr.log; then
    if jq -e '
      .report_id == "sql-review-e2e" and
      .context.total_sql_count == 3 and
      .gate.conclusion and
      (.findings | length == 3) and
      (.findings[] | select(.mapper_method == "selectByCnId") | .call_chain | length) == 2 and
      (.findings[] | select(.mapper_method == "selectByCnId") | .call_chain_broken) == false and
      (.review_checklist | type == "array") and
      (.artifacts.rules_file | test("phase4a_rules.json$")) and
      (.artifacts.explain_file | test("phase4b_explain.json$"))
    ' "$TMP_ACTUAL" >/dev/null; then
        echo -e "${GREEN}PASS${NC}"; PASS=$((PASS + 1)); rm -f "$TMP_ACTUAL"
    else
        echo -e "${RED}FAIL${NC} (output differs)"; FAIL=$((FAIL + 1))
    fi
else
    echo -e "${RED}FAIL${NC} (script error)"; FAIL=$((FAIL + 1)); cat /tmp/test_stderr.log
fi

# Test 11: resolve_dynamic_sql --mode resolve (NDJSON with needs_llm + unresolved_tags)
echo -n "TEST: resolve_dynamic_sql (resolve mode) ... "
if python3 scripts/parse_mapper.py --file tests/fixtures/mappers.xml 2>/dev/null | \
   python3 scripts/resolve_dynamic_sql.py --mode resolve 2>/dev/null | \
   jq -s 'sort_by(.sql_id)' > "$TMP_ACTUAL" 2>/dev/null; then
    jq -s 'sort_by(.sql_id)' "$SCRIPT_DIR/expected/resolve-mode-output.jsonl" > /tmp/jq_expected.json
    if diff -u /tmp/jq_expected.json "$TMP_ACTUAL"; then
        echo -e "${GREEN}PASS${NC}"; PASS=$((PASS + 1)); rm -f "$TMP_ACTUAL"
    else
        echo -e "${RED}FAIL${NC} (output differs)"; FAIL=$((FAIL + 1))
    fi
else
    echo -e "${RED}FAIL${NC} (script error)"; FAIL=$((FAIL + 1))
fi

# Test 12: resolve_dynamic_sql --mode resolve --skip-finalize (NDJSON with raw tags)
echo -n "TEST: resolve_dynamic_sql (resolve --skip-finalize) ... "
if python3 scripts/parse_mapper.py --file tests/fixtures/mappers.xml 2>/dev/null | \
   python3 scripts/resolve_dynamic_sql.py --mode resolve --skip-finalize 2>/dev/null | \
   jq -s 'sort_by(.sql_id)' > "$TMP_ACTUAL" 2>/dev/null; then
    jq -s 'sort_by(.sql_id)' "$SCRIPT_DIR/expected/resolve-skip-finalize-output.jsonl" > /tmp/jq_expected.json
    if diff -u /tmp/jq_expected.json "$TMP_ACTUAL"; then
        echo -e "${GREEN}PASS${NC}"; PASS=$((PASS + 1)); rm -f "$TMP_ACTUAL"
    else
        echo -e "${RED}FAIL${NC} (output differs)"; FAIL=$((FAIL + 1))
    fi
else
    echo -e "${RED}FAIL${NC} (script error)"; FAIL=$((FAIL + 1))
fi

# Test 13: discover_schema.py parse_create_table (DDL 类型白名单 + 复合主键)
echo -n "TEST: discover_schema parse_create_table ... "
if (cd "$PROJECT_DIR/scripts" && python3 - <<'PY' 2>/dev/null
import discover_schema
ddl = "CREATE TABLE t (`id` bigint NOT NULL, `code` varchar(32), `status` enum('a','b'), `data` json, PRIMARY KEY (`id`), KEY `idx_code` (`code`))"
s = discover_schema.parse_create_table(ddl)
assert s["columns"]["id"] == "bigint"
assert s["columns"]["code"] == "varchar"
assert s["columns"]["status"] == "enum"
assert s["columns"]["data"] == "json"
assert s["primary_key"] == "id"
assert s["primary_keys"] == ["id"]
assert s["indexes"]["idx_code"] == ["code"]
ddl2 = "CREATE TABLE t2 (`a` int, `b` int, PRIMARY KEY (`a`, `b`))"
s2 = discover_schema.parse_create_table(ddl2)
assert s2["primary_key"] == "a"
assert s2["primary_keys"] == ["a", "b"]
print("OK")
PY
); then
    echo -e "${GREEN}PASS${NC}"; PASS=$((PASS + 1))
else
    echo -e "${RED}FAIL${NC}"; FAIL=$((FAIL + 1))
fi

# Test 14: match_rules.py schema 感知（主键豁免 + 隐式转换 + 跨表回归）
echo -n "TEST: match_rules schema-aware ... "
if (cd "$PROJECT_DIR/scripts" && python3 - <<'PY' 2>/dev/null
import match_rules
schemas = {
    "orders": {"columns": {"id": "bigint", "user_id": "bigint", "code": "varchar", "del_flag": "tinyint"}, "primary_key": "id", "indexes": {}},
    "users": {"columns": {"user_id": "bigint", "name": "varchar"}, "primary_key": "user_id", "indexes": {}},
}
assert match_rules._is_pk_eq_query("SELECT * FROM orders WHERE id = ?", "orders", schemas) is True
assert match_rules._is_pk_eq_query("SELECT * FROM orders WHERE user_id = ?", "orders", schemas) is False
assert match_rules._check_string_column_eq_number("SELECT * FROM orders WHERE code = 123", "orders", schemas) is True
assert match_rules._check_string_column_eq_number("SELECT * FROM orders WHERE del_flag = 0", "orders", schemas) is False
r101 = {"id": "R101", "match": {"method": "schema_soft_delete_guard", "pattern": "(?i)(status_code|is_deleted|statecode|del_flag|deleted|is_del|delete_flag)"}, "risk_level": "HIGH"}
assert match_rules.match_rule("UPDATE orders SET status = ? WHERE id = ?", r101, "UPDATE", "orders", schemas) == (True, "HIGH")
assert match_rules.match_rule("UPDATE orders SET status = ? WHERE id = ? AND del_flag = 0", r101, "UPDATE", "orders", schemas) == (False, "NONE")
assert match_rules.match_rule("UPDATE users SET name = ? WHERE user_id = ?", r101, "UPDATE", "users", schemas) == (False, "NONE")
assert match_rules.match_rule("UPDATE t SET x = ? WHERE id = ?", r101, "UPDATE", "UNKNOWN", schemas) == (False, "NONE")
print("OK")
PY
); then
    echo -e "${GREEN}PASS${NC}"; PASS=$((PASS + 1))
else
    echo -e "${RED}FAIL${NC}"; FAIL=$((FAIL + 1))
fi

# Test 15: parse_mapper.py 负向用例（broken XML 跳过 + --parse-errors-output 落盘带 raw_fragment）
echo -n "TEST: parse_mapper negative (broken XML recorded) ... "
BROKEN_XML=$(mktemp --suffix=.xml)
BROKEN_ERR=$(mktemp)
cat > "$BROKEN_XML" <<'EOF'
<mapper namespace="com.example.BrokenMapper">
    <select id="broken" resultType="map">
        SELECT * FROM t WHERE amount < 100
    </select>
</mapper>
EOF
python3 scripts/parse_mapper.py \
    --files "[\"$BROKEN_XML\", \"tests/fixtures/mappers.xml\"]" \
    --parse-errors-output "$BROKEN_ERR" 2>/dev/null > "$TMP_ACTUAL"
if jq -e 'length == 34' "$TMP_ACTUAL" >/dev/null 2>&1; then
    if jq -e 'length == 1 and .[0].file and .[0].error and (.[0].raw_fragment | length > 0)' "$BROKEN_ERR" >/dev/null 2>&1; then
        echo -e "${GREEN}PASS${NC}"; PASS=$((PASS + 1)); rm -f "$TMP_ACTUAL"
    else
        echo -e "${RED}FAIL${NC} (parse-errors-output missing raw_fragment)"; FAIL=$((FAIL + 1))
    fi
else
    echo -e "${RED}FAIL${NC} (expected 34 parsed statements)"; FAIL=$((FAIL + 1))
fi
rm -f "$BROKEN_XML" "$BROKEN_ERR"

echo ""
if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}All $PASS tests PASSED${NC}"
else
    echo -e "${RED}$FAIL/$((PASS+FAIL)) tests FAILED${NC}"
fi
exit $FAIL
