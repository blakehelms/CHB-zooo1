"""Decoded acquisition sample contract. No simulated source exists in the app."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Sample:
    source_time: float
    values: tuple
    received_mono: float


AUXILIARY_STREAMS = {
    "accgyro": ("ACCGYRO", 52.0, (6,)),
    "optics": ("PPG", 64.0, (4, 8, 16)),
    "battery": ("Battery", 0.2, (1,)),
}


@dataclass(frozen=True)
class SensorBatch:
    channels: tuple
    rate_hz: float
    samples: list[Sample]
