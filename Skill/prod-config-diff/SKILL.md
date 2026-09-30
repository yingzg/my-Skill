---
name: prod-config-diff
description: GitLab CI 脚本，自动检测 MR 中 prod 配置变更，对比同子模块内各环境差异，发现不一致时在 MR diff 添加行内评论
version: 1.0.0
author: Claude Code
tags: [ci, config, prod, diff, gitlab]
---

# Prod Config Diff

## 概述

在多环境部署的 Java 项目中，同一子模块下通常有多套 prod 配置（如 `application-prod1.yml`、`application-prod2.yml`）。MR 中修改某个环境配置时，容易遗漏其他环境的同步变更。

此工具作为 **GitLab CI 脚本**运行，自动检测 MR 中 prod 配置的变更，对比同子模块内各环境的差异，发现不一致时在 MR diff 对应位置添加行内评论。

## 特点

- 纯 Python，无 LLM 依赖，CI 运行快速且确定性高
- Diff 驱动，只检查 MR 变更涉及的属性，不做全量对比
- 支持两种配置布局：同目录多 prod yml / 跨 prod 目录同名文件
- GitLab Discussions API 行内评论 + 降级普通评论
- 自动去重，rebase 后不重复评论

## 检查规则

| 规则 ID | 检查项 |
|---------|--------|
| MISSING_KEY | 属性在某环境存在但其他环境缺失 |
| PLACEHOLDER_VS_VALUE | 占位符 `${...}` vs 实际值 |
| URL_FORMAT_MISMATCH | URL 格式不一致 |
| ENCRYPT_MISMATCH | 加密 vs 明文 |
| MAGNITUDE_DIFF | 数值量级差异 >10x |
| BOOL_MISMATCH | 布尔值不一致 |
| TYPE_MISMATCH | 值类型不一致 |

## 集成方式

接入项目 `.gitlab-ci.yml` 添加远程引用即可，零文件依赖：

```yaml
include:
  - project: 'your-org/skill-hub'
    ref: master
    file: 'skill/prod-config-diff/ci/gitlab-ci-prod-config-diff.yml'
```

前置条件：skill-hub **Settings → CI/CD → Job token permissions** 中允许目标项目（或在目标项目配置 `SKILL_HUB_TOKEN` 变量）。
