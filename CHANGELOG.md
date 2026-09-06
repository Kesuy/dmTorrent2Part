# Changelog

## v1.1.3

### Added

- Added Torrent compatibility diagnosis before opening failure dialogs.
- Added Torrent repair workflow for recoverable malformed torrent tails.
- Added GUI version display in the application title.

### Fixed

- Fixed non-standard torrent files with harmless trailing data (CRLF/BOM/whitespace) being treated as corrupted.
- Improved error reporting so users can distinguish repairable compatibility issues from real corruption.

### Improved

- Release notes now include explicit version changes instead of relying only on GitHub compare links.
- Added regression coverage for real-world torrent compatibility cases.

## v1.1.2

### Added

- Added torrent compatibility diagnostics.
- Added cleaned torrent export workflow for recoverable malformed tails.
  - Detect harmless trailing CRLF, whitespace, and BOM.
  - Keep strict rejection for real corrupted trailing data.

### Fixed

- Fixed some 迅雷 / 国产站点 generated torrent files failing to open.
- Fixed `trailing data after encoded value` caused by valid bencode followed by harmless bytes.

### Improved

- Improved error messages to distinguish recoverable compatibility issues from damaged torrent files.
- Added regression coverage for real-world torrent compatibility cases.

## v1.1.1

### Fixed

- 修复部分迅雷、国产站点生成的 torrent 无法打开的问题。
- bencode 解析从严格 EOF 模式调整为兼容模式：允许文件尾存在无害的空格、Tab、CRLF、UTF-8 BOM。
- 对真正的异常尾部垃圾仍保持报错，避免静默读取错误文件。
- 优化错误场景兼容性，避免出现 `trailing data after encoded value` 导致正常 torrent 无法导入。

### Improved

- 增加现实世界 torrent 兼容性。
- 为后续版本增加 torrent 解析兼容回归测试。

## v1.1.0

### Added

- Torrent → ED2K 主流程。
- BitTorrent v1/v2/hybrid torrent 文件解析。
- BitComet ED2K 扩展读取。
- 本地文件 ED2K 计算。
- 保留未完成文件 → eMule `.part/.part.met` 功能。
- Windows 单文件 EXE 发布。

### Notes

- 普通 torrent 不一定包含 ED2K 哈希；没有内置 ED2K 时需要完整本地文件计算。
