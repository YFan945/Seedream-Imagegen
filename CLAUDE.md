# Repository Guidelines

本仓库是面向 Claude Code 的 `imagegen` skill，所有回答与文档默认使用中文；技术术语、命令和代码标识符保持原文。skill 的可分发内容位于 `skills/imagegen/`；改动流程或参数时同步更新其中的 `SKILL.md` 与 `references/`。

## 项目结构与模块

- `skills/imagegen/scripts/image_gen.py`：Doubao Seedream 5.0 Lite/Pro 的受校验 CLI；不要以临时 SDK 脚本替代它。
- `skills/imagegen/scripts/remove_chroma_key.py`：将均匀色键背景转换为透明 alpha。
- `tests/`：`pytest` 单元测试，分别覆盖 CLI 与色键处理。
- `skills/imagegen/references/`：模型能力、CLI、提示词、模板和视觉示例说明；修改流程或参数时同步更新对应文件。
- `skills/imagegen/assets/examples/`：按需使用的典型视觉参考，不是默认模型输入；新增或调整图片时同步更新 `references/visual-examples.md`。
- `skills/imagegen/logo/`：README 横幅和方形 skill 图标，仅用于项目品牌展示。
- `skills/imagegen/requirements.txt`：唯一依赖入口，包含运行与测试依赖。
- `pyproject.toml`：项目元数据和 `pytest` 配置，不声明第二套安装依赖。
- 单图默认放在当前项目根目录，以清理后的 prompt 命名；组图默认放在 `images/`；不得提交 `.env`、缓存或请求状态文件。
- `README.md`：GitHub 英文入口，包含安装、配置和使用条件。
- `README-zh.md`：GitHub 中文入口。

## 开发与测试命令

安装全部依赖（运行与测试）：

```powershell
python -m pip install -r skills/imagegen/requirements.txt
```

运行完整测试：

```powershell
python -m pytest -q
```

调试 CLI 时优先使用不计费的预检：

```powershell
python skills\imagegen\scripts\image_gen.py generate --model lite --prompt "测试" --out output\test.png --dry-run
```

真实请求前确认 `ARK_API_KEY` 已在 skill-local `.env` 或进程环境中配置；不得输出或提交密钥。agent 创建的 prompt 临时文件统一使用项目根目录 `.seedream-prompt-<random-id>.txt`，其中 `<random-id>` 为 6–64 位 ASCII 字母、数字、`_` 或 `-`，并配合 `--cleanup-prompt-file`。不得删除用户输入或不确定请求状态文件。

## 代码风格与命名

使用 Python 3、4 空格缩进、UTF-8 编码和类型注解。函数、变量使用 `snake_case`，常量使用 `UPPER_SNAKE_CASE`，测试文件为 `test_<模块>.py`。保持现有标准库优先的实现方式；错误信息应为清晰的中文，并避免泄露密钥、URL token 或 Base64 内容。没有配置格式化或 lint 工具，提交前至少运行测试并保持改动小而聚焦。

## 测试准则

为每个新参数校验、模型能力分支、输出冲突处理或失败恢复补充针对性测试。测试不得访问真实 Ark API、读取真实 `.env` 或产生计费请求；使用临时目录、mock 和 `--dry-run` 覆盖边界条件。修改图片处理逻辑时，同时验证格式、尺寸与 alpha 行为。

## 提交与 PR

使用祈使句 Conventional Commit，例如 `fix: reject Pro web-search` 或 `docs: clarify chroma-key workflow`。PR 应说明目的、影响的模型/CLI 行为、执行过的测试及文档更新；涉及视觉输出时附示例或截图。禁止提交 `.env`、生成图片和不确定状态的 `.seedream-request.json`。

提交前至少运行 `python -m pytest -q`，并检查 `git diff --check`、`git status --short`。仅提交与当前任务相关的文件；不要使用未审查的 `git add -A` 覆盖混合工作区。

## 发布与敏感文件

- 远程仓库：`https://github.com/YFan945/Seedream-Imagegen`。
- 公开描述：专为 Claude Code 提供豆包生图能力的 skill。
- 真实 `.env`、`output/`、`images/`、`tmp/`、缓存、生成图片和请求状态文件不得进入 Git。
- 真实 Ark 请求可能计费；测试必须使用 mock、临时目录和 `--dry-run`，不得访问真实 API。

## Agent 专项规则

遵循 `skills/imagegen/SKILL.md`：不得擅自替换用户选择的 Lite/Pro；任何可能计费的迭代请求须先取得授权；遇到 `pending` 或 `ambiguous` 请求状态必须停止，不能自动重试。
