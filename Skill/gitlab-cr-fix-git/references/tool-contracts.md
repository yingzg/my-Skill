# 工具契约

本文档列出当前 skill 期望的真实生产输入，以及 fixture 文件如何模拟这些输入。

GitLab API 的网络调用、认证、分页、限流、错误处理应由 GitLab MCP 负责。Skill 只消费 MCP 返回的数据，或在 fixture 模式下读取同名本地文件。

## `gitlab_get_merge_request`

必需字段：

```json
{
  "iid": 12,
  "title": "MR title",
  "state": "opened",
  "author": {
    "username": "alice",
    "name": "Alice",
    "email": "alice@example.com"
  },
  "source_branch": "feature/x",
  "target_branch": "main",
  "merge_status": "can_be_merged",
  "detailed_merge_status": "ci_must_pass",
  "head_pipeline": {
    "id": 88991,
    "status": "failed",
    "web_url": "https://gitlab.example.com/.../pipelines/88991"
  },
  "diff_refs": {
    "base_sha": "base",
    "start_sha": "start",
    "head_sha": "head"
  },
  "web_url": "https://gitlab.example.com/group/project/-/merge_requests/12"
}
```

fixture 文件：

```text
gitlab_get_merge_request.json
```

说明：

1. 行级评论依赖 `diff_refs.base_sha`、`diff_refs.start_sha`、`diff_refs.head_sha`。
2. 如果 GitLab MCP 无法在该工具中返回 `diff_refs`，应提供单独的 `gitlab_get_merge_request_diff_refs`。

## `gitlab_get_merge_request_changes`

必需字段：

```json
{
  "changes": [
    {
      "old_path": "src/main/java/OrderService.java",
      "new_path": "src/main/java/OrderService.java",
      "new_file": false,
      "renamed_file": false,
      "deleted_file": false,
      "diff": "@@ -10,5 +10,8 @@ ..."
    }
  ]
}
```

fixture 文件：

```text
gitlab_get_merge_request_changes.json
```

说明：

1. `diff` 必须保留统一 diff hunk 信息，否则无法稳定计算行级评论位置。
2. 二进制文件或无 diff 的文件不应生成行级评论。

## `gitlab_list_merge_request_discussions`

期望结构：

```json
[
  {
    "id": "discussion-1",
    "notes": [
      {
        "id": 9001,
        "body": "### Gate Report ...",
        "author": { "username": "MockGateBot" },
        "system": false
      }
    ]
  }
]
```

fixture 文件：

```text
gitlab_list_merge_request_discussions.json
```

用途：

1. 解析 GateBot / 门禁 Bot 类门禁报告。
2. 判断已有评论，避免重复发布。
3. 识别人工讨论、系统 note 和可能的 approval 线索。

## `gitlab_create_merge_request_diff_note`

用途：

```text
发布 GitLab 行级 Diff Note。
```

期望输入：

```json
{
  "project_id": "group/project",
  "merge_request_iid": 12,
  "body": "**[CR] ...",
  "position": {
    "position_type": "text",
    "base_sha": "base",
    "start_sha": "start",
    "head_sha": "head",
    "old_path": "src/main/java/A.java",
    "new_path": "src/main/java/A.java",
    "old_line": null,
    "new_line": 42
  }
}
```

说明：

1. 新增行使用 `new_line`。
2. 删除行使用 `old_line`。
3. 修改行优先评论在修改后的 `new_line`。
4. 发布前必须确认该行来自当前 MR diff。

## `gitlab_list_pipeline_jobs`

期望结构：

```json
[
  {
    "id": 77101,
    "name": "unit-test",
    "status": "failed",
    "stage": "test",
    "web_url": "https://gitlab.example.com/.../jobs/77101"
  }
]
```

fixture 文件：

```text
gitlab_list_pipeline_jobs.json
```

用途：

1. 找到失败 job。
2. 找到最可能包含单测、编译、Sonar 信息的 job。
3. 为读取 job trace 或 artifact 提供 `job_id`。

## `gitlab_get_job_trace`

期望文本可能包含 Maven、Gradle、npm、pytest 或自定义测试摘要。

支持的信号示例：

```text
Total Passed: 42
Total Failed: 1
Total Test Cases: 43
FAILED: com.demo.OrderServiceTest.method
[ERROR] com.demo.OrderServiceTest.method
Tests run: 5, Failures: 1, Errors: 0, Skipped: 0
[ERROR] /path/A.java:[49,14] cannot find symbol
```

fixture 文件：

```text
gitlab_get_job_trace.txt
```

用途：

1. 提取编译错误。
2. 提取失败测试。
3. 提取测试总数、失败数和通过率。
4. 为最终报告提供直接证据。

## `gitlab_download_job_artifact`

建议工具，用于生产级门禁诊断。

用途：

```text
下载 JUnit XML、coverage XML、test result JSON 或其他 CI artifact。
```

fixture 文件：

```text
junit_report.xml
jacoco.xml
test_case_result.json
```

解析脚本：

```bash
node --experimental-strip-types scripts/parse_junit_xml.ts <junit_report.xml>
node --experimental-strip-types scripts/parse_coverage_xml.ts <jacoco.xml>
```

### JUnit XML 契约

```xml
<testsuite name="com.demo.OrderServiceTest" tests="5" errors="0" skipped="0" failures="1">
  <testcase name="createOrder_shouldReject" classname="com.demo.OrderServiceTest">
    <failure message="expected ..." type="java.lang.AssertionError">...</failure>
  </testcase>
</testsuite>
```

说明：

1. `parse_junit_xml.ts` 累加所有 `<testsuite>` 的 tests/failures/errors/skipped，提取含 `<failure>`/`<error>` 子元素的 testcase 明细。
2. JUnit XML 通常是「单个测试类」的报告；全局通过率应优先用 job trace 的 `Total` 数字。

### JaCoCo coverage XML 契约

```xml
<report name="order-service">
  <package name="com/demo/order">...</package>
  <counter type="LINE" missed="55" covered="45"/>
</report>
```

说明：

1. `parse_coverage_xml.ts` 提取 `<report>` 直接子级（最后一个 `</package>` 之后）的 counter，计算行/分支覆盖率。
2. JaCoCo 的 line coverage 是「全量」覆盖，非「新增代码」覆盖；门禁诊断时须标注，Sonar `new_line_coverage` 才是新增代码口径。

artifact 通常比 job trace 更结构化、更可靠。生产级诊断应优先 artifact。

## Sonar 指标 API

**数据来源边界**：本 skill 只解析 Sonar measures，不内置 Sonar API 调用、不管理 token。真实模式下 measures 数据须由外部提供（MCP 扩展、独立脚本或用户手动喂 JSON）；缺失时覆盖率诊断降级为「从 JaCoCo artifact 自算」，且必须标注口径差异。

期望结构：

```json
{
  "component": {
    "key": "demo:order-service",
    "measures": [
      { "metric": "new_line_coverage", "value": "45.0" },
      { "metric": "new_lines_to_cover", "value": "100" },
      { "metric": "new_uncovered_lines", "value": "55" }
    ]
  }
}
```

fixture 文件：

```text
sonar_measures_component.json
```

用途：

1. 判断新增代码覆盖率是否达标。
2. 计算覆盖率差距。
3. 为“应补哪些测试”提供诊断依据。

说明：本 skill 不解析 Sonar 的 bugs / vulnerabilities / code_smells 等代码规范维度。代码规范门禁缺失时显式标注，不得把「覆盖率达标」等同于「Sonar 质量门禁通过」。

## `gitlab_get_merge_request_approvals`

建议工具，用于诊断 approval 状态。

用途：

```text
读取 MR approval 状态、已批准人数、所需批准人数和批准规则。
```

说明：

1. 本 skill 只诊断 approval，不自动 approve。
2. 如果该工具不可用，可以从 discussions/system notes 或 GateBot 文本中弱解析，但必须标记证据不足。
