# dmTorrent2Part

一个面向现代 Windows 的 **clean-room Python 重写版** dmTorrent2Part。

它用于把 BitTorrent 客户端留下的未完成文件中，**已经通过 torrent SHA-1 校验的分片**转换成 eMule/eDonkey 可继续下载的 `.part` + `.part.met`。

> 本项目没有使用原程序源码。实现依据公开的 BitTorrent v1、eD2K / eMule `.part.met` 格式，以及对旧程序公开可见行为的兼容性观察重新实现。

## 为什么重写

旧版 dmTorrent2Part 已多年停止维护，原程序是 32 位原生 Windows 程序并经过压缩/保护。与其维护不可读的反编译代码，本项目只复现有价值的兼容行为：

- 读取 BitTorrent v1 `.torrent`
- 多文件 torrent 文件列表选择
- SHA-1 验证未完成文件中真正完整的 BT 分片
- 解析 `ed2k://|file|...` 链接及可选 `p=` 分块哈希
- 生成 eMule/eDonkey `.part` / `.part.met`
- 4 GiB+ 文件使用 large-file part.met 版本
- 多文件 torrent 的跨文件边界分片采用保守策略：无法仅凭单个文件验证时标记为缺口，避免把错误数据交给 eMule
- 中文 GUI + CLI
- GitHub Actions 自动测试并打包 Windows 单文件 EXE

## 使用方法

### Windows 图形界面

```powershell
python -m dmtorrent2part
```

依次选择：

1. `.torrent`
2. torrent 内目标文件（单文件种子会自动只有一项）
3. BT 客户端留下的未完成文件
4. 对应文件的 ED2K 链接
5. 输出目录与 Part 编号
6. 点击“开始转换”

输出例如：

```text
001.part
001.part.met
```

把两个文件放入 eMule 的临时目录，再让 eMule 重新载入即可。

### CLI

```powershell
dmTorrent2Part movie.torrent movie.mkv "ed2k://|file|movie.mkv|123456789|0123456789ABCDEF0123456789ABCDEF|/" -o output
```

多文件种子可先查看索引：

```powershell
dmTorrent2Part package.torrent dummy "ed2k://|file|x|0|00000000000000000000000000000000|/" --list
```

再用 `--index N` 选择目标文件。

## 安装 / 开发

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
pytest -q
python -m dmtorrent2part
```

## 打包 EXE

```powershell
pyinstaller --noconfirm --clean --onefile --windowed --name dmTorrent2Part dmTorrent2Part.py
```

生成：`dist/dmTorrent2Part.exe`

仓库内 `.github/workflows/windows-build.yml` 也会在 Windows Runner 上自动测试和构建 EXE artifact。

## 数据安全策略

dmTorrent2Part **不会把“文件里非零的数据”直接视为已完成**。只有 torrent v1 SHA-1 校验通过的完整 piece 才会写入新 `.part`，其余范围都记录为 gap 交给 eMule 重下。

这意味着在多文件 torrent 中，如果一个 BT piece 横跨两个文件，而你只给程序其中一个文件，那个边界 piece 无法独立验证。本项目会宁可少保留一些数据，也不把未经验证的数据误标成完整。

## 已知限制

- 目前支持 BitTorrent v1；v2-only torrent 不支持。带 v1 `pieces` 的 hybrid torrent 可用。
- 要生成可继续下载的 eMule 任务，必须有匹配目标文件的 ED2K 链接。
- `.part.met` 会写入 ED2K 链接自带的 `p=` 分块哈希；普通 ED2K 链接没有 `p=` 时不伪造 hashset，由 eMule 后续从网络获取。
- “仅生成 `.part.met`”适用于你已经自行准备好对应 `.part` 的情况。

## License

MIT
