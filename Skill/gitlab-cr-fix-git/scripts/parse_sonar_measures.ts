#!/usr/bin/env node

import { readFileSync } from "node:fs";

type Measure = {
  metric?: string;
  value?: string;
};

type SonarMeasures = {
  component?: {
    key?: string;
    measures?: Measure[];
  };
};

function numberMeasure(measures: Record<string, string>, key: string): number | null {
  const raw = measures[key];
  if (raw === undefined) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

function parse(input: SonarMeasures) {
  const measures = Object.fromEntries((input.component?.measures ?? []).map((measure) => [measure.metric ?? "", measure.value ?? ""]));
  const newLineCoverage = numberMeasure(measures, "new_line_coverage");
  const genericCoverage = numberMeasure(measures, "coverage") ?? numberMeasure(measures, "line_coverage");
  const coverage = newLineCoverage ?? genericCoverage;
  const required = 60;

  return {
    component_key: input.component?.key ?? null,
    coverage_metric: newLineCoverage !== null ? "new_line_coverage" : genericCoverage !== null ? "coverage" : null,
    coverage,
    required,
    passed: coverage !== null ? coverage >= required : null,
    new_lines_to_cover: numberMeasure(measures, "new_lines_to_cover"),
    new_uncovered_lines: numberMeasure(measures, "new_uncovered_lines"),
    raw_measures: measures,
  };
}

const path = process.argv[2];
if (!path) {
  console.error("Usage: node --experimental-strip-types scripts/parse_sonar_measures.ts <sonar_measures_component.json>");
  process.exit(2);
}

try {
  const input = JSON.parse(readFileSync(path, "utf8"));
  console.log(JSON.stringify(parse(input), null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}

