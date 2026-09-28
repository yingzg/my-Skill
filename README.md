# my-Skill

围绕 **Java 后端提效** 打造的 AI 工具集：**11 个 Skill 技能包 + 1 个 MCP 工具**，配套完整设计文档与开发教程。

## 目录结构

```
my-Skill/
├── Skill/          # AI 编程助手技能包（11 个）
├── Mcp/            # GitLab Stdio MCP 工具
├── docs/           # 设计文档、学习笔记、MCP 开发教程
│   └── mcp-guide/  # MCP 开发教程（入门 / 规范 / 最佳实践）
└── .github/        # 工程化钩子
```

## Skill 技能包

| 技能 | 定位 | 核心能力 |
| --- | --- | --- |
| `code-flowchart` | 调用链可视化 | 把 explore_symbol 调用链渲染成流程图 + 时序图（自包含 HTML） |
| `code-review-plus` | 代码审查 | Claude + Codex 交叉审查，生成 HTML 可视化报告 |
| `continuous-execution-guard` | 行为约束 | 复杂多步骤任务的连续执行行为约束 |
| `git-conflict-resolver` | 冲突解决 | Git 合并冲突检测、原因分析、自动修复 |
| `gitlab-cr-fix-git` | MR 审查 | GitLab MR 审查、逐行 CR 评论、门禁诊断 |
| `install-skill` | 技能安装 | skill 软链接安装到 Claude Code / OpenCode / Gemini |
| `local-coverage-booster` | 覆盖率提升 | JUnit5 + Mockito 单测生成，JaCoCo 变更行覆盖率 |
| `online-troubleshoot` | 线上排障 | 工单根因分析，代码 + 日志 + SQL + trace 证据链 |
| `prod-config-diff` | 配置一致性 | GitLab CI 检测 prod 配置环境差异并添加行内评论 |
| `sql-review` | SQL 审查 | MyBatis Mapper 慢查询风险四层分析审查 |
| `writer-reviewer` | 编码质量 | Writer-Reviewer 双层循环质量保障工作流 |

## MCP 工具

**gitlab-stdio-mcp**：本地 stdio MCP Server，提供 GitLab 仓库与 CI/CD 操作能力（MR、Pipeline、变量、Job 等），含运行时参数校验、密钥脱敏、项目白名单、只读模式等安全护栏。详见 [Mcp/README.md](Mcp/README.md)。

## 文档

- `docs/`：SKILL 设计方法论、行为约束型 SKILL 设计、各技能学习笔记
- `docs/mcp-guide/`：MCP 入门开发教程、复杂开发代码规范、生产最佳实践

## 使用方式

每个 Skill 通过 `SKILL.md` 定义（frontmatter 含 `name` 与 `description`），将技能目录安装到 AI 编程助手的 skills 目录即可被自动识别与调用。具体工作流与脚本编排见各 `Skill/*/SKILL.md`。

MCP 工具通过 `node build/index.js` 启动，配置方式见 [Mcp/README.md](Mcp/README.md)。

## License

Private
