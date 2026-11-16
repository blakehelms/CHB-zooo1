"""Decoded acquisition sample contract. No simulated source exists in the app."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Sample:
    source_time: float
    values: tuple
    received_mono: float
