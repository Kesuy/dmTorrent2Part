# dmTorrent2Part

`dmTorrent2Part` 是一个面向 Windows 的 **Torrent → ED2K** 工具，并保留旧版程序最有价值的“BT 未完成文件 → eMule `.part/.part.met`”兼容功能。

本项目是 clean-room Python 重写：没有使用旧程序源码，实现依据公开的 BitTorrent / ED2K / eMule 文件格式以及旧程序可观察行为重新实现。

## 主要功能

### 1. Torrent → ED2K（默认功能）

打开 `.torrent` 后，程序会按种子原有目录结构列出全部文件：

- torrent 内本身带有 ED2K 哈希时，点击文件即可直接显示并复制 `ed2k://` 链接；
- torrent 没有 ED2K 哈希时，可选择对应的本地完整文件计算；
- 可选择下载根目录，自动匹配 torrent 中的文件并批量计算缺失的 ED2K；
- 自动跳过 BitTorrent padding 文件；
- 计算在后台线程运行，不阻塞界面。

> **为什么有些 torrent 不能“直接转换”？**  
> BitTorrent v1 保存的是 SHA-1 piece 哈希，BitTorrent v2 使用 SHA-256 Merkle tree，而 ED2K 使用 MD4/ED2K 哈希。不同哈希之间不能相互换算。因此，只有种子本身携带 ED2K 扩展字段时才能仅凭 torrent 立即得到链接；否则必须读取本地完整文件计算 ED2K。本程序不会伪造链接。

### 2. 更广的 Torrent 兼容

文件列表 / ED2K 主功能支持：

- BitTorrent v1 单文件、多文件种子；
- BitTorrent v2-only `file tree`；
- v1/v2 hybrid torrent；
- `name.utf-8` / `path.utf-8`；
- torrent 声明的 `encoding` / `codepage`（例如 GBK/GB2312 等旧种子）；
- BitComet 常见的 `ed2k` 扩展：单文件、逐文件、连续 16-byte 哈希表、哈希列表、32 位十六进制形式；
- padding 文件识别；
- 即使 v1 `pieces` 缺失或异常，仍尽可能读取文件树和已有 ED2K 信息。

### 3. 本地 ED2K 计算

- 使用 eMule 兼容的 9,728,000-byte 分块规则；
- 正确处理文件大小刚好为 ED2K 分块整数倍的兼容行为；
- 优先使用 PyCryptodome 的 C 实现加速 MD4；仍保留纯 Python fallback；
- 支持多 GB 文件和批量计算。

### 4. 旧版 Part 转换仍保留

第二个标签页保留 v1.0 的兼容功能：

- 校验 BitTorrent v1 SHA-1 pieces；
- 只把校验通过的数据写入 eMule `.part`；
- 生成 `.part.met`；
- 支持仅生成 `.part.met`；
- 支持 4 GiB+ 文件；
- 多文件 torrent 的跨文件边界 piece 采用保守策略，避免把未经验证的数据标记为完整。

该功能依赖 **有效的 BitTorrent v1 pieces**。v2-only torrent 可用于 Torrent → ED2K，但不能用于旧 Part 恢复流程。

## Windows 图形界面

直接运行 Release 中的 `dmTorrent2Part.exe`。

默认打开 **Torrent → ED2K** 标签页：

1. 点击“打开 Torrent…”；
2. 左侧目录树会显示种子中的全部文件；
3. 点击文件：
   - 如果 torrent 已带 ED2K，链接立即显示；
   - 如果没有，点击“选择本地文件计算…”；
4. 如果已经下载了整个 torrent，可选择“本地下载根目录”，再点“批量计算缺失 ED2K”；
5. 点击“复制 ED2K”。

也可以把 `.torrent` 路径作为启动参数传给程序，启动后自动打开。

## CLI

只查看 torrent 文件与 ED2K 状态：

```powershell
dmTorrent2Part example.torrent
```

指定一个本地完整文件计算选中索引的 ED2K：

```powershell
dmTorrent2Part example.torrent --index 2 --local-file "D:\Downloads\movie.mkv"
```

按下载根目录批量匹配并输出 ED2K：

```powershell
dmTorrent2Part example.torrent --root "D:\Downloads"
```

旧版 Part 转换命令仍兼容：

```powershell
dmTorrent2Part movie.torrent movie.mkv "ed2k://|file|movie.mkv|123456789|0123456789ABCDEF0123456789ABCDEF|/" -o output
```

## 安装 / 开发

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
pytest -q
python -m dmtorrent2part
```

## Windows EXE

GitHub Actions 会在 Windows Runner 上执行测试并用 PyInstaller 生成单文件 EXE。EXE 和窗口使用从旧版 `dmTorrent2Part` 提取的原始 `MAINICON` 图标资源。

本地构建：

```powershell
python -c "from dmtorrent2part.icons import write_ico; write_ico('dmTorrent2Part.ico')"
pyinstaller --noconfirm --clean --onefile --windowed --icon dmTorrent2Part.ico --name dmTorrent2Part dmTorrent2Part.py
```

## 数据安全

旧 Part 转换不会把“文件里已有的数据”直接视为有效。只有 torrent v1 SHA-1 校验通过的完整 piece 才写入新 `.part`，其余范围都作为 gap 交给 eMule 重下。

ED2K 主功能同样不会从 SHA-1 / SHA-256 猜测 MD4：没有内嵌 ED2K 时必须从完整本地文件计算。

## License

MIT
