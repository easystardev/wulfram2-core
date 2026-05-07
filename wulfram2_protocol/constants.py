"""
Physics and protocol constants shared between server and client.

Values here are kept aligned with the shared runtime used by the public
Python client/server work and adjusted when empirical behavior requires it.
"""

from .entities import EntityType, VEHICLE_PHYSICS_CONFIGS

# ============ Tick / Timing ============

TICK_RATE_HZ = 30
TICK_DT = 1.0 / TICK_RATE_HZ  # ~0.0333s

# Physics substep limits
SUBSTEP_DT_MAX = 0.04          # Physics substep ceiling
SUBSTEP_SPLIT_THRESHOLD = 0.08  # Split to half-step above this


# ============ Damping / Friction ============

# Angular velocity damping
ANGULAR_DAMP_COEFF = 2.0

# Linear velocity damping
COASTING_DAMP = 1.5            # active PhysicsConfig linear damping
DRIVING_DAMP = 1.5             # same coefficient while driving
# Live OG memory shows the tank's active PhysicsConfig linear damping at 1.5
# with the linear-damping flag enabled.

# Softbody damping multiplier
DAMPING_MULTIPLIER = 1.4137167


# ============ Position / Velocity Limits ============

VEC_POS_MAX = 8192.0           # Position quantizer max (+/-8192 world units)
STEADY_STATE_SPEED = 56.7      # u/s at full throttle with driving_damp=1.5


# ============ Gravity ============

GRAVITY_ACCEL = -50.0          # units/s^2 (server default)
GROUND_LEVEL = 5.0             # Default ground Z (before terrain heightmap)
TERRAIN_HEIGHT_OFFSET = 5.0    # Added to heightmap Z for entity position


# ============ Behavior Defaults ============
# From BEHAVIOR packet Section 6 (Active Vehicle Physics)

_TANK_CONFIG = VEHICLE_PHYSICS_CONFIGS[EntityType.TANK]

# Compatibility shim: canonical values live in entities.VEHICLE_PHYSICS_CONFIGS.
TANK_TURN_ADJUST = _TANK_CONFIG.turn_adjust
TANK_MOVE_ADJUST = _TANK_CONFIG.move_adjust
TANK_STRAFE_ADJUST = _TANK_CONFIG.strafe_adjust
TANK_MAX_VELOCITY = _TANK_CONFIG.max_velocity
TANK_LOW_FUEL_LEVEL = _TANK_CONFIG.low_fuel_level
TANK_MAX_ALTITUDE = _TANK_CONFIG.max_altitude
TANK_GRAVITY_PCT = _TANK_CONFIG.gravity_pct
