# 色键转透明参考

本文是 `remove_chroma_key.py` 的唯一参数与失败恢复说明。透明背景 prompt 模板见 `sample-prompts.md`；主生图 CLI 见 `cli.md`。

## 适用边界

适用于完全平坦、高饱和、颜色已知的绿/洋红/蓝/青背景，以及与键色色相族分离的实心主体。毛发、烟雾、液体、玻璃、薄纱、运动模糊、软阴影、强反光或包含键色色相族的主体不属于可靠范围；改用专业分割工具。

## 推荐命令

始终从任意 CWD 使用 skill 绝对路径，并把实际生成键色显式传入：

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/remove_chroma_key.py" `
  --input "${CLAUDE_PROJECT_DIR}/tmp/seedream/source.png" `
  --out "${CLAUDE_PROJECT_DIR}/output/subject.png" `
  --key-color 00ff00 --soft-matte --despill --border-connected
```

先不用 `--force`。只有用户明确授权覆盖时才添加它。

## 参数

- `--key-color RRGGBB`：推荐；必须与实际背景一致。
- `--auto-key border|corners`：仅当四角一致、dominant cluster 占比与均匀度通过时使用；多峰、渐变、低饱和或角落不一致会在写文件前失败。
- `--tolerance 0..255`：hard key 的逐通道容差，默认 12。
- `--soft-matte`：使用稳定色度参考估算连续 alpha，并对 partial pixels 做 foreground recovery。
- `--despill`：只处理 partial edge；fully opaque RGB 保持不变。
- `--border-connected`：只移除与画布边框连通的键色区域，避免主体内部孤立键色孔洞。
- `--edge-contract 0..16`：只收缩 chroma matte。
- `--edge-feather 0..64`：只向主体内侧柔化 chroma matte，不复活 `source alpha=0`。
- `--transparent-threshold` / `--opaque-threshold`：旧版兼容参数；新 soft matte 不再用动态距离阈值估算 alpha，不应依赖它们调结果。

## I/O 与 alpha 契约

- 输入必须是单帧静态图片；动画显式拒绝。HEIC/HEIF 由 `pillow-heif` 支持。
- 单文件不超过 30,000,000 bytes，总像素不超过 36,000,000。
- EXIF Orientation 在处理前转正；16-bit/HDR 输入降级为 RGBA8。ICC、EXIF、DPI 和动画 metadata 不保留。
- 输出仅支持 PNG/WebP；编码后会重开验证格式、尺寸和 alpha。
- `source_alpha` 与 `chroma_matte` 分离，最终为二者相乘；输入 alpha 1～254 不会被 matte noise floor 误删。
- 拒绝 input=output。默认原子 no-clobber；失败、中断、磁盘或编码错误不破坏旧输出。

## 诊断与交付检查

CLI 分别报告 `source-transparent`、`key-matched`、`final-transparent`、`partial` 和 `total`。全透明、全不透明或零匹配会警告。

交付前只做一次轻量检查：

1. 重开文件，确认格式、尺寸和 alpha；结果不是意外全空或全不透明。
2. 在棋盘格或一个高对比底色上查看，确认无明显孔洞、主体变色、黑边或键色边。
3. 失败时保留源图与结果并报告；再次调用付费生成前必须取得授权。
