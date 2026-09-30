import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

export type GateConfig = {
  bot_usernames: string[];
  min_effective_comments: number;
  test_pass_rate_threshold: number;
};

export type PipelineConfig = {
  test_job_patterns: string[];
  build_job_patterns: string[];
};

export type SonarConfig = {
  coverage_threshold: number;
};

export type SkillConfig = {
  gate: GateConfig;
  pipeline: PipelineConfig;
  sonar: SonarConfig;
};

const DEFAULTS: SkillConfig = {
  gate: {
    bot_usernames: ["MockGateBot", "GateBot", "QualityBot"],
    min_effective_comments: 5,
    test_pass_rate_threshold: 100,
  },
  pipeline: {
    test_job_patterns: [
      "sonar-scan\\+test",
      "unit[-_ ]?test",
      "\\btest\\b",
      "maven.*test",
      "npm.*test",
    ],
    build_job_patterns: [
      "\\bbuild\\b",
      "\\bcompile\\b",
      "mvn.*(package|install|compile)",
      "gradle.*(build|assemble)",
    ],
  },
  sonar: {
    coverage_threshold: 60,
  },
};

function skillRootDir(): string {
  const scriptsDir = dirname(fileURLToPath(import.meta.url));
  return dirname(scriptsDir);
}

function readConfigFile(): Partial<SkillConfig> {
  const envPath = process.env.GITLAB_CR_FIX_GIT_CONFIG;
  const defaultPath = join(skillRootDir(), "config.json");
  const path = envPath && envPath.trim() ? envPath : defaultPath;
  if (!existsSync(path)) return {};
  try {
    return JSON.parse(readFileSync(path, "utf8")) as Partial<SkillConfig>;
  } catch (error) {
    console.error(
      `[config] 无法解析配置文件 ${path}：${error instanceof Error ? error.message : String(error)}`,
    );
    return {};
  }
}

function mergeConfig(): SkillConfig {
  const user = readConfigFile();
  const envThreshold = Number(process.env.GITLAB_CR_FIX_GIT_SONAR_COVERAGE_THRESHOLD);
  return {
    gate: {
      bot_usernames: user.gate?.bot_usernames ?? DEFAULTS.gate.bot_usernames,
      min_effective_comments:
        user.gate?.min_effective_comments ?? DEFAULTS.gate.min_effective_comments,
      test_pass_rate_threshold:
        user.gate?.test_pass_rate_threshold ?? DEFAULTS.gate.test_pass_rate_threshold,
    },
    pipeline: {
      test_job_patterns:
        user.pipeline?.test_job_patterns ?? DEFAULTS.pipeline.test_job_patterns,
      build_job_patterns:
        user.pipeline?.build_job_patterns ?? DEFAULTS.pipeline.build_job_patterns,
    },
    sonar: {
      coverage_threshold:
        Number.isFinite(envThreshold) && envThreshold > 0
          ? envThreshold
          : user.sonar?.coverage_threshold ?? DEFAULTS.sonar.coverage_threshold,
    },
  };
}

export const config: SkillConfig = mergeConfig();

// 读取脚本输入：pathArg 为 "-" 时读 stdin（fd 0），否则读文件路径。
export function readInput(pathArg: string): string {
  if (pathArg === "-") {
    return readFileSync(0, "utf8");
  }
  return readFileSync(pathArg, "utf8");
}
