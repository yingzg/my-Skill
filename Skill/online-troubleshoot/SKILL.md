---
name: online-troubleshoot
description: Use when investigating online production incidents, customer tickets, data anomalies, API errors, failed pages, slow or broken business flows, or requests to analyze root cause with code, logs, SQL, database evidence, trace data, historical cases, restricted_info, fail-closed output, three-tier (P0/P1/P2) recommendations, and optional case write-back. Supports traceId-driven fast path for rapid log-based diagnosis.
---

# Online Troubleshoot

## Core Positioning

Use this Skill to investigate online production tickets with this operating model:

```text
选系统 -> 查经验库 -> 代码+数据双路验证 -> 按固定契约输出结论 -> 可选回写
```

This Skill is a troubleshooting contract, not a generic debugging chat. Its job is to prevent invented evidence, overconfident root causes, skipped verification, and unstable output.

## Non-Negotiable Principles

1. **Zero interruption first**: Do not ask field-by-field follow-up questions. The only blocking questions allowed are system selection and write-back confirmation.
2. **No Invention**: Never invent interface paths, table names, SQL results, file paths, line numbers, historical cases, logs, business facts, owners, or root causes.
3. **Fail-Closed**: Missing critical evidence must degrade the result to `partial_success` or `failed`.
4. **Evidence closure**: A root cause claim must trace back to code, log, SQL, database result, user input, or historical case evidence.
5. **Golden Cases are tests**: `golden-cases/` validates this Skill's behavior. It is not the production case library and must not be searched as `CASES_DIR`.

## Resource Loading

- Read `references/log-patterns.md` when user input contains logs or stack traces.
- Read `references/trace-diagnosis.md` when user input contains a traceId or the trace-driven fast path is triggered in step 2.
- Read `references/troubleshoot-examples.md` when behavior is ambiguous or examples help calibrate output.
- Read `templates/output.md` when producing brief, detailed, or write-back output.
- Read `golden-cases/README.md` only when validating or changing this Skill.

## Allowed Blocking Questions

Ask at most one blocking question only in these cases:

- **System selection**: multiple systems are plausible and choosing the wrong system would make code or data access unsafe.
- **Write-back confirmation**: step 7 wants to write or update a case record.

For all other missing information, continue with best-effort investigation, record the gap in `restricted_info`, and let the gap affect final `status`.

## Seven-Step Pipeline

Run the steps in order unless the step 1 high-confidence jump path applies.

### Step 1: Historical Case Precheck

Search the local production case library, not `golden-cases/`.

Default case path pattern:

```text
CASES_DIR/CASE-xxx.md
```

If `CASES_DIR` is unknown, search the current repo or workspace for plausible case directories. If no case library is found, record `经验库路径未知或未找到` in `restricted_info` and continue to step 2.

Run two retrieval rounds:

1. **Exact retrieval**: system name, interface path, error code, exception class, page/module name, business ID type.
2. **Fuzzy retrieval**: business symptom, error text, module semantics, similar root cause.

Classify confidence:

| Confidence | Criteria | Behavior |
| --- | --- | --- |
| High | system and symptom match, plus at least two key evidence points match | Jump over steps 2-4, run step 5 minimal verification, then step 6 |
| Medium | partial symptom or mechanism match, but fewer than two key evidence points | Treat as hypothesis only; continue normal flow |
| Miss | no useful case | Continue normal flow |

High-confidence historical case reuse cannot produce `success` by itself. Step 5 minimal verification is mandatory.

Step 1 output:

- matched cases and confidence;
- retrieval queries used;
- jump-path decision;
- `restricted_info` for missing case library or low confidence.

Checkpoint after step 1.

### Step 2: Context Extraction

**Trace-Driven Fast Path** — Triggered when user input contains a traceId or equivalent Trace identifier.

Detection signals:
- Explicit traceId string (UUID/snowflake format).
- Keywords: `trace` / `span` / `traceId` / `requestId` accompanied by an ID value.
- Links from Hera / Jaeger / Zipkin / SkyWalking.

When triggered, load `references/trace-diagnosis.md` and execute Phases A through C before falling through to the standard extraction logic.

**Phase A — Fetch Raw Trace and Log Data**

Use ITraceFetcher to obtain Trace and log data:

```ts
interface ITraceFetcher {
  getTrace(traceId: string, options?: { appName?: string; area?: string; env?: string }): Promise<TraceDetail | TraceError>
  getLogs(traceId: string, options?: { level?: "ERROR"|"WARN"|"INFO"; keyword?: string; timeRange?: string; pageSize?: number; page?: number }): Promise<LogEntry[] | LogError>
}
```

ITraceFetcher is an abstract contract. The actual adapter (Hera CLI, Jaeger API, ElasticSearch, etc.) is configured externally. The Skill only depends on the interface.

Phase A operations:
1. Call `getTrace(traceId)` → TraceDetail.
2. Extract signals: root operation name, total duration, root span error flag, child span duration distribution, service/environment/area, exception type/message, thread information, HTTP status code, DB span tags.
3. Call `getLogs(traceId, {level: "ERROR", pageSize: 5})` → error logs.
4. If Phase A produced an exception type, call `getLogs(traceId, {keyword: exceptionType, pageSize: 5})`.

**Phase A Failure Fallback**:

| Failure | Behavior |
|---------|----------|
| permission_denied / not_found | Annotate `restricted_info` → abandon fast path → continue with standard extraction below |
| timeout / 504 | Retry with smaller time window (-360,0 → -180,0 → -60,0); if still failing → annotate `restricted_info` → continue with partial data |
| parse_error | Preserve raw response → annotate `restricted_info` → continue |
| is_overflow on logs | Shrink pageSize (5→1) and timeRange; prior logs at ERROR/WARN level are complete; annotate `restricted_info` for incomplete INFO timeline |

**Phase B — Trace Diagnosis**

1. **Timeline Reconstruction**: Build timeline from root span start → child spans → error/exception log timestamp.
2. **Blackhole Detection**: Calculate `blackhole_ms = totalDuration - Σ(childSpan.duration)`. If `blackhole_percent > 50%`, mark as uninstrumented processing segment. If `blackhole_percent > 90%`, strong signal.
3. **Pattern Matching**: Match against the six diagnostic patterns in `references/trace-diagnosis.md`:
   - Pattern 1: Broken Pipe / ClientAbortException
   - Pattern 2: Long duration but child calls not slow (blackhole > 50%)
   - Pattern 3: Rollback without explicit downstream errors
   - Pattern 4: High-frequency repeated calls (N+1)
   - Pattern 5: Log overflow
   - Pattern 6: Thread Blocking (blackhole > 70% + thread wait signals + Broken pipe)
4. Apply pattern matching priority: Pattern 5 → Pattern 1 → Pattern 2 → Pattern 6 → Pattern 4 → Pattern 3.
5. Produce diagnosis summary: matched pattern(s), blackhole percentage, confidence.

**Phase C — Extract Code Search Clues**

Extract precise search terms from the Trace data to feed into step 3:

| Trace signal | Step 3 search method |
|---|---|
| Root operation name (e.g. `/api/trade/order/detail`) | `searchByRoute()` — high precision |
| Exception class name (e.g. `IllegalStateException`) | `searchByKeyword()` — medium precision |
| Exception message (e.g. `item snapshot missing`) | `searchByKeyword()` or `searchByError()` |
| Slow method name from child spans | `searchByKeyword()` |
| SQL fragments from DB span tags | `searchByKeyword()` |
| Thread blocking signals | `searchByKeyword()` for `synchronized`/`lock`/`CompletableFuture` |

Mark code search clue source as `"trace"` (distinct from `"user_input"`) for traceability.

**Standard Extraction** — Always run after the fast path (or directly when no traceId is present).

Extract a structured summary from the user's text, screenshots, logs, and error descriptions. Do not ask for each missing field.

Extract when present:

- system/module;
- interface path;
- page name or module name;
- business ID and ID type;
- time range;
- error text or error code;
- log text;
- business entities such as user, tenant, store, order, settlement, product, activity;
- screenshot-derived page clues if available.

If logs are present, load `references/log-patterns.md` and apply the pattern library. If no pattern matches, preserve raw text and add `日志格式未识别，可能遗漏信息` to `restricted_info`.

Freeze the output schema at the end of step 2:

```yaml
status
summary
problem
root_cause
evidence
restricted_info
recommendations
```

After freezing, do not add top-level output fields. If another field would help, put that need in `restricted_info`; if it blocks confidence, degrade to `partial_success`.

Step 2 output:

- structured context summary;
- extracted log fields;
- investigation plan preview;
- frozen output schema;
- `restricted_info`.

Checkpoint after step 2.

### Step 3: Code Location

Use available code search tools behind a normalized contract. Do not depend on a specific external API.

Conceptual interface:

```ts
interface ICodeSearcher {
  searchByKeyword(query: string): CodeMatch[]
  searchBySemantics(description: string): CodeMatch[]
  searchByRoute(path: string): CodeMatch[]
  searchByError(errorCode: string): CodeMatch[]
}
```

Normalize every result:

```ts
type CodeMatch = {
  file: string
  line?: number
  snippet: string
  matchType: "route" | "error" | "keyword" | "semantic" | "sql" | "call_chain"
  confidence: "high" | "medium" | "low"
  source: "gitnexus" | "rag" | "grep" | "manual"
  query: string
  raw_ref?: string
  restricted_info?: string[]
}
```

Routing rules:

- Interface path, class name, method name, annotation, SQL fragment, or error code -> prefer structural search such as gitnexus.
- Only business symptom or page behavior -> prefer semantic search such as RAG.
- RAG and gitnexus unavailable, unavailable in current toolset, or low-confidence -> use enhanced grep.
- Code clues from Trace fast path (Phase C) carry `source: "trace"` and have highest routing priority — use `searchByRoute()` for interface paths, `searchByKeyword()` for exception/class/method names.

Enhanced grep strategy:

1. Search original keywords.
2. Search error code and error text.
3. Search page/module names and route fragments.
4. Search exception type, enum names, constants, and i18n keys.
5. Search candidate tables and SQL fragments.
6. Weight Controller, Service, Mapper, DAO, SQL XML, enum, constant, and config files higher.
7. Use first-pass matches to run second-pass context search.

Step 3 output must include:

- interface candidates;
- code file paths and line numbers when available;
- snippets;
- call-chain summary;
- candidate table names;
- `CodeMatch[]`;
- confidence and `restricted_info`.

If only semantic matches exist and no code location can be verified, final status cannot be `success`.

Checkpoint after step 3.

### Step 4: SQL Preparation

Prepare SQL only after table and datasource provenance are understood.

Create two SQL classes:

- **minimal_verify**: smallest query that confirms whether the reported phenomenon exists.
- **root_cause_confirm**: deeper query that validates causal fields, status transition, config value, or relational consistency.

Each SQL item must include:

- purpose;
- SQL text;
- table name source;
- datasource source;
- required input conditions;
- expected observation;
- execution risk;
- whether it can be executed safely in read-only mode.

If table name or datasource is uncertain, self-verify from code/config first. If still uncertain, SQL can be proposed but must not be treated as evidence.

Checkpoint after step 4.

### Step 5: Database Query

Use available database tools behind a normalized contract:

```ts
interface IDatabaseQuery {
  query(sql: string, purpose: "minimal_verify" | "root_cause_confirm"): QueryResult
}
```

Query rules:

- Prefer read-only SQL.
- Use the minimal verification SQL first.
- Retry transient failures up to 3 times when retry is reasonable.
- Record permission, timeout, empty result, parse error, and datasource mismatch as evidence.
- Never invent query results.

SQL text alone is not evidence. A database evidence item requires an actual query result or an actual tool error.

If all database access fails, final status is at most `partial_success`.

Checkpoint after step 5.

### Step 6: Root Cause Analysis and Output

Default to the brief output template from `templates/output.md`.

Only output `success` when all conditions are true:

- system/module is known;
- problem is clearly restated;
- code evidence points to concrete file/method/line or an equivalent stable code reference;
- database evidence comes from an actual query result;
- business logic connects the data state to the observed symptom;
- no blocking `restricted_info` remains.

Use `partial_success` when a likely direction exists but critical verification is missing.

Use `failed` when the system cannot be selected, no usable evidence can be collected, required tools are unavailable with no fallback, or meaningful output would require invention.

**Recommendations Generation**

The `recommendations` field is mandatory in v0.2. Generate at least one recommendation per tier where evidence supports it. Recommendations must be anchored to specific evidence — never write generic advice like "suggest optimizing performance."

Three-tier definition:

| Tier | Goal | Owner | Timeframe |
|------|------|-------|-----------|
| P0 | Immediate mitigation — stop the user from seeing errors | Ops/on-call, no code deploy required | 1-2 days |
| P1 | Performance/logic governance — make the problem visible and prevent recurrence | Business dev team, code changes OK | 1 week |
| P2 | Architecture evolution — prevent this class of problem from recurring | Architecture team, cross-team coordination | 1 month+ |

P0 constraints:
- Must be executable by ops/on-call without code deployment.
- Typical actions: adjust timeout/config thresholds, toggle feature flags, scale resources, route traffic.
- Must not require modifying application code.

P1 constraints:
- Must be anchored to a specific code file, method, or data pattern identified in evidence.
- Typical actions: add spans, add cache, optimize SQL, parallelize serial calls.

P2 constraints:
- May span teams or require architectural changes.
- Typical actions: sync-to-async, sharding, framework upgrades, monitoring/alarm infrastructure.

Tier omission rules:
- If evidence is insufficient to support a tier, that tier may be empty `[]`.
- Do not write "suggest investigating XX" — investigation is the Skill's job, not a recommendation.
- In `partial_success` or `failed` status, P1/P2 can be omitted if unreliable; P0 should still be provided for triage.

Recommendations and `restricted_info` must not overlap:
- `restricted_info` describes what was missing during investigation.
- `recommendations` describe what to do to fix the problem.

Run L4 final validation before responding.

Checkpoint after step 6.

### Step 7: Case Write-Back

Only prepare a draft. Ask for confirmation before writing.

Prefer updating an existing case over creating a duplicate. The draft should include:

- symptom;
- system/module;
- root cause;
- evidence summary;
- verification SQL or tool reference;
- handling suggestion;
- verifier;
- `restricted_info`;
- follow-up owner if known.

Do not write to `golden-cases/`. Write-back targets only the production case library.

Checkpoint after step 7.

## Output Contract

The v0.2 schema has exactly seven top-level fields:

```yaml
status: success | partial_success | failed
summary: string
problem: string
root_cause: string
evidence: Evidence[]
restricted_info: string[]
recommendations: Recommendation[]
```

Recommendation shape:

```yaml
- level: P0 | P1 | P2
  action: string        # concrete executable operation
  owner: string         # suggested executor/role
  verification: string  # acceptance criteria
  estimated_effort: string
```

Evidence shape:

```yaml
- type: code | db | log | case | user_input | tool_error
  source: string
  observation: string
  supports: string
  confidence: high | medium | low
```

### Status Rules

`success`:

- code and DB evidence both exist;
- if traceId was provided and fast path was triggered, trace evidence must be included;
- evidence and business logic form a closed chain;
- no blocking restricted information remains.

`partial_success`:

- likely cause exists, but DB, code, log, permission, business ID, time range, datasource, config, or case verification is missing;
- SQL is prepared but not executed;
- historical case is relevant but minimal verification fails or is unavailable.

`failed`:

- no system can be selected or inferred;
- no useful evidence exists;
- tools and fallbacks are unavailable;
- any useful conclusion would require invented data.

## Fail-Closed and restricted_info

Use `restricted_info` to say exactly what is missing and how it limits confidence.

Common entries:

- `缺少业务 ID，无法执行最小验证 SQL`
- `数据库权限不可用，无法验证真实数据状态`
- `经验库路径未知，未完成历史案例预检`
- `仅有 RAG 语义命中，未定位到可验证代码行`
- `日志格式未识别，可能遗漏信息`
- `表名来源不明确，SQL 只能作为建议`

If a missing item blocks success, do not hide it in prose. Add it to `restricted_info` and downgrade status.

### Trace-Driven Fast Path Fail-Closed Matrix

When the trace-driven fast path is active, apply this additional fail-closed matrix:

| Degradation trigger | Behavior | Status impact |
|---|---|---|
| Trace API permission_denied or not_found | Annotate `restricted_info` ("Trace 查询不可用: {reason}"), abandon fast path, continue with standard extraction | None — standard extraction can still produce `success` |
| Trace API timeout after retries | Use partial data + annotate `restricted_info` ("Trace 查询超时，仅获取部分数据") | Downgrade to at most `partial_success` if blackhole cannot be confirmed |
| Log API overflow | ERROR/WARN logs complete, INFO sampled; annotate `restricted_info` ("INFO 日志溢出，仅采样关键时间点") | None unless overflow blocks pattern matching |
| Blackhole detected but code not located | Use semantic search (RAG) for blackhole-adjacent method names; if still unfound → annotate `restricted_info` ("黑洞代码段未定位: {phase}") | Downgrade to `partial_success` — blackhole without code anchor is unverified |
| No diagnostic pattern matched | Output basic trace summary + annotate `restricted_info` ("未匹配已知诊断模式"); do not force a match | None — basic diagnosis is still useful |

## No Invention Rules

Never write these as facts unless directly observed from user input, code, logs, tool output, DB results, or case files:

- SQL query results;
- file paths or line numbers;
- table names or datasource names;
- historical case IDs;
- owners, verifiers, or processors;
- config values;
- root cause mechanisms;
- user identity, tenant, store, order, or payment facts.

When unsure, write uncertainty as `restricted_info` and continue.

## Checkpoint Protocol

After every completed step, write a checkpoint when the runtime permits it.

Default path:

```text
.troubleshoot-checkpoints/<ticket-id-or-hash>.json
```

If the workspace path is not writable, use a local temporary path and report it.

Checkpoint shape:

```json
{
  "skill_name": "online-troubleshoot",
  "skill_version": "0.2",
  "ticket_id": "...",
  "current_step": 3,
  "completed_steps": [1, 2],
  "output_schema": ["status", "summary", "problem", "root_cause", "evidence", "restricted_info", "recommendations"],
  "schema_frozen_at_step": 2,
  "trace_fast_path": {
    "triggered": true,
    "trace_id": "9a3f2b1c-d4e5-6f7a-8b9c-0d1e2f3a4b5c",
    "fetcher_source": "hera",
    "phase_a_status": "complete",
    "blackhole_ms": 5950,
    "blackhole_percent": 93,
    "matched_patterns": ["Pattern 1: Broken pipe", "Pattern 2: Blackhole"],
    "code_clues_count": 3
  },
  "tool_call_count": {
    "case_search": 2,
    "trace_query": 1,
    "log_query": 3,
    "code_search": 4,
    "database_query": 1
  },
  "step_outputs": {},
  "restricted_info": [],
  "resume_notes": []
}
```

On resume:

1. Load the checkpoint.
2. Continue from `current_step`.
3. If Skill version or schema expectations changed, do not restart by default.
4. Mark completed step outputs with `schema 已变更，结论可能需要重新校验`.
5. Continue and revalidate before final output.

## Four-Layer Validation

### L1: Tool Return Validation

Before using a tool result, check:

- data, empty result, permission error, timeout, parse error, or datasource mismatch;
- whether the result corresponds to the query;
- whether the result is raw output, normalized output, or model interpretation.

### L2: Step Contract Validation

Each step must produce its required outputs. Missing required outputs must enter `restricted_info` before continuing.

### L3: Business Logic Validation

Verify that code, SQL, data, logs, and business meaning agree.

Examples:

- a status value maps to the business status being discussed;
- a config switch affects the blamed code path;
- a historical case matches the same mechanism, not just similar words.

### L4: Final Output Validation

Before final output, verify:

- `status` matches evidence strength;
- v0.2 top-level fields only;
- every evidence item is traceable;
- no invented result, path, line, case ID, owner, config, or root cause;
- `restricted_info` lists blockers;
- brief output is business-readable.

## Quick Execution Checklist

Use this checklist during every ticket:

1. Select or infer system; ask once only if necessary.
2. Search production case library twice; classify confidence.
3. **If traceId present, trigger trace-driven fast path (Phase A→B→C); load `references/trace-diagnosis.md`**.
4. Extract context once; freeze seven-field schema after step 2.
5. Locate code with structured, semantic, or enhanced grep search; prioritize trace-derived clues.
6. Prepare SQL with table and datasource provenance.
7. Query DB when available; never invent results.
8. Output seven-field contract with L4 validation; generate P0/P1/P2 recommendations anchored to evidence.
9. Prepare write-back draft only after conclusion; write only after confirmation.

## Common Failure Modes

| Failure mode | Required behavior |
| --- | --- |
| Similar historical case found | Treat as hypothesis unless high confidence; still run minimal verification before `success` |
| RAG returns plausible code but no file/line | Use as low/medium confidence; cannot produce `success` alone |
| SQL prepared but DB unavailable | `partial_success`; SQL is not evidence |
| Missing business ID or time range | Continue; record gap; SQL may remain suggested only |
| Logs unrecognized | Preserve raw text and add restricted info |
| User asks for detailed report | Use detailed template only after brief conclusion or when explicitly requested |
| Trace fast path triggered but Trace API unavailable | Annotate `restricted_info`; fall back to standard extraction; do NOT abort |
| Blackhole detected but code not located by step 3 | Downgrade to `partial_success`; annotate `restricted_info` |
| Log overflow during fast path log query | Shrink pageSize/timeRange; annotate `restricted_info` for incomplete INFO timeline |
| recommendations empty or generic | Must be anchored to specific evidence; P0 must be ops-executable |

## Self-Check Before Final Response

Do not respond until these checks pass:

- Did I avoid all unapproved blocking questions?
- Did I separate Golden Cases from the production case library?
- Did I preserve and report missing critical fields?
- Did I avoid invented SQL results, file paths, line numbers, Trace data, and root causes?
- Did I downgrade when code or DB evidence was missing?
- Did I downgrade when blackhole was detected but code could not be located?
- Did I keep the output schema to seven top-level fields after step 2?
- Did I cite evidence clearly enough for another engineer to verify?
- Did I generate P0/P1/P2 recommendations anchored to specific evidence?
- Did I ensure P0 recommendations are ops-executable without code deployment?
- If trace fast path was triggered, did I annotate `restricted_info` for any degraded data?
