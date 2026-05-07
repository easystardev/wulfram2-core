"""
Entity type definitions, shared vehicle helpers, and behavior slot indices.
"""

from enum import IntEnum
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple
import math


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


def tank_softbody_suspension_force(
    average_height: float,
    vertical_velocity: float,
    slot5: float,
    *,
    gravity: float = -50.0,
    max_altitude: float = 3.25,
    gravity_pct: float = 1.0,
    force_offset: float = 0.0,
    rest_height: float = OG_TANK_SOFTBODY_REST_HEIGHT,
    target_average_height: float = OG_TANK_SOFTBODY_FLAT_AVERAGE_HEIGHT,
    idle_slot5: float = OG_TANK_SOFTBODY_IDLE_SLOT5,
    damping: float = 6.0,
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
      (`stiffness * max_altitude + shear + force_offset`), compressing the
      missing piecewise curve into a bounded effective flat-height equilibrium;
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

    return TankSoftbodyForce(
        model="softbody_empirical_flat",
        lift_accel=float(lift),
        support_accel=float(support),
        height_response_accel=float(height_response),
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


def tank_terrain_contact_coupling(
    move_x: float,
    move_y: float,
    contact_x: float,
    contact_y: float,
    max_ground_speed: float = 64.8,
) -> tuple[float, float, float]:
    """Apply the decompile-shaped tank terrain-contact coupling in XY.

    The original reads `contact_x/contact_y` from the active spring/softbody
    state. The public runtime can reuse the exact coupling math even when the
    contact vector is only an approximation.

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
