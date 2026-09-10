"""
Packet type definitions, name lookups, and shared protocol constants.

Builder functions remain in the server module; this file provides
the enums, constants, and compression helpers they depend on.
"""

import math
import os
from .hud_state import HUD_FRACTION_MAX, HUD_FRACTION_RANGE, validate_hud_fraction_schema
from typing import Optional


def _read_float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


# ============ Packet Types ============

class PacketType:
    """Wire packet type opcodes."""
    # D_ protocol (service-layer control over UDP)
    D_IGNORE = 0x01
    D_ACK = 0x02
    D_HANDSHAKE = 0x03
    D_SET_START = 0x04

    # Core protocol
    D_PROTOCOL = 0x08
    HELLO = 0x13
    PLAYER = 0x17
    PLAYER_INFO = 0x18  # Spawns local player vehicle
    TANK = 0x18  # Legacy alias
    ADD_TO_ROSTER = 0x1A
    UPDATE_STATS = 0x1C
    BIRTH_NOTICE = 0x1E
    GAME_CLOCK = 0x2F
    COMM_MESSAGE = 0x1F
    LOGIN_STATUS = 0x22
    MOTD = 0x23
    REQUEST_START = 0x23  # Legacy alias; older code often calls this MOTD
    LOGIN_REQUEST = 0x21
    BEHAVIOR = 0x24
    REINCARNATE = 0x25
    RETARGET = 0x26
    TEAM_INFO = 0x28
    DROP_REQUEST = 0x2B
    WEAPON_DEMAND = 0x2E
    TRANSLATION = 0x32
    WANT_UPDATES = 0x39
    IDENTIFIED_UDP = 0x4D
    BPS = 0x4E
    UPDATE_ARRAY = 0x0E
    UPDATE_ARRAY_STREAM = 0x10
    WORLD_STATS = 0x16
    PING_REQUEST = 0x0B
    STATE_REQUEST = 0x0C
    VIEW_UPDATE = 0x0F
    DELETE_OBJECT = 0x15
    ACTION_DUMP = 0x09
    ACTION_UPDATE = 0x0A
    INPUT_FEEDBACK = 0x40
    DEBUG_SYNC = 0x60

    # Additional protocol packets
    TRANSIENT_ARRAY = 0x0D
    SHIP_STATUS = 0x27
    CARRYING_INFO = 0x29
    UPLINK_INFO = 0x2A
    WARP_STATUS = 0x30
    CONTINUOUS_SOUND = 0x31
    STRING_VALUE = 0x36
    VERSION_ERROR = 0x37
    RESET_GAME = 0x3F
    SHUTDOWN = 0x41
    ROUTING_PING = 0x4C
    MILTAB = 0x50
    VIDEOMSG = 0x53
    DEBUG_COORDS = 0x55


# ============ Packet Name Lookup ============

PACKET_NAMES = {
    0x00: "STREAM_CHECK",
    0x01: "D_IGNORE",
    0x02: "D_ACK",
    0x03: "D_HANDSHAKE",
    0x04: "D_SET_START",
    0x05: "D_TYPE5",
    0x06: "D_TYPE6",
    0x07: "D_TYPE7",
    0x08: "HELLO_ACK",
    0x09: "ACTION_DUMP",
    0x0A: "ACTION_UPDATE",
    0x0B: "PING_REQUEST",
    0x0C: "STATE_REQUEST",
    0x0D: "TRANSIENT_ARRAY",
    0x0E: "UPDATE_ARRAY",
    0x0F: "VIEW_UPDATE",
    0x10: "UPDATE_ARRAY_STREAM",
    0x11: "HUD_MESSAGE",
    0x12: "LAG_FIX",
    0x13: "HELLO",
    0x14: "HIDE_OBJECT",
    0x15: "DELETE_OBJECT",
    0x16: "WORLD_STATS",
    0x17: "PLAYER",
    0x18: "TANK",
    0x19: "TANK_RESEND",
    0x1A: "ADD_TO_ROSTER",
    0x1B: "REMOVE_FROM_ROSTER",
    0x1C: "UPDATE_STATS",
    0x1D: "DEATH_NOTICE",
    0x1E: "BIRTH_NOTICE",
    0x2F: "GAME_CLOCK",
    0x1F: "COMM_MESSAGE",
    0x20: "CHAT",
    0x21: "LOGIN_REQUEST",
    0x22: "LOGIN_STATUS",
    0x23: "REQUEST_START",
    0x24: "BEHAVIOR",
    0x25: "REINCARNATE",
    0x26: "RETARGET",
    0x28: "TEAM_INFO",
    0x2B: "DROP_REQUEST",
    0x2C: "SPACE_MAP_UPDATE",
    0x2D: "SUPPLY_SHIP_INFO",
    0x2E: "WEAPON_DEMAND",
    0x32: "TRANSLATION",
    0x33: "TRANSLATION_ACK",
    0x34: "MODEM",
    0x35: "VIEWPOINT_INFO",
    0x39: "WANT_UPDATES",
    0x27: "SHIP_STATUS",
    0x29: "CARRYING_INFO",
    0x2A: "UPLINK_INFO",
    0x30: "WARP_STATUS",
    0x31: "CONTINUOUS_SOUND",
    0x36: "STRING_VALUE",
    0x37: "VERSION_ERROR",
    0x38: "DOCKING",
    0x3a: "BEACON_REQ",
    0x3B: "BEACON_MODIFY",
    0x3C: "BEACON_STATUS",
    0x3D: "BEACON_DELETE",
    0x3E: "LOAD_STATUS",
    0x3F: "RESET_GAME",
    0x40: "INPUT_FEEDBACK",
    0x41: "SHUTDOWN",
    0x4C: "ROUTING_PING",
    0x4D: "IDENTIFIED_UDP",
    0x55: "DEBUG_COORDS",
    0x50: "MILTAB",
    0x53: "VIDEOMSG",
    0x4E: "BPS",
    0x4F: "KUDOS",
    0x54: "VOICE_DATA",
    0x60: "DEBUG_SYNC",
}


def get_packet_name(pkt_type: int) -> str:
    return PACKET_NAMES.get(pkt_type, f"UNKNOWN_{pkt_type:02X}")


# ============ BEHAVIOR Packet Layout Constants ============

BEHAVIOR_HEADER_SIZE = 95
BEHAVIOR_WEAPON_UNITS = 4
BEHAVIOR_WEAPON_SLOTS = 13
BEHAVIOR_WEAPON_SLOT_SIZE = 45


# ============ Vector Quantizer Constants ============
# Defaults match wulf-forge unless overridden via env vars.

VEC_POS_MAX = _read_float_env("WULFRAM_VEC_POS_MAX", 8192.0)
VEC_POS_RANGE = _read_float_env("WULFRAM_VEC_POS_RANGE", 16384.0)
# Current shared velocity quantizer defaults:
# max=200, range=400, 16-bit precision. A broader 1000/2000 range reduces
# replay/update precision enough to undermine the old client's tighter
# replay validation path.
VEC_VEL_MAX = _read_float_env("WULFRAM_VEC_VEL_MAX", 200.0)
VEC_VEL_RANGE = _read_float_env("WULFRAM_VEC_VEL_RANGE", 400.0)
VEC_ROT_MAX = _read_float_env("WULFRAM_VEC_ROT_MAX", 6.3)
VEC_ROT_RANGE = _read_float_env("WULFRAM_VEC_ROT_RANGE", 12.6)
VEC_SPIN_MAX = _read_float_env("WULFRAM_VEC_SPIN_MAX", 200.0)
VEC_SPIN_RANGE = _read_float_env("WULFRAM_VEC_SPIN_RANGE", 400.0)


# ============ Health / Energy Quantizer Constants ============

HEALTH_MAX = _read_float_env("WULFRAM_HEALTH_MAX", 1.0)
HEALTH_RANGE = _read_float_env("WULFRAM_HEALTH_RANGE", HEALTH_MAX)
ENERGY_MAX = _read_float_env("WULFRAM_ENERGY_MAX", HEALTH_MAX)
ENERGY_RANGE = _read_float_env("WULFRAM_ENERGY_RANGE", ENERGY_MAX)
HEALTH_NORMALIZED = os.environ.get("WULFRAM_HEALTH_NORMALIZED", "1") == "1"

_RAW_HEALTH_MODE = os.environ.get("WULFRAM_HEALTH_RAW_MODE", "wulf").strip().lower()
_ALLOW_LINEAR_HEALTH = os.environ.get("WULFRAM_ALLOW_LINEAR_HEALTH", "0") == "1"
if _RAW_HEALTH_MODE in ("linear", "lin") and not _ALLOW_LINEAR_HEALTH:
    HEALTH_RAW_MODE = "wulf"
elif _RAW_HEALTH_MODE:
    HEALTH_RAW_MODE = _RAW_HEALTH_MODE
else:
    HEALTH_RAW_MODE = "wulf"

ENTITY_VITALS_MODE = os.environ.get("WULFRAM_ENTITY_VITALS_MODE", "health").strip().lower()


# ============ Local State Turret Config ============

LOCAL_STATE_TURRET_HEADER_BITS = int(os.environ.get("WULFRAM_LOCAL_STATE_TURRET_HEADER_BITS", "0"))
LOCAL_STATE_TURRET_PRIORITY = int(os.environ.get("WULFRAM_LOCAL_STATE_TURRET_PRIORITY", "15"))


# ============ Compression / Quantization Helpers ============

def compress_value(val: float, max_val: float, range_val: float, total_bits: int = 16) -> int:
    """Compress a value using the same inverse quantization as wulf-forge."""
    if not math.isfinite(val):
        # TOTAL SERIALIZER GUARD: this quantizer is on every replication path
        # (UPDATE_ARRAY / state-sync), called from BOTH the per-client tick loop
        # and the shared UDP thread. A non-finite physics value (e.g. an attitude
        # acos/asin domain NaN, or a spring-instability inf) must never reach
        # int(NaN) below and crash the thread — encode it as the neutral 0 value
        # so the packet stays well-formed and the server keeps running. Fires
        # ONLY on already-broken (non-finite) input. (A3 soak, 2026-06-01.)
        return 0
    min_val = max_val - range_val
    if val == 0.0:
        return 0
    if val > max_val:
        val = max_val
    if val < min_val:
        val = min_val
    denom = (1 << total_bits) - 2
    delta = max_val - val
    scaled = (delta * denom) / range_val
    return int(scaled) + 1


def compress_position(value: float, max_val: float = None, range_val: float = None,
                      total_bits: int = 16):
    """Compress a position value. Returns (header, quantized_value)."""
    if max_val is None:
        max_val = VEC_POS_MAX
    if range_val is None:
        range_val = VEC_POS_RANGE
    return (15, compress_value(value, max_val, range_val, total_bits=total_bits))


def compress_rotation(value: float, max_val: float = None, range_val: float = None,
                      total_bits: int = 16):
    """Compress a rotation value. Returns (header, quantized_value)."""
    if max_val is None:
        max_val = VEC_ROT_MAX
    if range_val is None:
        range_val = VEC_ROT_RANGE
    return (15, compress_value(value, max_val, range_val, total_bits=total_bits))


def encode_health_bits(value: float, total_bits: int = 10, *, max_val: Optional[float] = None,
                       range_val: Optional[float] = None) -> int:
    """Encode health/energy for local-state + TankPacket vitals.

    Modes:
    - "linear": value 0..1 mapped to [0, 2^bits-1]
    - "wulf": wulf-forge quantizer (raw=1 -> max)
    """
    if value is None:
        value = 0.0
    max_val = HEALTH_MAX if max_val is None else max_val
    range_val = HEALTH_RANGE if range_val is None else range_val
    value = float(value)
    if HEALTH_NORMALIZED and max_val > 0:
        value = value * max_val
    if max_val > 0:
        value = max(0.0, min(max_val, value))
    else:
        value = max(0.0, value)
    if HEALTH_RAW_MODE in ("wulf", "wulfforge"):
        return compress_value(value, max_val, range_val, total_bits=total_bits)
    denom = (1 << total_bits) - 1
    if denom <= 0:
        return 0
    if max_val <= 0:
        return 0
    scaled = value / max_val
    return int(round(scaled * denom)) & denom


def write_local_player_state(bw, include: bool,
                             weapon_id: int = 0,
                             health: float = 1.0,
                             fuel: float = 1.0,
                             ammo_count_bits: int = 0,
                             ammo_count: int = 0,
                             primary_turret_bits: int = 0,
                             primary_turret_angle: float = 0.0,
                             secondary_turret_bits: int = 0,
                             secondary_turret_angle: float = 0.0,
                             turret_max: float = HUD_FRACTION_MAX,
                             turret_range: float = HUD_FRACTION_RANGE,
                             include_ammo_turrets: bool = True) -> None:
    """Write local player state block used by UPDATE_ARRAY and PLAYER_INFO.

    Wire format:
    - 1 bit flag
    - weapon type (5 bits)
    - health (10 bits)
    - fuel/energy (10 bits)
    - ammo bitmask bits (size from ammo slot state pool)
    - optional primary/secondary turret angles
    """
    if not include:
        bw.write_bits(1, 0)
        return

    bw.write_bits(1, 1)
    bw.write_bits(5, weapon_id & 0x1F)
    bw.write_bits(10, encode_health_bits(health, total_bits=10))
    bw.write_bits(10, encode_health_bits(fuel, total_bits=10, max_val=ENERGY_MAX, range_val=ENERGY_RANGE))

    if include_ammo_turrets and ammo_count_bits > 0:
        bw.write_bits(ammo_count_bits, ammo_count & ((1 << ammo_count_bits) - 1))

    # Legacy names retained for callers. These values are HUD fractions:
    # primary=slot-4 pulse charge, secondary=slot-1 repair fraction.
    if include_ammo_turrets and primary_turret_bits:
        validate_hud_fraction_schema(primary_turret_bits, turret_max, turret_range)
        if LOCAL_STATE_TURRET_HEADER_BITS:
            raise ValueError("HUD fraction fields do not have a priority header")
        if LOCAL_STATE_TURRET_HEADER_BITS > 0:
            bw.write_bits(LOCAL_STATE_TURRET_HEADER_BITS, LOCAL_STATE_TURRET_PRIORITY & ((1 << LOCAL_STATE_TURRET_HEADER_BITS) - 1))
        bw.write_bits(primary_turret_bits, compress_value(primary_turret_angle, turret_max, turret_range, total_bits=primary_turret_bits))
    if include_ammo_turrets and secondary_turret_bits:
        validate_hud_fraction_schema(secondary_turret_bits, turret_max, turret_range)
        if LOCAL_STATE_TURRET_HEADER_BITS:
            raise ValueError("HUD fraction fields do not have a priority header")
        if LOCAL_STATE_TURRET_HEADER_BITS > 0:
            bw.write_bits(LOCAL_STATE_TURRET_HEADER_BITS, LOCAL_STATE_TURRET_PRIORITY & ((1 << LOCAL_STATE_TURRET_HEADER_BITS) - 1))
        bw.write_bits(secondary_turret_bits, compress_value(secondary_turret_angle, turret_max, turret_range, total_bits=secondary_turret_bits))


def write_update_array_entity(bw,
                              *,
                              entity_id: int,
                              is_manned: bool,
                              pos,
                              vel,
                              rot,
                              include_pos: bool,
                              include_vel: bool,
                              include_rot: bool,
                              include_spin: bool = False,
                              spin=(0.0, 0.0, 0.0),
                              include_entity_vitals: bool = False,
                              speed_scale: float = 1.0,
                              fuel: float = 1.0,
                              ammo_unit: Optional[int] = None,
                              ammo_active_bits: int = 0,
                              ammo_active_mask: int = 0,
                              include_reset: bool = False) -> None:
    """Write a single entity update block to an UPDATE_ARRAY bitstream.

    ``include_reset`` sets update-mask bit 9, the death/teleport bit. It is
    OFF by default and no production path sets it.

    Bit 9 is the client's hard-snap selector. Traced in the pristine image:
    the 10-bit mask is read by ``MemBuff_read_nbits(payload, 10, &mask)`` at
    ``0047d889`` inside ``0047d760``; bit 9 reaches ``BL`` in ``0047d2f0``,
    where ``TEST BL,BL`` / ``JZ`` at ``0047d3e1`` selects between the ordinary
    wake path (bit clear, ``0047dd2c`` ``RigidBody_wake``) and the direct
    reset path (bit set, ``0047d3e9`` -> ``0047d670`` ``Entity_reset_physics``).
    Reaching reset_physics' full side effects rather than its zero-motion
    fallback additionally needs bits 1 and 3 present in the same record.

    WARNING, and the reason this is opt-in rather than inferred from the other
    flags: bits 1+3+9 together are the documented client-crash path. The reset
    routes into an attitude slerp whose ``acos(dot)`` is unclamped, so a
    sub-epsilon attitude delta yields ``dot`` just above 1.0, ``acos`` = NaN,
    and a crash -- roughly one time in two on a native ~60 fps client, and
    almost never on a ~12 fps WARP VM. See ``docs/freeze-correction-arc-2026-07.md``
    and the project CLAUDE.md. Do not enable this against a host client you
    care about.

    This exists so the S1 ingress-ownership capture can exercise the reset
    branch at all: it had fired zero times across a 3,123-record accepted
    tape, because nothing in this encoder had ever set the bit.
    """
    bw.write_bits(32, entity_id)
    bw.write_bits(1, 1 if is_manned else 0)

    update_mask = 0
    if include_pos:
        update_mask |= (1 << 1)
    if include_vel:
        update_mask |= (1 << 2)
    if include_rot:
        update_mask |= (1 << 3)
    if include_spin:
        update_mask |= (1 << 4)
    if include_entity_vitals:
        update_mask |= (1 << 5)
        update_mask |= (1 << 7)
    if ammo_unit is not None:
        if int(ammo_unit) != 0 or int(ammo_active_bits) != 9:
            raise ValueError("only Tank ammo unit 0 with active width 9 is supported")
        update_mask |= (1 << 6)
    if include_reset:
        update_mask |= (1 << 9)
    bw.write_bits(10, update_mask)

    bw.write_bits(16, 0)  # Bank selector

    if include_pos:
        bw.write_bits(4, 15)
        for v in pos:
            bw.write_bits(16, compress_value(v, VEC_POS_MAX, VEC_POS_RANGE, total_bits=16))

    if include_vel:
        bw.write_bits(4, 15)
        for v in vel:
            bw.write_bits(16, compress_value(v, VEC_VEL_MAX, VEC_VEL_RANGE, total_bits=16))

    if include_rot:
        bw.write_bits(4, 15)
        for v in rot:
            bw.write_bits(16, compress_value(v, VEC_ROT_MAX, VEC_ROT_RANGE, total_bits=16))

    if include_spin:
        bw.write_bits(4, 15)
        for v in spin:
            bw.write_bits(16, compress_value(v, VEC_SPIN_MAX, VEC_SPIN_RANGE, total_bits=16))

    if include_entity_vitals:
        if ENTITY_VITALS_MODE in ("health", "vitals"):
            bw.write_bits(10, encode_health_bits(speed_scale, total_bits=10))
        else:
            bw.write_bits(10, compress_value(speed_scale, 1.0, 1.0, total_bits=10))

    # Bounded Tank ammo state. The emitted Tank BEHAVIOR row has property
    # widths (count=0, enabled=0, active=9, word=0), so only its unit and
    # property-3 mask occur on wire. Other rows require a generalized schema.
    if ammo_unit is not None:
        bw.write_bits(5, int(ammo_unit) & 0x1F)
        if ammo_active_bits:
            bw.write_bits(ammo_active_bits, int(ammo_active_mask) & ((1 << ammo_active_bits) - 1))

    if include_entity_vitals:
        if ENTITY_VITALS_MODE in ("health", "vitals"):
            bw.write_bits(10, encode_health_bits(fuel, total_bits=10, max_val=ENERGY_MAX, range_val=ENERGY_RANGE))
        else:
            bw.write_bits(10, compress_value(fuel, 1.0, 1.0, total_bits=10))
