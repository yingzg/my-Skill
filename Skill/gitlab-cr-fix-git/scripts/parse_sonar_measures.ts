#!/usr/bin/env node

import { readInput } from "./config.ts";
import { parseSonarMeasures, type SonarResponse } from "./sonar_measures.ts";

const path = process.argv[2];
if (!path) {
  console.error("Usage: node --experimental-strip-types scripts/parse_sonar_measures.ts <sonar_measures_component.json> | -（stdin）");
  process.exit(2);
}

try {
  const input = JSON.parse(readInput(path)) as SonarResponse;
  console.log(JSON.stringify(parseSonarMeasures(input), null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
