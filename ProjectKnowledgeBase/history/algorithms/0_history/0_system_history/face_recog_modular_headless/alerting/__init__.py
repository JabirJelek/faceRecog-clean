# alerting/__init__.py
"""
Alert management and notification systems.
"""

from .alert_manager import AlertManager, DurationAwareAlertManager
from .voice_interface import VoiceInterface


__all__ = ["AlertManager", "DurationAwareAlertManager", "VoiceInterface"]