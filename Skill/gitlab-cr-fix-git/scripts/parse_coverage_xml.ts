#!/usr/bin/env node

import { readInput } from "./config.ts";

type Counter = {
  type: string;
  missed: number;
  covered: number;
  coverage: number | null;
};

function attr(tag: string, name: string): string | null {
  const match = tag.match(new RegExp(`\\b${name}="([^"]*)"`));
  return match ? match[1] : null;
}

function parseCounter(tag: string): Counter | null {
  const type = attr(tag, "type");
  if (!type) return null;
  const missed = Number(attr(tag, "missed") ?? "0");
  const covered = Number(attr(tag, "covered") ?? "0");
  const total = missed + covered;
  return {
    type,
    missed,
    covered,
    coverage: total > 0 ? Number(((covered / total) * 100).toFixed(2)) : null,
  };
}

// JaCoCo XML 的全局汇总 counter 是 <report> 的直接子元素，位于最后一个 </package> 之后。
function extractTopLevelCounters(xml: string): Counter[] {
  const lastPackageClose = xml.lastIndexOf("</package>");
  const tail = lastPackageClose >= 0 ? xml.slice(lastPackageClose + "</package>".length) : xml;
  const tags = tail.match(/<counter\b[^>]*?\/>/g) ?? [];
  return tags.map(parseCounter).filter((counter): counter is Counter => counter !== null);
}

function parseCoverage(xml: string) {
  const counters = extractTopLevelCounters(xml);
  const byType: Record<string, Counter> = {};
  for (const counter of counters) {
    byType[counter.type] = counter;
  }
  return {
    counters: byType,
    line_coverage: byType.LINE?.coverage ?? null,
  };
}

const path = process.argv[2];
if (!path) {
  console.error("Usage: node --experimental-strip-types scripts/parse_coverage_xml.ts <jacoco.xml>");
  process.exit(2);
}

try {
  const xml = readInput(path);
  console.log(JSON.stringify(parseCoverage(xml), null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
