# CHANGELOG

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
