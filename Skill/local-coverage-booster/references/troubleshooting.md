# Troubleshooting

## JaCoCo XML Missing

Symptoms:

```text
Command succeeded but JaCoCo XML was not found
```

Check:

1. Maven can download and run `jacoco-maven-plugin`, or the Gradle JaCoCo plugin exists.
2. `coverage_command` attaches the JaCoCo agent before tests and then generates XML.
3. `jacoco_xml` path matches the module being tested.

Common Maven command:

```bash
mvn org.jacoco:jacoco-maven-plugin:0.8.12:prepare-agent test org.jacoco:jacoco-maven-plugin:0.8.12:report
```

Common Gradle command:

```bash
./gradlew test jacocoTestReport
```

## Coverage Does Not Move

Possible causes:

- Test did not execute the changed method.
- Test class naming does not match Surefire includes.
- Maven command ran a different module.
- JaCoCo XML path points to a stale report.
- The uncovered line is not coverable bytecode.
- The code path requires different branch input.

Actions:

1. Run the specific test class.
2. Confirm the test appears in test logs.
3. Delete old JaCoCo report and regenerate.
4. Verify `coverage_command`, module path, and `jacoco_xml`.
5. Inspect `mb/cb` branch counters for partial branch coverage.

## Mockito UnnecessaryStubbingException

Move stubs into only the test methods that use them, or use `lenient()` for intentionally optional stubs.

Prefer:

```java
lenient().when(client.query(any())).thenReturn(response);
```

only when the same setup supports multiple branches.

## Tests Need Real Infrastructure

Do not connect to real DB/Redis/MQ/HTTP.

Options:

1. Mock repository/client/gateway/producer.
2. Test the branch through a smaller public method.
3. Mark the line as not suitable for V1 local unit testing in the report.

## Local Passes But Remote Fails

Common reasons:

- SonarQube exclusions differ.
- CI runs another Maven profile.
- CI target branch differs from local `base_ref`.
- Multi-module report path differs.

Raise `local_target_threshold` and align `coverage_command` with CI.
