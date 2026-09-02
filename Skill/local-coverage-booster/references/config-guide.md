# Configuration Guide

Keep project configuration inside this Skill directory:

```text
local-coverage-booster/config/projects.yaml
```

Do not write configuration into a business repository unless the user explicitly changes this policy.

## Minimal Project Entry

```yaml
projects:
  - name: order-service
    remote_url_contains: order-service
    base_ref: auto
    gate_threshold: 60
    local_target_threshold: 68
    coverage_command: mvn org.jacoco:jacoco-maven-plugin:0.8.12:prepare-agent test org.jacoco:jacoco-maven-plugin:0.8.12:report
    jacoco_xml: target/site/jacoco/jacoco.xml
```

## Fields

| Field | Required | Default | Meaning |
|---|---|---|---|
| `name` | yes | none | Human-readable project name. Also used as weak fallback matching. |
| `project_root` | no | none | Exact local Git root. Best when path is stable. |
| `remote_url_contains` | no | none | Stable substring from `git remote get-url origin`. Recommended for shared config. |
| `base_ref` | no | `auto` | Ref used for changed-line comparison. Auto tries local main/master before common remote refs. |
| `gate_threshold` | no | `60` | Real remote gate threshold. |
| `local_target_threshold` | no | `gate_threshold + 8` | Local target with safety buffer. |
| `coverage_command` | yes | auto-detect | Command that runs tests and generates JaCoCo XML. |
| `jacoco_xml` | yes | auto-detect | JaCoCo XML path relative to project root. |
| `test_command` | no | `coverage_command` | Command for local test verification. |
| `source_root` | no | `src/main/java` | Production Java root. |
| `test_root` | no | `src/test/java` | Test Java root. |

## Matching Order

1. Exact `project_root`.
2. `remote_url_contains`.
3. `name` equals project directory name.
4. Auto-detection.

## Multi-Module Maven

Use module-specific commands and paths:

```yaml
projects:
  - name: order-service-module
    remote_url_contains: backend-platform
    base_ref: auto
    gate_threshold: 60
    local_target_threshold: 70
    coverage_command: mvn -pl order-service org.jacoco:jacoco-maven-plugin:0.8.12:prepare-agent test org.jacoco:jacoco-maven-plugin:0.8.12:report
    test_command: mvn test -pl order-service
    source_root: order-service/src/main/java
    test_root: order-service/src/test/java
    jacoco_xml: order-service/target/site/jacoco/jacoco.xml
```

Prefer one entry per module when one MR only changes a known module. This keeps reports smaller and feedback faster.
