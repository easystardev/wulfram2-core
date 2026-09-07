"""Wire schema for optional local HUD state fractions.

Legacy packet APIs call these fields primary/secondary turret angles. Original
HUD consumers establish them as slot-4 pulse charge and slot-1 repair fraction.
"""

HUD_FRACTION_BITS = 8
HUD_FRACTION_MAX = 1.0
HUD_FRACTION_RANGE = 1.0


def validate_hud_fraction_schema(bits: int, maximum: float, range_value: float) -> None:
    if int(bits) != HUD_FRACTION_BITS:
        raise ValueError("HUD fraction width must match TRANSLATION width 8")
    if float(maximum) != HUD_FRACTION_MAX or float(range_value) != HUD_FRACTION_RANGE:
        raise ValueError("HUD fraction max/range must match TRANSLATION 1/1")
