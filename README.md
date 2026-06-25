# Wulfram2 Core

Shared Python core layer for the Wulfram II revival work: the wire protocol **and** the deterministic sim/physics kernel.

This repo contains the wire-format codec, packet constants, quantizer helpers, shared entity definitions, gameplay constants, and the shared deterministic simulation kernel (`sim_kernel_cpp/`) used by both the Python server and Python client work.

## Package

```text
wulfram2_protocol/
  codec.py        Bitstream helpers and framing
  packets.py      Packet opcodes, names, and shared protocol constants
  quantizers.py   Shared quantizer tables and helpers
  entities.py     Entity enums and vehicle config data
  constants.py    Shared physics and timing constants
```

## What this repo is for

Use this repo when you need:

- packet opcodes and packet-name lookup
- shared compression / quantization math
- entity and vehicle enum/config definitions
- one protocol surface imported by both client and server code

This repo is intentionally narrow: it is the shared protocol/decode layer, not the full game client or full server.

## Using it with the server repo

The current `wulfram-server` scripts look for this repo as a sibling directory named `shared`.

Recommended layout:

```text
work/
  server/   <- https://github.com/easystardev/wulfram-server
  shared/   <- this repo
```

Example:

```powershell
mkdir C:\dev\wulfram-runtime
cd C:\dev\wulfram-runtime
git clone https://github.com/easystardev/wulfram-server.git server
git clone https://github.com/easystardev/wulfram2-core.git shared
```

You can also install it into an environment if you want direct imports:

```powershell
uv pip install -e .
```

## Example imports

```python
from wulfram2_protocol.codec import BitReader, BitWriter
from wulfram2_protocol.entities import EntityType, VEHICLE_PHYSICS_CONFIGS
from wulfram2_protocol.packets import PacketType, get_packet_name
```

## Status

This package is extracted from the larger `wolfram` workspace and is being kept public so other repos can consume the same shared protocol definitions without copying them.

It is focused on interoperability: shared wire-format definitions, codec helpers, and gameplay-facing enums/constants. It does not ship original game assets or original client/server source.

## License

[MIT](LICENSE). Independent, fan-made preservation / reverse-engineering work —
not affiliated with the original developers or rights holders, and ships no
original game assets or binaries.
