# 修改日志 — 2026-07-15

| 字段 | 内容 |
| --- | --- |
| 提交者 | yfan945 |
| 提交 Hash | `9d70b49`、`e60fee8`、`a7c5454` |

## 今日概述

今日共 3 个提交（06:01 ~ 07:16），完成 imagegen 项目作为 Claude Code skill 的正式结构迁移：将核心技能内容整体下放到 `skills/imagegen/`，精简并规范化 `SKILL.md` 与参考文档，新增 `CLAUDE.md` 作为 Claude Code 专属上下文，同时扩展文档契约测试的覆盖范围。

## 变更内容

### feat · New Feature

- **Skill 目录结构迁移**：将 `scripts/`、`SKILL.md`、`.env.example`、`references/`、`requirements.txt`、`assets/examples/` 和 `logo/` 统一迁入 `skills/imagegen/`，使仓库符合 Claude Code skill 加载规范；同步更新 CI、测试、README 与 `AGENTS.md` 中的路径引用。 (`skills/imagegen/`, `.github/workflows/ci.yml`, `tests/`, `AGENTS.md`, `README.md`, `README-zh.md`)

### refactor · Refactoring

- **项目精简与文档规范化**：精简 `SKILL.md` 中冗余的实现细节与重复说明，将具体规则下沉到 `references/`；清理 `scripts/image_gen.py` 中已文档化的能力说明，保持 CLI 代码聚焦；更新 references 中 CLI、Lite、Pro、prompting 文档的一致性。 (`SKILL.md`, `skills/imagegen/scripts/image_gen.py`, `references/`)

### docs · Documentation

- **新增 CLAUDE.md**：补充 Claude Code 专属项目上下文与开发约定。 (`CLAUDE.md`)
- **路径与引用优化**：同步更新 README、`AGENTS.md` 和 references 中所有资源路径，匹配新的 `skills/imagegen/` 布局。 (`README.md`, `README-zh.md`, `AGENTS.md`, `references/`)

### test · Testing

- **文档契约测试扩展**：`tests/test_docs_contract.py` 更新路径引用与验证逻辑，新增/调整资源位置、README Logo 引用和视觉示例文档一致性检查。 (`tests/test_docs_contract.py`)

## 文件更改

| File | Changes |
| --- | --- |
| `.github/workflows/ci.yml` | 路径更新 |
| `AGENTS.md` | 路径与结构说明更新 |
| `CLAUDE.md` | 新增 |
| `README.md` / `README-zh.md` | 引用路径更新 |
| `SKILL.md` | 大幅精简 |
| `references/*.md` | 规范化更新 |
| `skills/imagegen/SKILL.md` | 新增（从根目录移入并精简） |
| `skills/imagegen/scripts/image_gen.py` | 清理冗余说明 |
| `skills/imagegen/references/*.md` | 从根目录移入并更新 |
| `tests/test_docs_contract.py` | 路径与断言扩展 |
| `tests/test_image_gen.py` | 路径更新 |
| `tests/test_remove_chroma_key.py` | 路径更新 |
| `tests/benchmark_remove_chroma_key.py` | 路径更新 |

_（已提交改动共 28 个文件，+511 / -326；另有未提交的工作区改动见“未完成事项”。）_

## 未完成事项

- 已确认品牌资产放在根目录 `logo/`，`AGENTS.md`、`CLAUDE.md` 与 `tests/test_docs_contract.py` 已同步更新。
- `pyproject.toml` 版本号已更新为 `2.0.0`。

## 明日计划

1. 提交当前改动并打 tag `v2.0.0`。
2. 推送后检查 GitHub README、Logo、badges 和 CI 状态的实际渲染。
3. 依据真实使用反馈继续校准色键算法与跨平台路径边界。

## 备注

- 本次改动未发起真实 Ark 请求；测试使用 mock 或 dry-run。
- 测试验证：`python -m pytest -q` → `135 passed, 1 skipped, 89 subtests passed`。
- `git diff --check`：通过。
- v2.0.0 版本日志已写入根目录 `CHANGELOG.md`。
