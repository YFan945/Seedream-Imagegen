# CHANGELOG

## v1.2.1 — 2026-07-14

| 字段 | 内容 |
| --- | --- |
| 版本 | `v1.2.1` |
| 时间范围 | 2026-07-14 15:57 ~ 19:39 |
| Git 范围 | `v1.2.0` → `cf423ed` |
| 提交数 | 3 |
| 主要贡献者 | yfan945 |

## 版本概述

v1.2.0 发布后的加固补丁版本。核心改进：模型配置支持通过 `ARK_PRO_MODEL`/`ARK_LITE_MODEL` 环境变量覆盖，实现跨机器/CI 场景的可移植部署；输出路径验证从仅校验文件名扩展为全组件检测；技能资源目录完成重组（品牌资产统一到 `logo/`，视觉参考样例独立到 `assets/examples/`），配套补齐视觉参考文档和契约测试。

## Bug 修复

- **可移植模型配置**：新增 `ARK_PRO_MODEL` / `ARK_LITE_MODEL` 环境变量，支持 CI、容器和不同机器在不改安装目录 `.env` 的情况下覆盖模型 ID；进程环境配置优先级高于本地 `.env`；`.env` 文件读取兼容 UTF-8 BOM（`scripts/image_gen.py`）。
- **输出路径验证加固**：`_validate_portable_target` 从仅校验文件名改为校验路径所有组件——空格/句点结尾、不可移植字符、Windows 设备名（含 `CON.extra.png` 等变体）、组件 UTF-8 长度、总路径 240 字符上限（`scripts/image_gen.py`）。

## 重要调整

- **资源目录重组**：品牌资产（logo/icon）从 `assets/` 统一迁入 `logo/`；新增 `assets/examples/` 存放四类可选视觉参考样例（写实自然、商品棚拍、信息图、叙事插画）——同步更新 `AGENTS.md`、`README.md`、`README-zh.md`、`SKILL.md` 中所有引用路径。
- **视觉参考文档**：新增 `references/visual-examples.md`，含四类典型视觉方向的分类说明、完整 prompt、适用场景和使用限制。
- **文档清理**：删除已完成的 `AUDIT-AND-REMEDIATION-PLAN.md`（654 行审计记录），并更新 `AGENTS.md` 中对项目目录结构的描述。
- **CI 矩阵扩展**：GitHub Actions 增加 `macos-latest` 平台，验证跨平台兼容性。

## 验证记录

- `python -m pytest -q`：`127 passed, 89 subtests passed`。
- `git diff --check`：通过。
- 未发起真实 Ark 请求；测试使用 mock 或 dry-run。

## 已知问题与后续计划

- `MAX_PORTABLE_PATH_LENGTH = 240` 目前仅在 `_validate_portable_target` 中生效，其他路径处理函数尚未引用该上限。
- CI 目前仅有 validate job（测试 + 编译 + 空白检查），无自动发布流水线。
- 跨平台路径规则验证覆盖了 Windows/Linux/macOS，但实际行为待各平台真实运行确认。

## 参考来源

- Git baseline: `v1.2.0` (`313ef98`)
- Daily changelog: [Changelog-2026-07-14-afternoon.md](Changelog-2026-07-14-afternoon.md)

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
