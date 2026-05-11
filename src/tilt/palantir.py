"""Palantir-style colour palette (matching the parent SecondBrain wiki spec)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    ink: str = "#0E0E0C"          # deep dark anchor
    stage: str = "#E9E6DE"        # light bone / background
    bone: str = "#F5F3EE"         # off-white card surface
    mute: str = "#8C8A82"         # muted grey for labels
    graphite: str = "#3D3D38"     # body text
    hairline_dk: str = "#1B1B17"  # hairlines on dark bg
    hairline_lt: str = "#D6D2C8"  # hairlines on light bg
    accent_green: str = "#1E6E40" # editorial emerald accent


PL = Palette()
