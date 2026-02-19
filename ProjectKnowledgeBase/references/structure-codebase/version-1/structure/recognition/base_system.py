# recognition/base_system.py
import cv2
import json
from pathlib import Path
from ultralytics import YOLO
from deepface import DeepFace
from sklearn.metrics.pairwise import cosine_similarity
import onnxruntime as ort
import numpy as np
from collections import deque
from typing import Dict, List, Tuple, Optional
import time
import torch
import logging

class FaceRecognitionSystem:
    def __init__(self, config: Dict):
        # Initialize logger
        self.logger = logging.getLogger(__name__)
        
        self.config = config
        self.detection_model = None
        self.mask_detector = None
        self.mask_input_size = None  # Will be dynamically set from model
        self.embeddings_db = {}
        self.identity_centroids = {}
        
        # ENHANCED: Use circular buffers to prevent memory leaks
        self.debug_stats = {
            'total_frames_processed': 0,
            'total_faces_detected': 0,
            'total_faces_recognized': 0,
            'total_masks_detected': 0,
            'detection_times': deque(maxlen=50),
            'mask_detection_times': deque(maxlen=50),
            'embedding_times': deque(maxlen=50),
            'recognition_times': deque(maxlen=50),
            'last_processing_time': 0
        }
        
        # Check GPU availability and update config
        self._verify_gpu_config()
        
        self._load_models()
        self._load_mask_detector()  
        self._load_embeddings_database()

    def _verify_gpu_config(self):
        """Verify and update GPU configuration based on actual availability"""
        if self.config.get('use_gpu', False):
            try:
                if torch.cuda.is_available():
                    device_count = torch.cuda.device_count()
                    current_device = self.config.get('gpu_device', 0)
                    
                    if current_device < device_count:
                        gpu_name = torch.cuda.get_device_name(current_device)
                        self.logger.info(f"GPU {current_device}: {gpu_name} confirmed available")
                        self.config['use_gpu'] = True
                    else:
                        self.logger.warning(f"GPU device {current_device} not available, falling back to CPU")
                        self.config['use_gpu'] = False
                else:
                    self.logger.warning("CUDA not available, falling back to CPU")
                    self.config['use_gpu'] = False
            except Exception as e:
                self.logger.warning(f"GPU verification failed: {e}, falling back to CPU")
                self.config['use_gpu'] = False
        
    def _load_mask_detector(self):
        """Load ONNX mask detection model with GPU support and dynamic input size detection"""
        try:
            mask_model_path = Path(self.config.get('mask_model_path', ''))
            if not mask_model_path.exists():
                self.logger.warning("Mask model not found, continuing without mask detection")
                return
                
            # Set providers for GPU acceleration
            providers = []
            if self.config.get('use_gpu', False):
                # Try CUDA first, then fall back to CPU
                try:
                    providers = [
                        ('CUDAExecutionProvider', {
                            'device_id': self.config.get('gpu_device', 0),
                            'arena_extend_strategy': 'kNextPowerOfTwo',
                            'gpu_mem_limit': 2 * 1024 * 1024 * 1024,  # 2GB limit
                            'cudnn_conv_algo_search': 'EXHAUSTIVE',
                            'do_copy_in_default_stream': True,
                        }),
                        'CPUExecutionProvider'
                    ]
                    self.logger.info("Using CUDA for mask detection")
                except Exception as e:
                    self.logger.warning(f"CUDA not available for mask detection: {e}")
                    providers = ['CPUExecutionProvider']
            else:
                providers = ['CPUExecutionProvider']
                
            # Initialize ONNX Runtime session with providers
            self.mask_detector = ort.InferenceSession(
                str(mask_model_path), 
                providers=providers
            )
            
            # DYNAMIC INPUT SIZE DETECTION
            # Get input shape from model
            input_details = self.mask_detector.get_inputs()[0]
            input_shape = input_details.shape
            
            # Determine input size based on shape format
            # Common formats: (batch, channels, height, width) or (batch, height, width, channels)
            if len(input_shape) == 4:
                if input_shape[1] == 3:  # NCHW format (batch, channels, height, width)
                    # Your model structure shows (None, 40, 50, 3) which is NHWC
                    # But ONNX often uses NCHW, so we need to check
                    height, width = input_shape[2], input_shape[3]
                    self.channel_format = 'NCHW'
                elif input_shape[3] == 3:  # NHWC format (batch, height, width, channels)
                    height, width = input_shape[1], input_shape[2]
                    self.channel_format = 'NHWC'
                else:
                    # Try to infer from the shape
                    # Find dimensions that look like spatial dimensions (larger than 3)
                    spatial_dims = [dim for dim in input_shape[1:] if dim > 3]
                    if len(spatial_dims) >= 2:
                        height, width = spatial_dims[0], spatial_dims[1]
                        self.channel_format = 'UNKNOWN'
                    else:
                        # Default fallback
                        height, width = 40, 50  # Based on your model structure
                        self.channel_format = 'DEFAULT'
                        self.logger.warning(f"Could not determine input shape, using default: {height}x{width}")
            else:
                # Unexpected shape format, use default from your model
                height, width = 40, 50
                self.channel_format = 'UNKNOWN'
                self.logger.warning(f"Unexpected input shape {input_shape}, using default: {height}x{width}")
            
            # Store the dynamic input size
            self.mask_input_size = (height, width)
            
            # Validate model input/output
            input_name = input_details.name
            output_name = self.mask_detector.get_outputs()[0].name
            
            self.logger.info(f"Mask detection model loaded with input size: {width}x{height}")
            self.logger.info(f"Channel format: {self.channel_format}")
            self.logger.info(f"Input: {input_name}, Output: {output_name}")
            self.logger.info(f"Input shape: {input_shape}")
            self.logger.info(f"Using providers: {[p if isinstance(p, str) else p[0] for p in providers]}")
            
        except Exception as e:
            self.logger.error(f"Failed to load mask detection model: {e}")
            # Don't raise exception, continue without mask detection
                      
    def detect_mask(self, face_roi: np.ndarray) -> Tuple[str, float]:
        """Enhanced mask detection with dynamic input size and better ROI handling"""
        if self.mask_detector is None or self.mask_input_size is None:
            return "no_mask", 0.0
            
        start_time = time.time()
        
        try:
            # More thorough ROI validation
            if (face_roi.size == 0 or face_roi.shape[0] < 40 or face_roi.shape[1] < 40 or
                np.std(face_roi) < 15):  # Check for low variance (blurry/featureless)
                return "unknown", 0.0
            
            # Use dynamic input size from model
            input_height, input_width = self.mask_input_size
            
            # DYNAMIC: Use the detected input size
            input_size = (input_height, input_width)
            h, w = face_roi.shape[:2]
            
            # Calculate scaling factor that preserves aspect ratio
            scale = min(input_size[0] / h, input_size[1] / w)
            new_h, new_w = int(h * scale), int(w * scale)
            
            # Resize with aspect ratio preservation
            resized_face = cv2.resize(face_roi, (new_w, new_h), interpolation=cv2.INTER_AREA)
            
            # Create padded image
            padded_face = np.zeros((input_size[0], input_size[1], 3), dtype=np.float32)
            y_offset = (input_size[0] - new_h) // 2
            x_offset = (input_size[1] - new_w) // 2
            padded_face[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized_face
            
            # Convert to RGB and normalize
            rgb_face = cv2.cvtColor(padded_face.astype(np.uint8), cv2.COLOR_BGR2RGB)
            normalized_face = rgb_face.astype(np.float32) / 255.0
            
            # Prepare input based on channel format
            if self.channel_format == 'NCHW':
                # Convert from NHWC to NCHW (batch, channels, height, width)
                input_data = np.transpose(normalized_face, (2, 0, 1))  # HWC to CHW
                input_data = np.expand_dims(input_data, axis=0)  # Add batch dimension
            elif self.channel_format == 'NHWC':
                # Keep as NHWC (batch, height, width, channels)
                input_data = np.expand_dims(normalized_face, axis=0)
            else:
                # Try both formats
                try:
                    # First try NCHW
                    input_data = np.transpose(normalized_face, (2, 0, 1))
                    input_data = np.expand_dims(input_data, axis=0)
                except:
                    # Fall back to NHWC
                    input_data = np.expand_dims(normalized_face, axis=0)
            
            # Run inference
            input_name = self.mask_detector.get_inputs()[0].name
            output_name = self.mask_detector.get_outputs()[0].name
            
            outputs = self.mask_detector.run([output_name], {input_name: input_data})
            predictions = outputs[0][0]  # First batch, first prediction
            
            # 🎯 ENHANCED FRAMEWORK LOGIC WITH CONFIDENCE THRESHOLDING
            mask_prob = float(predictions[0])
            without_mask_prob = float(predictions[1])
            
            # Get the configuration threshold (default to 0.8 if not set)
            mask_threshold = self.config.get('mask_detection_threshold', 0.8)
            
            # Use threshold to reduce false positives
            if mask_prob > without_mask_prob and mask_prob >= mask_threshold:
                mask_status = "mask"
                confidence = mask_prob
            else:
                mask_status = "no_mask" 
                confidence = without_mask_prob
            
            # Update stats
            mask_time = (time.time() - start_time) * 1000
            self.debug_stats['mask_detection_times'].append(mask_time)
            
            return mask_status, confidence
            
        except Exception as e:
            self.logger.error(f"Mask detection error: {e}")
            return "unknown", 0.0
                
    def _load_models(self):
        """Load YOLO face detection model from local path with GPU support"""
        try:
            model_path = Path(self.config['detection_model_path'])
            if not model_path.exists():
                raise FileNotFoundError(f"YOLO model not found at {model_path}")
                
            # Load model with GPU support
            self.detection_model = YOLO(str(model_path))
            
            # Move model to GPU if available
            if self.config.get('use_gpu', False):
                device = self.config.get('gpu_device', 0)  # Default to GPU 0
                # Convert to torch device
                torch_device = f'cuda:{device}'
                self.detection_model.to(torch_device)
                self.logger.info(f"YOLO model loaded on {torch_device}")
                
                # Verify the model is actually on GPU
                model_device = next(self.detection_model.model.parameters()).device
                self.logger.info(f"YOLO model verified on device: {model_device}")
            else:
                self.logger.info(f"YOLO model loaded on CPU")
                
        except Exception as e:
            self.logger.error(f"Failed to load YOLO model: {e}")
            raise
               
    def _load_embeddings_database(self):
        """Load pre-computed face embeddings from JSON with your structure"""
        try:
            db_path = Path(self.config['embeddings_db_path'])
            if not db_path.exists():
                self.logger.warning("Embeddings database not found, starting fresh")
                self.embeddings_db = {"persons": {}, "metadata": {}}
                return
                
            with open(db_path, 'r') as f:
                self.embeddings_db = json.load(f)
                
            if "persons" in self.embeddings_db:
                for person_id, person_data in self.embeddings_db["persons"].items():
                    display_name = person_data["display_name"]
                    centroid = person_data["centroid_embedding"]
                    self.identity_centroids[display_name] = np.array(centroid)
                    
                self.logger.info(f"Loaded {len(self.identity_centroids)} identities from database")
                self.logger.info(f"Available persons: {list(self.identity_centroids.keys())}")
                
            else:
                self.logger.warning("No 'persons' key found in JSON database")
                
        except Exception as e:
            self.logger.error(f"Failed to load embeddings database: {e}")
            raise

    def detect_faces(self, frame: np.ndarray) -> List[Dict]:
            """Detect faces using YOLO with GPU optimization"""
            start_time = time.time()
            try:
                # Use GPU if configured - FIXED: Use proper device string
                if self.config.get('use_gpu', False):
                    device = self.config.get('gpu_device', 0)
                    device_str = f'cuda:{device}'
                else:
                    device_str = 'cpu'
                
                results = self.detection_model(
                    frame, 
                    conf=self.config['detection_confidence'],
                    iou=self.config['detection_iou'],
                    verbose=False,
                    device=device_str  # Specify device for inference
                )
                
                detections = []
                for result in results:
                    boxes = result.boxes
                    if boxes is not None:
                        for box in boxes:
                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()  # Ensure tensor is moved to CPU for numpy
                            confidence = box.conf[0].cpu().numpy()
                            
                            detections.append({
                                'bbox': [int(x1), int(y1), int(x2), int(y2)],
                                'confidence': float(confidence)
                            })
                
                detection_time = (time.time() - start_time) * 1000
                self.debug_stats['detection_times'].append(detection_time)
                
                if self.config.get('debug', {}).get('verbose', False):
                    self.logger.debug(f"Detected {len(detections)} faces in {detection_time:.2f}ms")
                            
                return detections
                
            except Exception as e:
                self.logger.error(f"Detection error: {e}")
                return []
                    
    def extract_embedding(self, face_roi: np.ndarray) -> Optional[np.ndarray]:
        """Optimized embedding extraction with GPU support"""
        start_time = time.time()
        
        # Validate ROI dimensions more thoroughly
        if (face_roi.size == 0 or face_roi.shape[0] < 50 or face_roi.shape[1] < 50 or 
            np.max(face_roi) - np.min(face_roi) < 10):  # Check for low contrast
            if self.config.get('debug', {}).get('verbose', False):
                self.logger.warning("Invalid face ROI for embedding extraction")
            return None
            
        try:
            # Convert to RGB and ensure proper data type
            if len(face_roi.shape) == 3:
                face_rgb = cv2.cvtColor(face_roi, cv2.COLOR_BGR2RGB)
            else:
                face_rgb = cv2.cvtColor(face_roi, cv2.COLOR_GRAY2RGB)
            
            # Normalize pixel values
            face_rgb = face_rgb.astype(np.float32) / 255.0
            
            # Set device for DeepFace - FIXED: Use proper device format
            if self.config.get('use_gpu', False):
                device = self.config.get('gpu_device', 0)
                # DeepFace uses different device format
                device_name = f'cuda:{device}'
            else:
                device_name = 'cpu'
                
            if self.config.get('debug', {}).get('verbose', False):
                self.logger.debug(f"Extracting embedding on device: {device_name}")
                
            embedding_obj = DeepFace.represent(
                face_rgb,
                model_name=self.config['embedding_model'],
                enforce_detection=False,
                detector_backend='skip',
                align=True
            )
            
            if embedding_obj and len(embedding_obj) > 0:
                embedding_time = (time.time() - start_time) * 1000
                self.debug_stats['embedding_times'].append(embedding_time)
                
                if self.config.get('debug', {}).get('verbose', False):
                    self.logger.debug(f"Embedding extracted in {embedding_time:.2f}ms")
               
                return np.array(embedding_obj[0]['embedding'])
            else:
                if self.config.get('debug', {}).get('verbose', False):
                    self.logger.warning("No embedding extracted")
                
        except Exception as e:
            if self.config.get('verbose', False):
                self.logger.error(f"Embedding extraction error: {e}")
                
        return None
    
    def recognize_face(self, embedding: np.ndarray) -> Tuple[Optional[str], float]:
        """Enhanced matching with multiple similarity strategies"""
        start_time = time.time()
        
        if not self.identity_centroids:
            return None, 0.0
            
        best_similarity = -1.0
        best_identity = None
        
        embedding = embedding.flatten()
        
        for identity, centroid in self.identity_centroids.items():
            centroid = centroid.flatten()
            
            # Cosine similarity (primary)
            cosine_sim = cosine_similarity([embedding], [centroid])[0][0]
            
            # Optional: Euclidean distance (normalized to 0-1)
            euclidean_dist = np.linalg.norm(embedding - centroid)
            euclidean_sim = 1 / (1 + euclidean_dist)  # Convert distance to similarity
            
            # Combine strategies (weighted)
            final_similarity = 0.8 * cosine_sim + 0.2 * euclidean_sim
            
            if final_similarity > best_similarity and final_similarity >= self.config['recognition_threshold']:
                best_similarity = final_similarity
                best_identity = identity
        
        recognition_time = (time.time() - start_time) * 1000
        self.debug_stats['recognition_times'].append(recognition_time)
        
        return best_identity, best_similarity

    def process_frame(self, frame: np.ndarray) -> List[Dict]:
        """Enhanced pipeline: detect → mask detection → extract → recognize"""
        start_time = time.time()
        results = []
        
        # Detect faces
        detections = self.detect_faces(frame)
        
        for detection in detections:
            x1, y1, x2, y2 = detection['bbox']
            
            padding = self.config.get('roi_padding', 20)  # Increased padding for better mask detection
            h, w = frame.shape[:2]
            x1_pad = max(0, x1 - padding)
            y1_pad = max(0, y1 - padding)
            x2_pad = min(w, x2 + padding)
            y2_pad = min(h, y2 + padding)
            
            face_roi = frame[y1_pad:y2_pad, x1_pad:x2_pad]
            
            # Better ROI validation
            if (face_roi.size == 0 or face_roi.shape[0] < 40 or face_roi.shape[1] < 40 or
                np.std(face_roi) < 10):  # Check for low contrast
                continue
                
            # NEW: Enhanced Mask detection
            mask_status, mask_confidence = self.detect_mask(face_roi)
            
            # Continue with embedding extraction only if we have a good face ROI
            embedding = self.extract_embedding(face_roi)
            if embedding is None:
                continue
                
            identity, recognition_confidence = self.recognize_face(embedding)
            
            # Update mask statistics
            if mask_status == "mask":
                self.debug_stats['total_masks_detected'] += 1
            
            results.append({
                'bbox': detection['bbox'],
                'detection_confidence': detection['confidence'],
                'mask_status': mask_status,  
                'mask_confidence': mask_confidence,  
                'identity': identity,
                'recognition_confidence': recognition_confidence,
                'embedding': embedding.tolist()
            })
        
        # Update overall stats
        self.debug_stats['total_frames_processed'] += 1
        self.debug_stats['total_faces_detected'] += len(detections)
        self.debug_stats['total_faces_recognized'] += len([r for r in results if r['identity']])
        self.debug_stats['last_processing_time'] = (time.time() - start_time) * 1000
            
        return results
        
    def get_debug_stats(self) -> Dict:
        """Enhanced performance statistics"""
        stats = self.debug_stats.copy()
        
        # Calculate averages and percentiles
        stats['avg_detection_time'] = np.mean(stats['detection_times']) if stats['detection_times'] else 0
        stats['p95_detection_time'] = np.percentile(stats['detection_times'], 95) if stats['detection_times'] else 0
        stats['max_detection_time'] = np.max(stats['detection_times']) if stats['detection_times'] else 0
        
        stats['avg_embedding_time'] = np.mean(stats['embedding_times']) if stats['embedding_times'] else 0
        stats['p95_embedding_time'] = np.percentile(stats['embedding_times'], 95) if stats['embedding_times'] else 0
        
        stats['avg_recognition_time'] = np.mean(stats['recognition_times']) if stats['recognition_times'] else 0
        
        # Calculate mask detection time
        stats['avg_detection_time'] = np.mean(stats['detection_times']) if stats['detection_times'] else 0
        stats['avg_mask_detection_time'] = np.mean(stats['mask_detection_times']) if stats['mask_detection_times'] else 0
        
        # Add mask input size to stats if available
        if self.mask_input_size:
            stats['mask_input_size'] = f"{self.mask_input_size[1]}x{self.mask_input_size[0]}"
            stats['mask_channel_format'] = self.channel_format
                     
        # Calculate rates and efficiencies
        if stats['total_faces_detected'] > 0:
            stats['mask_detection_rate'] = (stats['total_masks_detected'] / stats['total_faces_detected']) * 100
            stats['recognition_rate'] = (stats['total_faces_recognized'] / stats['total_faces_detected']) * 100
        else:
            stats['mask_detection_rate'] = 0
            stats['recognition_rate'] = 0
            
        if stats['total_frames_processed'] > 0:
            stats['faces_per_frame'] = stats['total_faces_detected'] / stats['total_frames_processed']
        else:
            stats['faces_per_frame'] = 0
                
        # Memory usage (approximate)
        try:
            import psutil
            process = psutil.Process()
            stats['memory_mb'] = process.memory_info().rss / 1024 / 1024
        except ImportError:
            stats['memory_mb'] = 0
        
        return stats

    def get_known_identities(self) -> List[str]:
        """Get list of all known identities"""
        return list(self.identity_centroids.keys())

    def get_model_info(self) -> Dict:
        """Get information about loaded models"""
        info = {
            'mask_detector_loaded': self.mask_detector is not None,
            'face_detector_loaded': self.detection_model is not None,
            'known_identities_count': len(self.identity_centroids)
        }
        
        if self.mask_detector:
            info['mask_input_size'] = self.mask_input_size
            info['mask_channel_format'] = self.channel_format
            info['mask_input_name'] = self.mask_detector.get_inputs()[0].name
            info['mask_output_name'] = self.mask_detector.get_outputs()[0].name
            
        return info