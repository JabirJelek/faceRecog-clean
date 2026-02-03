# # recognition/faiss_system.py
# import faiss
# import numpy as np
# import json
# from pathlib import Path
# from typing import Dict, List, Tuple, Optional, Union
# import logging
# from deepface import DeepFace
# from sklearn.metrics.pairwise import cosine_similarity
# import onnxruntime as ort
# import cv2
# from ultralytics import YOLO
# import torch
# from collections import deque
# import time

# class FaissFaceRecognitionSystem:
#     """FAISS-based face recognition system for efficient similarity search."""
    
#     def __init__(self, config: Dict):
#         self.config = config
#         self.logger = logging.getLogger(__name__)
        
#         # FAISS index and database
#         self.faiss_index = None
#         self.embedding_dim = None
#         self.id_to_identity = {}  # Maps FAISS index to identity name
#         self.identity_to_ids = {}  # Maps identity name to list of FAISS indices
        
#         # For backward compatibility with existing code
#         self.embeddings_db = {}
#         self.identity_centroids = {}
        
#         # Performance tracking
#         self.debug_stats = {
#             'total_faiss_searches': 0,
#             'avg_faiss_search_time': 0,
#             'faiss_search_times': deque(maxlen=50),
#             'faiss_build_time': 0
#         }
        
#         # Check GPU availability for FAISS
#         self._verify_faiss_gpu_config()
        
#         # Load models and database
#         self._load_models()
#         self._load_embeddings_database()
#         self._build_faiss_index()
        
#         # Mask detector (for compatibility)
#         self.mask_detector = None
#         self.mask_input_size = None
#         self.channel_format = None
        
#     def _verify_faiss_gpu_config(self):
#         """Verify and configure FAISS GPU support."""
#         if self.config.get('use_gpu', False) and self.config.get('use_faiss_gpu', False):
#             try:
#                 # Check if FAISS GPU is available
#                 if hasattr(faiss, 'get_num_gpus') and faiss.get_num_gpus() > 0:
#                     self.use_faiss_gpu = True
#                     self.gpu_device = self.config.get('gpu_device', 0)
#                     self.logger.info(f"FAISS GPU support available on device {self.gpu_device}")
#                 else:
#                     self.use_faiss_gpu = False
#                     self.logger.warning("FAISS GPU not available, falling back to CPU")
#             except Exception as e:
#                 self.use_faiss_gpu = False
#                 self.logger.warning(f"FAISS GPU verification failed: {e}, using CPU")
#         else:
#             self.use_faiss_gpu = False
            
#     def _load_models(self):
#         """Load YOLO face detection model with GPU support."""
#         try:
#             model_path = Path(self.config['detection_model_path'])
#             if not model_path.exists():
#                 raise FileNotFoundError(f"YOLO model not found at {model_path}")
                
#             self.detection_model = YOLO(str(model_path))
            
#             if self.config.get('use_gpu', False):
#                 device = self.config.get('gpu_device', 0)
#                 torch_device = f'cuda:{device}'
#                 self.detection_model.to(torch_device)
#                 self.logger.info(f"YOLO model loaded on {torch_device}")
#             else:
#                 self.logger.info("YOLO model loaded on CPU")
                
#         except Exception as e:
#             self.logger.error(f"Failed to load YOLO model: {e}")
#             raise
            
#     def _load_embeddings_database(self):
#         """Load embeddings from JSON and prepare for FAISS indexing."""
#         try:
#             db_path = Path(self.config['embeddings_db_path'])
#             if not db_path.exists():
#                 self.logger.warning("Embeddings database not found, starting fresh")
#                 self.embeddings_db = {"persons": {}, "metadata": {}}
#                 return
                
#             with open(db_path, 'r') as f:
#                 self.embeddings_db = json.load(f)
                
#             # Process persons for FAISS
#             if "persons" in self.embeddings_db:
#                 for person_id, person_data in self.embeddings_db["persons"].items():
#                     display_name = person_data["display_name"]
#                     centroid = person_data["centroid_embedding"]
                    
#                     # Store for backward compatibility
#                     self.identity_centroids[display_name] = np.array(centroid)
                    
#                 self.logger.info(f"Loaded {len(self.identity_centroids)} identities from database")
                
#             else:
#                 self.logger.warning("No 'persons' key found in JSON database")
                
#         except Exception as e:
#             self.logger.error(f"Failed to load embeddings database: {e}")
#             raise
            
#     def _build_faiss_index(self):
#         """Build FAISS index from loaded embeddings."""
#         if not self.identity_centroids:
#             self.logger.warning("No embeddings available for FAISS index")
#             return
            
#         start_time = time.time()
        
#         try:
#             # Convert embeddings to numpy array
#             embeddings_list = []
#             identity_names = []
            
#             for idx, (identity, centroid) in enumerate(self.identity_centroids.items()):
#                 centroid_np = np.array(centroid).flatten().astype('float32')
#                 embeddings_list.append(centroid_np)
#                 identity_names.append(identity)
                
#                 # Store mapping
#                 self.id_to_identity[idx] = identity
#                 if identity not in self.identity_to_ids:
#                     self.identity_to_ids[identity] = []
#                 self.identity_to_ids[identity].append(idx)
                
#             embeddings_matrix = np.vstack(embeddings_list)
#             self.embedding_dim = embeddings_matrix.shape[1]
            
#             # Choose FAISS index type based on configuration
#             index_type = self.config.get('faiss_index_type', 'FlatL2')
#             nlist = self.config.get('faiss_nlist', 100)  # For IVF indices
            
#             if index_type == 'FlatL2':
#                 # Exact search with L2 distance
#                 self.faiss_index = faiss.IndexFlatL2(self.embedding_dim)
                
#             elif index_type == 'FlatIP':
#                 # Exact search with inner product (cosine similarity)
#                 self.faiss_index = faiss.IndexFlatIP(self.embedding_dim)
                
#             elif index_type == 'IVFFlat':
#                 # Approximate search with IVF
#                 quantizer = faiss.IndexFlatL2(self.embedding_dim)
#                 self.faiss_index = faiss.IndexIVFFlat(quantizer, self.embedding_dim, nlist)
#                 self.faiss_index.train(embeddings_matrix)
                
#             elif index_type == 'IVFPQ':
#                 # Product quantization for memory efficiency
#                 m = self.config.get('faiss_pq_m', 8)  # Number of sub-vectors
#                 bits = self.config.get('faiss_pq_bits', 8)  # Bits per sub-vector
#                 quantizer = faiss.IndexFlatL2(self.embedding_dim)
#                 self.faiss_index = faiss.IndexIVFPQ(quantizer, self.embedding_dim, nlist, m, bits)
#                 self.faiss_index.train(embeddings_matrix)
                
#             else:
#                 self.logger.warning(f"Unknown FAISS index type: {index_type}, using FlatL2")
#                 self.faiss_index = faiss.IndexFlatL2(self.embedding_dim)
            
#             # Move to GPU if configured
#             if self.use_faiss_gpu:
#                 try:
#                     gpu_resources = faiss.StandardGpuResources()
#                     self.faiss_index = faiss.index_cpu_to_gpu(gpu_resources, self.gpu_device, self.faiss_index)
#                     self.logger.info(f"FAISS index moved to GPU device {self.gpu_device}")
#                 except Exception as e:
#                     self.logger.warning(f"Failed to move FAISS to GPU: {e}")
            
#             # Add embeddings to index
#             self.faiss_index.add(embeddings_matrix)
            
#             build_time = (time.time() - start_time) * 1000
#             self.debug_stats['faiss_build_time'] = build_time
            
#             self.logger.info(f"FAISS {index_type} index built with {len(embeddings_list)} embeddings "
#                            f"(dim={self.embedding_dim}) in {build_time:.2f}ms")
            
#         except Exception as e:
#             self.logger.error(f"Failed to build FAISS index: {e}")
#             # Fallback to empty index
#             self.faiss_index = None
            
#     def extract_embedding(self, face_roi: np.ndarray) -> Optional[np.ndarray]:
#         """Extract face embedding using DeepFace."""
#         start_time = time.time()
        
#         if (face_roi.size == 0 or face_roi.shape[0] < 50 or face_roi.shape[1] < 50 or 
#             np.max(face_roi) - np.min(face_roi) < 10):
#             return None
            
#         try:
#             if len(face_roi.shape) == 3:
#                 face_rgb = cv2.cvtColor(face_roi, cv2.COLOR_BGR2RGB)
#             else:
#                 face_rgb = cv2.cvtColor(face_roi, cv2.COLOR_GRAY2RGB)
            
#             face_rgb = face_rgb.astype(np.float32) / 255.0
            
#             embedding_obj = DeepFace.represent(
#                 face_rgb,
#                 model_name=self.config['embedding_model'],
#                 enforce_detection=False,
#                 detector_backend='skip',
#                 align=True
#             )
            
#             if embedding_obj and len(embedding_obj) > 0:
#                 embedding = np.array(embedding_obj[0]['embedding'], dtype='float32')
#                 embedding = embedding.flatten()
                
#                 # Normalize for cosine similarity if needed
#                 if self.config.get('faiss_index_type') == 'FlatIP':
#                     embedding = embedding / np.linalg.norm(embedding)
                    
#                 return embedding
                
#         except Exception as e:
#             self.logger.error(f"Embedding extraction error: {e}")
            
#         return None
        
#     def recognize_face_faiss(self, embedding: np.ndarray, k: int = 1) -> Tuple[List[str], List[float]]:
#         """
#         Recognize face using FAISS similarity search.
        
#         Args:
#             embedding: Face embedding vector
#             k: Number of nearest neighbors to return
            
#         Returns:
#             Tuple of (identities, similarities)
#         """
#         if self.faiss_index is None or embedding is None:
#             return [], []
            
#         start_time = time.time()
        
#         try:
#             # Prepare query embedding
#             query_embedding = embedding.astype('float32').reshape(1, -1)
            
#             # Normalize for cosine similarity if using FlatIP
#             if self.config.get('faiss_index_type') == 'FlatIP':
#                 query_embedding = query_embedding / np.linalg.norm(query_embedding)
            
#             # FAISS search
#             k = min(k, self.faiss_index.ntotal)
#             if k == 0:
#                 return [], []
                
#             distances, indices = self.faiss_index.search(query_embedding, k)
            
#             # Convert indices to identities and distances to similarities
#             identities = []
#             similarities = []
            
#             for i in range(k):
#                 idx = indices[0][i]
#                 if idx != -1:  # -1 indicates no result
#                     identity = self.id_to_identity.get(idx, "Unknown")
                    
#                     # Convert distance to similarity score
#                     if self.config.get('faiss_index_type') == 'FlatL2':
#                         # L2 distance: lower is better, convert to similarity (0-1)
#                         max_dist = self.config.get('faiss_max_l2_distance', 100.0)
#                         similarity = max(0, 1 - (distances[0][i] / max_dist))
#                     elif self.config.get('faiss_index_type') == 'FlatIP':
#                         # Inner product: higher is better, already normalized
#                         similarity = max(0, min(1, distances[0][i]))
#                     else:
#                         # For other indices, use cosine similarity as fallback
#                         try:
#                             centroid = self.identity_centroids.get(identity)
#                             if centroid is not None:
#                                 similarity = cosine_similarity([embedding], [centroid])[0][0]
#                             else:
#                                 similarity = 0
#                         except:
#                             similarity = 0
                    
#                     identities.append(identity)
#                     similarities.append(float(similarity))
            
#             # Update stats
#             search_time = (time.time() - start_time) * 1000
#             self.debug_stats['total_faiss_searches'] += 1
#             self.debug_stats['faiss_search_times'].append(search_time)
#             self.debug_stats['avg_faiss_search_time'] = np.mean(self.debug_stats['faiss_search_times'])
            
#             return identities, similarities
            
#         except Exception as e:
#             self.logger.error(f"FAISS search error: {e}")
#             return [], []
            
#     def recognize_face(self, embedding: np.ndarray) -> Tuple[Optional[str], float]:
#         """
#         Recognize face with thresholding (compatible with existing interface).
        
#         Args:
#             embedding: Face embedding vector
            
#         Returns:
#             Tuple of (identity, similarity) or (None, 0.0)
#         """
#         identities, similarities = self.recognize_face_faiss(embedding, k=1)
        
#         if identities and similarities:
#             best_similarity = similarities[0]
#             if best_similarity >= self.config.get('recognition_threshold', 0.8):
#                 return identities[0], best_similarity
                
#         return None, 0.0
        
#     def find_similar_faces(self, embedding: np.ndarray, k: int = 5, 
#                           threshold: float = 0.0) -> List[Tuple[str, float]]:
#         """
#         Find k most similar faces with optional threshold.
        
#         Args:
#             embedding: Query embedding
#             k: Number of results to return
#             threshold: Minimum similarity threshold
            
#         Returns:
#             List of (identity, similarity) tuples
#         """
#         identities, similarities = self.recognize_face_faiss(embedding, k=k)
        
#         results = []
#         for identity, similarity in zip(identities, similarities):
#             if similarity >= threshold:
#                 results.append((identity, similarity))
                
#         return results
        
#     def add_embedding_to_index(self, identity: str, embedding: np.ndarray):
#         """Add a new embedding to the FAISS index."""
#         if self.faiss_index is None:
#             self.logger.warning("FAISS index not initialized")
#             return False
            
#         try:
#             # Prepare embedding
#             embedding_np = embedding.astype('float32').reshape(1, -1)
            
#             # Normalize if using FlatIP
#             if self.config.get('faiss_index_type') == 'FlatIP':
#                 embedding_np = embedding_np / np.linalg.norm(embedding_np)
            
#             # Add to index
#             self.faiss_index.add(embedding_np)
            
#             # Update mappings
#             new_id = self.faiss_index.ntotal - 1
#             self.id_to_identity[new_id] = identity
#             if identity not in self.identity_to_ids:
#                 self.identity_to_ids[identity] = []
#             self.identity_to_ids[identity].append(new_id)
            
#             # Update centroid for backward compatibility
#             self.identity_centroids[identity] = embedding
            
#             self.logger.info(f"Added embedding for '{identity}' to FAISS index (ID: {new_id})")
#             return True
            
#         except Exception as e:
#             self.logger.error(f"Failed to add embedding: {e}")
#             return False
            
#     def remove_identity(self, identity: str):
#         """Remove all embeddings for an identity from the index."""
#         if identity not in self.identity_to_ids:
#             self.logger.warning(f"Identity '{identity}' not found in index")
#             return False
            
#         try:
#             # This is complex in FAISS - we need to rebuild the index
#             # For now, we'll mark as removed in our mappings
#             removed_ids = self.identity_to_ids.pop(identity, [])
#             for idx in removed_ids:
#                 self.id_to_identity.pop(idx, None)
                
#             self.identity_centroids.pop(identity, None)
            
#             self.logger.info(f"Marked identity '{identity}' for removal (requires index rebuild)")
#             return True
            
#         except Exception as e:
#             self.logger.error(f"Failed to remove identity: {e}")
#             return False
            
#     def rebuild_index(self):
#         """Rebuild FAISS index from current embeddings."""
#         self.logger.info("Rebuilding FAISS index...")
        
#         # Save current mappings
#         old_id_to_identity = self.id_to_identity.copy()
#         old_identity_to_ids = self.identity_to_ids.copy()
#         old_centroids = self.identity_centroids.copy()
        
#         try:
#             # Clear and rebuild
#             self.faiss_index = None
#             self.id_to_identity = {}
#             self.identity_to_ids = {}
#             self.identity_centroids = {}
            
#             # Re-add embeddings
#             for identity, centroid in old_centroids.items():
#                 self.identity_centroids[identity] = centroid
                
#             self._build_faiss_index()
#             self.logger.info("FAISS index rebuilt successfully")
#             return True
            
#         except Exception as e:
#             # Restore old state
#             self.faiss_index = None
#             self.id_to_identity = old_id_to_identity
#             self.identity_to_ids = old_identity_to_ids
#             self.identity_centroids = old_centroids
#             self.logger.error(f"Failed to rebuild index: {e}")
#             return False
            
#     def detect_faces(self, frame: np.ndarray) -> List[Dict]:
#         """Detect faces using YOLO (for compatibility)."""
#         start_time = time.time()
        
#         try:
#             if self.config.get('use_gpu', False):
#                 device = self.config.get('gpu_device', 0)
#                 device_str = f'cuda:{device}'
#             else:
#                 device_str = 'cpu'
                
#             results = self.detection_model(
#                 frame, 
#                 conf=self.config['detection_confidence'],
#                 iou=self.config['detection_iou'],
#                 verbose=False,
#                 device=device_str
#             )
            
#             detections = []
#             for result in results:
#                 boxes = result.boxes
#                 if boxes is not None:
#                     for box in boxes:
#                         x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
#                         confidence = box.conf[0].cpu().numpy()
                        
#                         detections.append({
#                             'bbox': [int(x1), int(y1), int(x2), int(y2)],
#                             'confidence': float(confidence)
#                         })
                        
#             return detections
            
#         except Exception as e:
#             self.logger.error(f"Detection error: {e}")
#             return []
            
#     def process_frame(self, frame: np.ndarray) -> List[Dict]:
#         """
#         Process frame: detect faces, extract embeddings, recognize.
        
#         Returns list of detection results with FAISS recognition.
#         """
#         results = []
        
#         # Detect faces
#         detections = self.detect_faces(frame)
        
#         for detection in detections:
#             x1, y1, x2, y2 = detection['bbox']
            
#             padding = self.config.get('roi_padding', 20)
#             h, w = frame.shape[:2]
#             x1_pad = max(0, x1 - padding)
#             y1_pad = max(0, y1 - padding)
#             x2_pad = min(w, x2 + padding)
#             y2_pad = min(h, y2 + padding)
            
#             face_roi = frame[y1_pad:y2_pad, x1_pad:x2_pad]
            
#             if (face_roi.size == 0 or face_roi.shape[0] < 40 or face_roi.shape[1] < 40 or
#                 np.std(face_roi) < 10):
#                 continue
                
#             # Extract embedding
#             embedding = self.extract_embedding(face_roi)
#             if embedding is None:
#                 continue
                
#             # Recognize with FAISS
#             identity, confidence = self.recognize_face(embedding)
            
#             # Find similar faces for debugging
#             similar_faces = []
#             if self.config.get('debug', {}).get('show_similar', False):
#                 similar_faces = self.find_similar_faces(embedding, k=3, threshold=0.5)
            
#             results.append({
#                 'bbox': detection['bbox'],
#                 'detection_confidence': detection['confidence'],
#                 'identity': identity,
#                 'recognition_confidence': confidence,
#                 'embedding': embedding.tolist(),
#                 'similar_faces': similar_faces
#             })
            
#         return results
        
#     def get_faiss_stats(self) -> Dict:
#         """Get FAISS-specific statistics."""
#         stats = {
#             'faiss_index_type': self.config.get('faiss_index_type', 'FlatL2'),
#             'use_faiss_gpu': self.use_faiss_gpu,
#             'embedding_dim': self.embedding_dim,
#             'total_embeddings': self.faiss_index.ntotal if self.faiss_index else 0,
#             'unique_identities': len(self.identity_to_ids),
#             'total_faiss_searches': self.debug_stats['total_faiss_searches'],
#             'avg_faiss_search_time_ms': self.debug_stats['avg_faiss_search_time'],
#             'faiss_build_time_ms': self.debug_stats['faiss_build_time']
#         }
        
#         if self.faiss_index:
#             stats['index_size_mb'] = self.faiss_index.get_index_size() / (1024 * 1024) if hasattr(self.faiss_index, 'get_index_size') else 0
            
#         return stats
        
#     def get_debug_stats(self) -> Dict:
#         """Get comprehensive debug statistics."""
#         stats = self.debug_stats.copy()
        
#         # Add FAISS stats
#         faiss_stats = self.get_faiss_stats()
#         stats.update(faiss_stats)
        
#         # Calculate search time percentiles
#         if stats['faiss_search_times']:
#             stats['p95_faiss_search_time'] = np.percentile(stats['faiss_search_times'], 95)
#             stats['max_faiss_search_time'] = np.max(stats['faiss_search_times'])
            
#         return stats
        
#     def get_known_identities(self) -> List[str]:
#         """Get list of all known identities."""
#         return list(self.identity_to_ids.keys())
        
#     def save_index(self, filepath: str):
#         """Save FAISS index to disk."""
#         if self.faiss_index is None:
#             self.logger.warning("No FAISS index to save")
#             return False
            
#         try:
#             # Save FAISS index
#             faiss.write_index(self.faiss_index, filepath)
            
#             # Save metadata
#             metadata_file = filepath.replace('.index', '_metadata.json')
#             metadata = {
#                 'id_to_identity': self.id_to_identity,
#                 'identity_to_ids': self.identity_to_ids,
#                 'identity_centroids': {k: v.tolist() for k, v in self.identity_centroids.items()},
#                 'embedding_dim': self.embedding_dim,
#                 'config': self.config
#             }
            
#             with open(metadata_file, 'w') as f:
#                 json.dump(metadata, f)
                
#             self.logger.info(f"FAISS index saved to {filepath}")
#             return True
            
#         except Exception as e:
#             self.logger.error(f"Failed to save FAISS index: {e}")
#             return False
            
#     def load_index(self, filepath: str):
#         """Load FAISS index from disk."""
#         try:
#             # Load FAISS index
#             self.faiss_index = faiss.read_index(filepath)
            
#             # Load metadata
#             metadata_file = filepath.replace('.index', '_metadata.json')
#             with open(metadata_file, 'r') as f:
#                 metadata = json.load(f)
                
#             self.id_to_identity = metadata['id_to_identity']
#             self.identity_to_ids = metadata['identity_to_ids']
#             self.identity_centroids = {k: np.array(v) for k, v in metadata['identity_centroids'].items()}
#             self.embedding_dim = metadata['embedding_dim']
            
#             # Convert string keys back to integers
#             self.id_to_identity = {int(k): v for k, v in self.id_to_identity.items()}
            
#             self.logger.info(f"FAISS index loaded from {filepath} with {self.faiss_index.ntotal} embeddings")
#             return True
            
#         except Exception as e:
#             self.logger.error(f"Failed to load FAISS index: {e}")
#             return False
