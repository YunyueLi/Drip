"""Centralised logging for Drip.

Every module that needs operational logging imports from here::

    from drip.log import logger

    logger.info("collector fetched %d campaigns", len(metrics))
    logger.warning("LLM narration failed, falling back to template", exc_info=True)
    logger.error("write to Meta API failed", exc_info=True)

This keeps all logging config in one place and avoids ``print()`` calls that
can't be redirected to a file or filtered by severity.

By default the logger writes to stderr at INFO level. Set ``DRIP_LOG_LEVEL``
to ``DEBUG``, ``WARNING``, or ``ERROR`` to adjust.
"""

from __future__ import annotations

import logging
import os
import sys

_log_level = os.getenv("DRIP_LOG_LEVEL", "INFO").upper()
if _log_level not in logging._nameToLevel:
    _log_level = "INFO"

_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)-7s] %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
))

logger = logging.getLogger("drip")
logger.setLevel(getattr(logging, _log_level))
logger.addHandler(_handler)
logger.propagate = False  # don't spam the root logger
