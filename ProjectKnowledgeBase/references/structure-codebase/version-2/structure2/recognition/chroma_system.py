# recognition/chroma_system.py
import chromadb
from chromadb.config import Settings
import numpy as np
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import logging
from .base_system import FaceRecognitionSystem

class ChromaFaceRecognitionSystem(FaceRecognitionSystem):
    """
    Extended Face Recognition System with ChromaDB integration for scalable embedding storage.
    """
    
    def __init__(self, config: Dict):
        # Initialize parent class
        super().__init__(config)
        
        # ChromaDB specific configuration
        self.chroma_config = config.get('chromadb', {})
        
        # Initialize ChromaDB
        self.chroma_client = None
        self.face_collection = None
        self.person_collection = None
        
        self._init_chromadb()
        
    def _init_chromadb(self):
        """Initialize ChromaDB client and collections"""
        try:
            # Get ChromaDB configuration
            persist_directory = self.chroma_config.get(
                'persist_directory', 
                r'C:\raihan\dokumen\project\global-env\faceRecog\run_py\modular\0_dataset\chroma_db'
            )
            
            # Create directory if it doesn't exist
            persist_path = Path(persist_directory)
            persist_path.mkdir(parents=True, exist_ok=True)
            
            # Initialize client (persistent or in-memory)
            if self.chroma_config.get('persistent', True):
                self.chroma_client = chromadb.PersistentClient(
                    path=str(persist_path),
                    settings=Settings(
                        anonymized_telemetry=False,
                        allow_reset=True
                    )
                )
                self.logger.info(f"ChromaDB persistent client initialized at: {persist_path}")
            else:
                self.chroma_client = chromadb.Client()
                self.logger.info("ChromaDB in-memory client initialized")
            
            # Create or get collections
            self._setup_collections()
            
            # Log existing data
            face_count = self.face_collection.count() if self.face_collection else 0
            person_count = self.person_collection.count() if self.person_collection else 0
            self.logger.info(f"ChromaDB initialized with {face_count} faces and {person_count} persons")
            
            # Migrate existing data if needed
            if self.chroma_config.get('migrate_existing', False):
                self._migrate_existing_embeddings()
                
        except Exception as e:
            self.logger.error(f"Failed to initialize ChromaDB: {e}")
            # Fall back to parent class behavior
            self.chroma_client = None
            self.face_collection = None
            self.person_collection = None
            
    def _setup_collections(self):
        """Setup ChromaDB collections for faces and persons"""
        try:
            # Collection for individual face embeddings
            self.face_collection = self.chroma_client.get_or_create_collection(
                name="face_embeddings",
                metadata={
                    "description": "Individual face embeddings with metadata",
                    "created": datetime.now().isoformat(),
                    "embedding_model": self.config['embedding_model']
                },
                embedding_function=None  # We provide our own embeddings
            )
            
            # Collection for person centroids/aggregated data
            self.person_collection = self.chroma_client.get_or_create_collection(
                name="person_profiles",
                metadata={
                    "description": "Person profiles with aggregated embeddings",
                    "created": datetime.now().isoformat()
                }
            )
            
            self.logger.info("ChromaDB collections initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to setup collections: {e}")
            raise
    
    def _migrate_existing_embeddings(self):
        """Migrate existing JSON embeddings to ChromaDB"""
        try:
            if not self.embeddings_db or "persons" not in self.embeddings_db:
                return
                
            migrated_count = 0
            for person_id, person_data in self.embeddings_db["persons"].items():
                display_name = person_data["display_name"]
                
                # Check if centroid exists and is valid
                if "centroid_embedding" in person_data and person_data["centroid_embedding"]:
                    centroid = np.array(person_data["centroid_embedding"])
                    
                    # Add person profile with centroid
                    self.add_person_profile(
                        display_name=display_name,
                        centroid_embedding=centroid.tolist(),
                        metadata={
                            "original_person_id": person_id,
                            "folder_name": person_data.get("folder_name", ""),
                            "total_images": person_data.get("total_images", 0),
                            "successful_embeddings": person_data.get("successful_embeddings", 0)
                        },
                        source="migrated"
                    )
                
                # Add individual embeddings if available
                if "embeddings" in person_data and person_data["embeddings"]:
                    for i, embedding in enumerate(person_data["embeddings"]):
                        # Ensure embedding is a numpy array
                        if isinstance(embedding, list):
                            embedding_array = np.array(embedding)
                        elif isinstance(embedding, np.ndarray):
                            embedding_array = embedding
                        else:
                            continue  # Skip invalid embeddings
                        
                        # Add individual face embedding
                        self.add_face_embedding(
                            embedding=embedding_array,
                            person_name=display_name,
                            metadata={
                                "migrated": True,
                                "original_person_id": person_id,
                                "embedding_index": i,
                                "folder_name": person_data.get("folder_name", "")
                            }
                        )
                        migrated_count += 1
            
            self.logger.info(f"Migrated {migrated_count} embeddings to ChromaDB")
            
        except Exception as e:
            self.logger.error(f"Migration failed: {e}")
            
    def add_person_profile(self, display_name: str, centroid_embedding: List[float], 
                          metadata: Dict = None, source: str = "manual"):
        """Add or update a person's profile (centroid) in ChromaDB"""
        try:
            # Prepare metadata - FIXED SYNTAX
            base_metadata = {
                "display_name": display_name,
                "source": source,
                "created": datetime.now().isoformat(),
                "embedding_dimension": len(centroid_embedding)
            }
            
            # Merge with additional metadata if provided
            if metadata:
                base_metadata.update(metadata)
            
            # Generate a deterministic ID
            person_id = f"person_{display_name.replace(' ', '_').lower()}"
            
            # Add to person collection
            self.person_collection.upsert(
                ids=[person_id],
                embeddings=[centroid_embedding],
                metadatas=[base_metadata]
            )
            
            # Update in-memory cache for backward compatibility
            self.identity_centroids[display_name] = np.array(centroid_embedding)
            
            self.logger.info(f"Added/updated person profile: {display_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add person profile: {e}")
            return False
        
    def add_face_embedding(self, embedding, person_name: str, 
                        metadata: Dict = None) -> str:
        """Add a face embedding to ChromaDB with associated metadata"""
        try:
            # Ensure embedding is a numpy array
            if isinstance(embedding, list):
                embedding_array = np.array(embedding)
            elif isinstance(embedding, np.ndarray):
                embedding_array = embedding
            else:
                raise ValueError(f"Embedding must be list or numpy array, got {type(embedding)}")
            
            # Validate embedding shape
            if embedding_array.ndim != 1:
                if embedding_array.ndim == 2 and embedding_array.shape[0] == 1:
                    embedding_array = embedding_array.flatten()
                else:
                    raise ValueError(f"Invalid embedding shape: {embedding_array.shape}")
            
            # Generate unique ID
            embedding_id = f"face_{uuid.uuid4().hex[:12]}"
            
            # Prepare metadata
            face_metadata = {
                "person_name": person_name,
                "timestamp": datetime.now().isoformat(),
                "added_via": "recognition_pipeline",
                "embedding_dimension": len(embedding_array)
            }
            
            # Add additional metadata if provided
            if metadata:
                face_metadata.update(metadata)
            
            # Add to face collection
            self.face_collection.add(
                ids=[embedding_id],
                embeddings=[embedding_array.tolist()],  # Now it's safe to call tolist()
                metadatas=[face_metadata]
            )
            
            # Optionally update person centroid
            self._update_person_centroid(person_name, embedding_array)
            
            return embedding_id
            
        except Exception as e:
            self.logger.error(f"Failed to add face embedding: {e}")
            return None
            
    def _update_person_centroid(self, person_name: str, new_embedding: np.ndarray):
        """Update person's centroid embedding based on new face data"""
        try:
            # Query existing embeddings for this person
            results = self.face_collection.get(
                where={"person_name": person_name},
                include=["embeddings"]
            )
            
            if results["embeddings"]:
                # Calculate new centroid (average of all embeddings)
                all_embeddings = np.array(results["embeddings"])
                new_embeddings = np.vstack([all_embeddings, new_embedding])
                new_centroid = np.mean(new_embeddings, axis=0).tolist()
                
                # Update person profile
                self.add_person_profile(
                    display_name=person_name,
                    centroid_embedding=new_centroid,
                    metadata={"sample_count": len(new_embeddings)},
                    source="auto_updated"
                )
                
        except Exception as e:
            self.logger.warning(f"Could not update person centroid: {e}")
    
    def recognize_face_chroma(self, embedding: np.ndarray) -> Tuple[Optional[str], float, Dict]:
        """
        Recognize face using ChromaDB query (enhanced version).
        Returns: (identity, confidence, match_details)
        """
        try:
            # Query ChromaDB for similar embeddings
            results = self.face_collection.query(
                query_embeddings=[embedding.tolist()],
                n_results=5,  # Get top 5 matches
                include=["metadatas", "distances"]
            )
            
            if not results["ids"][0]:
                return None, 0.0, {}
            
            # Get the best match
            best_distance = results["distances"][0][0]
            best_confidence = 1 - best_distance  # Convert distance to similarity
            best_metadata = results["metadatas"][0][0] if results["metadatas"][0] else {}
            person_name = best_metadata.get("person_name")
            
            # Apply threshold
            if best_confidence >= self.config['recognition_threshold']:
                return person_name, best_confidence, {
                    "match_id": results["ids"][0][0],
                    "distance": best_distance,
                    "all_matches": [
                        {
                            "person": results["metadatas"][0][i].get("person_name"),
                            "confidence": 1 - results["distances"][0][i]
                        }
                        for i in range(len(results["ids"][0]))
                    ]
                }
            else:
                return None, best_confidence, {}
                
        except Exception as e:
            self.logger.error(f"ChromaDB recognition failed: {e}")
            # Fall back to parent method
            identity, confidence = super().recognize_face(embedding)
            return identity, confidence, {}
    
    def process_frame_chroma(self, frame: np.ndarray) -> List[Dict]:
        """
        Enhanced frame processing with ChromaDB integration.
        Stores embeddings in ChromaDB and uses it for recognition.
        """
        results = []
        
        # Get detections from parent class
        detections = self.detect_faces(frame)
        
        for detection in detections:
            x1, y1, x2, y2 = detection['bbox']
            
            # Extract face ROI
            padding = self.config.get('roi_padding', 20)
            h, w = frame.shape[:2]
            x1_pad = max(0, x1 - padding)
            y1_pad = max(0, y1 - padding)
            x2_pad = min(w, x2 + padding)
            y2_pad = min(h, y2 + padding)
            
            face_roi = frame[y1_pad:y2_pad, x1_pad:x2_pad]
            
            # Skip invalid ROIs
            if face_roi.size == 0 or face_roi.shape[0] < 40 or face_roi.shape[1] < 40:
                continue
            
            # Mask detection
            mask_status, mask_confidence = self.detect_mask(face_roi)
            
            # Extract embedding
            embedding = self.extract_embedding(face_roi)
            if embedding is None:
                continue
            
            # Recognize using ChromaDB
            identity, recognition_confidence, match_details = self.recognize_face_chroma(embedding)
            
            # Store embedding in ChromaDB if configured
            if self.chroma_config.get('store_all_faces', False):
                embedding_id = self.add_face_embedding(
                    embedding=embedding,
                    person_name=identity if identity else "unknown",
                    metadata={
                        "bbox": detection['bbox'],
                        "mask_status": mask_status,
                        "mask_confidence": mask_confidence,
                        "recognition_confidence": recognition_confidence,
                        "frame_timestamp": datetime.now().isoformat()
                    }
                )
            else:
                embedding_id = None
            
            # Add unknown faces to review collection
            if (not identity and 
                self.chroma_config.get('store_unknown_faces', True) and
                recognition_confidence < self.config.get('unknown_threshold', 0.3)):
                
                self._store_unknown_face(embedding, face_roi, detection['bbox'])
            
            results.append({
                'bbox': detection['bbox'],
                'detection_confidence': detection['confidence'],
                'mask_status': mask_status,
                'mask_confidence': mask_confidence,
                'identity': identity,
                'recognition_confidence': recognition_confidence,
                'embedding': embedding.tolist(),
                'chroma_embedding_id': embedding_id,
                'match_details': match_details
            })
        
        # Update stats
        self.debug_stats['total_frames_processed'] += 1
        self.debug_stats['total_faces_detected'] += len(detections)
        self.debug_stats['total_faces_recognized'] += len([r for r in results if r['identity']])
        
        return results
    
    def _store_unknown_face(self, embedding: np.ndarray, face_roi: np.ndarray, bbox: List[int]):
        """Store unknown faces for later review/clustering"""
        try:
            # Create a collection for unknown faces if it doesn't exist
            unknown_collection = self.chroma_client.get_or_create_collection(
                name="unknown_faces",
                metadata={"description": "Unknown faces for review"}
            )
            
            embedding_id = f"unknown_{uuid.uuid4().hex[:8]}"
            
            unknown_collection.add(
                ids=[embedding_id],
                embeddings=[embedding.tolist()],
                metadatas=[{
                    "timestamp": datetime.now().isoformat(),
                    "bbox": bbox,
                    "status": "unreviewed",
                    "image_size": face_roi.shape[:2]
                }]
            )
            
            self.logger.debug(f"Stored unknown face: {embedding_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to store unknown face: {e}")
    
    def find_similar_faces(self, embedding: np.ndarray, n_results: int = 10, 
                          threshold: float = 0.7) -> List[Dict]:
        """Find similar faces across all collections"""
        try:
            # Search in known faces
            known_results = self.face_collection.query(
                query_embeddings=[embedding.tolist()],
                n_results=n_results,
                include=["metadatas", "distances"]
            )
            
            # Filter by threshold
            similar_faces = []
            for i in range(len(known_results["ids"][0])):
                distance = known_results["distances"][0][i]
                confidence = 1 - distance
                
                if confidence >= threshold:
                    similar_faces.append({
                        "id": known_results["ids"][0][i],
                        "person": known_results["metadatas"][0][i].get("person_name"),
                        "confidence": confidence,
                        "distance": distance,
                        "metadata": known_results["metadatas"][0][i],
                        "type": "known"
                    })
            
            return similar_faces
            
        except Exception as e:
            self.logger.error(f"Find similar faces failed: {e}")
            return []
    
    def cluster_unknown_faces(self, threshold: float = 0.8) -> Dict:
        """Cluster unknown faces to identify potential new persons"""
        try:
            unknown_collection = self.chroma_client.get_or_create_collection("unknown_faces")
            
            # Get all unknown faces
            results = unknown_collection.get(include=["embeddings", "metadatas"])
            
            if not results["ids"]:
                return {"clusters": [], "total": 0}
            
            # Simple clustering (for production, use dedicated clustering)
            embeddings = results["embeddings"]
            metadatas = results["metadatas"]
            
            clusters = []
            used_indices = set()
            
            for i in range(len(embeddings)):
                if i in used_indices:
                    continue
                
                # Create new cluster
                cluster_members = [i]
                used_indices.add(i)
                
                # Find similar faces
                for j in range(i + 1, len(embeddings)):
                    if j in used_indices:
                        continue
                    
                    # Calculate similarity
                    similarity = 1 - np.linalg.norm(
                        np.array(embeddings[i]) - np.array(embeddings[j])
                    )
                    
                    if similarity >= threshold:
                        cluster_members.append(j)
                        used_indices.add(j)
                
                if len(cluster_members) >= 2:  # Only clusters with 2+ members
                    clusters.append({
                        "cluster_id": f"cluster_{len(clusters)}",
                        "member_indices": cluster_members,
                        "size": len(cluster_members),
                        "representative_metadata": metadatas[cluster_members[0]]
                    })
            
            return {
                "clusters": clusters,
                "total_unknown": len(embeddings),
                "clustered": len(used_indices),
                "unique_clusters": len(clusters)
            }
            
        except Exception as e:
            self.logger.error(f"Clustering failed: {e}")
            return {"clusters": [], "total": 0}
    
    def export_embeddings(self, output_path: str = None) -> Dict:
        """Export all embeddings from ChromaDB to JSON format"""
        try:
            export_data = {
                "metadata": {
                    "export_timestamp": datetime.now().isoformat(),
                    "chromadb_version": "exported",
                    "total_persons": self.person_collection.count(),
                    "total_faces": self.face_collection.count()
                },
                "persons": {}
            }
            
            # Export person profiles
            person_results = self.person_collection.get(include=["embeddings", "metadatas"])
            
            for i, person_id in enumerate(person_results["ids"]):
                metadata = person_results["metadatas"][i]
                display_name = metadata.get("display_name", person_id)
                
                export_data["persons"][person_id] = {
                    "display_name": display_name,
                    "centroid_embedding": person_results["embeddings"][i],
                    "metadata": metadata
                }
            
            # Export individual faces
            export_data["individual_faces"] = {
                "count": self.face_collection.count(),
                "collection": "face_embeddings"
            }
            
            # Save to file if path provided
            if output_path:
                with open(output_path, 'w') as f:
                    json.dump(export_data, f, indent=2, default=str)
                self.logger.info(f"Exported embeddings to: {output_path}")
            
            return export_data
            
        except Exception as e:
            self.logger.error(f"Export failed: {e}")
            return {}
    
    def get_chroma_stats(self) -> Dict:
        """Get ChromaDB-specific statistics"""
        try:
            if not self.chroma_client:
                return {"chroma_available": False}
            
            stats = {
                "chroma_available": True,
                "persistent": self.chroma_config.get('persistent', True),
                "collections": {
                    "face_embeddings": self.face_collection.count() if self.face_collection else 0,
                    "person_profiles": self.person_collection.count() if self.person_collection else 0
                },
                "unknown_faces": self.chroma_client.get_collection("unknown_faces").count()
                if self.chroma_client.has_collection("unknown_faces") else 0
            }
            
            # Add query performance if available
            if hasattr(self, 'last_query_stats'):
                stats['query_performance'] = self.last_query_stats
            
            return stats
            
        except Exception as e:
            return {"chroma_available": False, "error": str(e)}
    
    def get_debug_stats(self) -> Dict:
        """Enhanced debug stats with ChromaDB information"""
        stats = super().get_debug_stats()
        
        # Add ChromaDB stats
        chroma_stats = self.get_chroma_stats()
        stats['chromadb'] = chroma_stats
        
        return stats
    
    def close(self):
        """Cleanup resources"""
        try:
            # ChromaDB doesn't require explicit closing for persistent client
            # but we can log the closure
            if self.chroma_client:
                self.logger.info("ChromaDB connection resources released")
                
            # Call parent cleanup if needed
            if hasattr(super(), 'close'):
                super().close()
                
        except Exception as e:
            self.logger.error(f"Cleanup error: {e}")