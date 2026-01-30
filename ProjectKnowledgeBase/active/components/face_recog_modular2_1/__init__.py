# root/__init__.py
"""
Face Recognition System
A comprehensive, modular face recognition system with mask detection and real-time processing.
"""

__version__ = "1.0.0"
__author__ = "Face Recognition System"

# Main classes and functions for easy access
from .config import ConfigManager, ValidationRules
from .recognition import FaceRecognitionSystem, RobustFaceRecognitionSystem, VoyagerFaceRecognitionSystem
from .streaming import RealTimeProcessor, StreamManager, RealTimeProcessorHeadless, MultiSourceRealTimeProcessor
from .alerting import  DurationAwareAlertManager, VoiceInterface
from .logging import DataLogger, ImageLogger




# Main entry point
def create_system(config: dict, system_type: str = "robust"):
    """Factory function to create a face recognition system."""
    config_manager = ConfigManager(config)
    system_config = config_manager.get_component_config(system_type)
    
    if system_type == "Robust":
        return RobustFaceRecognitionSystem(system_config)
    elif system_type == "Voyager":
        return VoyagerFaceRecognitionSystem(system_config)
    else:
        return VoyagerFaceRecognitionSystem(system_config)

__all__ = [
    "ConfigManager",
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