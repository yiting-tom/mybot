"""Configuration module for mybot."""

from mybot.config.loader import get_config_path, load_config
from mybot.config.schema import Config

__all__ = ["Config", "load_config", "get_config_path"]
