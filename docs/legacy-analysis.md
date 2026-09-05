# Legacy dmTorrent2Part analysis

This document records only compatibility-relevant observations from the user-supplied legacy executable. No original source code is included in this repository.

## Sample

- File: `dmTorrent2Part.exe`
- SHA-256: `de6caafa363b062e93ffcfe467687d425fdaceea971b67d963713c2af716fc5d`
- Format: 32-bit PE GUI executable (x86)
- CLR header: absent; this is not a .NET executable
- PE timestamp: 1992-06-19, inconsistent with the application's known era and therefore not treated as trustworthy provenance
- Import/section layout strongly suggests packing/protection, so machine-code decompilation would produce poor maintenance source

## Framework / UI clues

Static resources contain Borland/VCL-style identifiers including `TPF0` / `TFormMain` and `Software\\Borland\\Database Engine`. The embedded form resources expose compatibility-relevant controls and labels such as:

- `.torrent` input
- incomplete-file input
- `.part.met` number
- ED2K link input
- torrent file grid (name / size / ed2k)
- “show pieces/gaps” operation
- “only part.met” option
- create operation
- SHA-1 hash component identifier (`THash_SHA1`)

Those observations are used only to define the expected user workflow. The Python implementation is new code based on public protocol/file-format behavior.

## Clean-room decision

A literal decompilation was intentionally rejected as the implementation strategy because:

1. the binary is packed/protected and would yield low-quality pseudo-code;
2. the application behavior is mainly an interoperability pipeline between documented formats;
3. a small, testable parser/verifier/writer is safer to maintain than reconstructed 32-bit GUI code;
4. no legacy assets or source code are required to achieve file-format compatibility.

The rewrite therefore implements the behavior independently: parse BitTorrent v1 metadata, SHA-1 verify reusable pieces, parse the ED2K file link, and write eMule-compatible part/gap metadata.
