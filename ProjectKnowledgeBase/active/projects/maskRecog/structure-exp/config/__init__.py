# config/__init__.py
"""
Configuration management for the face recognition system.
"""

from .config_manager import ConfigManager
from .validation_rules import ValidationRules

__all__ = ["ConfigManager", "ValidationRules"]