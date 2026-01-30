# recognition/robust_system.py
import numpy as np
from collections import deque
from typing import Dict, List
import time
from face_recog_modular.processing.temporal_processing import MultiScaleFaceProcessor, TemporalFusion
from face_recog_modular.processing.quality_assessment import FaceQualityAssessor, AdaptiveThresholdManager
from face_recog_modular.recognition.voyager_system import VoyagerFaceRecognitionSystem

class RobustFaceRecognitionSystem(VoyagerFaceRecognitionSystem):
    def __init__(self, config: Dict):
        super().__init__(config)
        
        # Enhanced components
        self.multi_scale_processor = MultiScaleFaceProcessor(config)
        self.temporal_fusion = TemporalFusion(config)
        self.quality_assessor = FaceQualityAssessor(config)
        self.threshold_manager = AdaptiveThresholdManager(config)
        
        # Enhanced configuration
        self.robust_config = {
            'enable_multi_scale': config.get('enable_multi_scale', True),
            'enable_temporal_fusion': config.get('enable_temporal_fusion', True),
            'enable_quality_aware': config.get('enable_quality_aware', True),
            'min_face_quality': config.get('min_face_quality', 0.3),
            'temporal_buffer_size': config.get('temporal_buffer_size', 10),
        }
        
        # Initialize for statistics
        self.last_results = []
        
        print("🎯 Robust Face Recognition with VOYAGER similarity engine")
              
    def process_frame_robust(self, frame: np.ndarray) -> List[Dict]:
        """Enhanced robust processing with quality-adaptive similarity"""
        start_time = time.time()
        results = []
        
        # Detect faces
        detections = self.detect_faces(frame)
        
        for detection in detections:
            x1, y1, x2, y2 = detection['bbox']
            
            # Extract face ROI with padding
            padding = self.config.get('roi_padding', 15)
            h, w = frame.shape[:2]
            x1_pad = max(0, x1 - padding)
            y1_pad = max(0, y1 - padding)
            x2_pad = min(w, x2 + padding)
            y2_pad = min(h, y2 + padding)
            
            face_roi = frame[y1_pad:y2_pad, x1_pad:x2_pad]
            
            # Skip if ROI is invalid
            if face_roi.size == 0 or face_roi.shape[0] < 20 or face_roi.shape[1] < 20:
                continue
                
            # Quality assessment
            quality_scores = self.quality_assessor.assess_face_quality(face_roi, detection['bbox'])
            
            # Skip very low quality faces entirely
            if not self.threshold_manager.should_process_face(quality_scores):
                if self.config.get('verbose', False):
                    print(f"⏭️ Skipping low quality face (score: {quality_scores.get('overall', 0):.2f})")
                continue
                
            # Mask detection
            mask_status, mask_confidence = self.detect_mask(face_roi)
            
            # Enhanced embedding extraction
            if self.robust_config['enable_multi_scale'] and quality_scores.get('overall', 0) > 0.3:
                embeddings = self.multi_scale_processor.extract_multi_scale_embeddings(face_roi)
                if embeddings:
                    embedding = self.multi_scale_processor.fuse_embeddings(embeddings)
                else:
                    embedding = self.extract_embedding(face_roi)
            else:
                embedding = self.extract_embedding(face_roi)
            
            if embedding is None:
                continue
            
            # VOYAGER-BASED RECOGNITION
            identity, recognition_confidence = self.recognize_face(embedding)
            
            # Generate track ID for temporal fusion
            track_id = self._generate_track_id(detection['bbox'])
            
            # Update temporal buffer
            if identity and self.robust_config['enable_temporal_fusion']:
                self.temporal_fusion.update_temporal_buffer(track_id, identity, recognition_confidence)
                
                # Get temporal consensus
                temporal_identity, temporal_confidence = self.temporal_fusion.get_temporal_consensus(track_id)
                
                if temporal_identity and temporal_confidence > recognition_confidence:
                    identity = temporal_identity
                    recognition_confidence = temporal_confidence
            
            # Adaptive threshold for display
            adaptive_threshold = self.threshold_manager.compute_adaptive_threshold(quality_scores)
            
            results.append({
                'bbox': detection['bbox'],
                'detection_confidence': detection['confidence'],
                'mask_status': mask_status,
                'mask_confidence': mask_confidence,
                'identity': identity,
                'recognition_confidence': recognition_confidence,
                'embedding': embedding.tolist(),
                'quality_scores': quality_scores,
                'adaptive_threshold': adaptive_threshold,
                'track_id': track_id,
                'similarity_engine': 'voyager',
                'quality_adaptive': True
            })
        
        # Update stats and store last results
        self._update_robust_stats(results, start_time)
        self.last_results = results  # Store for statistics
        return results

    def _update_robust_stats(self, results: List[Dict], start_time: float):
        """Update enhanced statistics"""
        self.debug_stats['total_frames_processed'] += 1
        self.debug_stats['total_faces_detected'] += len(results)
        self.debug_stats['total_faces_recognized'] += len([r for r in results if r['identity']])
        self.debug_stats['last_processing_time'] = (time.time() - start_time) * 1000
        
        # Quality statistics
        if results:
            avg_quality = np.mean([r.get('quality_scores', {}).get('overall', 0) for r in results])
            self.debug_stats.setdefault('avg_face_quality', deque(maxlen=50)).append(avg_quality)
       
    def _generate_track_id(self, bbox: List[int]) -> int:
        """Generate simple track ID from bounding box position"""
        x1, y1, x2, y2 = bbox
        center_x, center_y = (x1 + x2) // 2, (y1 + y2) // 2
        return hash(f"{center_x}_{center_y}") % 1000000
         
    def get_robust_stats(self) -> Dict:
        """Get robust engine statistics"""
        stats = self.get_voyager_stats()
        
        # Add recognition statistics
        if hasattr(self, 'last_results'):
            total_faces = len(self.last_results)
            recognized_faces = len([r for r in self.last_results if r['identity']])
            stats['recognition_rate'] = recognized_faces / total_faces if total_faces > 0 else 0
        
        return stats         
