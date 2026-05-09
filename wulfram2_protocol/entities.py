"""
Entity type definitions, shared vehicle helpers, and behavior slot indices.
"""

from enum import IntEnum
from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Sequence, Tuple
import math
import struct


class BehaviorSlot(IntEnum):
    """Behavior slot indices for input axes.

    These are INPUT behavior slots (0-21), not weapon/ammo slots.
    Used in ACTION_DUMP (0x09) and ACTION_UPDATE (0x0A) packets.
    """
    UNUSED0 = 0
    TURNING = 1          # yaw (left/right)
    MOVING_FORWARD = 2   # W/S
    MOVING_SIDEWAYS = 3  # A/D
    # Empirical OG probe 2026-04-28: action_key "jumpjet" sets slot 4.
    # Slot 4 is not control-quantized in ACTION_UPDATE/ACTION_DUMP.
    JUMPJET = 4
    WEAPON_SELECT = 4      # Legacy alias; weapon hotkeys use direct slots 12-19.
    UPWARD_THRUST = 5    # Live OG Q/Z softbody throttle/stiffness (zoom quantizer)
    SLOT6 = 6            # Raw axis 6 / visual lean (control quantizer)
    SLOT7 = 7            # Unknown (control quantizer)
    FIRE = 8             # Primary fire trigger (binary)
    # Slots 9-21 are various other controls


TANK_SOFTBODY_CONTROL_SLOT = BehaviorSlot.UPWARD_THRUST


def tank_softbody_control_slot_value(
    behavior_slots: Sequence[float],
    *,
    default: float = 0.824,
    allow_legacy_slot6: bool = False,
) -> float:
    """Return the live OG Q/Z softbody throttle/stiffness slot value.

    Decompile-backed controller flow writes input axis 5 into the tank vehicle
    throttle, then copies that value into the active softbody stiffness field.
    Live wulftap Q/Z telemetry confirms decoded behavior slot 5 follows that
    vehicle_throttle/softbody_stiffness value, while slot 6 is raw-axis lean.
    Slot 6 is live OG raw-axis lean data, so it must not drive suspension in
    normal server/client paths. Older local harnesses may opt into that
    compatibility fallback explicitly.
    """
    try:
        primary = float(behavior_slots[int(BehaviorSlot.UPWARD_THRUST)])
    except (IndexError, TypeError, ValueError):
        primary = 0.0
    if abs(primary) > 0.001:
        return primary

    if allow_legacy_slot6:
        try:
            legacy = float(behavior_slots[int(BehaviorSlot.SLOT6)])
        except (IndexError, TypeError, ValueError):
            legacy = 0.0
        if abs(legacy) > 0.001:
            return legacy

    return float(default)


# Shared slot classification for ACTION_DUMP/ACTION_UPDATE encoding.
# Keep these authoritative to avoid client/server bitstream drift.
ACTION_ANALOG_SLOTS = frozenset({
    BehaviorSlot.UNUSED0,
    BehaviorSlot.TURNING,
    BehaviorSlot.MOVING_FORWARD,
    BehaviorSlot.MOVING_SIDEWAYS,
    BehaviorSlot.UPWARD_THRUST,
    TANK_SOFTBODY_CONTROL_SLOT,
    BehaviorSlot.SLOT6,
    BehaviorSlot.SLOT7,
})

# ACTION_DUMP writes UPWARD_THRUST with the zoom quantizer; this set is only
# the slots written with the control quantizer.
ACTION_DUMP_CONTROL_SLOTS = frozenset({
    BehaviorSlot.UNUSED0,
    BehaviorSlot.TURNING,
    BehaviorSlot.MOVING_FORWARD,
    BehaviorSlot.MOVING_SIDEWAYS,
    BehaviorSlot.SLOT6,
    BehaviorSlot.SLOT7,
})


def is_action_analog_slot(slot_idx: int) -> bool:
    """Return True when ACTION_UPDATE should encode this slot as analog."""
    return slot_idx in ACTION_ANALOG_SLOTS


def is_action_dump_control_slot(slot_idx: int) -> bool:
    """Return True when ACTION_DUMP should encode this slot with control quantizer."""
    return slot_idx in ACTION_DUMP_CONTROL_SLOTS


class EntityType(IntEnum):
    """Entity type IDs used by the shared protocol layer.

    Types 0-4: Vehicles (player-controllable)
    Types 5-18: Projectiles/ordnance
    Types 19-21: Special items
    Types 22: Torpedo
    Types 25-37: Buildings/structures (map objects)
    Sentinel 0x27 (39) = ILLEGAL
    """
    # Vehicles
    TANK = 0               # save: 't'
    SCOUT = 1              # save: (vehicle, not in save func) — also called Medic
    ASSAULT_PLATFORM = 2
    BOMBER = 3
    TRANSPORT = 4

    # Projectiles
    FLAK_SHELL = 5         # save: 'A'
    PULSE_SHELL = 6        # save: 'U'
    SHORT_MISSILE = 7      # save: 'O'
    HUNTER = 8             # save: 'm'
    HEAVY_MISSILE = 9      # save: 'M'
    MINE = 10              # save: 'i'
    PIERCER = 11           # save: 'P'
    THUMPER = 12           # save: 'H'
    CALTROP = 13           # save: 'k'
    ORBITAL_BOMB = 14
    CRUISE_MISSILE = 15
    MORTAR_SHELL = 16
    FLARE = 17
    AERIAL_BOMB = 18

    # Special items
    CARGO_BOX = 19         # save: 'c'
    UPLINK = 20            # save: 'u'
    SUPPLY_SHIP = 21       # save: 'h'

    # Torpedo
    TORPEDO = 22           # save: 'T' (0x16)

    # Types 23-24 unused/unknown

    # Buildings / structures
    ENERGY_BUILDING = 25   # save: 'e' (0x19)
    FUEL_BUILDING = 26     # save: 'f' (0x1a)
    REPAIR_BUILDING = 27   # save: 'r' (0x1b) — spawn points use this type
    SPECIAL_STRUCTURE = 28 # save: 'S' (0x1c)
    SENSOR_BUILDING = 29   # save: 's' (0x1d)
    GUN_TURRET = 30        # save: 'g' (0x1e)
    ENERGY_STRUCTURE = 31  # save: 'E' (0x1f)
    LAUNCHER = 32          # save: 'L' (0x20)
    PAD = 33               # save: 'p' (0x21)
    ORBITAL_BUILDING = 34  # save: 'o' (0x22)
    DARK_LIGHT = 35        # save: 'd' (0x23)
    BUILDING = 36          # save: 'b' (0x24)
    STRUCTURE = 37         # save: '*' (0x25)


class WeaponType(IntEnum):
    """Weapon types (ammo slot indices used by current gameplay traffic).

    Tank weapon slots currently used by shared client/server code:
    - Slot 0: Chain gun (instant hit)
    - Slot 4: Pulse cannon (projectile)
    - Slot 5: Flak
    - Slot 6: Guided missile
    - Slot 7: Hunter seeker
    - Slot 8: Mine
    - Slot 9: Thumper
    - Slot 10: Mortar
    - Slot 11: Piercer
    """
    CHAIN_GUN = 0       # Instant hit
    PULSE_CANNON = 4    # Energy projectile
    FLAK = 5            # Anti-air
    GUIDED_MISSILE = 6  # Lock-on missile
    HUNTER_SEEKER = 7   # Autonomous missile
    MINE = 8            # Deployable mine
    THUMPER = 9         # Heavy artillery
    MORTAR = 10         # Arc projectile
    PIERCER = 11        # Long-range sniper


# Weapon names for UI/logging
WEAPON_NAMES = {
    0: "Chain Gun",
    4: "Pulse Cannon",
    5: "Flak",
    6: "Guided Missile",
    7: "Hunter Seeker",
    8: "Mine",
    9: "Thumper",
    10: "Mortar",
    11: "Piercer",
}

# Valid Tank weapon slots
TANK_WEAPON_SLOTS = {0, 4, 5, 6, 7, 8, 9, 10, 11}

# UPDATE_ARRAY / PLAYER_INFO local-state turret flags are keyed by the
# local-state weapon/entity type value, not by the currently selected ammo slot.
# Shared local-state interpretation:
# - primary turret angle when local-state weapon type 0 is active
# - secondary turret angle when local-state weapon type 1 is active
# Keep this shared so server builders and client decoders stay aligned.
LOCAL_STATE_PRIMARY_TURRET_WEAPON_TYPES = frozenset({0})
LOCAL_STATE_SECONDARY_TURRET_WEAPON_TYPES = frozenset({1})


@dataclass
class VehiclePhysicsConfig:
    """Per-vehicle-type physics constants shared by client and server code.

    Static values cover movement and altitude behavior. Runtime values cover
    damping and mass used by the public Python simulation path.
    """
    # Static config
    turn_adjust: float      # angular acceleration multiplier
    move_adjust: float      # forward acceleration multiplier
    strafe_adjust: float    # strafe acceleration multiplier
    max_velocity: float     # velocity clamp / slope threshold
    low_fuel_level: float   # fuel threshold below which tank mobility is reduced
    max_altitude: float     # max hover height
    gravity_pct: float      # gravity multiplier (1.0 = normal)
    max_fuel: float = 33000.0

    # Runtime physics
    linear_damping_driving: float = 1.5   # active PhysicsConfig linear damping
    linear_damping_coasting: float = 1.5  # same coefficient while coasting
    angular_damping: float = 2.0          # runtime angular damping
    mass: float = 1.0                     # runtime mass scalar


@dataclass(frozen=True)
class JumpJetConfig:
    """Opt-in custom jump-jet tuning shared by server and Python prediction."""

    impulse: float = 15.0
    cooldown: float = 3.0
    fuel_cost: float = 10.0
    max_altitude: float = 50.0


# Custom extension, not part of the original Tank controller. The runtime gates
# use behind WULFRAM_JUMP_JETS so default clone physics remains OG-focused.
#
# The first 15u/s tank impulse technically fired but only peaked around 1.6u
# above the ground under the clone's normal gravity/damping, which is easy to
# miss in OG and Python cameras. The opt-in extension uses a larger impulse so
# a successful jump is observable without changing default clone physics.
JUMP_JET_SPAWN_LOCKOUT = 2.0
JUMP_JET_CONFIGS = {
    EntityType.TANK: JumpJetConfig(impulse=45.0, cooldown=3.0, fuel_cost=10.0, max_altitude=50.0),
    EntityType.SCOUT: JumpJetConfig(impulse=55.0, cooldown=2.0, fuel_cost=8.0, max_altitude=55.0),
    EntityType.ASSAULT_PLATFORM: JumpJetConfig(impulse=35.0, cooldown=5.0, fuel_cost=15.0, max_altitude=45.0),
}


@dataclass(frozen=True)
class FeedbackCurveTable:
    """Data from one OG `.atbl` response table."""

    abs_max_error: float
    mul_error: float
    abs_max_prime: float
    mul_prime: float
    abs_out: float
    use_damper: bool
    raw: tuple[float, ...]
    cor: tuple[float, ...]
    err: tuple[float, ...]
    prm: tuple[float, ...]


@dataclass(frozen=True)
class TankSpringPiecewiseForceSample:
    """One `GUESS4_Piecewise_sample_blended`-shaped force sample."""

    force_magnitude: float
    blend_factor: float
    react_blend: float
    fast_react: float
    slow_react: float
    height_curve_factor: float
    speed_curve_factor: float
    height_consider_factor: float
    abate_factor: float
    height_ratio: float
    force_error: float
    point_velocity_z: float


def tank_fuel_mobility_factor(current_fuel: float, low_fuel_level: float) -> float:
    """Return the tank forward-mobility cap from current fuel.

    `Tank_compute_mobility_factors` gates forward mobility on entity+0xD4.
    Live wulftap probes show that field is fuel/max-fuel state, not speed.
    The client only applies the 0.4-1.0 ramp when fuel is below the
    `low_fuel_level` BEHAVIOR value.
    """
    if low_fuel_level <= 0.0:
        return 1.0
    if current_fuel < 0.0:
        current_fuel = 0.0
    if current_fuel < low_fuel_level:
        factor = (current_fuel / low_fuel_level) * 0.6 + 0.4
        if factor < 0.4:
            return 0.4
        if factor > 1.0:
            return 1.0
        return factor
    return 1.0


def tank_low_speed_mobility_factor(current_speed: float, speed_threshold: float) -> float:
    """Deprecated compatibility wrapper for older callers.

    The original name came from an early decompile comment that misidentified
    entity+0xD4 as speed. Use `tank_fuel_mobility_factor` for clone logic.
    """
    return tank_fuel_mobility_factor(current_speed, speed_threshold)


def tank_slope_mobility_factor(
    slope_component: float,
    throttle: float,
    max_velocity: float,
) -> float:
    """Return the tank slope-based forward mobility penalty.

    `azurefishy-src` `Tank_compute_mobility_factors` (Vehicles.c:1148-1161):

    - `slope_component` is the forward-direction terrain slope (positive = uphill
      when moving forward). In the decompile this comes from dot(rotated_up, X).
    - Only penalizes when moving uphill (same sign for slope and throttle).
    - If |slope| > max_velocity threshold, compute excess ratio and reduce
      mobility multiplicatively.
    - Penalty cap is 0.2 of the threshold, below which mobility reaches 0.
    """
    if max_velocity <= 0.0:
        return 1.0
    # Only penalize uphill movement
    if not ((slope_component > 0.0 and throttle > 0.0) or
            (slope_component < 0.0 and throttle < 0.0)):
        return 1.0
    abs_slope = abs(slope_component)
    if abs_slope <= max_velocity:
        return 1.0
    slope_excess = (abs_slope - max_velocity) / max_velocity
    penalty_cap = 0.2
    if slope_excess > penalty_cap:
        slope_excess = penalty_cap
    factor = (penalty_cap - slope_excess) / penalty_cap
    if factor < 0.0:
        return 0.0
    if factor > 1.0:
        return 1.0
    return factor


def tank_altitude_mobility_factor(normalized_altitude_deviation: float) -> float:
    """Return the tank altitude mobility factor from a normalized hover deviation.

    `azurefishy-src` `Tank_compute_mobility_factors` applies this branch after
    slope reduction:

    - deviation <= 1.0: no penalty
    - excess above 1.0 capped to 0.4
    - factor = (0.4 - excess) / 0.4
    - floor factor at 0.35

    The original runtime gets `normalized_altitude_deviation` from the tank
    vehicle instance / spring state. The public Python runtime does not yet
    carry that full softbody state, so callers must supply the closest
    available normalized hover deviation.
    """
    if normalized_altitude_deviation <= 1.0:
        return 1.0
    excess = normalized_altitude_deviation - 1.0
    if excess >= 0.4:
        return 0.35
    factor = (0.4 - excess) / 0.4
    if factor < 0.35:
        return 0.35
    if factor > 1.0:
        return 1.0
    return factor


def tank_hover_clearance_target(spring_base_offset: float, max_altitude: float) -> float:
    """Return the tank spring rest clearance above raw terrain height.

    `TankController_update` writes `_DAT_005730c4 + max_altitude` into the
    active spring state before `Spring_update_world_state` derives the altitude
    ratio used by mobility and suspension. `_DAT_005730c4` is a computed
    collision-radius baseline, not the terrain heightmap Z offset. Keep this
    helper shared so server and Python prediction normalize rough-terrain
    clearance the same way.
    """
    target = float(spring_base_offset) + float(max_altitude)
    if target <= 0.001:
        return 0.001
    return target


def tank_spring_average_clearance(sum_clearance: float, point_count: int) -> float:
    """Return the decompile-shaped spring clearance aggregate.

    `Spring_update_world_state` accumulates per-point height-above-terrain
    values and stores `height_sum / (point_count - 1)` at spring offset +0x78.
    For the 4-point tank quad this means the aggregate is intentionally
    `sum / 3`, not the arithmetic mean `sum / 4`.
    """
    if point_count <= 1:
        return float(sum_clearance)
    return float(sum_clearance) / float(point_count - 1)


def tank_suspension_lift_accel(
    avg_clearance: float,
    target_clearance: float,
    vertical_velocity: float,
    *,
    stiffness: float = 40.0,
    damping: float = 1.5,
    lift_cap: float = 120.0,
) -> float:
    """Approximate the tank spring's upward acceleration contribution.

    The exact client path samples piecewise spring curves per corner. The clone
    still uses a compact controller model, so this supplies the missing
    upward-only support force from the same averaged clearance state already
    used for terrain mobility. The default stiffness follows the decompiled
    uniform SpringParam initializer (40). Gravity remains responsible for
    pulling an over-height tank back down.
    """
    if target_clearance <= 0.0 or lift_cap <= 0.0:
        return 0.0
    clearance_error = target_clearance - avg_clearance
    if clearance_error <= 0.0 and vertical_velocity >= 0.0:
        return 0.0

    lift = 0.0
    if clearance_error > 0.0 and stiffness > 0.0:
        lift += clearance_error * stiffness
    if vertical_velocity < 0.0 and damping > 0.0:
        lift += -vertical_velocity * damping

    if lift < 0.0:
        return 0.0
    if lift > lift_cap:
        return lift_cap
    return lift


OG_TANK_SOFTBODY_REST_HEIGHT = 13.0636
# Live OG after BEHAVIOR Section 5 emits the allocator-default down normals
# for each tank spring point. The earlier 2.4785 reading came from a malformed
# zero-normal BEHAVIOR payload and made both OG and server hug the low hover.
OG_TANK_SOFTBODY_FLAT_AVERAGE_HEIGHT = 4.342
OG_TANK_SOFTBODY_IDLE_SLOT5 = 0.824
OG_TANK_SOFTBODY_Q_SLOT5 = 1.0071
OG_TANK_SOFTBODY_Z_SLOT5 = 0.05
OG_TANK_SOFTBODY_POINT_COUNT = 4
OG_PHYSICS_TIMESTEP_FACTOR = 100.0
OG_TANK_SPRING_POINT_NORMAL = (0.0, 0.0, -1.0)
OG_TANK_FORCE_BASE_REACT = 0.0055
OG_TANK_FORCE_SLOPE_REACT = 0.003
OG_TANK_SPRING_SHEAR_STIFFNESS = 40.0
# `GUESS4_Spring_check_stretch_ratio` at 0x004ddec0 reads entity +0x18/+0x1C
# (persistent horizontal velocity), ignores Z, divides by the first float in
# the spring config block, and clamps to 1.0 before Spring_update_world_state
# stores the result at spring +0x88. Live H180/W rows bracket that denominator
# at about 60u/s (`15.9 / 0.2652`), matching the tank spring config rather than
# the raw movement impulse.
OG_TANK_SPRING_STRETCH_SPEED_DENOMINATOR = 60.0
OG_TANK_JET_ABATE_MAX = 1.5
OG_TANK_JET_HEIGHT_CURVE = (
    1.0,
    0.9985150098800659,
    0.9939879775047302,
    0.9842531681060791,
    0.9710888862609863,
    0.9583333134651184,
    0.949999988079071,
    0.9333333373069763,
    0.8833333253860474,
    0.7700000405311584,
    0.573333203792572,
    0.30166661739349365,
    0.009999999776482582,
)
OG_TANK_JET_SPEED_CURVE = (
    0.9900000095367432,
    0.9916640520095825,
    0.9938479065895081,
    0.9960829615592957,
    0.9980066418647766,
    0.9993624091148376,
    0.9998725056648254,
    1.0,
    1.0,
    0.9883584976196289,
    0.9417926073074341,
    0.8177949786186218,
    0.33000001311302185,
    0.15000000596046448,
    0.09000000357627869,
    0.07999999821186066,
)
OG_TANK_JET_HEIGHT_CONSIDER_CURVE = (
    0.0,
    0.0,
    0.018181825056672096,
    0.049675341695547104,
    0.09056279063224792,
    0.13865803182125092,
    0.18372297286987305,
    0.25,
    0.4284849762916565,
    0.762056291103363,
    0.8980087041854858,
    0.9509091377258301,
    0.9785570502281189,
    0.9935714602470398,
    0.9900000095367432,
)
OG_TANK_JET_ABATE_CURVE = (
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    0.9999725818634033,
    0.9985880851745605,
    0.9916743040084839,
    0.9717278480529785,
    0.9270676374435425,
    0.8590867519378662,
    0.7636765837669373,
    0.6481172442436218,
    0.521756112575531,
    0.39453262090682983,
    0.2750498056411743,
    0.16507287323474884,
    0.0725526437163353,
    0.011592447757720947,
    0.0,
)
OG_TANK_JET_FAST_REACT_TABLE = FeedbackCurveTable(
    abs_max_error=4.0,
    mul_error=1.0,
    abs_max_prime=40.0,
    mul_prime=1.0,
    abs_out=1.25,
    use_damper=True,
    raw=(
        0.0,
        0.012012012302875519,
        0.048048049211502075,
        0.13269220292568207,
        0.22482815384864807,
        0.3357541263103485,
        0.44965869188308716,
        0.5289380550384521,
        0.5841590762138367,
        0.6249136328697205,
        0.6603560447692871,
        0.6934602856636047,
        0.7239112257957458,
        0.7518199682235718,
        0.7773834466934204,
        0.8009890913963318,
        0.8231141567230225,
        0.8445252180099487,
        0.865683913230896,
        0.8863597512245178,
        0.9062333703041077,
        0.9249318838119507,
        0.9423050284385681,
        0.9585396647453308,
        0.9735909700393677,
        0.9874211549758911,
        1.0,
    ),
    cor=(
        0.0,
        0.14417357742786407,
        0.30285993218421936,
        0.470509797334671,
        0.6360411643981934,
        0.7828391194343567,
        0.8887560367584229,
        0.9092855453491211,
        0.923692524433136,
        0.9384045004844666,
        0.9566060304641724,
        0.9782384634017944,
        1.0,
    ),
    err=(
        0.9933333396911621,
        0.9955061674118042,
        0.997738242149353,
        0.899318516254425,
        0.717474102973938,
        0.5247857570648193,
        0.3866034150123596,
        0.2764957547187805,
        0.1872110515832901,
        0.1186164990067482,
        0.0686473622918129,
        0.03330701217055321,
        0.006666666828095913,
    ),
    prm=(
        0.9933333396911621,
        0.9939576387405396,
        0.9945635795593262,
        0.9951481223106384,
        0.9957080483436584,
        0.9962400197982788,
        0.9967363476753235,
        0.9971977472305298,
        0.9976284503936768,
        0.9932911992073059,
        0.9782395362854004,
        0.9481661319732666,
        0.9165400266647339,
        0.8666993975639343,
        0.8022806644439697,
        0.725062370300293,
        0.619817852973938,
        0.4538632035255432,
        0.2924923598766327,
        0.16571789979934692,
        0.0874946191906929,
        0.0533333346247673,
    ),
)
OG_TANK_JET_SLOW_REACT_TABLE = FeedbackCurveTable(
    abs_max_error=17.5,
    mul_error=1.0,
    abs_max_prime=200.0,
    mul_prime=1.0,
    abs_out=0.4000000059604645,
    use_damper=True,
    raw=(
        0.0,
        0.0559365339577198,
        0.20200367271900177,
        0.39350932836532593,
        0.6000000238418579,
        0.737250030040741,
        0.8447500467300415,
        0.9410000443458557,
        1.0,
    ),
    cor=(
        0.0,
        0.2774527668952942,
        0.5030505061149597,
        0.6869367957115173,
        0.8392552137374878,
        0.9701492786407471,
    ),
    err=(
        0.9933333396911621,
        0.9939393997192383,
        0.9938721060752869,
        0.9925541281700134,
        0.9695237874984741,
        0.8644155263900757,
        0.43653658032417297,
        0.2363058626651764,
        0.12715722620487213,
        0.06794607639312744,
        0.03393936529755592,
        0.006666666828095913,
    ),
    prm=(
        1.0,
        1.0,
        0.8613333106040955,
        0.5449999570846558,
        0.22133329510688782,
        0.05833331122994423,
        0.009999999776482582,
    ),
)


@dataclass(frozen=True)
class TankSoftbodyForce:
    """Result from the decompile-shaped tank softbody vertical force stand-in."""

    model: str
    lift_accel: float
    support_accel: float
    height_response_accel: float
    damping_accel: float
    average_height: float
    target_average_height: float
    height_error: float
    height_ratio: float
    slot5: float
    force_curve_input: float
    force_bias_accel: float
    vehicle_throttle: float
    softbody_stiffness: float
    response_scale: float
    gravity_pct: float
    rest_height: float
    max_altitude: float
    force_offset: float
    point_count: int = 0
    point_forces: tuple[float, ...] = ()
    point_vertical_forces: tuple[float, ...] = ()
    point_clearances: tuple[float, ...] = ()
    point_clamped_heights: tuple[float, ...] = ()
    point_height_errors: tuple[float, ...] = ()
    point_normal_z: tuple[float, ...] = ()
    point_stretch_ratios: tuple[float, ...] = ()
    point_force_curve_inputs: tuple[float, ...] = ()
    point_height_curve_factors: tuple[float, ...] = ()
    point_blend_factors: tuple[float, ...] = ()
    point_shear_corrections: tuple[float, ...] = ()
    point_velocity_z: tuple[float, ...] = ()
    point_decompile_force_magnitudes: tuple[float, ...] = ()
    point_decompile_react_blends: tuple[float, ...] = ()
    point_decompile_fast_reacts: tuple[float, ...] = ()
    point_decompile_slow_reacts: tuple[float, ...] = ()
    scalar_stretch_ratio: float = 0.0
    scalar_stretch_source: str = "none"
    scalar_stretch_speed: float = 0.0
    scalar_stretch_denominator: float = OG_TANK_SPRING_STRETCH_SPEED_DENOMINATOR


@dataclass(frozen=True)
class TankSpringAttitudeStep:
    """Integrated tank spring pitch/roll attitude response."""

    roll: float
    pitch: float
    roll_velocity: float
    pitch_velocity: float
    target_roll: float
    target_pitch: float
    roll_error: float
    pitch_error: float
    roll_torque: float
    pitch_torque: float
    stiffness: float
    damping: float
    dt: float


@dataclass(frozen=True)
class TankSpringForceAttitudeStep:
    """Integrated tank spring pitch/roll response from per-point force torque."""

    roll: float
    pitch: float
    roll_velocity: float
    pitch_velocity: float
    local_torque_x: float
    local_torque_y: float
    roll_torque: float
    pitch_torque: float
    point_forces: tuple[float, ...]
    total_lift: float
    torque_scale: float
    damping: float
    dt: float
    torque_model: str = "decompile_config"
    torque_force_scales: tuple[float, ...] = ()
    integration_model: str = "decompile_impulse"
    angular_velocity_before: tuple[float, float] = (0.0, 0.0)
    spring_angular_delta: tuple[float, float] = (0.0, 0.0)
    angular_velocity_after_spring: tuple[float, float] = (0.0, 0.0)
    angular_velocity_after_damping: tuple[float, float] = (0.0, 0.0)
    rotation_matrix: tuple[float, ...] = ()


@dataclass(frozen=True)
class StaticTerrainConstraintResult:
    """Result from an OG-shaped static terrain contact constraint solve."""

    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    angular_velocity: Tuple[float, float, float]
    debug: Mapping[str, object]


@dataclass(frozen=True)
class IterativeTerrainSeparationResult:
    """Result from the OG collision-at-start iterative separation branch."""

    position: Tuple[float, float, float]
    cleared: bool
    iterations: int
    debug: Mapping[str, object]


@dataclass(frozen=True)
class EntityInterpolationDecision:
    """Decision shape for OG Entity_interpolate_toward_target."""

    action: str
    interp_factor: float
    position_distance: float
    rotation_distance: float
    combined_radius: float
    tolerance: float
    elapsed_ticks: float
    reset_physics: bool
    wake: bool
    update_last_interp_tick: bool
    debug: Mapping[str, object]


def _vec3_dot(a: Sequence[float], b: Sequence[float]) -> float:
    return float(a[0]) * float(b[0]) + float(a[1]) * float(b[1]) + float(a[2]) * float(b[2])


def _vec3_cross(a: Sequence[float], b: Sequence[float]) -> Tuple[float, float, float]:
    return (
        float(a[1]) * float(b[2]) - float(a[2]) * float(b[1]),
        float(a[2]) * float(b[0]) - float(a[0]) * float(b[2]),
        float(a[0]) * float(b[1]) - float(a[1]) * float(b[0]),
    )


def _vec3_len(v: Sequence[float]) -> float:
    return math.sqrt(_vec3_dot(v, v))


def _vec3_normalize(v: Sequence[float]) -> Tuple[float, float, float] | None:
    length = _vec3_len(v)
    if length <= 1e-8:
        return None
    inv = 1.0 / length
    return (float(v[0]) * inv, float(v[1]) * inv, float(v[2]) * inv)


def resolve_iterative_terrain_start_contact(
    *,
    position: Sequence[float],
    contact_normal: Sequence[float],
    sample_contact: Callable[[Tuple[float, float, float]], object | None],
    slop: float = 0.005,
    max_iterations: int = 40,
    use_vertical_fallback: bool = True,
) -> IterativeTerrainSeparationResult:
    """Approximate `Collision_resolve_pair_iterative` for entity-vs-world starts.

    OG routes sweep records whose `+0x119` flag is set away from the normal
    constraint solver and into an iterative position-separation loop. For
    entity-vs-world pairs that loop restores the saved pose each attempt,
    pushes the entity along the contact normal blended toward a vertical
    fallback, escalates magnitude by 1.2x, and retests until the pair clears.
    """

    base = (float(position[0]), float(position[1]), float(position[2]))
    normal = _vec3_normalize(contact_normal) or (0.0, 0.0, 1.0)
    fallback = (0.0, 0.0, 1.0) if use_vertical_fallback else (0.0, 0.0, 1.0)
    blend = 1.0
    magnitude = 1.0
    iteration_limit = max(1, min(200, int(max_iterations)))
    slop_value = max(0.0, float(slop))
    attempts: list[dict[str, object]] = []
    best_position = base
    best_penetration: float | None = None

    for iteration in range(1, iteration_limit + 1):
        if magnitude > 1000.0:
            magnitude = 200.0
        if blend < 0.0:
            blend = 0.0
        random_weight = 1.0 - blend
        direction = _vec3_normalize((
            normal[0] * blend + fallback[0] * random_weight,
            normal[1] * blend + fallback[1] * random_weight,
            normal[2] * blend + fallback[2] * random_weight,
        )) or fallback
        candidate = (
            base[0] + direction[0] * magnitude,
            base[1] + direction[1] * magnitude,
            base[2] + direction[2] * magnitude,
        )
        contact = sample_contact(candidate)
        penetration = 0.0
        if contact is not None:
            try:
                penetration = float(getattr(contact, "penetration", 0.0) or 0.0)
            except (TypeError, ValueError):
                penetration = 0.0
        colliding = contact is not None and penetration > slop_value
        if best_penetration is None or penetration < best_penetration:
            best_penetration = penetration
            best_position = candidate
        if len(attempts) < 8:
            attempts.append({
                "iteration": iteration,
                "blend": blend,
                "magnitude": magnitude,
                "direction": direction,
                "position": candidate,
                "penetration": penetration,
                "colliding": colliding,
            })
        if not colliding:
            delta = (
                candidate[0] - base[0],
                candidate[1] - base[1],
                candidate[2] - base[2],
            )
            return IterativeTerrainSeparationResult(
                position=candidate,
                cleared=True,
                iterations=iteration,
                debug={
                    "response": "terrain_contact_iterative_position_rollback",
                    "iterative_separation_model": "Collision_resolve_pair_iterative_world_vertical",
                    "iterative_cleared": True,
                    "iterative_iterations": iteration,
                    "iterative_position_delta": delta,
                    "iterative_position_delta_mag": _vec3_len(delta),
                    "iterative_final_penetration": penetration,
                    "iterative_attempts": attempts,
                    "velocity_unchanged_by_iterative_separation": True,
                },
            )
        magnitude *= 1.2
        blend -= 0.05

    delta = (
        best_position[0] - base[0],
        best_position[1] - base[1],
        best_position[2] - base[2],
    )
    return IterativeTerrainSeparationResult(
        position=best_position,
        cleared=False,
        iterations=iteration_limit,
        debug={
            "response": "terrain_contact_iterative_position_rollback",
            "iterative_separation_model": "Collision_resolve_pair_iterative_world_vertical",
            "iterative_cleared": False,
            "iterative_iterations": iteration_limit,
            "iterative_position_delta": delta,
            "iterative_position_delta_mag": _vec3_len(delta),
            "iterative_final_penetration": best_penetration,
            "iterative_attempts": attempts,
            "velocity_unchanged_by_iterative_separation": True,
        },
    )


def _matrix3_transform_vector_shared(
    matrix: Sequence[float],
    vector: Sequence[float],
) -> Tuple[float, float, float]:
    """Mirror GUESS5_Vec3_transform_by_matrix3 for the shared matrix layout."""

    x = float(vector[0])
    y = float(vector[1])
    z = float(vector[2])
    m = tuple(float(v) for v in tuple(matrix)[:9])
    return (
        z * m[2] + x * m[0] + y * m[1],
        z * m[5] + y * m[4] + x * m[3],
        z * m[8] + y * m[7] + x * m[6],
    )


def rigid_body_point_velocity(
    position: Sequence[float],
    linear_velocity: Sequence[float],
    angular_velocity: Sequence[float],
    world_point: Sequence[float],
    *,
    rotation_matrix: Sequence[float] | None = None,
    angular_threshold_sq: float = 1.0e-5,
) -> Tuple[float, float, float]:
    """Port `RigidBody_compute_point_velocity` for spring/contact probes.

    The OG helper computes `linear_velocity + omega x r`, but first runs the
    entity-to-point offset through the entity rotation matrix when angular
    velocity has enough signal. `Piecewise_sample_blended` uses this value as
    the spring feedback-table derivative, so keep it as a shared primitive
    instead of duplicating local roll/pitch approximations in server/client code.
    """
    pos = (float(position[0]), float(position[1]), float(position[2]))
    vel = (
        float(linear_velocity[0]),
        float(linear_velocity[1]),
        float(linear_velocity[2]),
    )
    ang = (
        float(angular_velocity[0]),
        float(angular_velocity[1]),
        float(angular_velocity[2]),
    )
    point = (float(world_point[0]), float(world_point[1]), float(world_point[2]))
    mag_sq = ang[0] * ang[0] + ang[1] * ang[1] + ang[2] * ang[2]
    if mag_sq <= float(angular_threshold_sq):
        return vel

    lever = (point[0] - pos[0], point[1] - pos[1], point[2] - pos[2])
    if rotation_matrix is not None:
        try:
            if len(rotation_matrix) >= 9:
                lever = _matrix3_transform_vector_shared(rotation_matrix, lever)
        except (TypeError, ValueError):
            pass
    rotational = _vec3_cross(ang, lever)
    return (
        vel[0] + rotational[0],
        vel[1] + rotational[1],
        vel[2] + rotational[2],
    )


def _matrix3_inverse_transform_vector_shared(
    matrix: Sequence[float],
    vector: Sequence[float],
) -> Tuple[float, float, float]:
    """Rotate a world-space vector by the inverse entity matrix."""

    x = float(vector[0])
    y = float(vector[1])
    z = float(vector[2])
    m = tuple(float(v) for v in tuple(matrix)[:9])
    return (
        x * m[0] + y * m[3] + z * m[6],
        x * m[1] + y * m[4] + z * m[7],
        x * m[2] + y * m[5] + z * m[8],
    )


def mesh_aabb_half_extents_from_vertices(
    vertices: Sequence[object],
) -> Optional[Tuple[float, float, float]]:
    """Return half-extents from the mesh AABB used by OG bounds physics."""

    if not vertices:
        return None

    def coord(vertex: object, index: int, name: str) -> float:
        value = getattr(vertex, name, None)
        if value is None:
            value = vertex[index]  # type: ignore[index]
        return float(value)

    xs = [coord(vertex, 0, "x") for vertex in vertices]
    ys = [coord(vertex, 1, "y") for vertex in vertices]
    zs = [coord(vertex, 2, "z") for vertex in vertices]
    return (
        (max(xs) - min(xs)) * 0.5,
        (max(ys) - min(ys)) * 0.5,
        (max(zs) - min(zs)) * 0.5,
    )


def _decompile_mesh_bounds_inertia_diagonal(
    mass: float,
    half_extents: Sequence[float],
) -> Tuple[float, float, float]:
    """Return the diagonal inertia stored by CollisionMesh_compute_bounds_physics.

    The decompile writes inertia from full AABB extents as products of squared
    side lengths. The Python collision caches expose half-extents, so expand
    them back to full extents here.
    """

    hx = max(0.001, float(half_extents[0]))
    hy = max(0.001, float(half_extents[1]))
    hz = max(0.001, float(half_extents[2]))
    ex = hx * 2.0
    ey = hy * 2.0
    ez = hz * 2.0
    body_mass = max(0.001, float(mass))
    return (
        (ey * ey * ez * ez * body_mass) / 12.0,
        (ex * ex * ez * ez * body_mass) / 12.0,
        (ex * ex * ey * ey * body_mass) / 12.0,
    )


def _directional_inertia(
    torque_axis: Sequence[float],
    inertia_diagonal: Sequence[float],
) -> float:
    """Mirror Physics_calc_inertia_magnitude for a diagonal tensor."""

    torque_len = _vec3_len(torque_axis)
    ix = max(0.001, float(inertia_diagonal[0]))
    iy = max(0.001, float(inertia_diagonal[1]))
    iz = max(0.001, float(inertia_diagonal[2]))
    if torque_len <= 0.001:
        return (ix + iy + iz) / 3.0
    ux = float(torque_axis[0]) / torque_len
    uy = float(torque_axis[1]) / torque_len
    uz = float(torque_axis[2]) / torque_len
    return math.sqrt(ix * ux * ux + iy * uy * uy + iz * uz * uz)


def solve_static_terrain_constraint(
    *,
    position: Sequence[float],
    velocity: Sequence[float],
    angular_velocity: Sequence[float] = (0.0, 0.0, 0.0),
    contact_point: Sequence[float],
    contact_normal: Sequence[float],
    penetration: float,
    half_extents: Sequence[float],
    inertia_half_extents: Sequence[float] | None = None,
    inertia_diagonal: Sequence[float] | None = None,
    mass: float = 6700.0,
    friction: float = 0.2,
    terrain_friction: float = 1.0,
    dynamic_friction_enabled: bool = True,
    body_should_sleep: bool = False,
    body_is_sleeping: bool = False,
    terrain_should_sleep: bool = False,
    constraint_frozen: bool = False,
    slop: float = 0.005,
    correction_cap: float = 0.005,
    target_separation: float = 0.005,
    constraint_iterations: int = 100,
    solver_variant: str = "constraint",
    restitution_fraction: float = 0.1,
    enable_inactive_retest: bool = False,
    inactive_retest_bias: float = 0.1,
    projection_order: str = "body_minus_world",
    body_rotation: Sequence[float] | None = None,
    rotation_matrix: Sequence[float] | None = None,
) -> StaticTerrainConstraintResult:
    """Solve a static terrain contact using the decompiled constraint shape.

    This is the static-terrain half of the OG
    `Constraint_solve_iterative`/`Constraint_apply_friction` path:
    effective mass is computed at the contact point, normal impulses update
    both linear and angular velocity, friction uses tangential contact-point
    velocity, persistent +0xAE sleeping state softens effective mass and
    applied impulses, and the final 10% restitution impulse follows the
    decompile. Collision-pair bucketing and interpolation remain in the caller.
    """

    normal = _vec3_normalize(contact_normal)
    if normal is None:
        return StaticTerrainConstraintResult(
            position=(float(position[0]), float(position[1]), float(position[2])),
            velocity=(float(velocity[0]), float(velocity[1]), float(velocity[2])),
            angular_velocity=(
                float(angular_velocity[0]),
                float(angular_velocity[1]),
                float(angular_velocity[2]),
            ),
            debug={
                "response": "terrain_contact_constraint_solver_skipped",
                "reason": "degenerate normal",
            },
        )

    body_mass = max(0.001, float(mass))
    body_friction_coeff = max(0.0, float(friction))
    terrain_friction_coeff = max(0.0, float(terrain_friction))
    pair_friction_coeff = min(body_friction_coeff, terrain_friction_coeff)
    body_is_sleeping_flag = bool(body_is_sleeping)
    constraint_frozen_flag = bool(constraint_frozen)
    if body_is_sleeping_flag and constraint_frozen_flag:
        effective_mass_sleep_scale = 0.0
        impulse_sleep_scale = 0.0
    elif body_is_sleeping_flag:
        effective_mass_sleep_scale = 0.5
        impulse_sleep_scale = 0.5
    else:
        effective_mass_sleep_scale = 1.0
        impulse_sleep_scale = 1.0
    dynamic_friction_active = (
        bool(dynamic_friction_enabled)
        and not bool(body_should_sleep)
        and not bool(terrain_should_sleep)
    )
    if not bool(dynamic_friction_enabled):
        friction_skip_reason = "dynamic_friction_disabled"
    elif bool(body_should_sleep) or bool(terrain_should_sleep):
        friction_skip_reason = "should_sleep_flag"
    elif pair_friction_coeff <= 0.0:
        friction_skip_reason = "nonpositive_pair_friction"
    else:
        friction_skip_reason = None
    inertia_model = "provided_diagonal"
    if inertia_diagonal is None:
        inertia_extents = inertia_half_extents if inertia_half_extents is not None else half_extents
        inertia_diagonal = _decompile_mesh_bounds_inertia_diagonal(body_mass, inertia_extents)
        inertia_model = "decompile_mesh_bounds_full_extents"
    inertia_diagonal = (
        float(inertia_diagonal[0]),
        float(inertia_diagonal[1]),
        float(inertia_diagonal[2]),
    )
    pos = [float(position[0]), float(position[1]), float(position[2])]
    vel = [float(velocity[0]), float(velocity[1]), float(velocity[2])]
    ang = [
        float(angular_velocity[0]),
        float(angular_velocity[1]),
        float(angular_velocity[2]),
    ]
    point = (float(contact_point[0]), float(contact_point[1]), float(contact_point[2]))
    lever = (point[0] - pos[0], point[1] - pos[1], point[2] - pos[2])
    body_matrix: Tuple[float, ...] | None = None
    rotation_source = "identity"
    if rotation_matrix is not None:
        try:
            if len(rotation_matrix) >= 9:
                body_matrix = tuple(float(v) for v in tuple(rotation_matrix)[:9])
                rotation_source = "rotation_matrix"
        except (TypeError, ValueError):
            body_matrix = None
    if body_matrix is None and body_rotation is not None:
        try:
            if len(body_rotation) >= 3:
                body_matrix = _matrix3_from_euler_xyz_shared(
                    float(body_rotation[0]),
                    float(body_rotation[1]),
                    float(body_rotation[2]),
                )
                rotation_source = "body_rotation_euler"
        except (TypeError, ValueError):
            body_matrix = None
    if body_matrix is not None:
        lever_for_point_velocity = _matrix3_transform_vector_shared(body_matrix, lever)
    else:
        lever_for_point_velocity = lever

    correction_limit = max(0.0, min(0.5, float(correction_cap)))
    penetration_correction = max(0.0, float(penetration) - float(slop))
    position_correction = min(penetration_correction, correction_limit)
    pos[0] += normal[0] * position_correction
    pos[1] += normal[1] * position_correction
    pos[2] += normal[2] * position_correction

    def point_velocity() -> Tuple[float, float, float]:
        rotational = _vec3_cross(ang, lever_for_point_velocity)
        return (
            vel[0] + rotational[0],
            vel[1] + rotational[1],
            vel[2] + rotational[2],
        )

    def effective_mass(direction: Sequence[float]) -> Tuple[float, float, Tuple[float, float, float]]:
        torque = _vec3_cross(lever, direction)
        inertia = _directional_inertia(torque, inertia_diagonal)
        if body_is_sleeping_flag and constraint_frozen_flag:
            return 0.0, inertia, torque
        double_cross = _vec3_cross(torque, lever)
        angular_term = _vec3_dot(direction, double_cross) / max(inertia, 1e-8)
        effective = (1.0 / body_mass) + max(0.0, angular_term)
        return effective * effective_mass_sleep_scale, inertia, torque

    def apply_impulse(direction: Sequence[float], impulse: float) -> Tuple[float, float, float]:
        torque = _vec3_cross(lever, direction)
        if body_is_sleeping_flag and constraint_frozen_flag:
            return torque
        impulse = float(impulse) * impulse_sleep_scale
        inertia = _directional_inertia(torque, inertia_diagonal)
        angular_torque = (
            _matrix3_inverse_transform_vector_shared(body_matrix, torque)
            if body_matrix is not None
            else torque
        )
        linear_scale = impulse / body_mass
        angular_scale = impulse / max(inertia, 1e-8)
        vel[0] += float(direction[0]) * linear_scale
        vel[1] += float(direction[1]) * linear_scale
        vel[2] += float(direction[2]) * linear_scale
        ang[0] += angular_torque[0] * angular_scale
        ang[1] += angular_torque[1] * angular_scale
        ang[2] += angular_torque[2] * angular_scale
        return torque

    pv_before = point_velocity()
    world_point_velocity = (0.0, 0.0, 0.0)
    relative_velocity_body_minus_world = (
        pv_before[0] - world_point_velocity[0],
        pv_before[1] - world_point_velocity[1],
        pv_before[2] - world_point_velocity[2],
    )
    relative_velocity_world_minus_body = (
        world_point_velocity[0] - pv_before[0],
        world_point_velocity[1] - pv_before[1],
        world_point_velocity[2] - pv_before[2],
    )
    center_normal_before = _vec3_dot(vel, normal)
    point_normal_before = _vec3_dot(relative_velocity_body_minus_world, normal)
    opposite_point_normal_before = _vec3_dot(relative_velocity_world_minus_body, normal)
    eff_normal_initial, inertia_normal_initial, torque_normal = effective_mass(normal)
    projection_order_key = str(projection_order or "body_minus_world").strip().lower()
    if projection_order_key in {
        "opposite-if-separating",
        "opposite_if_separating",
        "opposite_if_body_separating",
        "world_if_body_separating",
    }:
        projection_order_key = "opposite_if_separating"
    elif projection_order_key in {
        "world-body",
        "world_body",
        "world_minus_body",
        "static_minus_body",
        "opposite",
    }:
        projection_order_key = "world_minus_body"
    else:
        projection_order_key = "body_minus_world"
    projection_speed_source = "body_minus_world"
    accumulated_normal_impulse = 0.0
    total_friction_impulse = 0.0
    max_friction_impulse = 0.0
    max_post_normal_tangent_speed = 0.0
    normal_iterations = 0
    friction_iterations = 0
    solver_variant_key = str(solver_variant or "constraint").strip().lower()
    if solver_variant_key in {
        "contact",
        "contact_iterative",
        "direct_contact",
        "type0d_contact",
        "type_0d_contact",
    }:
        solver_variant_key = "contact_iterative"
        iteration_limit = max(1, min(40, int(constraint_iterations)))
        solver_min_correction_initial = 0.1
        solver_min_correction_increment = 0.002
        solver_progressive_scaling = False
    else:
        solver_variant_key = "constraint_iterative"
        iteration_limit = max(1, min(100, int(constraint_iterations)))
        solver_min_correction_initial = 0.005
        solver_min_correction_increment = 0.0001
        solver_progressive_scaling = True
    primary_normal_iterations = 0
    retest_iterations = 0
    primary_start_separation_speed = point_normal_before
    primary_final_separation_speed = point_normal_before
    retest_applied = False
    retest_start_separation_speed = None
    retest_target_separation = None
    retest_final_separation_speed = None

    def projected_velocity(pass_target_separation: float) -> Tuple[Tuple[float, float, float], float, str]:
        pv = point_velocity()
        body_projection = _vec3_dot(pv, normal)
        if projection_order_key == "world_minus_body":
            return (-pv[0], -pv[1], -pv[2]), -body_projection, "world_minus_body"
        if (
            projection_order_key == "opposite_if_separating"
            and body_projection >= float(pass_target_separation)
            and -body_projection < float(pass_target_separation)
        ):
            return (-pv[0], -pv[1], -pv[2]), -body_projection, "world_minus_body_if_body_separating"
        return pv, body_projection, "body_minus_world"

    def run_constraint_pass(pass_target_separation: float) -> Tuple[float, float, int, str]:
        nonlocal accumulated_normal_impulse
        nonlocal total_friction_impulse
        nonlocal max_friction_impulse
        nonlocal max_post_normal_tangent_speed
        nonlocal normal_iterations
        nonlocal friction_iterations
        nonlocal projection_speed_source

        min_correction_threshold = solver_min_correction_initial
        projection_pv, start_speed, pass_projection_source = projected_velocity(pass_target_separation)
        start_projection_source = pass_projection_source
        projection_speed_source = pass_projection_source
        final_speed = start_speed
        pass_iterations = 0
        for iteration in range(1, iteration_limit + 1):
            projection_pv, separation_speed, pass_projection_source = projected_velocity(pass_target_separation)
            projection_speed_source = pass_projection_source
            final_speed = separation_speed
            if separation_speed >= float(pass_target_separation):
                break
            correction = float(pass_target_separation) - separation_speed
            if solver_progressive_scaling and min_correction_threshold < correction:
                correction = (correction * float(iteration)) / 500.0
            if correction < min_correction_threshold:
                correction = min_correction_threshold

            eff_normal, _inertia_normal, _torque = effective_mass(normal)
            if eff_normal <= 1e-8:
                break
            normal_impulse = correction / eff_normal
            apply_impulse(normal, normal_impulse)
            accumulated_normal_impulse += normal_impulse
            normal_iterations += 1
            pass_iterations += 1

            post_normal_pv = point_velocity()
            _post_projection_pv, final_speed, projection_speed_source = projected_velocity(pass_target_separation)
            post_normal_component = _vec3_dot(post_normal_pv, normal)
            post_normal_tangent = (
                post_normal_pv[0] - normal[0] * post_normal_component,
                post_normal_pv[1] - normal[1] * post_normal_component,
                post_normal_pv[2] - normal[2] * post_normal_component,
            )
            max_post_normal_tangent_speed = max(
                max_post_normal_tangent_speed,
                _vec3_len(post_normal_tangent),
            )

            # OG passes the relative-velocity projection buffer captured before
            # the normal impulse into Constraint_apply_friction, then recomputes
            # the projection after friction for the loop condition.
            # `opposite_if_separating` only changes the normal activation
            # projection; tangent friction still opposes the body's point motion.
            friction_pv = point_velocity() if pass_projection_source != "body_minus_world" else projection_pv
            normal_component = _vec3_dot(friction_pv, normal)
            tangent = (
                friction_pv[0] - normal[0] * normal_component,
                friction_pv[1] - normal[1] * normal_component,
                friction_pv[2] - normal[2] * normal_component,
            )
            tangent_speed = _vec3_len(tangent)
            if tangent_speed >= 0.001 and dynamic_friction_active and pair_friction_coeff > 0.0:
                tangent_dir = (
                    tangent[0] / tangent_speed,
                    tangent[1] / tangent_speed,
                    tangent[2] / tangent_speed,
                )
                eff_tangent, _inertia_tangent, _torque_tangent = effective_mass(tangent_dir)
                if eff_tangent > 1e-8:
                    friction_impulse = -(
                        pair_friction_coeff * _vec3_dot(friction_pv, tangent_dir)
                    ) / eff_tangent
                    apply_impulse(tangent_dir, friction_impulse)
                    total_friction_impulse += friction_impulse
                    max_friction_impulse = max(max_friction_impulse, abs(friction_impulse))
                    friction_iterations += 1
                    _post_friction_pv, final_speed, projection_speed_source = projected_velocity(pass_target_separation)

            min_correction_threshold += solver_min_correction_increment
        return start_speed, final_speed, pass_iterations, start_projection_source

    (
        primary_start_separation_speed,
        primary_final_separation_speed,
        primary_normal_iterations,
        primary_projection_speed_source,
    ) = run_constraint_pass(float(target_separation))

    if (
        bool(enable_inactive_retest)
        and accumulated_normal_impulse <= 0.0
        and float(inactive_retest_bias) > 0.0
    ):
        # Collision_process_pair reruns inactive constraints in retest mode,
        # where the new target is the cached final separation speed plus 0.1.
        retest_start_separation_speed = _vec3_dot(point_velocity(), normal)
        retest_target_separation = retest_start_separation_speed + float(inactive_retest_bias)
        (
            _retest_start,
            retest_final_separation_speed,
            retest_iterations,
            retest_projection_speed_source,
        ) = run_constraint_pass(retest_target_separation)
        projection_speed_source = retest_projection_speed_source
        retest_applied = retest_iterations > 0

    restitution_impulse = 0.0
    if accumulated_normal_impulse > 0.0001 and float(restitution_fraction) > 0.0:
        restitution_impulse = accumulated_normal_impulse * float(restitution_fraction)
        apply_impulse(normal, restitution_impulse)

    pv_after = point_velocity()
    center_normal_after = _vec3_dot(vel, normal)
    point_normal_after = _vec3_dot(pv_after, normal)
    normal_linear_delta = center_normal_after - center_normal_before
    angular_delta = (
        ang[0] - float(angular_velocity[0]),
        ang[1] - float(angular_velocity[1]),
        ang[2] - float(angular_velocity[2]),
    )
    debug = {
        "response": "terrain_contact_constraint_solver",
        "constraint_model": "decompile_static_terrain_sequential_impulse",
        "constraint_solver_variant": solver_variant_key,
        "constraint_iteration_limit": iteration_limit,
        "constraint_min_correction_initial": solver_min_correction_initial,
        "constraint_min_correction_increment": solver_min_correction_increment,
        "constraint_progressive_scaling": solver_progressive_scaling,
        "constraint_pair_order": "static_world_body",
        "constraint_record_order": "body_static_world",
        "constraint_record_order_source": "inferred_entity_vs_world_body_positive_impulse",
        "constraint_projection_model": "Constraint_compute_velocity_projection_body_minus_world",
        "constraint_projection_order": projection_order_key,
        "constraint_projection_speed_source": projection_speed_source,
        "constraint_primary_projection_speed_source": primary_projection_speed_source,
        "constraint_world_point_velocity_before": world_point_velocity,
        "constraint_body_point_velocity_before": pv_before,
        "constraint_relative_velocity_before": relative_velocity_body_minus_world,
        "constraint_opposite_relative_velocity_before": relative_velocity_world_minus_body,
        "constraint_normal_used_for_projection": normal,
        "constraint_body_minus_world_speed_before": point_normal_before,
        "constraint_world_minus_body_speed_before": opposite_point_normal_before,
        "constraint_selected_separation_speed_before": primary_start_separation_speed,
        "constraint_separation_speed_before": point_normal_before,
        "constraint_opposite_separation_speed_before": opposite_point_normal_before,
        "normal_impulse_body_sign": 1.0,
        "normal_impulse_world_sign": -1.0,
        "normal_impulse_body_direction": normal,
        "position_correction": position_correction,
        "position_correction_cap": correction_limit,
        "normal_velocity_before": center_normal_before,
        "point_normal_velocity_before": point_normal_before,
        "point_normal_velocity_after": point_normal_after,
        "normal_delta": normal_linear_delta,
        "target_separation": float(target_separation),
        "effective_mass_normal": eff_normal_initial,
        "normal_inertia": inertia_normal_initial,
        "normal_torque": torque_normal,
        "normal_impulse": accumulated_normal_impulse,
        "normal_iterations": normal_iterations,
        "primary_normal_iterations": primary_normal_iterations,
        "primary_start_separation_speed": primary_start_separation_speed,
        "primary_final_separation_speed": primary_final_separation_speed,
        "inactive_retest_enabled": bool(enable_inactive_retest),
        "inactive_retest_bias": float(inactive_retest_bias),
        "inactive_retest_applied": retest_applied,
        "inactive_retest_iterations": retest_iterations,
        "inactive_retest_start_separation_speed": retest_start_separation_speed,
        "inactive_retest_target_separation": retest_target_separation,
        "inactive_retest_final_separation_speed": retest_final_separation_speed,
        "friction_coeff": float(friction),
        "friction_model": "decompile_constraint_apply_friction_min_pair",
        "friction_velocity_source": "pre_normal_projection_buffer",
        "post_normal_tangent_speed_abs_max": max_post_normal_tangent_speed,
        "body_friction_coeff": body_friction_coeff,
        "terrain_friction_coeff": terrain_friction_coeff,
        "pair_friction_coeff": pair_friction_coeff,
        "dynamic_friction_enabled": bool(dynamic_friction_enabled),
        "body_should_sleep": bool(body_should_sleep),
        "body_is_sleeping": body_is_sleeping_flag,
        "terrain_should_sleep": bool(terrain_should_sleep),
        "constraint_frozen": constraint_frozen_flag,
        "effective_mass_sleep_scale": effective_mass_sleep_scale,
        "impulse_sleep_scale": impulse_sleep_scale,
        "friction_skip_reason": friction_skip_reason,
        "friction_impulse": total_friction_impulse,
        "friction_impulse_abs_max": max_friction_impulse,
        "friction_iterations": friction_iterations,
        "restitution_fraction": float(restitution_fraction),
        "restitution_impulse": restitution_impulse,
        "contact_lever": lever,
        "contact_lever_point_velocity_frame": lever_for_point_velocity,
        "angular_velocity_frame": "entity_local",
        "torque_delta_frame": "entity_local" if body_matrix is not None else "world_identity",
        "rotation_source": rotation_source,
        "rotation_matrix": body_matrix,
        "inertia_diagonal": inertia_diagonal,
        "inertia_model": inertia_model,
        "angular_velocity_before": (
            float(angular_velocity[0]),
            float(angular_velocity[1]),
            float(angular_velocity[2]),
        ),
        "angular_velocity_after": (ang[0], ang[1], ang[2]),
        "angular_delta": angular_delta,
        "point_velocity_before": pv_before,
        "point_velocity_after": pv_after,
    }
    return StaticTerrainConstraintResult(
        position=(pos[0], pos[1], pos[2]),
        velocity=(vel[0], vel[1], vel[2]),
        angular_velocity=(ang[0], ang[1], ang[2]),
        debug=debug,
    )


def _short_angle_delta(target: float, current: float) -> float:
    """Return the shortest signed delta from current to target in radians."""
    delta = (float(target) - float(current) + math.pi) % (2.0 * math.pi) - math.pi
    if delta <= -math.pi:
        delta += 2.0 * math.pi
    return delta


def entity_interp_factor(delta_seconds: float) -> float:
    """Mirror Entity_calc_interp_factor from the decompile."""

    delta = max(0.0, float(delta_seconds))
    if delta > 0.2:
        return 0.0
    if delta < 0.04:
        return 1.0
    return ((1.0 / delta) - 5.0) / 20.0


def _u32_tick_as_float(tick: int) -> float:
    value = int(tick)
    if value < 0:
        value += 4294967296
    return float(value & 0xFFFFFFFF)


def entity_interpolate_toward_target_decision(
    *,
    current_position: Sequence[float],
    target_position: Sequence[float] | None,
    current_rotation: Sequence[float],
    target_rotation: Sequence[float] | None,
    tolerance: float,
    combined_radius: float,
    current_tick: int,
    last_interp_tick: int,
    delta_seconds: float,
    wake_override: bool = False,
    debug_curve_enabled: bool = False,
    rotation_distance: float | None = None,
) -> EntityInterpolationDecision:
    """Evaluate the decompiled Entity_interpolate_toward_target decision.

    The exact OG rotation metric comes from FPU state left by
    `Euler_compose_rotations`; callers can pass that value when observed. The
    fallback uses wrapped per-axis distance so the threshold shape remains
    inspectable until the FPU metric is recovered.
    """

    interp_factor = entity_interp_factor(delta_seconds)
    tol = float(tolerance)
    radius = float(combined_radius)
    elapsed_ticks = _u32_tick_as_float(current_tick) - _u32_tick_as_float(last_interp_tick)

    base_debug = {
        "entity_interpolation_model": "decompile_entity_interpolate_toward_target",
        "interp_factor": interp_factor,
        "delta_seconds": float(delta_seconds),
        "tolerance": tol,
        "combined_radius": radius,
        "current_tick": int(current_tick),
        "last_interp_tick": int(last_interp_tick),
        "elapsed_ticks": elapsed_ticks,
        "wake_override": bool(wake_override),
        "debug_curve_enabled": bool(debug_curve_enabled),
    }

    if debug_curve_enabled:
        return EntityInterpolationDecision(
            action="skip_debug_curve",
            interp_factor=interp_factor,
            position_distance=0.0,
            rotation_distance=0.0,
            combined_radius=radius,
            tolerance=tol,
            elapsed_ticks=elapsed_ticks,
            reset_physics=False,
            wake=False,
            update_last_interp_tick=False,
            debug={**base_debug, "interpolation_action": "skip_debug_curve"},
        )

    if wake_override:
        return EntityInterpolationDecision(
            action="wake_forced",
            interp_factor=interp_factor,
            position_distance=0.0,
            rotation_distance=0.0,
            combined_radius=radius,
            tolerance=tol,
            elapsed_ticks=elapsed_ticks,
            reset_physics=False,
            wake=True,
            update_last_interp_tick=False,
            debug={**base_debug, "interpolation_action": "wake_forced"},
        )

    if target_position is None or target_rotation is None:
        return EntityInterpolationDecision(
            action="target_unavailable",
            interp_factor=interp_factor,
            position_distance=0.0,
            rotation_distance=0.0,
            combined_radius=radius,
            tolerance=tol,
            elapsed_ticks=elapsed_ticks,
            reset_physics=False,
            wake=False,
            update_last_interp_tick=False,
            debug={**base_debug, "interpolation_action": "target_unavailable"},
        )

    pos_distance = (
        abs(float(target_position[0]) - float(current_position[0]))
        + abs(float(target_position[1]) - float(current_position[1]))
        + abs(float(target_position[2]) - float(current_position[2]))
    )
    rotation_model = "provided"
    if rotation_distance is None:
        rotation_distance = (
            abs(_short_angle_delta(float(target_rotation[0]), float(current_rotation[0])))
            + abs(_short_angle_delta(float(target_rotation[1]), float(current_rotation[1])))
            + abs(_short_angle_delta(float(target_rotation[2]), float(current_rotation[2])))
        )
        rotation_model = "wrapped_axis_manhattan_fallback"
    rot_distance = float(rotation_distance)

    position_gate = pos_distance * interp_factor < tol + 0.03
    rotation_gate = rot_distance * interp_factor < (tol / 100.0) + 0.006
    radius_gate = radius * interp_factor < (tol * 1.4) + 1.3
    reset_gate = elapsed_ticks > interp_factor * 12.0

    debug = {
        **base_debug,
        "position_distance": pos_distance,
        "rotation_distance": rot_distance,
        "rotation_distance_model": rotation_model,
        "position_gate": position_gate,
        "rotation_gate": rotation_gate,
        "radius_gate": radius_gate,
        "reset_tick_threshold": interp_factor * 12.0,
        "reset_gate": reset_gate,
    }
    if position_gate and rotation_gate and radius_gate:
        if reset_gate:
            action = "reset_physics"
            reset_physics = True
            wake = False
        else:
            action = "wake_without_tick_update"
            reset_physics = False
            wake = True
        update_last_interp_tick = False
    else:
        action = "wake_update_last_interp_tick"
        reset_physics = False
        wake = True
        update_last_interp_tick = True

    return EntityInterpolationDecision(
        action=action,
        interp_factor=interp_factor,
        position_distance=pos_distance,
        rotation_distance=rot_distance,
        combined_radius=radius,
        tolerance=tol,
        elapsed_ticks=elapsed_ticks,
        reset_physics=reset_physics,
        wake=wake,
        update_last_interp_tick=update_last_interp_tick,
        debug={**debug, "interpolation_action": action},
    )


def tank_spring_attitude_step(
    current_roll: float,
    current_pitch: float,
    target_roll: float,
    target_pitch: float,
    roll_velocity: float,
    pitch_velocity: float,
    dt: float,
    *,
    stiffness: float = 40.0,
    damping: float = 2.0,
) -> TankSpringAttitudeStep:
    """Step the tank spring's pitch/roll attitude toward its target.

    `Spring_compute_suspension_forces` does not set entity pitch/roll directly:
    it accumulates pitch/roll torque, and `Spring_apply_forces_to_entity` adds
    that torque to the entity angular velocity. This helper keeps the public
    Python runtimes on that shape while the full per-point force curve is still
    being ported. Defaults use the recovered uniform spring stiffness (`40`)
    and the runtime angular damping from `VehiclePhysicsConfig`.
    """
    step_dt = max(0.0, float(dt))
    spring_k = max(0.0, float(stiffness))
    spring_damp = max(0.0, float(damping))
    cur_roll = float(current_roll)
    cur_pitch = float(current_pitch)
    vel_roll = float(roll_velocity)
    vel_pitch = float(pitch_velocity)

    roll_error = _short_angle_delta(target_roll, cur_roll)
    pitch_error = _short_angle_delta(target_pitch, cur_pitch)
    roll_torque = spring_k * roll_error - spring_damp * vel_roll
    pitch_torque = spring_k * pitch_error - spring_damp * vel_pitch

    if step_dt > 0.0:
        vel_roll += roll_torque * step_dt
        vel_pitch += pitch_torque * step_dt
        cur_roll = (cur_roll + vel_roll * step_dt) % (2.0 * math.pi)
        cur_pitch = (cur_pitch + vel_pitch * step_dt) % (2.0 * math.pi)

    return TankSpringAttitudeStep(
        roll=cur_roll,
        pitch=cur_pitch,
        roll_velocity=vel_roll,
        pitch_velocity=vel_pitch,
        target_roll=float(target_roll),
        target_pitch=float(target_pitch),
        roll_error=float(roll_error),
        pitch_error=float(pitch_error),
        roll_torque=float(roll_torque),
        pitch_torque=float(pitch_torque),
        stiffness=float(spring_k),
        damping=float(spring_damp),
        dt=float(step_dt),
    )


def _matrix3_from_euler_xyz_shared(ex: float, ey: float, ez: float) -> tuple[float, ...]:
    """Build the row-major XYZ rotation matrix used by the decompiled client."""
    cx = math.cos(ex)
    sx = math.sin(ex)
    cy = math.cos(ey)
    sy = math.sin(ey)
    cz = math.cos(ez)
    sz = math.sin(ez)
    return (
        cz * cy,
        cz * sy * sx - sz * cx,
        sz * sx + cz * cx * sy,
        sz * cy,
        sy * sx * sz + cz * cx,
        sy * cx * sz - cz * sx,
        -sy,
        cy * sx,
        cx * cy,
    )


def _f32_shared(value: float) -> float:
    return struct.unpack("f", struct.pack("f", float(value)))[0]


_F32_TWO_PI = _f32_shared(6.2831855)


def _normalize_angle_positive_shared(angle: float) -> float:
    out = _f32_shared(angle)
    if out > 20000.0 or out < -20000.0:
        return 0.0
    while out < 0.0:
        out = _f32_shared(out + _F32_TWO_PI)
    while out > _F32_TWO_PI:
        out = _f32_shared(out - _F32_TWO_PI)
    return out


def _matrix3_from_axis_angle_shared(
    omega_x: float,
    omega_y: float,
    omega_z: float,
) -> tuple[float, ...]:
    angle_sq = omega_x * omega_x + omega_y * omega_y + omega_z * omega_z
    angle_f64 = math.sqrt(angle_sq)
    angle = _f32_shared(angle_f64)
    if angle < 1e-05:
        return (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)

    inv_len = _f32_shared(1.0 / angle)
    nx = _f32_shared(omega_x * inv_len)
    ny = _f32_shared(omega_y * inv_len)
    nz = _f32_shared(omega_z * inv_len)
    c = _f32_shared(math.cos(angle_f64))
    s = _f32_shared(math.sin(angle_f64))
    t = _f32_shared(1.0 - c)
    t_nx = _f32_shared(nx * t)
    t_ny = _f32_shared(ny * t)
    t_nz = _f32_shared(nz * t)

    return (
        _f32_shared(_f32_shared(nx * t_nx) + c),
        _f32_shared(_f32_shared(ny * t_nx) + _f32_shared(nz * s)),
        _f32_shared(_f32_shared(t_nx * nz) - _f32_shared(ny * s)),
        _f32_shared(_f32_shared(t_ny * nx) - _f32_shared(nz * s)),
        _f32_shared(_f32_shared(ny * t_ny) + c),
        _f32_shared(_f32_shared(t_ny * nz) + _f32_shared(nx * s)),
        _f32_shared(_f32_shared(nx * t_nz) + _f32_shared(ny * s)),
        _f32_shared(_f32_shared(ny * t_nz) - _f32_shared(nx * s)),
        _f32_shared(_f32_shared(nz * t_nz) + c),
    )


def _extract_euler_angles_shared(matrix: Sequence[float]) -> tuple[float, float, float]:
    fm0 = _f32_shared(float(matrix[0]))
    fm1 = _f32_shared(float(matrix[1]))
    fm3 = _f32_shared(float(matrix[3]))
    fm6 = _f32_shared(float(matrix[6]))
    fm7 = _f32_shared(float(matrix[7]))
    fm8 = _f32_shared(float(matrix[8]))
    gimbal = math.sqrt(fm0 * fm0 + fm1 * fm1)

    if gimbal <= 1.9073486328125e-06:
        euler_x = _f32_shared(math.atan2(fm7, fm8))
        euler_y = _f32_shared(math.atan2(-fm6, gimbal))
        euler_z = 0.0
    else:
        euler_x = _f32_shared(math.atan2(fm7, fm8))
        euler_y = _f32_shared(math.atan2(-fm6, gimbal))
        euler_z = _f32_shared(math.atan2(fm3, fm0))
    return (
        _normalize_angle_positive_shared(euler_x),
        _normalize_angle_positive_shared(euler_y),
        _normalize_angle_positive_shared(euler_z),
    )


def _angle_delta_shared(target: float, source: float) -> float:
    delta = _f32_shared(float(target) - float(source))
    while delta <= -math.pi:
        delta = _f32_shared(delta + _F32_TWO_PI)
    while delta > math.pi:
        delta = _f32_shared(delta - _F32_TWO_PI)
    return delta


def tank_body_matrix_with_heading(
    rotation_matrix: Sequence[float] | None,
    heading: float,
    *,
    fallback_roll: float = 0.0,
    fallback_pitch: float = 0.0,
) -> tuple[float, ...]:
    """Return a spring/body matrix whose yaw matches the authoritative heading.

    The tank keeps yaw in the normal entity heading path while spring forces
    maintain the body pitch/roll matrix. Control-plane resets and yaw physics
    can therefore leave a valid spring matrix with stale yaw. `Spring_update_world_state`
    and `TankVehicle_apply_physics` both consume the full entity matrix, so
    rotate the matrix basis around world Z to the current heading before using it.
    """
    try:
        matrix = tuple(_f32_shared(float(v)) for v in tuple(rotation_matrix or ())[:9])
    except (TypeError, ValueError):
        matrix = ()
    if len(matrix) != 9:
        return _matrix3_from_euler_xyz_shared(
            float(fallback_roll),
            float(fallback_pitch),
            float(heading),
        )

    _roll, _pitch, current_yaw = _extract_euler_angles_shared(matrix)
    delta = _angle_delta_shared(float(heading), current_yaw)
    if abs(delta) <= 1e-6:
        return tuple(float(v) for v in matrix)

    cos_d = _f32_shared(math.cos(delta))
    sin_d = _f32_shared(math.sin(delta))
    return (
        _f32_shared(_f32_shared(cos_d * matrix[0]) - _f32_shared(sin_d * matrix[3])),
        _f32_shared(_f32_shared(cos_d * matrix[1]) - _f32_shared(sin_d * matrix[4])),
        _f32_shared(_f32_shared(cos_d * matrix[2]) - _f32_shared(sin_d * matrix[5])),
        _f32_shared(_f32_shared(sin_d * matrix[0]) + _f32_shared(cos_d * matrix[3])),
        _f32_shared(_f32_shared(sin_d * matrix[1]) + _f32_shared(cos_d * matrix[4])),
        _f32_shared(_f32_shared(sin_d * matrix[2]) + _f32_shared(cos_d * matrix[5])),
        float(matrix[6]),
        float(matrix[7]),
        float(matrix[8]),
    )


def matrix3_integrate_angular_shared(
    matrix: Sequence[float],
    angular_velocity: Sequence[float],
    dt: float,
    *,
    angular_acceleration: Sequence[float] | None = None,
    angular_damping: float = 0.0,
) -> tuple[tuple[float, ...], tuple[float, float, float], tuple[float, float, float]]:
    """Mirror `GUESS5_Matrix3_integrate_angular` for spring body pose.

    The decompile builds an axis-angle delta from angular_velocity * dt,
    multiplies it into the current matrix using float intermediates, extracts
    euler angles, then applies angular acceleration plus damping to angular
    velocity for the next substep.
    """
    fdt = _f32_shared(max(0.0, float(dt)))
    omega = (
        _f32_shared(float(angular_velocity[0]) * fdt),
        _f32_shared(float(angular_velocity[1]) * fdt),
        _f32_shared(float(angular_velocity[2]) * fdt),
    )
    delta = _matrix3_from_axis_angle_shared(omega[0], omega[1], omega[2])
    source = tuple(_f32_shared(float(v)) for v in tuple(matrix)[:9])
    if len(source) != 9:
        source = _matrix3_from_euler_xyz_shared(0.0, 0.0, 0.0)
    d = delta
    m = source

    r00 = _f32_shared(_f32_shared(_f32_shared(d[2] * m[2]) + _f32_shared(d[0] * m[0])) + _f32_shared(d[1] * m[1]))
    r01 = _f32_shared(_f32_shared(_f32_shared(d[2] * m[5]) + _f32_shared(d[0] * m[3])) + _f32_shared(d[1] * m[4]))
    r02 = _f32_shared(_f32_shared(_f32_shared(d[2] * m[8]) + _f32_shared(d[0] * m[6])) + _f32_shared(d[1] * m[7]))
    r10 = _f32_shared(_f32_shared(_f32_shared(d[5] * m[2]) + _f32_shared(d[3] * m[0])) + _f32_shared(d[4] * m[1]))
    r11 = _f32_shared(_f32_shared(_f32_shared(d[5] * m[5]) + _f32_shared(d[3] * m[3])) + _f32_shared(d[4] * m[4]))
    r12 = _f32_shared(_f32_shared(_f32_shared(d[5] * m[8]) + _f32_shared(d[3] * m[6])) + _f32_shared(d[4] * m[7]))
    r20 = _f32_shared(_f32_shared(_f32_shared(d[8] * m[2]) + _f32_shared(d[6] * m[0])) + _f32_shared(d[7] * m[1]))
    r21 = _f32_shared(_f32_shared(_f32_shared(d[8] * m[5]) + _f32_shared(d[6] * m[3])) + _f32_shared(d[7] * m[4]))
    r22 = _f32_shared(_f32_shared(_f32_shared(d[8] * m[8]) + _f32_shared(d[6] * m[6])) + _f32_shared(d[7] * m[7]))

    out_matrix = (
        float(r00),
        float(r10),
        float(r20),
        float(r01),
        float(r11),
        float(r21),
        float(r02),
        float(r12),
        float(r22),
    )
    euler = _extract_euler_angles_shared(out_matrix)

    damp = max(0.0, float(angular_damping))
    accel_source = tuple(float(v) for v in tuple(angular_acceleration or (0.0, 0.0, 0.0))[:3])
    if len(accel_source) != 3:
        accel_source = (0.0, 0.0, 0.0)
    if fdt > 0.0 and (damp > 0.0 or any(abs(v) > 0.0 for v in accel_source)):
        out_velocity = tuple(
            _f32_shared(
                float(angular_velocity[i])
                + _f32_shared(
                    _f32_shared(float(accel_source[i]))
                    + _f32_shared(_f32_shared(-float(angular_velocity[i])) * _f32_shared(damp))
                )
                * fdt
            )
            for i in range(3)
        )
    else:
        out_velocity = (
            float(angular_velocity[0]),
            float(angular_velocity[1]),
            float(angular_velocity[2]),
        )
    return out_matrix, euler, out_velocity


def tank_body_matrix_drive_basis(
    heading: float,
    *,
    roll: float = 0.0,
    pitch: float = 0.0,
    rotation_matrix: Sequence[float] | None = None,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return TankVehicle_apply_physics' body-rotated forward/right basis.

    The decompiled tank drive path builds a local movement vector with
    `move_vec_z = 0`, then rotates that vector by the entity Euler/body matrix
    before applying the move-adjust cap. Once the clone has live spring-derived
    body pitch/roll, using the body matrix is the decompile-backed path; the
    older flat-yaw basis remains useful only as an explicit debug fallback.
    """
    matrix = tank_body_matrix_with_heading(
        rotation_matrix,
        heading,
        fallback_roll=float(roll),
        fallback_pitch=float(pitch),
    )
    # Local +X is forward, local +Y is right in the same row-major matrix shape
    # used by Spring_update_world_state.
    forward = (matrix[0], matrix[3], matrix[6])
    right = (matrix[1], matrix[4], matrix[7])
    return forward, right


def _sample_float(sample: Mapping[str, object], key: str, default: float = 0.0) -> float:
    try:
        return float(sample.get(key, default))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float(default)


def _sample_pair(
    sample: Mapping[str, object],
    key: str,
    default: tuple[float, float] = (0.0, 0.0),
) -> tuple[float, float]:
    value = sample.get(key)
    try:
        return (float(value[0]), float(value[1]))  # type: ignore[index]
    except (TypeError, IndexError, ValueError):
        return default


def _sample_vec3(
    sample: Mapping[str, object],
    key: str,
    default: tuple[float, float, float] = (0.0, 0.0, 1.0),
) -> tuple[float, float, float]:
    value = sample.get(key)
    try:
        return (float(value[0]), float(value[1]), float(value[2]))  # type: ignore[index]
    except (TypeError, IndexError, ValueError):
        return default


def _spring_sample_world_offset(sample: Mapping[str, object]) -> tuple[float, float, float]:
    world_x, world_y = _sample_pair(sample, "world_offset")
    return (world_x, world_y, _sample_float(sample, "world_offset_z", 0.0))


def _spring_sample_local_offset(sample: Mapping[str, object]) -> tuple[float, float, float]:
    local_x, local_y = _sample_pair(sample, "local_offset", _sample_pair(sample, "world_offset"))
    return (local_x, local_y, 0.0)


def _spring_edge_angle(
    samples: Sequence[Mapping[str, object]],
    point_a: int,
    point_b: int,
) -> float:
    if point_a >= len(samples) or point_b >= len(samples):
        return 0.0
    ax, ay, az = _spring_sample_world_offset(samples[point_a])
    bx, by, bz = _spring_sample_world_offset(samples[point_b])
    dx = bx - ax
    dy = by - ay
    dz = bz - az
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length <= 1e-9:
        return 0.0
    # Spring_calc_edge_angle uses (z_a - z_b) / segment_length.
    ratio = max(-1.0, min(1.0, (az - bz) / length))
    return math.asin(ratio)


def _spring_apply_shear_pair(
    corrections: list[float],
    samples: Sequence[Mapping[str, object]],
    point_a: int,
    point_b: int,
    reference_a: int,
    reference_b: int,
    *,
    local_axis: int,
    stiffness: float,
) -> None:
    if point_a >= len(samples) or point_b >= len(samples):
        return
    local_a = _spring_sample_local_offset(samples[point_a])
    local_b = _spring_sample_local_offset(samples[point_b])
    length_component = abs(local_a[local_axis] - local_b[local_axis])
    if length_component <= 1e-9:
        return
    angle = _spring_edge_angle(samples, point_a, point_b)
    reference_angle = _spring_edge_angle(samples, reference_a, reference_b)
    # The decompiled helper has the shape `sin(angle_a) -
    # tan(angle_b)*cos(angle_a)`. That expression is zero when paired edges have
    # the same angle and produces an asymmetric point correction when the spring
    # quad twists.
    reference_angle = max(math.radians(-80.0), min(math.radians(80.0), reference_angle))
    shear = (
        math.sin(angle) - math.tan(reference_angle) * math.cos(angle)
    ) * length_component * max(0.0, float(stiffness))
    if shear < 0.0:
        corrections[point_b] -= shear
    else:
        corrections[point_a] += shear


def tank_spring_shear_corrections(
    samples: Sequence[Mapping[str, object]],
    *,
    diagonal_stiffness: float = OG_TANK_SPRING_SHEAR_STIFFNESS,
    edge_stiffness: float = OG_TANK_SPRING_SHEAR_STIFFNESS,
) -> tuple[float, ...]:
    """Return decompile-shaped per-point spring shear corrections.

    `Spring_compute_suspension_forces` first adds two diagonal and two edge
    shear terms into the per-point force-curve input before sampling the
    piecewise spring curve. The exact FPU argument recovery is imperfect in the
    decompile, but the helper shape and topology are clear: compare paired
    edge inclination angles, scale by local point separation and SpringParam
    stiffness, then apply the signed result to one endpoint.
    """
    clean = list(samples[:OG_TANK_SOFTBODY_POINT_COUNT])
    corrections = [0.0 for _ in clean]
    if len(clean) < OG_TANK_SOFTBODY_POINT_COUNT:
        return tuple(corrections)

    _spring_apply_shear_pair(
        corrections,
        clean,
        0,
        2,
        1,
        3,
        local_axis=0,
        stiffness=diagonal_stiffness,
    )
    _spring_apply_shear_pair(
        corrections,
        clean,
        1,
        3,
        0,
        2,
        local_axis=0,
        stiffness=diagonal_stiffness,
    )
    _spring_apply_shear_pair(
        corrections,
        clean,
        0,
        1,
        2,
        3,
        local_axis=1,
        stiffness=edge_stiffness,
    )
    _spring_apply_shear_pair(
        corrections,
        clean,
        2,
        3,
        0,
        1,
        local_axis=1,
        stiffness=edge_stiffness,
    )
    return tuple(float(v) for v in corrections)


def piecewise_interpolate(
    samples: Sequence[float],
    value: float,
    *,
    domain_min: float = 0.0,
    domain_max: float = 1.0,
) -> float:
    """Linearly sample an OG piecewise table.

    `GUESS5_Piecewise_interpolate` clamps outside the configured domain and
    linearly blends between evenly spaced samples. The tank `.pcw` files use
    the default `0..1` domain.
    """
    values = tuple(float(v) for v in samples)
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    v = float(value)
    lo = float(domain_min)
    hi = float(domain_max)
    if hi <= lo:
        return values[-1]
    if v <= lo:
        return values[0]
    if v >= hi:
        return values[-1]
    scaled = (v - lo) / (hi - lo) * float(len(values) - 1)
    idx = int(math.floor(scaled))
    if idx >= len(values) - 1:
        idx = len(values) - 2
    frac = scaled - float(idx)
    return values[idx] + (values[idx + 1] - values[idx]) * frac


def tank_spring_height_curve_factor(
    clearance: float,
    *,
    rest_height: float = OG_TANK_SOFTBODY_REST_HEIGHT,
    jet_abate_max: float = OG_TANK_JET_ABATE_MAX,
) -> float:
    """Return the decompile-backed tank jet-height curve multiplier."""
    rest = max(0.001, float(rest_height))
    abate = max(0.001, float(jet_abate_max))
    height_ratio = max(0.0, float(clearance)) / rest
    return piecewise_interpolate(OG_TANK_JET_HEIGHT_CURVE, height_ratio / abate)


def tank_spring_piecewise_blend_factor(
    clearance: float,
    stretch_ratio: float,
    *,
    rest_height: float = OG_TANK_SOFTBODY_REST_HEIGHT,
) -> float:
    """Return `GUESS4_Piecewise_sample_blended`'s output blend parameter."""
    rest = max(0.001, float(rest_height))
    height_ratio = max(0.0, min(1.0, float(clearance) / rest))
    stretch = max(0.0, min(1.0, float(stretch_ratio)))
    return min(stretch, max(0.0, 1.0 - height_ratio))


def tank_spring_scalar_stretch_ratio(
    vel_x: float,
    vel_y: float,
    *,
    speed_denominator: float = OG_TANK_SPRING_STRETCH_SPEED_DENOMINATOR,
) -> float:
    """Return the scalar stretch stored at spring state +0x88.

    The recovered call site passes the entity to `GUESS4_Spring_check_stretch_ratio`
    before `TankVehicle_apply_physics`. The function reads entity velocity X/Y
    at +0x18/+0x1C, computes horizontal speed, divides by the spring config's
    first float, and returns a value clamped to `<= 1.0`.
    """
    try:
        x = float(vel_x)
        y = float(vel_y)
        denom = float(speed_denominator)
    except (TypeError, ValueError):
        return 0.0
    if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(denom)):
        return 0.0
    if denom <= 0.0:
        return 0.0
    ratio = math.hypot(x, y) / denom
    if ratio <= 0.0:
        return 0.0
    if ratio >= 1.0:
        return 1.0
    return float(ratio)


def _clamp_unit(value: float) -> float:
    if value < -1.0:
        return -1.0
    if value > 1.0:
        return 1.0
    return value


def feedback_table_apply_curves(
    table: FeedbackCurveTable,
    error: float,
    prime: float,
) -> float:
    """Apply one OG `.atbl` response table.

    This ports the `GUESS5_AimControl_apply_curves` shape used by
    `GUESS4_Piecewise_sample_blended`: normalize error and derivative inputs,
    sample the raw/correction curves, optionally sample the damper weighting
    curves, restore signs, clamp the blend, then multiply by `abs_out`.
    """
    range_x = max(0.001, float(table.abs_max_error))
    range_y = max(0.001, float(table.abs_max_prime))
    input_x = float(error)
    input_y = float(prime)

    norm_x = _clamp_unit(input_x / range_x)
    norm_y = _clamp_unit(input_y / range_y)
    scaled_x = _clamp_unit(float(table.mul_error) * input_x / range_x)
    scaled_y = _clamp_unit(float(table.mul_prime) * input_y / range_y)

    sign_x = scaled_x < 0.0
    sign_y = scaled_y < 0.0
    if sign_x:
        scaled_x = -scaled_x
        norm_x = -norm_x
    if sign_y:
        scaled_y = -scaled_y
        norm_y = -norm_y

    curve_x = piecewise_interpolate(table.raw, scaled_x)
    curve_y = -piecewise_interpolate(table.cor, scaled_y)
    if table.use_damper:
        weight_x = piecewise_interpolate(table.err, norm_x)
        weight_y = piecewise_interpolate(table.prm, norm_y)
    else:
        weight_x = 1.0
        weight_y = 1.0

    if sign_x:
        curve_x = -curve_x
    if sign_y:
        curve_y = -curve_y

    blended = _clamp_unit(weight_x * curve_y + weight_y * curve_x)
    return float(table.abs_out) * blended


def tank_spring_piecewise_force_sample(
    force_input: float,
    terrain_height: float,
    point_velocity_z: float,
    stretch_ratio: float,
    *,
    point_count: int = OG_TANK_SOFTBODY_POINT_COUNT,
    rest_height: float = OG_TANK_SOFTBODY_REST_HEIGHT,
    gravity_pct: float = 1.0,
    physics_timestep_factor: float = OG_PHYSICS_TIMESTEP_FACTOR,
    jet_abate_max: float = OG_TANK_JET_ABATE_MAX,
) -> TankSpringPiecewiseForceSample:
    """Sample the decompile-backed tank spring piecewise force path.

    `Spring_compute_suspension_forces` feeds
    `GUESS4_Piecewise_sample_blended` with
    `stiffness * max_altitude + shear + force_offset` and the per-point
    terrain height. This helper ports the visible part of that routine using
    the recovered tank `.pcw` and `.atbl` tables. Point velocity is currently
    supplied as the vertical component available to the public runtime; live
    force-row probes can replace it with true point velocity when exposed.
    """
    rest = max(0.001, float(rest_height))
    terrain = max(0.5, float(terrain_height))
    stretch = max(0.0, min(1.0, float(stretch_ratio)))
    count_denom = max(1.0, float(int(point_count) - 1))

    height_ratio_unclamped = terrain / rest
    height_ratio = min(1.0, max(0.0, height_ratio_unclamped))
    blend_factor = min(stretch, max(0.0, 1.0 - height_ratio))
    height_curve_factor = tank_spring_height_curve_factor(
        terrain,
        rest_height=rest,
        jet_abate_max=jet_abate_max,
    )
    speed_curve_factor = piecewise_interpolate(OG_TANK_JET_SPEED_CURVE, stretch)
    # The file names are misleading here. The recovered
    # `GUESS4_Piecewise_sample_blended` call order samples the `abate` table
    # with the height ratio, then uses the `height_consider` table as the
    # stretch-side denominator term. Live OG force rows match that call order;
    # the name-based mapping over-predicts active rough-terrain spring impulse.
    height_consider_factor = piecewise_interpolate(
        OG_TANK_JET_ABATE_CURVE,
        height_ratio,
    )
    abate_factor = piecewise_interpolate(OG_TANK_JET_HEIGHT_CONSIDER_CURVE, stretch)
    react_blend = (
        (speed_curve_factor + height_consider_factor * abate_factor)
        / max(0.001, abate_factor + 1.0)
    )

    force_error = float(force_input) - terrain
    prime = float(point_velocity_z)
    fast_react = feedback_table_apply_curves(
        OG_TANK_JET_FAST_REACT_TABLE,
        force_error,
        prime,
    )
    slow_react = feedback_table_apply_curves(
        OG_TANK_JET_SLOW_REACT_TABLE,
        force_error,
        prime,
    )
    response = react_blend * fast_react + (1.0 - react_blend) * slow_react
    base = max(0.0, float(physics_timestep_factor))
    force = (
        (base + response * max(0.0, float(gravity_pct)) * base)
        * height_curve_factor
        / count_denom
    )
    if force < 0.0:
        force = 0.0
    return TankSpringPiecewiseForceSample(
        force_magnitude=float(force),
        blend_factor=float(blend_factor),
        react_blend=float(react_blend),
        fast_react=float(fast_react),
        slow_react=float(slow_react),
        height_curve_factor=float(height_curve_factor),
        speed_curve_factor=float(speed_curve_factor),
        height_consider_factor=float(height_consider_factor),
        abate_factor=float(abate_factor),
        height_ratio=float(height_ratio),
        force_error=float(force_error),
        point_velocity_z=float(prime),
    )


def tank_spring_force_attitude_step(
    current_roll: float,
    current_pitch: float,
    heading: float,
    samples: Sequence[Mapping[str, object]],
    roll_velocity: float,
    pitch_velocity: float,
    dt: float,
    total_lift: float,
    *,
    damping: float = 2.0,
    point_forces: Sequence[float] | None = None,
    point_blend_factors: Sequence[float] | None = None,
    force_base: float = OG_TANK_FORCE_BASE_REACT,
    force_scale: float = OG_TANK_FORCE_SLOPE_REACT,
    torque_model: str = "decompile_config",
    integration_model: str = "decompile_accel",
    rotation_matrix: Sequence[float] | None = None,
) -> TankSpringForceAttitudeStep:
    """Step tank pitch/roll from per-point suspension force torque.

    The OG spring path does not directly snap the entity to the accumulated
    terrain normal. `Spring_compute_suspension_forces` samples a force per
    spring point, applies that force along the spring point normal, computes
    force-vs-lever torque, then zeroes yaw torque. `Spring_apply_forces_to_entity`
    accumulates that pitch/roll torque into entity angular acceleration; this
    helper ports that timing while the exact piecewise curve is still being
    recovered.
    """
    step_dt = max(0.0, float(dt))
    lift = max(0.0, float(total_lift))
    spring_damp = max(0.0, float(damping))
    cur_roll = float(current_roll)
    cur_pitch = float(current_pitch)
    vel_roll = float(roll_velocity)
    vel_pitch = float(pitch_velocity)
    velocity_before = (vel_roll, vel_pitch)
    integrate_model = str(integration_model or "decompile_accel").strip().lower()
    if integrate_model not in {"decompile_accel", "decompile_impulse", "legacy_accel"}:
        integrate_model = "decompile_accel"
    try:
        source_matrix = (
            tuple(float(v) for v in tuple(rotation_matrix or ())[:9])
            if rotation_matrix is not None
            else ()
        )
    except (TypeError, ValueError):
        source_matrix = ()
    if len(source_matrix) != 9:
        source_matrix = _matrix3_from_euler_xyz_shared(cur_roll, cur_pitch, float(heading))
    else:
        source_matrix = tank_body_matrix_with_heading(
            source_matrix,
            heading,
            fallback_roll=cur_roll,
            fallback_pitch=cur_pitch,
        )

    clean_samples = list(samples[:4])
    point_count = len(clean_samples)
    if lift <= 0.0 or point_count <= 0:
        roll_torque = -spring_damp * vel_roll
        pitch_torque = -spring_damp * vel_pitch
        if step_dt > 0.0:
            vel_roll += roll_torque * step_dt
            vel_pitch += pitch_torque * step_dt
            cur_roll = (cur_roll + vel_roll * step_dt) % (2.0 * math.pi)
            cur_pitch = (cur_pitch + vel_pitch * step_dt) % (2.0 * math.pi)
        out_matrix = _matrix3_from_euler_xyz_shared(cur_roll, cur_pitch, float(heading))
        return TankSpringForceAttitudeStep(
            roll=cur_roll,
            pitch=cur_pitch,
            roll_velocity=vel_roll,
            pitch_velocity=vel_pitch,
            local_torque_x=0.0,
            local_torque_y=0.0,
            roll_torque=roll_torque,
            pitch_torque=pitch_torque,
            point_forces=tuple(0.0 for _ in clean_samples),
            total_lift=lift,
            torque_scale=0.0,
            damping=spring_damp,
            dt=step_dt,
            torque_model=torque_model,
            torque_force_scales=tuple(0.0 for _ in clean_samples),
            integration_model=integrate_model,
            angular_velocity_before=velocity_before,
            spring_angular_delta=(0.0, 0.0),
            angular_velocity_after_spring=velocity_before,
            angular_velocity_after_damping=(vel_roll, vel_pitch),
            rotation_matrix=tuple(float(v) for v in out_matrix),
        )

    supplied_point_forces: tuple[float, ...] = ()
    if point_forces is not None:
        try:
            supplied_point_forces = tuple(
                max(0.0, float(v)) for v in tuple(point_forces)[:point_count]
            )
        except (TypeError, ValueError):
            supplied_point_forces = ()
    if len(supplied_point_forces) == point_count and sum(supplied_point_forces) > 1e-9:
        point_force_values = supplied_point_forces
    else:
        clearances = [max(0.5, _sample_float(sample, "clearance", 0.5)) for sample in clean_samples]
        # Lower/compressed points receive a larger share of the existing vertical
        # support. This mirrors the piecewise force curve's height blend without
        # inventing a separate vertical target.
        weights = [1.0 / clearance for clearance in clearances]
        weight_sum = sum(weights)
        if weight_sum <= 1e-9:
            point_force_values = tuple(lift / float(point_count) for _ in clean_samples)
        else:
            point_force_values = tuple(lift * weight / weight_sum for weight in weights)

    blend_values: tuple[float, ...] = tuple(0.0 for _ in clean_samples)
    if point_blend_factors is not None:
        try:
            blend_values = tuple(
                max(0.0, min(1.0, float(v)))
                for v in tuple(point_blend_factors)[:point_count]
            )
        except (TypeError, ValueError):
            blend_values = tuple(0.0 for _ in clean_samples)
    if len(blend_values) != point_count:
        blend_values = tuple(0.0 for _ in clean_samples)

    model = str(torque_model or "decompile_config").strip().lower()
    if model not in {"decompile_config", "legacy_lift_normalized"}:
        model = "decompile_config"
    base_react = max(0.0, float(force_base))
    slope_react = max(0.0, float(force_scale))
    legacy_scale = 1.0 / max(lift, 1.0)
    if model == "legacy_lift_normalized":
        torque_scales = tuple(legacy_scale for _ in clean_samples)
    else:
        # Decompile: torque force is (config+0x20 + config+0x24*blend) times
        # the same per-point force magnitude used for vertical support.
        torque_scales = tuple(base_react + slope_react * blend for blend in blend_values)

    # BEHAVIOR Section 5 currently emits allocator-default local normals
    # `(0, 0, -1)`. The force kernel negates the magnitude, so the effective
    # world force is along the body up column.
    matrix = source_matrix
    force_dir = (matrix[2], matrix[5], matrix[8])

    local_torque_x = 0.0
    local_torque_y = 0.0
    for sample, force_mag, torque_force_scale in zip(
        clean_samples,
        point_force_values,
        torque_scales,
    ):
        world_x, world_y = _sample_pair(sample, "world_offset")
        lever_x = float(world_x)
        lever_y = float(world_y)
        lever_z = _sample_float(sample, "world_offset_z", 0.0)
        weighted_force_mag = force_mag * torque_force_scale
        force_x = force_dir[0] * weighted_force_mag
        force_y = force_dir[1] * weighted_force_mag
        force_z = force_dir[2] * weighted_force_mag
        # Decompile order: force x lever, then inverse-transform to local.
        world_torque_x = force_z * lever_y - force_y * lever_z
        world_torque_y = force_x * lever_z - lever_x * force_z
        world_torque_z = lever_x * force_y - force_x * lever_y
        local_torque_x += (
            matrix[6] * world_torque_z
            + matrix[0] * world_torque_x
            + matrix[3] * world_torque_y
        )
        local_torque_y += (
            matrix[7] * world_torque_z
            + matrix[1] * world_torque_x
            + matrix[4] * world_torque_y
        )

    torque_scale = (
        sum(torque_scales) / float(len(torque_scales))
        if torque_scales
        else 0.0
    )
    if integrate_model == "legacy_accel":
        roll_torque = local_torque_x - spring_damp * vel_roll
        pitch_torque = local_torque_y - spring_damp * vel_pitch
        if step_dt > 0.0:
            vel_roll += roll_torque * step_dt
            vel_pitch += pitch_torque * step_dt
            cur_roll = (cur_roll + vel_roll * step_dt) % (2.0 * math.pi)
            cur_pitch = (cur_pitch + vel_pitch * step_dt) % (2.0 * math.pi)
        out_matrix = _matrix3_from_euler_xyz_shared(cur_roll, cur_pitch, float(heading))
        spring_delta = (local_torque_x * step_dt, local_torque_y * step_dt)
        velocity_after_spring = (
            velocity_before[0] + spring_delta[0],
            velocity_before[1] + spring_delta[1],
        )
        velocity_after_damping = (vel_roll, vel_pitch)
    elif integrate_model == "decompile_impulse":
        # Decompile ordering: Spring_apply_forces_to_entity adds spring torque
        # to the entity angular state before Physics_substep_integrate_angular.
        # Kept as an A/B probe; the default path below uses the recovered
        # acceleration offsets instead.
        roll_torque = local_torque_x
        pitch_torque = local_torque_y
        spring_delta = (local_torque_x, local_torque_y)
        velocity_after_spring = (
            vel_roll + local_torque_x,
            vel_pitch + local_torque_y,
        )
        out_matrix, euler, out_velocity = matrix3_integrate_angular_shared(
            source_matrix,
            (velocity_after_spring[0], velocity_after_spring[1], 0.0),
            step_dt,
            angular_damping=spring_damp,
        )
        cur_roll = euler[0]
        cur_pitch = euler[1]
        vel_roll = out_velocity[0]
        vel_pitch = out_velocity[1]
        velocity_after_damping = (vel_roll, vel_pitch)
    else:
        # Spring_apply_forces_to_entity writes pitch/roll torque into entity
        # angular acceleration (+0x48/+0x4c). Physics_substep_integrate_angular
        # rotates by the current angular velocity, then applies acceleration
        # plus damping to the angular velocity for the next tick.
        roll_torque = local_torque_x
        pitch_torque = local_torque_y
        spring_delta = (local_torque_x * step_dt, local_torque_y * step_dt)
        velocity_after_spring = (
            vel_roll + spring_delta[0],
            vel_pitch + spring_delta[1],
        )
        out_matrix, euler, out_velocity = matrix3_integrate_angular_shared(
            source_matrix,
            (vel_roll, vel_pitch, 0.0),
            step_dt,
            angular_acceleration=(local_torque_x, local_torque_y, 0.0),
            angular_damping=spring_damp,
        )
        cur_roll = euler[0]
        cur_pitch = euler[1]
        vel_roll = out_velocity[0]
        vel_pitch = out_velocity[1]
        velocity_after_damping = (vel_roll, vel_pitch)

    return TankSpringForceAttitudeStep(
        roll=cur_roll,
        pitch=cur_pitch,
        roll_velocity=vel_roll,
        pitch_velocity=vel_pitch,
        local_torque_x=float(local_torque_x),
        local_torque_y=float(local_torque_y),
        roll_torque=float(roll_torque),
        pitch_torque=float(pitch_torque),
        point_forces=tuple(float(v) for v in point_force_values),
        total_lift=lift,
        torque_scale=float(torque_scale),
        damping=spring_damp,
        dt=step_dt,
        torque_model=model,
        torque_force_scales=tuple(float(v) for v in torque_scales),
        integration_model=integrate_model,
        angular_velocity_before=tuple(float(v) for v in velocity_before),
        spring_angular_delta=tuple(float(v) for v in spring_delta),
        angular_velocity_after_spring=tuple(float(v) for v in velocity_after_spring),
        angular_velocity_after_damping=tuple(float(v) for v in velocity_after_damping),
        rotation_matrix=tuple(float(v) for v in out_matrix),
    )


def tank_softbody_suspension_force(
    average_height: float,
    vertical_velocity: float,
    slot5: float,
    *,
    samples: Sequence[Mapping[str, object]] | None = None,
    stretch_ratios: Sequence[float] | None = None,
    use_per_point_lift: bool = False,
    gravity: float = -50.0,
    physics_timestep_factor: float = OG_PHYSICS_TIMESTEP_FACTOR,
    max_altitude: float = 3.25,
    gravity_pct: float = 1.0,
    force_offset: float = 0.0,
    rest_height: float = OG_TANK_SOFTBODY_REST_HEIGHT,
    target_average_height: float = OG_TANK_SOFTBODY_FLAT_AVERAGE_HEIGHT,
    idle_slot5: float = OG_TANK_SOFTBODY_IDLE_SLOT5,
    damping: float = 6.0,
    use_shear_corrections: bool = True,
    shear_stiffness: float = OG_TANK_SPRING_SHEAR_STIFFNESS,
    scalar_stretch_ratio: float = 0.0,
    scalar_stretch_source: str = "none",
    scalar_stretch_speed: float = 0.0,
    scalar_stretch_denominator: float = OG_TANK_SPRING_STRETCH_SPEED_DENOMINATOR,
    use_piecewise_height_factor: bool = False,
    use_decompile_piecewise_force: bool = False,
) -> TankSoftbodyForce:
    """Approximate the OG tank softbody's vertical spring-force path.

    The old compact helper treated `rest_height + max_altitude` as a center
    lift target. Live wulftap shows the OG softbody at rest instead reports a
    four-point Spring_update_world_state average height around 2.48u and keeps
    gravity supported there. This helper mirrors the decompile shape relevant
    to flat terrain:

    - operate on Spring_update_world_state's averaged per-point height;
    - keep slot 5 as the softbody stiffness/vehicle throttle input written
      into the spring state before Spring_compute_suspension_forces;
    - feed that stiffness into the force response path as the decompile does
      (`stiffness * max_altitude + shear + force_offset`), using the BEHAVIOR
      physics timestep factor as the spring's base force term while gravity is
      still applied by the rigid-body tick;
    - produce a spring-force contribution, not a direct Q/Z vertical impulse;
    - leave the legacy compact target path available for blocker probes.
    """
    avg = float(average_height)
    vel = float(vertical_velocity)
    throttle = max(0.0, min(1.2, float(slot5)))
    rest = max(0.001, float(rest_height))
    max_alt = max(0.001, float(max_altitude))
    base_target = max(0.001, float(target_average_height))
    gravity_factor = max(0.0, float(gravity_pct))

    support = max(0.0, float(physics_timestep_factor)) * gravity_factor
    if support <= 0.0:
        support = abs(float(gravity)) * gravity_factor
    idle = max(0.001, abs(float(idle_slot5)))
    # Spring_compute_suspension_forces samples the jet/spring curve with
    # stiffness * max_altitude plus shear and force_offset. A direct additive
    # interpretation only changes Q by about 0.6u/s^2 against 50u/s^2 gravity,
    # which live OG reports as no visible hover-height control. The curve's
    # flat-terrain effect is an equilibrium shift: idle maps to the observed
    # flat average height, Q raises that equilibrium, and Z lowers it. The
    # lower bound stays above the terrain-height clamp so Z is a low hover, not
    # a request to drive the body through the ground.
    force_curve_input = max(0.0, throttle * max_alt + float(force_offset))
    idle_force_curve_input = max(0.001, idle * max_alt + float(force_offset))
    input_ratio = force_curve_input / idle_force_curve_input
    target_floor = max(0.5, base_target * 0.5)
    target_ceiling = base_target + max_alt
    target = base_target * input_ratio
    if target < target_floor:
        target = target_floor
    elif target > target_ceiling:
        target = target_ceiling
    # Slot 5 still affects response gain, but the original piecewise curve has
    # base force terms, so a low Z slot should not make the spring completely
    # unresponsive.
    response_scale = max(0.4, throttle / idle)
    height_error = target - avg
    height_response = height_error * (support / max_alt) * response_scale
    force_bias_accel = (target - base_target) * (support / max_alt) * response_scale
    damping_accel = -vel * max(0.0, float(damping))

    lift = support + height_response + damping_accel
    if lift < 0.0:
        lift = 0.0
    # Keep the stand-in bounded like the original per-frame spring contribution
    # while allowing a firm response from terrain contact.
    lift_cap = max(support * 2.4, support + max_alt * (support / max_alt) * 2.0)
    if lift > lift_cap:
        lift = lift_cap
    model = "softbody_empirical_flat"
    actual_height_response = float(height_response)
    point_force_values: tuple[float, ...] = ()
    point_vertical_forces: tuple[float, ...] = ()
    point_clearances: tuple[float, ...] = ()
    point_clamped_heights: tuple[float, ...] = ()
    point_height_errors: tuple[float, ...] = ()
    point_normal_z: tuple[float, ...] = ()
    point_stretch_values: tuple[float, ...] = ()
    point_force_curve_inputs: tuple[float, ...] = ()
    point_height_curve_factors: tuple[float, ...] = ()
    point_blend_values: tuple[float, ...] = ()
    point_shear_values: tuple[float, ...] = ()
    point_velocity_values: tuple[float, ...] = ()
    point_decompile_force_values: tuple[float, ...] = ()
    point_decompile_react_blends: tuple[float, ...] = ()
    point_decompile_fast_reacts: tuple[float, ...] = ()
    point_decompile_slow_reacts: tuple[float, ...] = ()
    global_stretch_blend = max(0.0, min(1.0, float(scalar_stretch_ratio)))
    stretch_source = str(scalar_stretch_source or "none")
    try:
        stretch_speed = max(0.0, float(scalar_stretch_speed))
    except (TypeError, ValueError):
        stretch_speed = 0.0
    try:
        stretch_denominator = max(0.0, float(scalar_stretch_denominator))
    except (TypeError, ValueError):
        stretch_denominator = OG_TANK_SPRING_STRETCH_SPEED_DENOMINATOR

    clean_samples = list(samples[:OG_TANK_SOFTBODY_POINT_COUNT]) if samples is not None else []
    if clean_samples:
        point_count = len(clean_samples)
        denom = max(1.0, float(point_count - 1))
        support_share = support / float(point_count)
        damping_share = damping_accel / float(point_count)
        response_factor = (support / max_alt) * response_scale / denom
        if use_shear_corrections:
            point_shear_values = tank_spring_shear_corrections(
                clean_samples,
                diagonal_stiffness=shear_stiffness,
                edge_stiffness=shear_stiffness,
            )
        else:
            point_shear_values = tuple(0.0 for _ in clean_samples)
        stretch_inputs: tuple[float, ...] = ()
        if stretch_ratios is not None:
            try:
                stretch_inputs = tuple(float(v) for v in tuple(stretch_ratios)[:point_count])
            except (TypeError, ValueError):
                stretch_inputs = ()

        forces: list[float] = []
        vertical_forces: list[float] = []
        clearances: list[float] = []
        clamped_heights: list[float] = []
        height_errors: list[float] = []
        normal_z_values: list[float] = []
        stretch_values: list[float] = []
        curve_inputs: list[float] = []
        height_curve_factors: list[float] = []
        blend_values: list[float] = []
        velocity_values: list[float] = []
        decompile_forces: list[float] = []
        decompile_react_blends: list[float] = []
        decompile_fast_reacts: list[float] = []
        decompile_slow_reacts: list[float] = []
        for idx, sample in enumerate(clean_samples):
            clearance = _sample_float(sample, "clearance", avg * denom / float(point_count))
            terrain_height = max(0.5, clearance)
            try:
                sample_stretch = float(sample.get("stretch_ratio", 1.0))
            except (TypeError, ValueError):
                sample_stretch = 1.0
            if idx < len(stretch_inputs):
                sample_stretch = stretch_inputs[idx]
            if sample_stretch <= 0.0:
                sample_stretch = 1.0
            # The exact piecewise samples are still data-backed by OG traces, but
            # the force path shape is decompiled: each point gets its own
            # terrain-height input, force-curve input, optional stretch, and
            # loaded spring-point normal. The terrain surface normal is only
            # accumulated by Spring_update_world_state; the force kernel uses
            # the Section-5 point normal, whose allocator/default value is
            # (0, 0, -1), then negates force magnitude.
            shear_correction = (
                point_shear_values[idx]
                if idx < len(point_shear_values)
                else 0.0
            )
            point_force_curve_input = max(0.0, force_curve_input + shear_correction)
            point_velocity_z = _sample_float(sample, "point_velocity_z", vel)
            piecewise_sample = tank_spring_piecewise_force_sample(
                point_force_curve_input,
                terrain_height,
                point_velocity_z,
                global_stretch_blend,
                point_count=point_count,
                rest_height=rest,
                gravity_pct=gravity_factor,
                physics_timestep_factor=support,
            )
            height_curve_factor = piecewise_sample.height_curve_factor
            point_input_ratio = point_force_curve_input / idle_force_curve_input
            point_target_average = base_target * point_input_ratio
            if point_target_average < target_floor:
                point_target_average = target_floor
            elif point_target_average > target_ceiling:
                point_target_average = target_ceiling
            point_target = point_target_average * denom / float(point_count)
            point_error = point_target - terrain_height
            if use_decompile_piecewise_force:
                point_force = piecewise_sample.force_magnitude * sample_stretch
            else:
                point_force = (support_share + point_error * response_factor + damping_share) * sample_stretch
            if use_piecewise_height_factor:
                point_force *= height_curve_factor
            if point_force < 0.0:
                point_force = 0.0
            normal = _sample_vec3(sample, "spring_normal", OG_TANK_SPRING_POINT_NORMAL)
            # Decompile: linear_force_z = (-force_magnitude) * normal_z. The
            # useful upward projection is therefore -normal_z, not terrain
            # surface normal Z.
            normal_z = max(0.0, min(1.0, -float(normal[2])))
            vertical_force = point_force * normal_z
            scalar_stretch = _sample_float(sample, "stretch_blend", global_stretch_blend)
            blend_factor = tank_spring_piecewise_blend_factor(
                terrain_height,
                scalar_stretch,
                rest_height=rest,
            )

            clearances.append(float(clearance))
            clamped_heights.append(float(terrain_height))
            height_errors.append(float(point_error))
            forces.append(float(point_force))
            vertical_forces.append(float(vertical_force))
            normal_z_values.append(float(normal_z))
            stretch_values.append(float(sample_stretch))
            curve_inputs.append(float(point_force_curve_input))
            height_curve_factors.append(float(height_curve_factor))
            blend_values.append(float(blend_factor))
            velocity_values.append(float(point_velocity_z))
            decompile_forces.append(float(piecewise_sample.force_magnitude))
            decompile_react_blends.append(float(piecewise_sample.react_blend))
            decompile_fast_reacts.append(float(piecewise_sample.fast_react))
            decompile_slow_reacts.append(float(piecewise_sample.slow_react))

        point_lift = sum(vertical_forces)
        if point_lift > lift_cap and point_lift > 1e-9:
            scale = lift_cap / point_lift
            forces = [v * scale for v in forces]
            vertical_forces = [v * scale for v in vertical_forces]
            point_lift = lift_cap
        point_force_values = tuple(forces)
        point_vertical_forces = tuple(vertical_forces)
        point_clearances = tuple(clearances)
        point_clamped_heights = tuple(clamped_heights)
        point_height_errors = tuple(height_errors)
        point_normal_z = tuple(normal_z_values)
        point_stretch_values = tuple(stretch_values)
        point_force_curve_inputs = tuple(curve_inputs)
        point_height_curve_factors = tuple(height_curve_factors)
        point_blend_values = tuple(blend_values)
        point_velocity_values = tuple(velocity_values)
        point_decompile_force_values = tuple(decompile_forces)
        point_decompile_react_blends = tuple(decompile_react_blends)
        point_decompile_fast_reacts = tuple(decompile_fast_reacts)
        point_decompile_slow_reacts = tuple(decompile_slow_reacts)
        model = "softbody_per_point_piecewise_probe"
        if use_per_point_lift or use_decompile_piecewise_force:
            lift = max(0.0, float(point_lift))
            actual_height_response = float(lift - support - damping_accel)
            model = (
                "softbody_per_point_decompile_piecewise"
                if use_decompile_piecewise_force
                else "softbody_per_point_piecewise_proxy"
            )

    return TankSoftbodyForce(
        model=model,
        lift_accel=float(lift),
        support_accel=float(support),
        height_response_accel=float(actual_height_response),
        damping_accel=float(damping_accel),
        average_height=avg,
        target_average_height=target,
        height_error=float(height_error),
        height_ratio=avg / rest,
        slot5=float(throttle),
        force_curve_input=float(force_curve_input),
        force_bias_accel=float(force_bias_accel),
        vehicle_throttle=float(throttle),
        softbody_stiffness=float(throttle),
        response_scale=float(response_scale),
        gravity_pct=float(gravity_factor),
        rest_height=float(rest),
        max_altitude=float(max_alt),
        force_offset=float(force_offset),
        point_count=len(point_force_values),
        point_forces=point_force_values,
        point_vertical_forces=point_vertical_forces,
        point_clearances=point_clearances,
        point_clamped_heights=point_clamped_heights,
        point_height_errors=point_height_errors,
        point_normal_z=point_normal_z,
        point_stretch_ratios=point_stretch_values,
        point_force_curve_inputs=point_force_curve_inputs,
        point_height_curve_factors=point_height_curve_factors,
        point_blend_factors=point_blend_values,
        point_shear_corrections=point_shear_values,
        point_velocity_z=point_velocity_values,
        point_decompile_force_magnitudes=point_decompile_force_values,
        point_decompile_react_blends=point_decompile_react_blends,
        point_decompile_fast_reacts=point_decompile_fast_reacts,
        point_decompile_slow_reacts=point_decompile_slow_reacts,
        scalar_stretch_ratio=float(global_stretch_blend),
        scalar_stretch_source=stretch_source,
        scalar_stretch_speed=float(stretch_speed),
        scalar_stretch_denominator=float(stretch_denominator),
    )


def tank_softbody_horizontal_damping(
    linear_damp: float,
    contact_damp: float,
    slot5: float,
    *,
    idle_slot5: float = OG_TANK_SOFTBODY_IDLE_SLOT5,
) -> tuple[float, float]:
    """Return planar damping for the tank softbody's current hover setting.

    Live OG Q+W telemetry shows high hover uses the normal PhysicsConfig
    linear damping (`1.5`), reaching roughly 29u/s with the recovered W impulse.
    The heavier contact damping is only appropriate for the low Z/ground-hugging
    hover state.
    """
    base = max(0.0, float(linear_damp))
    contact = max(0.0, float(contact_damp))
    if contact <= base:
        return base, 0.0
    try:
        control = float(slot5)
    except (TypeError, ValueError):
        control = idle_slot5
    if control < max(0.001, float(idle_slot5)) * 0.5:
        return contact, contact
    return base, 0.0


def vehicle_runtime_speed(vel_x: float, vel_y: float, vel_z: float, *, up_axis: str = "z") -> float:
    """Approximate the runtime entity speed scalar used by vehicle controllers.

    `azurefishy-src` reads tank/scout mobility speed from `entity+0xD4`, which is
    a scalar speed state rather than a direct raw Vec3 magnitude. The public
    runtime still lacks that exact field, but a persistent planar speed state is
    a closer stand-in than feeding controller mobility from full 3D velocity,
    especially on uneven terrain where vertical hover response should not fully
    count as forward ground speed.
    """
    if up_axis == "y":
        return math.sqrt(vel_x * vel_x + vel_z * vel_z)
    return math.sqrt(vel_x * vel_x + vel_y * vel_y)


def tank_spring_local_offsets(
    spring_states: object,
    *,
    state_index: int = 0,
) -> tuple[tuple[float, float], ...] | None:
    """Extract the first four local XY spring points from BEHAVIOR Section 5.

    `Spring_update_world_state` transforms local SpringState positions through
    the entity rotation matrix, and then `Spring_compute_suspension_forces`
    indexes points 0-3 as a quad. This helper intentionally accepts generic
    objects so the shared protocol layer does not depend on the client parser
    dataclasses.
    """
    if spring_states is None:
        return None

    states = spring_states
    if hasattr(states, "points"):
        state = states
    else:
        try:
            if len(states) <= state_index:  # type: ignore[arg-type]
                return None
            state = states[state_index]  # type: ignore[index]
        except (TypeError, IndexError):
            return None

    points = getattr(state, "points", state)
    try:
        if len(points) < 4:  # type: ignore[arg-type]
            return None
    except TypeError:
        return None

    offsets = []
    for point in points[:4]:  # type: ignore[index]
        pos = getattr(point, "pos", point)
        try:
            offsets.append((float(pos[0]), float(pos[1])))
        except (TypeError, IndexError, ValueError):
            return None
    return tuple(offsets)


def tank_spring_local_points(
    spring_states: object,
    *,
    state_index: int = 0,
) -> tuple[tuple[float, float, float], ...] | None:
    """Extract the first four local XYZ spring points from BEHAVIOR Section 5."""
    if spring_states is None:
        return None

    states = spring_states
    if hasattr(states, "points"):
        state = states
    else:
        try:
            if len(states) <= state_index:  # type: ignore[arg-type]
                return None
            state = states[state_index]  # type: ignore[index]
        except (TypeError, IndexError):
            return None

    points = getattr(state, "points", state)
    try:
        if len(points) < 4:  # type: ignore[arg-type]
            return None
    except TypeError:
        return None

    offsets = []
    for point in points[:4]:  # type: ignore[index]
        pos = getattr(point, "pos", point)
        try:
            offsets.append((float(pos[0]), float(pos[1]), float(pos[2])))
        except (TypeError, IndexError, ValueError):
            return None
    return tuple(offsets)


def tank_suspension_local_sample_offsets(
    *,
    longitudinal: float,
    lateral: float,
    local_offsets: Sequence[tuple[float, float]] | None = None,
) -> tuple[tuple[float, float], ...]:
    """Return the four tank-local spring sample points used for terrain queries."""
    if local_offsets is not None and len(local_offsets) >= 4:
        return tuple((float(x), float(y)) for x, y in local_offsets[:4])
    return (
        (float(longitudinal), float(lateral)),
        (float(longitudinal), -float(lateral)),
        (-float(longitudinal), float(lateral)),
        (-float(longitudinal), -float(lateral)),
    )


def tank_suspension_local_sample_points(
    *,
    longitudinal: float,
    lateral: float,
    local_points: Sequence[tuple[float, float, float]] | None = None,
    local_offsets: Sequence[tuple[float, float]] | None = None,
) -> tuple[tuple[float, float, float], ...]:
    """Return the four tank-local spring sample points used by OG spring state."""
    if local_points is not None and len(local_points) >= 4:
        return tuple((float(x), float(y), float(z)) for x, y, z in local_points[:4])
    offsets = tank_suspension_local_sample_offsets(
        longitudinal=longitudinal,
        lateral=lateral,
        local_offsets=local_offsets,
    )
    return tuple((x, y, 0.0) for x, y in offsets)


def tank_suspension_sample_offsets(
    heading: float,
    *,
    longitudinal: float,
    lateral: float,
    local_offsets: Sequence[tuple[float, float]] | None = None,
) -> tuple[tuple[float, float], ...]:
    """Return four heading-aligned terrain sample offsets for the tank footprint.

    The original tank controller gets altitude deviation and terrain contact
    direction from the active softbody/spring state loaded from BEHAVIOR
    Section 5. If parsed local offsets are available, use the same first-four
    spring points that the decompile indexes as a quad; otherwise fall back to
    the older radius-derived approximation.
    """
    cos_h = math.cos(heading)
    sin_h = math.sin(heading)
    forward = (cos_h, sin_h)
    right = (-sin_h, cos_h)
    samples = tank_suspension_local_sample_offsets(
        longitudinal=longitudinal,
        lateral=lateral,
        local_offsets=local_offsets,
    )
    return tuple(
        (
            forward_dist * forward[0] + lateral_dist * right[0],
            forward_dist * forward[1] + lateral_dist * right[1],
        )
        for forward_dist, lateral_dist in samples
    )


def tank_suspension_world_sample_offsets(
    heading: float,
    *,
    longitudinal: float,
    lateral: float,
    local_points: Sequence[tuple[float, float, float]] | None = None,
    local_offsets: Sequence[tuple[float, float]] | None = None,
    rotation_matrix: Sequence[float] | None = None,
) -> tuple[tuple[float, float, float], ...]:
    """Return decompile-shaped rotated spring sample offsets.

    `Spring_update_world_state` multiplies each local SpringState point by the
    entity rotation matrix before querying terrain constraints. The older clone
    sampler used only heading-aligned XY offsets, which loses the per-point Z
    offset created by body pitch/roll.
    """
    samples = tank_suspension_local_sample_points(
        longitudinal=longitudinal,
        lateral=lateral,
        local_points=local_points,
        local_offsets=local_offsets,
    )
    if rotation_matrix is None:
        cos_h = math.cos(heading)
        sin_h = math.sin(heading)
        rotation_matrix = (
            cos_h, -sin_h, 0.0,
            sin_h, cos_h, 0.0,
            0.0, 0.0, 1.0,
        )
    else:
        rotation_matrix = tank_body_matrix_with_heading(rotation_matrix, heading)
    return tuple(
        (
            local_z * float(rotation_matrix[2])
            + local_x * float(rotation_matrix[0])
            + local_y * float(rotation_matrix[1]),
            local_z * float(rotation_matrix[5])
            + local_x * float(rotation_matrix[3])
            + local_y * float(rotation_matrix[4]),
            local_z * float(rotation_matrix[8])
            + local_x * float(rotation_matrix[6])
            + local_y * float(rotation_matrix[7]),
        )
        for local_x, local_y, local_z in samples
    )


def terrain_aligned_basis(
    dh_dx: float,
    dh_dy: float,
    heading: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
    """Build a terrain-aligned local basis that preserves the given heading.

    This mirrors the decompile shape more closely than a heading-plus-pitch
    shortcut: movement is rotated by the tank's full terrain-aligned body
    basis, not just by heading with a separately sampled pitch angle.
    """
    def _normalize3(v: tuple[float, float, float], fallback: tuple[float, float, float]) -> tuple[float, float, float]:
        mag_sq = v[0] * v[0] + v[1] * v[1] + v[2] * v[2]
        if mag_sq <= 1e-10:
            return fallback
        inv_mag = 1.0 / math.sqrt(mag_sq)
        return (v[0] * inv_mag, v[1] * inv_mag, v[2] * inv_mag)

    def _dot3(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    def _cross3(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    up = _normalize3((-dh_dx, -dh_dy, 1.0), (0.0, 0.0, 1.0))
    planar_forward = (math.cos(heading), math.sin(heading), 0.0)
    forward_dot = _dot3(planar_forward, up)
    forward_tangent = (
        planar_forward[0] - up[0] * forward_dot,
        planar_forward[1] - up[1] * forward_dot,
        planar_forward[2] - up[2] * forward_dot,
    )
    forward = _normalize3(forward_tangent, planar_forward)
    right = _normalize3(
        _cross3(up, forward),
        (-math.sin(heading), math.cos(heading), 0.0),
    )
    forward = _normalize3(_cross3(right, up), forward)
    return forward, right, up


TANK_TERRAIN_CONTACT_NORMALIZER = math.sin(math.radians(49.5))


def tank_terrain_contact_coupling(
    move_x: float,
    move_y: float,
    contact_x: float,
    contact_y: float,
    max_ground_speed: float = TANK_TERRAIN_CONTACT_NORMALIZER,
) -> tuple[float, float, float]:
    """Apply the decompile-shaped tank terrain-contact coupling in XY.

    The original reads `contact_x/contact_y` directly from the active
    spring/softbody state and normalizes their magnitude by the tank global
    `_DAT_005d5ea8 = sin(49.5deg)`.

    Returns `(new_move_x, new_move_y, normalized_contact_speed)`.
    """
    ground_contact_mag = math.sqrt(contact_x * contact_x + contact_y * contact_y)
    if ground_contact_mag <= 0.1 or max_ground_speed <= 0.0:
        return move_x, move_y, 0.0

    normalized_speed = ground_contact_mag / max_ground_speed
    if normalized_speed > 1.0:
        normalized_speed = 1.0

    scale = normalized_speed / ground_contact_mag
    contact_x *= scale
    contact_y *= scale
    coupling_strength = abs((move_x * contact_x + move_y * contact_y) * normalized_speed)
    return (
        move_x + contact_x * coupling_strength,
        move_y + contact_y * coupling_strength,
        normalized_speed,
    )


# Per-vehicle-type configs used by the shared runtime
VEHICLE_PHYSICS_CONFIGS = {
    EntityType.TANK: VehiclePhysicsConfig(
        turn_adjust=4.5,
        move_adjust=85.0,
        strafe_adjust=69.7,
        max_velocity=80.0,
        low_fuel_level=2000.0,
        max_altitude=3.25,
        gravity_pct=1.0,
    ),
    EntityType.SCOUT: VehiclePhysicsConfig(
        turn_adjust=4.5,
        move_adjust=85.0,
        strafe_adjust=38.0,
        max_velocity=72.0,
        low_fuel_level=2000.0,
        max_altitude=4.9,
        gravity_pct=1.0,
    ),
}


class EntityPhysicsMode(IntEnum):
    """Physics config modes used by the shared runtime.

    The mode determines integration behavior, damping flags, and collision
    response for broad entity categories.
    """
    DEFAULT = 0       # standard entities
    PROJECTILE = 1    # projectile-style entities
    TORPEDO = 2       # torpedo-style entities


# Map entity types to their physics mode
ENTITY_PHYSICS_MODES = {
    EntityType.FLAK_SHELL: EntityPhysicsMode.PROJECTILE,
    EntityType.HUNTER: EntityPhysicsMode.PROJECTILE,
    EntityType.TORPEDO: EntityPhysicsMode.TORPEDO,
    # All other entity types use DEFAULT
}


def get_entity_physics_mode(entity_type: int) -> EntityPhysicsMode:
    """Get the physics mode for an entity type."""
    return ENTITY_PHYSICS_MODES.get(entity_type, EntityPhysicsMode.DEFAULT)


@dataclass
class Projectile:
    """Represents an in-flight projectile."""
    entity_id: int
    entity_type: EntityType
    owner_id: int
    team: int
    pos: Tuple[float, float, float]
    vel: Tuple[float, float, float]
    spawn_time: float
    lifetime: float = 5.0  # seconds before despawn
    debug_context: Optional[dict] = None
