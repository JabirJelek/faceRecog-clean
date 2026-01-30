# tracking/__init__.py
"""
Face tracking and fairness control systems.
"""

from .face_tracker import SimpleFaceTracker
from .fairness_controller import FairnessController
from .tracking_manager import TrackingManager

__all__ = ["SimpleFaceTracker", "FairnessController", "TrackingManager"]