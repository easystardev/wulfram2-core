"""
Quantizer configuration table.

Consolidates the 28 quantizer definitions used by TRANSLATION packets
and UPDATE_ARRAY/ACTION_DUMP decoding. Two groups:
- Scalars (0-15): behavioral input axes
- Vectors (16-27): positional state, 3 banks of 4 vectors each

Sources:
1. Server packets.py TRANSLATION builder
2. Server weapons.py behavior input decoding
3. Shared interoperability testing and packet analysis
"""

from dataclasses import dataclass
from typing import Optional
from .packets import (
    VEC_POS_MAX, VEC_POS_RANGE,
    VEC_VEL_MAX, VEC_VEL_RANGE,
    VEC_ROT_MAX, VEC_ROT_RANGE,
    VEC_SPIN_MAX, VEC_SPIN_RANGE,
    HEALTH_MAX, HEALTH_RANGE,
    ENERGY_MAX, ENERGY_RANGE,
)
from .hud_state import HUD_FRACTION_BITS, HUD_FRACTION_MAX, HUD_FRACTION_RANGE


@dataclass
class Quantizer:
    """A single quantizer configuration entry."""
    index: int
    name: str
    fixed_bits: int      # Primary bit count
    total_bits: int      # Secondary max_total_bits (0 for scalars)
    max_value: float     # Upper bound of range
    range_value: float   # Total range (max - min)
    group: str           # "scalar" or "vector"


# Scalar quantizers (0-15): behavioral input axes
# Used in ACTION_DUMP/ACTION_UPDATE for client inputs
SCALAR_QUANTIZERS = [
    Quantizer(0,  "control",       16,  0, 1000.0, 2000.0, "scalar"),
    Quantizer(1,  "weapon_id",      5,  0, 1000.0, 2000.0, "scalar"),
    Quantizer(2,  "entity_type",    8,  0,    1.0,    1.0, "scalar"),
    Quantizer(3,  "parent_team",    8,  0,    1.0,    1.0, "scalar"),
    Quantizer(4,  "scalar4",       16,  0, 1000.0, 2000.0, "scalar"),
    Quantizer(5,  "health",        10,  0, HEALTH_MAX, HEALTH_RANGE, "scalar"),
    Quantizer(6,  "scalar6",       16,  0, 1000.0, 2000.0, "scalar"),
    Quantizer(7,  "scalar7",       16,  0, 1000.0, 2000.0, "scalar"),
    Quantizer(8,  "energy",        10,  0, ENERGY_MAX, ENERGY_RANGE, "scalar"),
    Quantizer(9,  "scalar9",       16,  0, 1000.0, 2000.0, "scalar"),
    Quantizer(10, "scalar10",      16,  0, 1000.0, 2000.0, "scalar"),
    Quantizer(11, "scalar11",      16,  0, 1000.0, 2000.0, "scalar"),
    Quantizer(12, "scalar12",      16,  0, 1000.0, 2000.0, "scalar"),
    Quantizer(13, "pulse_charge", HUD_FRACTION_BITS, 0, HUD_FRACTION_MAX, HUD_FRACTION_RANGE, "scalar"),
    Quantizer(14, "repair_fraction", HUD_FRACTION_BITS, 0, HUD_FRACTION_MAX, HUD_FRACTION_RANGE, "scalar"),
    Quantizer(15, "slot_index",    16,  0, 1000.0, 2000.0, "scalar"),
]

# Vector quantizers (16-27): positional state
# 3 banks of 4 vectors each (bank 0 = idx 16-19, bank 1 = 20-23, bank 2 = 24-27)
# Each bank has: position, velocity, rotation, spin
VECTOR_QUANTIZERS = [
    # Bank 0 (indices 16-19)
    Quantizer(16, "pos_bank0",      4, 16, VEC_POS_MAX,  VEC_POS_RANGE,  "vector"),
    Quantizer(17, "vel_bank0",      4, 16, VEC_VEL_MAX,  VEC_VEL_RANGE,  "vector"),
    Quantizer(18, "rot_bank0",      4, 16, VEC_ROT_MAX,  VEC_ROT_RANGE,  "vector"),
    Quantizer(19, "spin_bank0",     4, 16, VEC_SPIN_MAX, VEC_SPIN_RANGE, "vector"),
    # Bank 1 (indices 20-23)
    Quantizer(20, "pos_bank1",      4, 16, VEC_POS_MAX,  VEC_POS_RANGE,  "vector"),
    Quantizer(21, "vel_bank1",      4, 16, VEC_VEL_MAX,  VEC_VEL_RANGE,  "vector"),
    Quantizer(22, "rot_bank1",      4, 16, VEC_ROT_MAX,  VEC_ROT_RANGE,  "vector"),
    Quantizer(23, "spin_bank1",     4, 16, VEC_SPIN_MAX, VEC_SPIN_RANGE, "vector"),
    # Bank 2 (indices 24-27)
    Quantizer(24, "pos_bank2",      4, 16, VEC_POS_MAX,  VEC_POS_RANGE,  "vector"),
    Quantizer(25, "vel_bank2",      4, 16, VEC_VEL_MAX,  VEC_VEL_RANGE,  "vector"),
    Quantizer(26, "rot_bank2",      4, 16, VEC_ROT_MAX,  VEC_ROT_RANGE,  "vector"),
    Quantizer(27, "spin_bank2",     4, 16, VEC_SPIN_MAX, VEC_SPIN_RANGE, "vector"),
]

# Full table: all 28 quantizers indexed by slot number
QUANTIZER_TABLE = SCALAR_QUANTIZERS + VECTOR_QUANTIZERS

# Dict lookup by index
QUANTIZERS_BY_INDEX = {q.index: q for q in QUANTIZER_TABLE}

# Dict lookup by name
QUANTIZERS_BY_NAME = {q.name: q for q in QUANTIZER_TABLE}


def get_quantizer(index: int) -> Optional[Quantizer]:
    """Get quantizer config by slot index (0-27)."""
    return QUANTIZERS_BY_INDEX.get(index)


def get_vector_quantizer(bank: int, offset: int) -> Optional[Quantizer]:
    """Get vector quantizer by bank (0-2) and offset (0=pos, 1=vel, 2=rot, 3=spin)."""
    index = 16 + bank * 4 + offset
    return QUANTIZERS_BY_INDEX.get(index)
