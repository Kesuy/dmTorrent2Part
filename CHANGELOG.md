# Changelog

本文件记录实际已经进入发布版本的功能。未完成的计划不会再提前写入正式版本说明。

## v1.1.4

### Added

- Torrent 文件树支持多选：普通鼠标拖选连续文件、`Ctrl` 点选/取消单个文件、`Shift` 连续范围选择。
- 多选文件后，下方 ED2K 文本框同时显示所有已取得的 ED2K 链接，**一行一个链接**。
- “复制 ED2K”在多选状态下会一次复制全部可用链接，并以换行分隔，便于直接粘贴到 eMule/文本工具。

### Improved

- ED2K 文本框扩大为多行视图；多选时显示“已选择 / 可用 ED2K / 缺失 ED2K”数量。
- 多选中存在尚无 ED2K 的文件时，只显示真实可用链接，不生成占位或伪链接；可继续使用“本地下载根目录 + 批量计算缺失 ED2K”。
- 单文件选择、单文件本地计算、Torrent 诊断/修复和旧 `.part/.part.met` 功能保持原有行为。

## v1.1.3

### Added

- 主界面新增可见的 **“诊断”** 按钮，可检查 torrent 的 bencode 主体、文件头 BOM 和文件尾附加数据。
- 主界面新增可见的 **“修复 Torrent…”** 按钮，可导出 `*.fixed.torrent`。
- 打开失败时自动运行 Torrent 诊断；属于可恢复的兼容问题时直接提示用户导出修复版。
- 软件窗口标题显示完整版本号：`dmTorrent2Part v1.1.3 - Torrent → ED2K`。
- Release 流程从本文件提取当前版本说明，GitHub Release 页面不再只有 `Full Changelog` 链接。

### Fixed

- 修复 `Queen8-QE021~QE030.torrent` 这类 **bencode 主体正常、文件尾额外带 CRLF** 的种子兼容问题。
- bencode 默认兼容模式支持文件头 UTF-8 BOM，以及文件尾 CR/LF、空格、Tab、BOM 的组合；严格模式仍保持严格 EOF 校验。
- 修复早期 `torrent_repair.py` 调用了不存在的 `decode(..., return_end=True)` 接口、导致诊断核心实际不可用的问题。
- 修复 v1.1.3 早期误发布的半成品：重新构建 EXE、覆盖 Release Asset，并把 `v1.1.3` tag 更新到最终通过 CI 的提交。

### Safety

- 自动修复只删除 **文件头 BOM** 和 **bencode 根对象之后的无害空白/BOM**。
- 不重新编码 bencode 主体、不修改 `info` 字典原始字节，因此不会改变 torrent info hash。
- 若根对象之后存在非空白随机数据，只诊断、不自动截断，避免误删未知有效内容。

## v1.1.2

### Notes

- 这是一次过渡版本，主要调整版本/文档与发布准备。
- 当时计划中的“Torrent 诊断 / 修复 Torrent”并没有完整进入 GUI；相关功能以 v1.1.3 实际发布内容为准。

## v1.1.1

### Fixed

- bencode 解析从严格 EOF 模式调整为现实兼容模式，允许部分下载器/旧制种工具写入的尾随 CRLF 或空白。
- 对真正的异常尾部数据仍保持报错，避免静默读取明显损坏的文件。

## v1.1.0

### Added

- 产品主流程调整为 Torrent → ED2K。
- 打开 torrent 后按原目录结构显示全部文件。
- 支持读取 torrent 内嵌 ED2K；没有 ED2K 时可用完整本地文件计算。
- 支持 BitTorrent v1、v2-only、v1/v2 hybrid、旧编码路径和 BitComet 常见 ED2K 扩展。
- 保留 BT 未完成文件 → eMule `.part/.part.met` 兼容功能。
- 使用旧版程序提取的原始图标生成 Windows 单文件 EXE。

### Notes

- 普通 torrent 的 SHA-1/SHA-256 不能反推出 ED2K/MD4；torrent 未内嵌 ED2K 时必须读取完整本地文件才能得到最终 ED2K。

## v1.0.0

### Added

- clean-room Python 重写首个正式版本。
- BitTorrent v1 piece 校验与 eMule `.part/.part.met` 生成。
- Windows GUI / CLI 与 GitHub Actions EXE 构建流程。
