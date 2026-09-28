import { config } from "./config.ts";

export type SonarMeasure = { metric?: string; value?: string };
export type SonarResponse = {
  component?: { key?: string; measures?: SonarMeasure[] };
};

function numberMeasure(measures: Record<string, string>, key: string): number | null {
  const raw = measures[key];
  if (raw === undefined) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

export function parseSonarMeasures(input: SonarResponse) {
  const measures = Object.fromEntries(
    (input.component?.measures ?? []).map((measure) => [measure.metric ?? "", measure.value ?? ""]),
  );
  const newLine = numberMeasure(measures, "new_line_coverage");
  const newLinesToCover = numberMeasure(measures, "new_lines_to_cover");
  const generic = numberMeasure(measures, "coverage") ?? numberMeasure(measures, "line_coverage");
  const newLineMeaningless = newLinesToCover === 0;
  const useNewLine = newLine !== null && !newLineMeaningless;
  const coverage = useNewLine ? newLine : generic;
  const required = config.sonar.coverage_threshold;

  return {
    component_key: input.component?.key ?? null,
    coverage_metric: coverage !== null ? (useNewLine ? "new_line_coverage" : "coverage") : null,
    coverage,
    required,
    passed: coverage !== null ? coverage >= required : null,
    new_lines_to_cover: newLinesToCover,
    new_uncovered_lines: numberMeasure(measures, "new_uncovered_lines"),
    raw_measures: measures,
  };
}
