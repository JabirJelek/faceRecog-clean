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

class FaceRecognitionSystem:
    def __init__(self, config: Dict):
        self.config = config
        self.detection_model = None
        self.mask_detector = None
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
                        print(f"✅ GPU {current_device}: {gpu_name} confirmed available")
                        self.config['use_gpu'] = True
                    else:
                        print(f"⚠️  GPU device {current_device} not available, falling back to CPU")
                        self.config['use_gpu'] = False
                else:
                    print("⚠️  CUDA not available, falling back to CPU")
                    self.config['use_gpu'] = False
            except Exception as e:
                print(f"⚠️  GPU verification failed: {e}, falling back to CPU")
                self.config['use_gpu'] = False
        
    def _load_mask_detector(self):
        """Load ONNX mask detection model with GPU support"""
        try:
            mask_model_path = Path(self.config.get('mask_model_path', ''))
            if not mask_model_path.exists():
                print("⚠️  Mask model not found, continuing without mask detection")
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
                    print("🎯 Using CUDA for mask detection")
                except Exception as e:
                    print(f"⚠️  CUDA not available for mask detection: {e}")
                    providers = ['CPUExecutionProvider']
            else:
                providers = ['CPUExecutionProvider']
                
            # Initialize ONNX Runtime session with providers
            self.mask_detector = ort.InferenceSession(
                str(mask_model_path), 
                providers=providers
            )
            
            # Validate model input/output
            input_name = self.mask_detector.get_inputs()[0].name
            output_name = self.mask_detector.get_outputs()[0].name
            
            print(f"✅ Mask detection model loaded")
            print(f"   - Input: {input_name}, Output: {output_name}")
            print(f"   - Input shape: {self.mask_detector.get_inputs()[0].shape}")
            print(f"   - Using providers: {[p if isinstance(p, str) else p[0] for p in providers]}")
            
        except Exception as e:
            print(f"❌ Failed to load mask detection model: {e}")
            # Don't raise exception, continue without mask detection
                      
    def detect_mask(self, face_roi: np.ndarray) -> Tuple[str, float]:
        """Enhanced mask detection with better ROI handling and thresholding"""
        if self.mask_detector is None:
            return "no_mask", 0.0
            
        start_time = time.time()
        
        try:
            # More thorough ROI validation
            if (face_roi.size == 0 or face_roi.shape[0] < 40 or face_roi.shape[1] < 40 or
                np.std(face_roi) < 15):  # Check for low variance (blurry/featureless)
                return "unknown", 0.0
                
            # Preserve aspect ratio with smart padding
            input_size = (224, 224)
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
            
            # Add batch dimension
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
            else: #without_mask_prob > mask_prob and without_mask_prob >= mask_threshold:
                mask_status = "no_mask" 
                confidence = without_mask_prob
            # else:
            #     # Confidence too low for either class
            #     mask_status = "unknown"
            #     confidence = max(mask_prob, without_mask_prob)
            
            # Update stats
            mask_time = (time.time() - start_time) * 1000
            self.debug_stats['mask_detection_times'].append(mask_time)
            
            return mask_status, confidence
            
        except Exception as e:
            print(f"Mask detection error: {e}")
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
                print(f"✅ YOLO model loaded on {torch_device}")
                
                # Verify the model is actually on GPU
                model_device = next(self.detection_model.model.parameters()).device
                print(f"✅ YOLO model verified on device: {model_device}")
            else:
                print(f"✅ YOLO model loaded on CPU")
                
        except Exception as e:
            print(f"❌ Failed to load YOLO model: {e}")
            raise
               
    def _load_embeddings_database(self):
        """Load pre-computed face embeddings from JSON with your structure"""
        try:
            db_path = Path(self.config['embeddings_db_path'])
            if not db_path.exists():
                print("⚠️  Embeddings database not found, starting fresh")
                self.embeddings_db = {"persons": {}, "metadata": {}}
                return
                
            with open(db_path, 'r') as f:
                self.embeddings_db = json.load(f)
                
            if "persons" in self.embeddings_db:
                for person_id, person_data in self.embeddings_db["persons"].items():
                    display_name = person_data["display_name"]
                    centroid = person_data["centroid_embedding"]
                    self.identity_centroids[display_name] = np.array(centroid)
                    
                print(f"✅ Loaded {len(self.identity_centroids)} identities from database")
                print(f"📊 Available persons: {list(self.identity_centroids.keys())}")
                
            else:
                print("⚠️  No 'persons' key found in JSON database")
                
        except Exception as e:
            print(f"❌ Failed to load embeddings database: {e}")
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
                    print(f"🔍 Detected {len(detections)} faces in {detection_time:.2f}ms")
                            
                return detections
                
            except Exception as e:
                print(f"❌ Detection error: {e}")
                return []
                    
    def extract_embedding(self, face_roi: np.ndarray) -> Optional[np.ndarray]:
        """Optimized embedding extraction with GPU support"""
        start_time = time.time()
        
        # Validate ROI dimensions more thoroughly
        if (face_roi.size == 0 or face_roi.shape[0] < 50 or face_roi.shape[1] < 50 or 
            np.max(face_roi) - np.min(face_roi) < 10):  # Check for low contrast
            if self.config.get('debug', {}).get('verbose', False):
                print("❌ Invalid face ROI for embedding extraction")
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
                print(f"🔍 Extracting embedding on device: {device_name}")
                
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
                    print(f"✅ Embedding extracted in {embedding_time:.2f}ms")
               
                return np.array(embedding_obj[0]['embedding'])
            else:
                if self.config.get('debug', {}).get('verbose', False):
                    print("❌ No embedding extracted")
                
        except Exception as e:
            if self.config.get('verbose', False):
                print(f"❌ Embedding extraction error: {e}")
                
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
        stats['avg_mask_detection_time'] = np.mean(stats['mask_detection_times']) if stats['mask_detection_times'] else 0  # NEW     
        
        if stats['total_faces_detected'] > 0:
            stats['mask_detection_rate'] = (stats['total_masks_detected'] / stats['total_faces_detected']) * 100
        else:
            stats['mask_detection_rate'] = 0
                     
        # Calculate rates and efficiencies
        if stats['total_faces_detected'] > 0:
            stats['recognition_rate'] = (stats['total_faces_recognized'] / stats['total_faces_detected']) * 100
        else:
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
