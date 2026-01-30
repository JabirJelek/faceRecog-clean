# recognition/voyager_system.py
import json
from pathlib import Path
from ultralytics import YOLO
import numpy as np
from collections import deque
from typing import Dict, Tuple, Optional
import time
import torch
import torch.nn.functional as F
from voyager import Index, Space
from .base_system import FaceRecognitionSystem

class VoyagerFaceRecognitionSystem(FaceRecognitionSystem):
    def __init__(self, config: Dict):
        # Initialize GPU device FIRST
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"🎯 Using device: {self.device}")
        
        # Initialize Voyager-specific attributes
        self.voyager_index = None
        self.voyager_id_to_identity = {}
        self.identity_to_voyager_id = {}
        self.next_voyager_id = 0
        self.voyager_performance_monitor = VoyagerPerformanceMonitor()
        
        # GPU-optimized tensor storage for centroids
        self.identity_centroids_tensor = None
        self.identity_names_list = []
        
        # Now call parent constructor
        super().__init__(config)
        
    def _load_embeddings_database(self):
        """Load embeddings into Voyager index with GPU optimization"""
        try:
            db_path = Path(self.config['embeddings_db_path'])
            if not db_path.exists():
                print("⚠️  Embeddings database not found, starting fresh")
                self.embeddings_db = {"persons": {}, "metadata": {}}
                # Initialize empty Voyager index for future additions
                self._initialize_voyager_index(512)  # Default dimension
                return
                
            with open(db_path, 'r') as f:
                self.embeddings_db = json.load(f)
                
            if "persons" in self.embeddings_db:
                # First, determine embedding dimension from the data
                embedding_dim = self._get_embedding_dimension_from_data()
                print(f"🔍 Detected embedding dimension: {embedding_dim}")
                
                # Initialize Voyager index with correct dimension
                self._initialize_voyager_index(embedding_dim)
                
                vectors = []
                voyager_ids = []
                identities = []
                centroid_tensors = []
                
                for person_id, person_data in self.embeddings_db["persons"].items():
                    display_name = person_data["display_name"]
                    
                    # Extract centroid embedding from your database structure
                    if "centroid_embedding" in person_data and person_data["centroid_embedding"]:
                        centroid = np.array(person_data["centroid_embedding"])
                    else:
                        # Fallback: use first embedding if no centroid
                        if (person_data.get("embeddings") and 
                            len(person_data["embeddings"]) > 0 and
                            "vector" in person_data["embeddings"][0]):
                            centroid = np.array(person_data["embeddings"][0]["vector"])
                            print(f"⚠️  Using first embedding as centroid for {display_name}")
                        else:
                            print(f"❌ No embeddings found for {display_name}, skipping")
                            continue
                    
                    # Store mapping and prepare for batch addition
                    voyager_id = self.next_voyager_id
                    self.voyager_id_to_identity[voyager_id] = display_name
                    self.identity_to_voyager_id[display_name] = voyager_id
                    self.identity_centroids[display_name] = centroid  # Keep for compatibility
                    
                    vectors.append(centroid)
                    voyager_ids.append(voyager_id)
                    identities.append(display_name)
                    
                    # Create GPU tensor for this centroid
                    centroid_tensor = torch.from_numpy(centroid).to(self.device).float()
                    centroid_tensors.append(centroid_tensor)
                    
                    self.next_voyager_id += 1
                
                # Batch add to Voyager for better performance
                if vectors:
                    vectors_array = np.array(vectors)
                    self.voyager_index.add_items(vectors_array, voyager_ids)
                    
                    # Create GPU tensor for all centroids
                    if centroid_tensors:
                        self.identity_centroids_tensor = torch.stack(centroid_tensors)
                        self.identity_names_list = identities
                    
                    print(f"✅ Loaded {len(vectors)} identities into Voyager index")
                    print(f"✅ Pre-loaded {len(centroid_tensors)} centroids to GPU memory")
                    
                    # Get the correct item count attribute
                    item_count = self._get_voyager_item_count()
                    print(f"📊 Voyager index size: {item_count} items")
                    
                    # Test query to verify index is working
                    if len(vectors) > 0:
                        try:
                            test_neighbors, test_distances = self.voyager_index.query(vectors[0], k=1)
                            if test_neighbors and len(test_neighbors) > 0:
                                print(f"🧪 Voyager test query successful: {len(test_neighbors)} results")
                        except Exception as e:
                            print(f"⚠️  Voyager test query failed: {e}")
                
                print(f"✅ Loaded {len(self.voyager_id_to_identity)} identities from database")
                print(f"📊 Available persons: {list(self.voyager_id_to_identity.values())}")
                
            else:
                print("⚠️  No 'persons' key found in JSON database")
                self._initialize_voyager_index(512)  # Default dimension
                
        except Exception as e:
            print(f"❌ Failed to load embeddings database: {e}")
            import traceback
            traceback.print_exc()
            # Initialize empty index anyway
            self._initialize_voyager_index(512)

    def _get_embedding_dimension_from_data(self) -> int:
        """Determine embedding dimension from the actual data"""
        try:
            # Look at the first person's centroid to determine dimension
            first_person = next(iter(self.embeddings_db["persons"].values()))
            
            if "centroid_embedding" in first_person and first_person["centroid_embedding"]:
                return len(first_person["centroid_embedding"])
            elif (first_person.get("embeddings") and 
                  len(first_person["embeddings"]) > 0 and
                  "vector" in first_person["embeddings"][0]):
                return len(first_person["embeddings"][0]["vector"])
            else:
                # Check embedding_length field
                if first_person.get("embeddings") and len(first_person["embeddings"]) > 0:
                    return first_person["embeddings"][0].get("embedding_length", 512)
        except Exception as e:
            print(f"⚠️  Could not determine embedding dimension from data: {e}")
        
        # Fallback to model-based dimension
        return self._get_embedding_dimension_from_model()

    def _get_embedding_dimension_from_model(self) -> int:
        """Determine embedding dimension based on model (fallback)"""
        model_dimensions = {
            'Facenet': 128,      # Based on your data, Facenet uses 128
            'VGGFace': 4096,     # VGGFace uses 4096
            'OpenFace': 128,     # OpenFace uses 128
            'Facenet512': 512,   # Facenet512 uses 512
            'DeepFace': 4096,    # DeepFace default (VGGFace)
        }
        model = self.config.get('embedding_model', 'Facenet512')
        dimension = model_dimensions.get(model, 512)  # Default to 128 based on your data
        print(f"🔍 Using model-based dimension {dimension} for {model}")
        return dimension

    def _initialize_voyager_index(self, dimension: int):
        """Initialize Voyager index with specific dimension"""
        print(f"🔧 Initializing Voyager index with dimension {dimension}")
        
        try:
            # Use cosine similarity as it matches your current approach
            self.voyager_index = Index(Space.Cosine, num_dimensions=dimension)
            print("🎯 Voyager index initialized with auto-tuning")
        except Exception as e:
            print(f"❌ Failed to initialize Voyager index: {e}")
            self.voyager_index = None

    def _get_voyager_item_count(self) -> int:
        """Safely get the number of items in Voyager index"""
        if self.voyager_index is None:
            return 0
        
        # Try different possible attribute names for item count
        try:
            if hasattr(self.voyager_index, 'get_n_items'):
                return self.voyager_index.get_n_items()
            elif hasattr(self.voyager_index, 'num_items'):
                return self.voyager_index.num_items
            elif hasattr(self.voyager_index, 'n_items'):
                return self.voyager_index.n_items
            else:
                # If we can't determine, return the count from our mapping
                return len(self.voyager_id_to_identity)
        except Exception as e:
            print(f"⚠️  Could not get Voyager item count: {e}")
            return len(self.voyager_id_to_identity)

    def recognize_face(self, embedding: np.ndarray) -> Tuple[Optional[str], float]:
        """Enhanced recognition using Voyager's approximate nearest neighbor search"""
        start_time = time.time()
        
        # Use Voyager if available and configured
        if (self.voyager_index is not None and 
            self._get_voyager_item_count() > 0 and
            self.config.get('use_voyager', True)):
            
            result = self._recognize_with_voyager(embedding, start_time)
            if result[0] is not None:  # If Voyager found a match
                return result
            # If Voyager didn't find a match, fall through to original method
        
        # Fallback to GPU-optimized recognition method
        result = self._recognize_face_gpu_optimized(embedding, start_time)
        self.voyager_performance_monitor.record_voyager_performance(
            start_time, success=False, used_fallback=True
        )
        return result

    def _recognize_with_voyager(self, embedding: np.ndarray, start_time: float) -> Tuple[Optional[str], float]:
        """Recognition using Voyager index"""
        try:
            # Ensure embedding is the right shape and type
            embedding = embedding.flatten().astype(np.float32)
            
            # Query Voyager for nearest neighbors - use adaptive k based on index size
            item_count = self._get_voyager_item_count()
            k = min(5, item_count)
            
            neighbors, distances = self.voyager_index.query(embedding, k=k)
            
            if len(neighbors) == 0 or len(distances) == 0:
                return None, 0.0
            
            # Convert Voyager distance to similarity score 
            # Voyager Cosine space: distance = 1 - cosine_similarity
            best_similarity = 1.0 - distances[0]
            best_voyager_id = neighbors[0]
            
            threshold = self.config['recognition_threshold']
            
            if best_similarity >= threshold:
                identity = self.voyager_id_to_identity.get(best_voyager_id)
                
                # Record successful Voyager query
                self.voyager_performance_monitor.record_voyager_performance(
                    start_time, success=True, used_fallback=False
                )
                
                if self.config.get('verbose_voyager', False):
                    print(f"🎯 Voyager matched: {identity} (similarity: {best_similarity:.3f})")
                
                return identity, best_similarity
            
            # No match above threshold
            self.voyager_performance_monitor.record_voyager_performance(
                start_time, success=False, used_fallback=False
            )
            return None, best_similarity
            
        except Exception as e:
            print(f"❌ Voyager recognition error: {e}")
            self.voyager_performance_monitor.record_voyager_performance(
                start_time, success=False, used_fallback=True
            )
            return None, 0.0

    def _recognize_face_gpu_optimized(self, embedding: np.ndarray, start_time: float) -> Tuple[Optional[str], float]:
        """GPU-optimized recognition method using PyTorch on GTX 1650 Ti"""
        if not self.identity_centroids or self.identity_centroids_tensor is None:
            return None, 0.0
        
        # Move embedding to GPU and ensure proper shape/type
        embedding_tensor = torch.from_numpy(embedding).to(self.device).float().flatten()
        
        # Use pre-loaded centroids tensor on GPU
        centroids_tensor = self.identity_centroids_tensor
        
        # Calculate cosine similarity on GPU (highly parallel)
        with torch.no_grad():
            # Normalize vectors for cosine similarity
            embedding_norm = F.normalize(embedding_tensor, p=2, dim=0)
            centroids_norm = F.normalize(centroids_tensor, p=2, dim=1)
            
            # Matrix multiplication for batch cosine similarity
            cosine_similarities = torch.mm(centroids_norm, embedding_norm.unsqueeze(1)).squeeze()
            
            # Find the best match
            best_similarity, best_index = torch.max(cosine_similarities, dim=0)
            best_similarity = best_similarity.item()
        
        # Get identity name from pre-loaded list
        best_identity = None
        if best_similarity >= self.config['recognition_threshold']:
            best_identity = self.identity_names_list[best_index]
        
        recognition_time = (time.time() - start_time) * 1000
        self.debug_stats['recognition_times'].append(recognition_time)
        
        return best_identity, best_similarity

    def _recognize_face_original(self, embedding: np.ndarray, start_time: float) -> Tuple[Optional[str], float]:
        """Original recognition method kept for compatibility - now uses GPU optimization"""
        return self._recognize_face_gpu_optimized(embedding, start_time)

    def add_identity_to_voyager(self, identity: str, embedding: np.ndarray):
        """Add new identity to Voyager index with GPU optimization"""
        if self.voyager_index is None:
            # Initialize with the dimension of the new embedding
            dimension = len(embedding.flatten())
            self._initialize_voyager_index(dimension)
        
        # Check if identity already exists
        if identity in self.identity_to_voyager_id:
            voyager_id = self.identity_to_voyager_id[identity]
            print(f"🔄 Updating existing identity '{identity}' in Voyager index")
            
            # Update GPU tensor
            if self.identity_centroids_tensor is not None:
                index = self.identity_names_list.index(identity)
                new_centroid_tensor = torch.from_numpy(embedding).to(self.device).float()
                self.identity_centroids_tensor[index] = new_centroid_tensor
        else:
            voyager_id = self.next_voyager_id
            self.next_voyager_id += 1
            
            # Add to GPU tensor
            new_centroid_tensor = torch.from_numpy(embedding).to(self.device).float()
            if self.identity_centroids_tensor is None:
                self.identity_centroids_tensor = new_centroid_tensor.unsqueeze(0)
                self.identity_names_list = [identity]
            else:
                self.identity_centroids_tensor = torch.cat([
                    self.identity_centroids_tensor, 
                    new_centroid_tensor.unsqueeze(0)
                ])
                self.identity_names_list.append(identity)
        
        # Update mappings
        self.voyager_id_to_identity[voyager_id] = identity
        self.identity_to_voyager_id[identity] = voyager_id
        self.identity_centroids[identity] = embedding  # Maintain compatibility
        
        # Add to Voyager index
        embedding_flat = embedding.flatten().astype(np.float32)
        self.voyager_index.add_items(np.array([embedding_flat]), [voyager_id])
        
        item_count = self._get_voyager_item_count()
        print(f"✅ Added/updated identity '{identity}' in Voyager index (ID: {voyager_id})")
        print(f"📊 Voyager index now contains {item_count} items")
        print(f"🎯 GPU tensor now contains {len(self.identity_names_list)} centroids")

    def get_voyager_stats(self) -> Dict:
        """Get Voyager performance statistics"""
        stats = self.voyager_performance_monitor.get_voyager_stats()
        item_count = self._get_voyager_item_count()
        
        # Add GPU memory info if available
        gpu_info = {}
        if torch.cuda.is_available():
            gpu_info = {
                'gpu_memory_allocated': torch.cuda.memory_allocated() / 1024**2,  # MB
                'gpu_memory_cached': torch.cuda.memory_cached() / 1024**2,  # MB
                'gpu_centroids_loaded': len(self.identity_names_list) if self.identity_names_list else 0
            }
        
        stats.update({
            'voyager_index_size': item_count,
            'total_identities': len(self.voyager_id_to_identity),
            'index_initialized': self.voyager_index is not None,
            **gpu_info
        })
        return stats

    def print_voyager_status(self):
        """Print Voyager system status with GPU info"""
        stats = self.get_voyager_stats()
        print("\n" + "="*50)
        print("🛰️  VOYAGER VECTOR SEARCH STATUS")
        print("="*50)
        print(f"Index Initialized: {stats['index_initialized']}")
        print(f"Index Size: {stats['voyager_index_size']} items")
        print(f"Total Identities: {stats['total_identities']}")
        print(f"GPU Centroids Loaded: {stats.get('gpu_centroids_loaded', 0)}")
        
        if torch.cuda.is_available():
            print(f"GPU Memory Used: {stats.get('gpu_memory_allocated', 0):.1f} MB")
            print(f"GPU Memory Cached: {stats.get('gpu_memory_cached', 0):.1f} MB")
        
        print(f"Total Queries: {stats['total_queries']}")
        if stats['total_queries'] > 0:
            print(f"Average Query Time: {stats['avg_query_time']:.2f}ms")
            print(f"Fallback Rate: {(stats['fallback_count']/stats['total_queries'])*100:.1f}%")
            print(f"Success Rate: {stats['recall_rate']*100:.1f}%")
        else:
            print("Average Query Time: N/A")
            print("Fallback Rate: N/A")
            print("Success Rate: N/A")
        print("="*50)
                       
class VoyagerPerformanceMonitor:
    def __init__(self):
        self.recognition_times = deque(maxlen=100)
        self.voyager_stats = {
            'total_queries': 0,
            'successful_queries': 0,
            'avg_query_time': 0.0,
            'recall_rate': 0.0,
            'fallback_count': 0
        }
    
    def record_voyager_performance(self, start_time: float, success: bool, used_fallback: bool = False):
        query_time = (time.time() - start_time) * 1000
        self.recognition_times.append(query_time)
        
        self.voyager_stats['total_queries'] += 1
        
        if success:
            self.voyager_stats['successful_queries'] += 1
        
        if used_fallback:
            self.voyager_stats['fallback_count'] += 1
        
        # Update averages
        if self.recognition_times:
            self.voyager_stats['avg_query_time'] = np.mean(self.recognition_times)
        
        # Update recall rate
        if self.voyager_stats['total_queries'] > 0:
            self.voyager_stats['recall_rate'] = (
                self.voyager_stats['successful_queries'] / 
                self.voyager_stats['total_queries']
            )

    def get_voyager_stats(self) -> Dict:
        return self.voyager_stats.copy()