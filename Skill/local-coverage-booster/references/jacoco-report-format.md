# JaCoCo Report Format

JaCoCo is the local coverage data source for this Skill.

Common Maven XML path:

```text
target/site/jacoco/jacoco.xml
```

Common Gradle XML path:

```text
build/reports/jacoco/test/jacocoTestReport.xml
```

## XML Shape

JaCoCo XML contains packages, source files, and line records:

```xml
<package name="com/example/order">
  <sourcefile name="OrderService.java">
    <line nr="42" mi="0" ci="4" mb="0" cb="0"/>
    <line nr="43" mi="3" ci="0" mb="1" cb="1"/>
  </sourcefile>
</package>
```

Line fields:

| Field | Meaning |
|---|---|
| `nr` | Source line number. |
| `mi` | Missed instructions. |
| `ci` | Covered instructions. |
| `mb` | Missed branches. |
| `cb` | Covered branches. |

## Local Coverage Interpretation

This Skill uses a pragmatic line-level interpretation:

```text
coverable = mi + ci + mb + cb > 0
covered = ci > 0 or cb > 0
uncovered = coverable and not covered
```

Branch gaps matter even if the line is partially executed, but V1 reports changed-line coverage first. When a changed line has `mb > 0`, inspect the surrounding branch and add a branch-specific test if the remote gate cares about branch coverage.

## Difference From SonarQube

Local JaCoCo changed-line coverage is not guaranteed to exactly match remote SonarQube new-line coverage.

Common causes:

- SonarQube exclusions differ from local defaults.
- CI runs a different module/test profile.
- Generated or Lombok code affects line mapping.
- Remote pipeline merges target branch state differently.

Use `local_target_threshold` higher than the real gate threshold to absorb these differences.
