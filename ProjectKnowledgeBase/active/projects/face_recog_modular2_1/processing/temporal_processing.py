# processing/temporal_processing.py
import cv2
from deepface import DeepFace
import numpy as np
from collections import deque
from typing import Dict, List, Tuple, Optional
import time
import torch
import math


class TemporalFusion:
    def __init__(self, config: Dict):
        self.config = config
        self.temporal_buffer = {}  # track_id -> deque of recent recognitions
        self.buffer_size = config.get('temporal_buffer_size', 40)
        self.confidence_threshold = config.get('temporal_confidence_threshold', 0.6)
        
    def update_temporal_buffer(self, track_id: int, identity: str, confidence: float):
        """Update temporal buffer with recent recognition results"""
        if track_id not in self.temporal_buffer:
            self.temporal_buffer[track_id] = deque(maxlen=self.buffer_size)
        
        self.temporal_buffer[track_id].append({
            'identity': identity,
            'confidence': confidence,
            'timestamp': time.time()
        })
    
    def get_temporal_consensus(self, track_id: int) -> Tuple[Optional[str], float]:
        """Get consensus identity from temporal buffer"""
        if track_id not in self.temporal_buffer or not self.temporal_buffer[track_id]:
            return None, 0.0
        
        buffer = self.temporal_buffer[track_id]
        
        # Count occurrences of each identity
        identity_counts = {}
        identity_confidences = {}
        
        for recognition in buffer:
            identity = recognition['identity']
            confidence = recognition['confidence']
            
            if identity not in identity_counts:
                identity_counts[identity] = 0
                identity_confidences[identity] = []
            
            identity_counts[identity] += 1
            identity_confidences[identity].append(confidence)
        
        # Find identity with highest frequency and confidence
        best_identity = None
        best_score = 0.0
        
        for identity, count in identity_counts.items():
            avg_confidence = np.mean(identity_confidences[identity])
            frequency = count / len(buffer)
            
            # Combined score: frequency * confidence
            combined_score = frequency * avg_confidence
            
            if combined_score > best_score and combined_score > self.confidence_threshold:
                best_score = combined_score
                best_identity = identity
        
        return best_identity, best_score
  
class MultiScaleFaceProcessor:
    def __init__(self, config: Dict):
        self.config = config
        self.scale_factors = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75]  # Added more scales
        self.rotation_angles = [-15, -10, -5, 0, 5, 10, 15]  # Increased rotation range
        
        # CUDA device setup
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        if self.device.type == 'cuda':
            print(f"Using GPU: {torch.cuda.get_device_name()}")
        else:
            print("Using CPU - CUDA not available")
        
    def _extract_single_embedding(self, face_roi: np.ndarray) -> Optional[np.ndarray]:
        """Extract embedding from a single face ROI"""
        # This would typically call the main system's embedding extraction
        # For now, return a dummy embedding or implement actual extraction
        try:
            # Convert to RGB and normalize
            if len(face_roi.shape) == 3:
                face_rgb = cv2.cvtColor(face_roi, cv2.COLOR_BGR2RGB)
            else:
                face_rgb = cv2.cvtColor(face_roi, cv2.COLOR_GRAY2RGB)
            
            face_rgb = face_rgb.astype(np.float32) / 255.0
            
            # Use DeepFace for embedding extraction
            embedding_obj = DeepFace.represent(
                face_rgb,
                model_name=self.config.get('embedding_model', 'Facenet'),
                enforce_detection=False,
                detector_backend='skip',
                align=True
            )
            
            if embedding_obj and len(embedding_obj) > 0:
                return np.array(embedding_obj[0]['embedding'])
                
        except Exception as e:
            if self.config.get('verbose', False):
                print(f"Multi-scale embedding extraction error: {e}")
                
        return None
        
    def _rotate_face_gpu(self, face: np.ndarray, angle: float) -> np.ndarray:
        """Rotate face on GPU using PyTorch."""
        if self.device.type != 'cuda':
            # Fallback to CPU if CUDA not available
            return self._rotate_face_cpu(face, angle)
            
        try:
            # Convert numpy to tensor and move to GPU
            face_tensor = torch.from_numpy(face).permute(2, 0, 1).unsqueeze(0).to(self.device).float() / 255.0
            
            # Use torchvision for GPU transforms
            import torchvision.transforms as T
            transform = T.RandomRotation(degrees=[angle, angle])
            rotated_tensor = transform(face_tensor)
            
            # Convert back to numpy
            rotated = (rotated_tensor.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
            return rotated
            
        except Exception as e:
            if self.config.get('verbose', False):
                print(f"GPU rotation failed: {e}, falling back to CPU")
            return self._rotate_face_cpu(face, angle)
    
    def _rotate_face_cpu(self, face: np.ndarray, angle: float) -> np.ndarray:
        """Rotate face by small angle for robustness (CPU fallback)"""
        h, w = face.shape[:2]
        center = (w // 2, h // 2)
        
        rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(face, rotation_matrix, (w, h), flags=cv2.INTER_CUBIC)
        
        return rotated
        
    def extract_multi_scale_embeddings(self, face_roi: np.ndarray) -> List[np.ndarray]:
        """Extract embeddings from multiple scales and slight rotations"""
        embeddings = []
        h, w = face_roi.shape[:2]
        
        for scale in self.scale_factors:
            # Scale the face ROI
            new_w, new_h = int(w * scale), int(h * scale)
            if new_w < 20 or new_h < 20:  # Minimum size
                continue
                
            scaled_face = cv2.resize(face_roi, (new_w, new_h), interpolation=cv2.INTER_AREA)
            
            # Extract embedding from scaled version
            embedding = self._extract_single_embedding(scaled_face)
            if embedding is not None:
                embeddings.append(embedding)
                
            # Add slightly rotated versions using GPU acceleration
            for angle in self.rotation_angles:
                rotated_face = self._rotate_face_gpu(scaled_face, angle)
                rot_embedding = self._extract_single_embedding(rotated_face)
                if rot_embedding is not None:
                    embeddings.append(rot_embedding)
        
        return embeddings
    
    def fuse_embeddings(self, embeddings: List[np.ndarray]) -> np.ndarray:
        """Fuse multiple embeddings into robust representation"""
        if not embeddings:
            return None
            
        # Simple average fusion
        fused = np.mean(embeddings, axis=0)
        
        # Optional: weighted fusion based on quality scores
        # weights = [self._calculate_embedding_quality(emb) for emb in embeddings]
        # fused = np.average(embeddings, axis=0, weights=weights)
        
        return fused
    
    