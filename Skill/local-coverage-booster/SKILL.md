---
name: local-coverage-booster
description: 本地 Java 单元测试覆盖率提升技能。Use when the user wants to improve local test coverage for changed Java code before pushing, generate meaningful JUnit5 + Mockito tests, analyze JaCoCo reports, calculate changed-line coverage from git diff, or avoid pseudo-coverage while trying to pass CI/SonarQube coverage gates.
---

# Local Coverage Booster

提升当前分支新增/修改 Java 代码的本地单测覆盖率。用 git diff 定位变更行，用 JaCoCo XML 判断变更行是否被覆盖，补写 JUnit5 + Mockito 测试，并强制测试验证业务可观察结果。

## Core Principle

Optimize for passing real pipeline coverage gates, but validate locally first:

```text
changed Java lines -> JaCoCo line coverage -> uncovered changed lines
  -> meaningful tests -> local verification -> before/after report
```

Do not call SonarQube in V1. Treat local JaCoCo changed-line coverage as a conservative pre-push signal, not as the remote gate's exact value.

## Files

- Read `config/projects.yaml` first. If no project entry matches, auto-detect and ask for only missing essentials.
- Read `references/config-guide.md` when configuration is missing or unclear.
- Read `references/jacoco-report-format.md` before interpreting JaCoCo XML manually.
- Read `references/junit5-mockito-aaa.md` before creating or heavily editing tests.
- Read `references/observable-behavior-rules.md` before judging whether tests are meaningful.
- Read `references/troubleshooting.md` when commands fail, JaCoCo XML is missing, or coverage does not move.

## Workflow

### Step 0: Load Configuration

Match the current project against `config/projects.yaml` using this order:

1. Exact `project_root`.
2. `remote_url_contains` against `git remote get-url origin`.
3. `name` against the project directory name.
4. Auto-detect with `scripts/detect_project.py`.

Required runtime values:

```text
base_ref
coverage_command
jacoco_xml
source_root
test_root
local_target_threshold
```

If required values cannot be detected, stop and ask the user for those values. Do not write configuration into the business repository. If the user asks to persist config, write it to this Skill's `config/projects.yaml`.

### Step 1: Extract Changed Java Lines

Run from the business project root:

```bash
python3 <skill_dir>/scripts/changed_lines.py \
  --project-root <project_root> \
  --base-ref <base_ref> \
  --source-root <source_root> \
  --output .coverage-booster/changed-lines.json
```

If no changed Java lines remain after default exclusions, report that no local coverage boost is needed.

### Step 2: Generate JaCoCo Report

Run:

```bash
python3 <skill_dir>/scripts/run_coverage.py \
  --project-root <project_root> \
  --command "<coverage_command>" \
  --jacoco-xml <jacoco_xml>
```

If the command fails or the XML is missing, read `references/troubleshooting.md`, explain the exact missing configuration, and stop.

### Step 3: Parse JaCoCo

Run:

```bash
python3 <skill_dir>/scripts/parse_jacoco.py \
  --xml <project_root>/<jacoco_xml> \
  --source-root <source_root> \
  --output .coverage-booster/jacoco-lines-before.json
```

### Step 4: Compute Coverage Gap

Run:

```bash
python3 <skill_dir>/scripts/coverage_gap.py \
  --changed .coverage-booster/changed-lines.json \
  --jacoco .coverage-booster/jacoco-lines-before.json \
  --threshold <local_target_threshold> \
  --output .coverage-booster/coverage-gap-before.json
```

If `passed=true`, report the local target passed and do not add tests.

### Step 5: Select Test Targets

Prioritize:

1. Service/domain/application classes.
2. Files with the most uncovered changed lines.
3. Public/protected methods with clear branches, returns, exceptions, or dependency calls.
4. Code paths that can be tested with mocks without real DB/Redis/MQ/HTTP.

Defer:

- DTO/VO/entity/config/generated/mapper code.
- Private helpers unless reachable through a public method.
- Paths requiring live infrastructure.

### Step 6: Add Meaningful Tests

Read the target source, existing tests, dependent DTOs/enums/exceptions, and mockable collaborators.

Prefer appending to existing test classes. If no test exists, create `<ClassName>Test` under `test_root` with the same package.

Use AAA:

```text
Arrange: prepare inputs, mocks, and state.
Act: call the public method under test.
Assert: verify observable business behavior.
```

### Step 7: Quality Check Tests

Run:

```bash
python3 <skill_dir>/scripts/test_quality_check.py \
  --project-root <project_root> \
  --source-root <source_root> \
  --test-files <changed_test_file_1> <changed_test_file_2> \
  --output .coverage-booster/test-quality.json
```

Fix all `ERROR` findings before verification. Review `WARNING` findings and improve tests where appropriate.

### Step 8: Verify And Iterate

Run tests and coverage again using `coverage_command`. Re-parse JaCoCo to:

```text
.coverage-booster/jacoco-lines-after.json
.coverage-booster/coverage-gap-after.json
```

Stop when any condition is true:

1. `local_changed_line_coverage >= local_target_threshold`.
2. Two local coverage-boost iterations have completed.
3. No remaining testable business methods exist.
4. Tests fail repeatedly for reasons not fixable in tests.
5. Continuing would require business-code changes.

### Step 9: Report

Run:

```bash
python3 <skill_dir>/scripts/summarize_report.py \
  --before .coverage-booster/coverage-gap-before.json \
  --after .coverage-booster/coverage-gap-after.json \
  --quality .coverage-booster/test-quality.json \
  --test-files <changed_test_files> \
  --output .coverage-booster/report.md
```

In the final answer, summarize:

- Before/after local changed-line coverage.
- Test files changed.
- What business behavior each test verifies.
- Remaining uncovered changed lines and why.
- Whether it is reasonable to push for pipeline validation.

## MUST DO

1. Calculate changed lines and JaCoCo coverage before deciding what tests to add.
2. Target current-branch changed Java code unless the user asks for historical coverage.
3. Prefer meaningful service/domain/application tests over structural DTO/config tests.
4. Use AAA structure.
5. Verify at least one observable business result in every new test.
6. Use `assertThrows` for error branches and validate exception type, message, or code.
7. Assert key fields for DTO/VO/List/Map returns.
8. Verify important repository/client/gateway/producer call parameters.
9. Run local tests and regenerate JaCoCo before claiming success.
10. Keep tests deterministic; mock time, randomness, network, DB, Redis, MQ, and HTTP.
11. Follow existing project test style before using the default template.

## MUST NOT DO

1. Do not modify production code to raise coverage.
2. Do not test private methods directly.
3. Do not delete existing tests.
4. Do not rewrite existing test behavior unless current changes broke compilation.
5. Do not use `assertTrue(true)`.
6. Do not use only `assertNotNull(result)` as the sole assertion.
7. Do not verify only `any()` arguments for important collaborator calls.
8. Do not introduce `@SpringBootTest` unless the project already uses it or the user asks.
9. Do not connect to real DB/Redis/MQ/HTTP services.
10. Do not push unless the user explicitly asks.
11. Do not describe local JaCoCo coverage as exact remote SonarQube coverage.

## Output Contract

Always distinguish:

```text
local_changed_line_coverage: local JaCoCo + git diff approximation
remote_gate_coverage: CI/SonarQube value, only known after remote scan
```

Use this completion language:

```text
Local target passed. Safe to push for pipeline validation.
```

Do not say:

```text
SonarQube gate will pass.
```
