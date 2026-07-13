# 修改日志 — 2026-07-14

| 字段 | 内容 |
| --- | --- |
| 提交者 | yfan945 |
| 提交 Hash | `071c0d6` |

## 今日概述

> 为 Seedream Imagegen 增加新的项目 Logo，并按照 GitHub 仓库常见格式完善中英文 README 顶部品牌区。同步移除旧 Logo 资源，保留安装、配置和使用说明不变。

## 变更内容

### feat · New Feature

- **项目品牌**：使用 imagegen 生成新的 `Seedream Imagegen` 横向 Logo，表达种子、光圈和生成火花的概念（`assets/seedream-imagegen-logo.png`）。

### docs · Documentation

- **GitHub README**：在中英文 README 顶部加入 `validate / license / runtime` badges，并替换旧图片引用（`README.md`、`README-zh.md`）。

### chore · Cleanup

- **资源清理**：删除旧的 `assets/imagegen.png` 与 `assets/imagegen-small.svg`，避免仓库保留重复品牌资源。

## 文件更改

| File | Changes |
| --- | --- |
| `README.md` | +7 -1 |
| `README-zh.md` | +7 -1 |
| `assets/seedream-imagegen-logo.png` | +723659 bytes |
| `assets/imagegen.png` | deleted |
| `assets/imagegen-small.svg` | deleted |

## 未完成事项

- 尚未在 GitHub 页面中进行浏览器端渲染截图验证；推送后可检查 Logo 与 badges 在窄屏下的显示效果。

## 明日计划

- 检查远程 README 的 Logo、badges 和中英文链接渲染。
- 如仓库体积或加载速度需要优化，再评估压缩 Logo 资源。

## 备注

- Logo 使用纯白背景 PNG，适合当前 README 的白色内容区。
