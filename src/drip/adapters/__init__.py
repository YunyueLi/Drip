"""External integrations — creative generation, value/LTV, and the ad write path.

Each adapter exposes a tiny domain interface and hides provider-specific
details. Swap providers by changing the import in `default()`.
"""

from drip.adapters.image import ImageAdapter
from drip.adapters.prediction import ValueEstimate, ValueModel, build_value_model
from drip.adapters.video import VideoAdapter

__all__ = [
    # creative-generation slots
    "ImageAdapter",
    "VideoAdapter",
    # prediction slot — "is this worth it" (LTV / value)
    "ValueModel",
    "ValueEstimate",
    "build_value_model",
]
