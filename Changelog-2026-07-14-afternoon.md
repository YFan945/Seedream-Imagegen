# 修改日志 — 2026-07-14（下午）

| 字段      | 内容                                         |
| --------- | -------------------------------------------- |
| 提交者    | yfan945                                      |
| 提交 Hash | `313ef98`、`4b465dc`、`f35261f`、`cf423ed`  |

## 今日概述

下午共 4 个提交（15:53~19:39），聚焦 v1.2.0 发布后的稳定性和配置可移植性加固。核心工作：模型配置支持环境变量覆盖（`ARK_PRO_MODEL`/`ARK_LITE_MODEL`），技能资源目录重组（品牌资产统一到 `logo/`、视觉参考样例独立到 `assets/examples/`），以及输出路径验证的全组件检测增强。

## 变更内容

### feat · New Feature

- **v1.2.0 发布**: 新增 CI 工作流（GitHub Actions，4 Python 版本 × 3 平台）、`pyproject.toml` 项目元信息、大规模重写 `image_gen.py`（~500 行增强，含 dry-run、请求恢复、原子保存、Lite 组图）、`remove_chroma_key.py` 重构、以及完整的测试套件。 (`pyproject.toml`, `.github/workflows/ci.yml`, `scripts/image_gen.py`)

### fix · Bug Fix

- **可移植模型配置**: 新增 `ARK_PRO_MODEL` 和 `ARK_LITE_MODEL` 环境变量，支持 CI/容器/不同机器在不改安装目录 `.env` 的情况下覆盖模型 ID；进程环境优先级高于本地 `.env`；`.env` 读取兼容 UTF-8 BOM。 (`scripts/image_gen.py`, `.env.example`)
- **输出路径验证加固**: `_validate_portable_target` 从仅校验文件名改为校验路径所有组件（空格/句点结尾、不可移植字符、Windows 保留名、组件长度、总路径长度上限 240 字符）。 (`scripts/image_gen.py`)

### refactor · Refactoring

- **资源目录重组**: 品牌资产（logo/icon）从 `assets/` 移入 `logo/`；新增 `assets/examples/` 存放可选视觉参考样例（写实自然、商品棚拍、信息图、叙事插画）。所有文档路径同步更新。 (`AGENTS.md`, `README.md`, `README-zh.md`, `SKILL.md`)
- **断言重构**: 测试用例重命名以更清晰表达意图；输出路径测试扩展为子测试，覆盖更多边界场景（`CON.extra.png`、`bad:name.png` 等）。 (`tests/test_image_gen.py`, `tests/test_docs_contract.py`)

### docs · Documentation

- **删除审计与修复计划**: 移除 `AUDIT-AND-REMEDIATION-PLAN.md`（654 行，已完成的审计文档清理）。 (`AGENTS.md`)
- **视觉参考文档**: 新增 `references/visual-examples.md`，含 4 类典型视觉方向的分类、完整 prompt、适用场景和使用限制。 (`references/visual-examples.md`)

### test · Testing

- **资源契约测试扩展**: 新增 `test_visual_examples_are_documented_and_valid_images`（验证 4 张示例图片存在、尺寸正常、被 SKILL.md 引用）和 `test_brand_assets_live_outside_visual_examples`（验证品牌资产已移至 `logo/` 且 README 引用同步）。
- **CI 矩阵扩展**: 增加 `macos-latest` 平台支持。 (`.github/workflows/ci.yml`)
- **模型配置测试**: 验证自定义模型 ID 可正确注入 payload 且不改变 tier 规则；非法模型 ID（含空格）被正确拒绝。

## 文件更改

| File                               | Changes   |
| ----------------------------------- | --------- |
| `.env.example`                      | +8 -3     |
| `.github/workflows/ci.yml`          | +32 -1    |
| `AGENTS.md`                         | +5 -3     |
| `AUDIT-AND-REMEDIATION-PLAN.md`     | -654      |
| `README-zh.md`                      | +6 -4     |
| `README.md`                         | +6 -4     |
| `SKILL.md`                          | +5 -1     |
| `pyproject.toml`                    | +9        |
| `references/visual-examples.md`     | +49       |
| `scripts/image_gen.py`              | +82 -40   |
| `tests/test_docs_contract.py`       | +62 -3    |
| `tests/test_image_gen.py`           | +64 -5    |
| `assets/examples/*.png` (4 张)      | 新增      |
| `logo/*.png` (2 张)                 | 从 assets 移入 |

## 未完成事项

- 输出路径验证新增了 `MAX_PORTABLE_PATH_LENGTH = 240`，但该常量目前仅在 `_validate_portable_target` 中使用，其他路径相关函数是否也需要引用该上限未做同步
- CI 目前只有 validate job（测试 + 编译 + 空白检查），无发布流水线

## 明日计划

1. 验证所有平台（Windows/macOS/Ubuntu）上端口路径规则的实际表现
2. 考虑为 CI 增加发布阶段（自动发布到 GitHub Releases）
3. 排查路径验证中 `225` 字符路径在边界情况下的行为

## 备注

本次改动主要是 v1.2.0 发布后的加固 cycle：模型配置从硬编码变为可外部覆盖，资源目录结构经过清理更清晰，测试覆盖了更多边界场景。下一步可考虑减少功能债务，专注 CI 发布流水线和跨平台兼容性证明。
