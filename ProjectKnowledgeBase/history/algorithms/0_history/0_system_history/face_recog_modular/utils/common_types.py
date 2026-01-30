# utils/common_types.py
"""
Common type definitions for the face recognition system.
"""

from typing import List, Tuple, Dict, Any, Optional
import numpy as np
from dataclasses import dataclass

# Type aliases
BoundingBox = List[int]  # [x1, y1, x2, y2]
Embedding = np.ndarray

@dataclass
class DetectionResult:
    """Result from face detection."""
    bbox: BoundingBox
    confidence: float
    embedding: Optional[Embedding] = None

@dataclass
class RecognitionResult:
    """Result from face recognition."""
    bbox: BoundingBox
    identity: Optional[str]
    recognition_confidence: float
    detection_confidence: float
    mask_status: str = "unknown"
    mask_confidence: float = 0.0
    quality_scores: Optional[Dict[str, float]] = None

@dataclass
class ProcessingMetrics:
    """Performance metrics for processing."""
    detection_time: float
    embedding_time: float
    recognition_time: float
    total_faces: int
    recognized_faces: int
    frame_processing_time: float