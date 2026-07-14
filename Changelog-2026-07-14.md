# 修改日志 — 2026-07-14

| 字段 | 内容 |
| --- | --- |
| 提交者 | yfan945（工作区改动） |
| 提交 Hash | `efedb72`（基线） |

## 今日概述

> 完成一次面向发布的安全与可维护性修复：强化 Seedream CLI 的请求状态、路径、配置、脱敏和输出保护；重做色键处理的 alpha、despill、auto-key 与格式安全边界；同步补齐文档契约、开发依赖、CI 和测试覆盖。中英文 README 与项目元数据也已更新到下一版本。

## 变更内容

### feat · New Feature

- **可靠色键工作流**：新增色键转透明参考和 border-connected/alpha 安全契约，支持明确的失败恢复边界（`scripts/remove_chroma_key.py`、`references/chroma-key.md`）。
- **持续集成**：新增覆盖 Windows/Linux 与 Python 3.10–3.13 的 GitHub Actions 验证流程（`.github/workflows/ci.yml`）。

### fix · Bug Fix

- **图片处理**：修复 soft matte、despill、feather、source alpha、auto-key 和静态图片格式处理中的错误交付风险（`scripts/remove_chroma_key.py`）。
- **请求安全**：修复 HTTP 错误状态分类、ambiguous 请求恢复、配置加载、输出路径、payload 资源上限和递归脱敏问题（`scripts/image_gen.py`）。

### docs · Documentation

- **运行契约**：同步更新中英文 README、SKILL 与 references，明确绝对路径、安装 scope、模型能力、计费风险和透明背景边界。
- **项目品牌**：保留新的 `Seedream Imagegen` Logo，并清理旧品牌资源（`assets/seedream-imagegen-logo.png`）。

### test · Test

- **回归覆盖**：扩展 CLI 与色键测试，并新增文档契约测试（`tests/`）。

### chore · Chore

- **开发配置**：新增 `pyproject.toml` 版本元数据、开发依赖和忽略规则调整。

## 文件更改

| File | Changes |
| --- | --- |
| `scripts/image_gen.py` | CLI 安全与恢复逻辑大幅扩展 |
| `scripts/remove_chroma_key.py` | 色键算法与图片安全逻辑大幅扩展 |
| `tests/` | 新增与扩展 CLI、色键和文档契约测试 |
| `README.md` / `README-zh.md` | 同步安装、能力和安全说明 |
| `references/` | 新增色键说明并更新 CLI、模型和 prompt 约束 |
| `.github/workflows/ci.yml` | 新增 CI 验证流程 |
| `pyproject.toml` / `requirements-dev.txt` | 新增版本与开发依赖配置 |

## 未完成事项

- 尚未在 GitHub 页面中进行浏览器端渲染截图验证；推送后可检查 Logo、badges 和 CI 状态。

## 明日计划

- 检查远程 README、CI 和中英文链接渲染。
- 依据真实使用反馈继续校准色键算法与跨平台路径边界。

## 备注

- 本次验证未发起真实 Ark 请求；所有测试使用 mock 或 dry-run。
