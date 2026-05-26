"""External integrations — image gen, video gen, simulation, ad APIs.

Each adapter exposes a tiny domain interface and hides provider-specific
details. Swap providers by changing the import in `default()`.
"""

from drip.adapters.ads import AdsAdapter
from drip.adapters.image import ImageAdapter
from drip.adapters.simulation import SimulationAdapter
from drip.adapters.video import VideoAdapter

__all__ = ["ImageAdapter", "VideoAdapter", "SimulationAdapter", "AdsAdapter"]
