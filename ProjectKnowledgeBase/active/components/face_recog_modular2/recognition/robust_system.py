# recognition/robust_system.py
import numpy as np
from collections import deque
from typing import Dict, List
import time
from face_recog_modular2.processing.temporal_processing import MultiScaleFaceProcessor, TemporalFusion
from face_recog_modular2.processing.quality_assessment import FaceQualityAssessor, AdaptiveThresholdManager
from face_recog_modular2.recognition.voyager_system import VoyagerFaceRecognitionSystem
import logging

class RobustFaceRecognitionSystem(VoyagerFaceRecognitionSystem):
    def __init__(self, config: Dict):
        super().__init__(config)
        
        # Enhanced components
        self.multi_scale_processor = MultiScaleFaceProcessor(config)
        self.temporal_fusion = TemporalFusion(config)
        self.quality_assessor = FaceQualityAssessor(config)
        self.threshold_manager = AdaptiveThresholdManager(config)
        
        # Enhanced configuration with optimization parameters
        self.robust_config = {
            'enable_multi_scale': config.get('enable_multi_scale', True),
            'enable_temporal_fusion': config.get('enable_temporal_fusion', True),
            'enable_quality_aware': config.get('enable_quality_aware', True),
            'min_face_quality': config.get('min_face_quality', 0.3),
            'temporal_buffer_size': config.get('temporal_buffer_size', 10),
            # Optimization thresholds
            'quality_marginal_lower': config.get('quality_marginal_lower', 0.3),
            'quality_marginal_upper': config.get('quality_marginal_upper', 0.6),
            'quality_high_threshold': config.get('quality_high_threshold', 0.7),
            'min_face_size': config.get('min_face_size', 20),
            'near_min_size_multiplier': config.get('near_min_size_multiplier', 1.5),
        }
        
        # Initialize for statistics
        self.last_results = []
        self.multi_scale_usage_stats = {'enabled': 0, 'disabled': 0, 'skipped_low': 0, 'skipped_high': 0}
        
        self.logger.info("Robust Face Recognition with VOYAGER similarity engine")
                    
    def process_frame_robust(self, frame: np.ndarray) -> List[Dict]:
        """Enhanced robust processing with quality-adaptive similarity and optimized multi-scale usage"""
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
            if face_roi.size == 0:
                continue
                
            # Calculate face size for optimization
            face_height = y2 - y1
            face_width = x2 - x1
            min_face_side = min(face_height, face_width)
            
            # Quality assessment
            quality_scores = self.quality_assessor.assess_face_quality(face_roi, detection['bbox'])
            overall_quality = quality_scores.get('overall', 0)
            
            # Skip very low quality faces entirely
            if not self.threshold_manager.should_process_face(quality_scores):
                self.multi_scale_usage_stats['skipped_low'] += 1
                if self.config.get('verbose', False):
                    self.logger.debug(f"Skipping low quality face (score: {overall_quality:.2f})")
                continue
                
            # Mask detection
            mask_status, mask_confidence = self.detect_mask(face_roi)
            
            # OPTIMIZED MULTI-SCALE DECISION LOGIC
            use_multi_scale = False
            multi_scale_reason = "standard"
            
            if self.robust_config['enable_multi_scale']:
                # Condition 1: Face quality is marginal (0.3 < quality < 0.6)
                condition_marginal_quality = (
                    overall_quality > self.robust_config['quality_marginal_lower'] and
                    overall_quality < self.robust_config['quality_marginal_upper']
                )
                
                # Condition 2: Face size is near the minimum threshold
                min_face_size = self.robust_config['min_face_size']
                near_min_threshold = min_face_size * self.robust_config['near_min_size_multiplier']
                condition_near_min_size = min_face_side < near_min_threshold
                
                # Decision logic based on optimization strategy
                if condition_marginal_quality:
                    # Quality is marginal - use multi-scale for boost
                    use_multi_scale = True
                    multi_scale_reason = "marginal_quality"
                elif condition_near_min_size and overall_quality > 0.3:
                    # Face is small and not extremely low quality - use multi-scale
                    use_multi_scale = True
                    multi_scale_reason = "near_min_size"
                elif overall_quality >= self.robust_config['quality_high_threshold']:
                    # High quality - skip multi-scale (fast path)
                    use_multi_scale = False
                    multi_scale_reason = "high_quality"
                    self.multi_scale_usage_stats['skipped_high'] += 1
                elif overall_quality <= self.robust_config['quality_marginal_lower']:
                    # Very low quality - skip multi-scale
                    use_multi_scale = False
                    multi_scale_reason = "low_quality"
                else:
                    # Default: use standard embedding
                    use_multi_scale = False
                    multi_scale_reason = "default"
                
                # Update statistics
                if use_multi_scale:
                    self.multi_scale_usage_stats['enabled'] += 1
                    if self.config.get('verbose', False):
                        self.logger.debug(f"Multi-scale enabled ({multi_scale_reason}): Q={overall_quality:.2f}, Size={min_face_side}")
                else:
                    self.multi_scale_usage_stats['disabled'] += 1

            
            # Enhanced embedding extraction with optimized multi-scale usage
            if use_multi_scale:
                embeddings = self.multi_scale_processor.extract_multi_scale_embeddings(face_roi)
                if embeddings:
                    embedding = self.multi_scale_processor.fuse_embeddings(embeddings)
                else:
                    embedding = self.extract_embedding(face_roi)
            else:
                # Fast path: single embedding extraction
                embedding = self.extract_embedding(face_roi)
            
            if embedding is None:
                continue
            
            # VOYAGER-BASED RECOGNITION
            identity, recognition_confidence = self.recognize_face(embedding)
            
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
                'similarity_engine': 'voyager',
                'quality_adaptive': True,
                'multi_scale_used': use_multi_scale,
                'multi_scale_reason': multi_scale_reason,
                'face_size': min_face_side
            })
        
        # Update stats and store last results
        self._update_robust_stats(results, start_time)
        self.last_results = results
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

         
    def get_robust_stats(self) -> Dict:
        """Get robust engine statistics"""
        stats = self.get_voyager_stats()
        
        # Add recognition statistics
        if hasattr(self, 'last_results'):
            total_faces = len(self.last_results)
            recognized_faces = len([r for r in self.last_results if r['identity']])
            stats['recognition_rate'] = recognized_faces / total_faces if total_faces > 0 else 0
        
        # Add multi-scale optimization statistics
        total_multi_scale_decisions = (self.multi_scale_usage_stats['enabled'] + 
                                      self.multi_scale_usage_stats['disabled'])
        if total_multi_scale_decisions > 0:
            stats['multi_scale_usage'] = {
                'enabled_percentage': (self.multi_scale_usage_stats['enabled'] / 
                                      total_multi_scale_decisions * 100),
                'disabled_percentage': (self.multi_scale_usage_stats['disabled'] / 
                                       total_multi_scale_decisions * 100),
                'skipped_low_quality': self.multi_scale_usage_stats['skipped_low'],
                'skipped_high_quality': self.multi_scale_usage_stats['skipped_high'],
                'total_decisions': total_multi_scale_decisions
            }
        
        return stats
    