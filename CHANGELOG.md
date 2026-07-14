# CHANGELOG

## v1.2.0 — 2026-07-14

| 字段 | 内容 |
| --- | --- |
| 版本 | `v1.2.0` |
| 时间范围 | 2026-07-14 |
| Git 范围 | `v1.1.0` → 工作区 |
| 提交数 | 本次工作区改动，待提交 |
| 主要贡献者 | yfan945 |

## 版本概述

本版本聚焦 Seedream Imagegen 的发布安全与可维护性。强化 CLI 的请求状态、路径、配置、脱敏和输出保护，修复色键处理的 alpha、despill、auto-key 与格式安全边界，并同步补齐文档契约、开发依赖、CI 和回归测试。

## 重大功能

- **可靠色键工作流**：新增色键转透明参考，明确 border-connected、alpha 契约、格式边界和失败恢复流程。
- **持续集成**：新增覆盖 Windows/Linux 与 Python 3.10–3.13 的 GitHub Actions 验证流程。

## Bug 修复

- **图片处理**：修复 soft matte、despill、feather、source alpha、auto-key 和静态图片格式处理中的错误交付风险。
- **请求安全**：修复 HTTP 错误分类、ambiguous 请求恢复、配置加载、输出路径、payload 资源上限和递归脱敏问题。

## 重要调整

- **文档与安装**：同步中英文 README、SKILL 和 references，明确绝对路径、安装 scope、模型能力、计费风险和透明背景边界。
- **项目配置**：版本提升至 `1.2.0`，新增开发依赖、文档契约测试和 CI 发布门禁。

## 验证记录

- `python -m pytest -q`：`122 passed, 83 subtests passed`。
- `git diff --check`：通过。
- 未发起真实 Ark 请求；测试使用 mock 或 dry-run。

## 已知问题与后续计划

- 推送后检查 GitHub README、Logo、badges 和 CI 状态的实际渲染。
- 依据真实使用反馈继续校准色键算法与跨平台路径边界。

## 参考来源

- Git baseline: `v1.1.0` (`efedb72`)
- Daily changelog: [Changelog-2026-07-14.md](Changelog-2026-07-14.md)

## v1.1.0 — 2026-07-14

| 字段 | 内容 |
| --- | --- |
| 版本 | `v1.1.0` |
| 时间范围 | 2026-07-14 |
| Git 范围 | `d72ea32` → `071c0d6` |
| 提交数 | 1 |
| 主要贡献者 | yfan945 |

## 版本概述

本版本更新 Seedream Imagegen 的 GitHub 品牌展示。新增由 imagegen 生成的项目 Logo，在中英文 README 顶部加入 validate、license 和 runtime badges，并移除旧 Logo 资源。

## 重大功能

- **项目品牌**：新增 `assets/seedream-imagegen-logo.png`，使用种子、光圈和生成火花构成项目视觉标识。

## 重要调整

- **README 展示**：`README.md` 与 `README-zh.md` 使用新的 Logo，并加入 GitHub 风格 badges。
- **资源清理**：删除 `assets/imagegen.png` 与 `assets/imagegen-small.svg`，避免重复资源。

## 验证记录

- `python -m pytest -q`：69 passed，57 subtests passed。
- `git diff --check`：通过。
- 已实际查看生成 Logo，确认文字与图形可用于 README 品牌区。

## 已知问题与后续计划

- 尚未进行 GitHub 页面窄屏渲染截图验证；推送后可检查 Logo 和 badges 的显示效果。
- Logo 当前为白底 PNG，如后续需要深色主题适配，可另行生成透明或深色版本。

## 参考来源

- Git commits: `d72ea32..071c0d6`
- Daily changelog: [Changelog-2026-07-14.md](Changelog-2026-07-14.md)
