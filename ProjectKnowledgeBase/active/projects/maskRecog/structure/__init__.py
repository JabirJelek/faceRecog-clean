# root/__init__.py
"""
Face Recognition System
A comprehensive, modular face recognition system with mask detection and real-time processing.
"""

__version__ = "1.0.0"
__author__ = "Face Recognition System"

# Main classes and functions for easy access
from .config import ConfigManager, ValidationRules
from .recognition import FaceRecognitionSystem, RobustFaceRecognitionSystem, VoyagerFaceRecognitionSystem #, ChromaFaceRecognitionSystem FaissFaceRecognitionSystem
from .streaming import RealTimeProcessor, StreamManager, RealTimeProcessorHeadless, MultiSourceRealTimeProcessor
from .alerting import  DurationAwareAlertManager, VoiceInterface
from .logging import DataLogger, ImageLogger




# Main entry point
 

# Explicit mapping: system type -> class
_SYSTEM_CLASSES = {
    "robust": RobustFaceRecognitionSystem,
    "voyager": VoyagerFaceRecognitionSystem,
    # Add others as they become available
}

def create_system(config: dict, system_type: str = "robust", config_profile: str = None):
    """
    Factory function to create a face recognition system.

    Args:
        config: Base configuration dictionary.
        system_type: Type of system to create (e.g., "robust", "voyager").
        config_profile: Name of the configuration profile to use.
                        If None, defaults to system_type.

    Returns:
        An instance of the requested face recognition system.

    Raises:
        ValueError: If system_type is unknown.
    """
    # Determine which config profile to load
    if config_profile is None:
        config_profile = system_type

    # Get the configuration for the selected profile
    config_manager = ConfigManager(config)
    system_config = config_manager.get_component_config(config_profile)

    # Look up the class for the requested system type
    if system_type not in _SYSTEM_CLASSES:
        raise ValueError(
            f"Unknown system_type '{system_type}'. "
            f"Available: {list(_SYSTEM_CLASSES.keys())}"
        )

    system_class = _SYSTEM_CLASSES[system_type]
    return system_class(system_config)

__all__ = [
    "ConfigManager", #"ChromaFaceRecognitionSystem", 'FaissFaceRecognitionSystem',
    "FaceRecognitionSystem",
    "RobustFaceRecognitionSystem",
    "RealTimeProcessor",
    "StreamManager",
    "DurationAwareAlertManager",
    "create_system",
    "DataLogger",
    "ImageLogger",
    "VoiceInterface",
    "ValidationRules",
    "RealTimeProcessor1",
    "RealTimeProcessorHeadless",
    "MultiSourceRealTimeProcessor",
]