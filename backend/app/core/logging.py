import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
