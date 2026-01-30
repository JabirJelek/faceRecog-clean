"""
Image logging system for saving annotated frames with violations.
"""

import cv2
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import numpy as np
import logging
from collections import deque
import base64
import json

class ImageLogger:
    """Handles image logging for mask violations and system events."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logging_enabled = False
        self.image_log_folder: Optional[Path] = None
        self.saved_image_count = 0
        self.last_image_save_time = 0
        
        # Configuration parameters
        self.image_log_interval = config.get('image_log_interval', 3)
        self.max_images_per_session = config.get('max_images_per_session', 500)
        self.min_save_interval = config.get('min_save_interval', 2.0)
        self.image_quality = config.get('image_quality', 95)
        self.annotate_images = config.get('annotate_images', True)
        self.enable_base64_logging = config.get('enable_base64_logging', True)
        self.base64_quality = config.get('base64_quality', 85)
        
        # Image resize configuration
        self.enable_resize = config.get('enable_image_resize', False)
        self.resize_width = config.get('image_resize_width', 640)
        self.resize_height = config.get('image_resize_height', 480)
        self.resize_method = config.get('image_resize_method', 'default')
        
        # CCTV name configuration
        self.cctv_name = config.get('cctv_name', 'Unknown-Camera')
        
        # Statistics
        self.stats = {
            'total_saved': 0,
            'violations_logged': 0,
            'base64_saved': 0,
            'errors': 0,
            'last_save_time': None,
            'resized_images': 0
        }
        
        self.logger = logging.getLogger(__name__)
        self.recent_violations = deque(maxlen=10)
        
    def setup_image_logging(self, base_filename: Optional[str] = None) -> bool:
        """
        Setup image logging folder structure.
        
        Args:
            base_filename: Base filename for the logging session
            
        Returns:
            bool: True if setup successful
        """
        try:
            if base_filename is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                base_filename = f"face_recognition_{timestamp}"
            
            # Extract base name without extension
            base_name = Path(base_filename).stem
            self.image_log_folder = Path(f"{base_name}_images")
            
            # Create directory
            self.image_log_folder.mkdir(exist_ok=True, parents=True)
            
            # Create subdirectories
            (self.image_log_folder / "violations").mkdir(exist_ok=True)
            (self.image_log_folder / "debug").mkdir(exist_ok=True)
            (self.image_log_folder / "snapshots").mkdir(exist_ok=True)
            
            # Create base64 subdirectories if enabled
            if self.enable_base64_logging:
                (self.image_log_folder / "base64").mkdir(exist_ok=True)
                (self.image_log_folder / "base64" / "violations").mkdir(exist_ok=True)
                (self.image_log_folder / "base64" / "debug").mkdir(exist_ok=True)
                (self.image_log_folder / "base64" / "snapshots").mkdir(exist_ok=True)
            
            self.logging_enabled = True
            self.saved_image_count = 0
            
            self.logger.info(f"Image logging ENABLED: {self.image_log_folder}")
            self.logger.info(f"  - Max images: {self.max_images_per_session}")
            self.logger.info(f"  - Quality: {self.image_quality}%")
            self.logger.info(f"  - Annotations: {self.annotate_images}")
            self.logger.info(f"  - Base64 logging: {self.enable_base64_logging}")
            self.logger.info(f"  - Resize enabled: {self.enable_resize}")
            self.logger.info(f"  - CCTV Name: {self.cctv_name}")
            if self.enable_resize:
                self.logger.info(f"  - Resize dimensions: {self.resize_width}x{self.resize_height}")
                self.logger.info(f"  - Resize method: {self.resize_method}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to setup image logging: {e}")
            self.logging_enabled = False
            self.image_log_folder = None
            return False
        
    def _resize_image(self, image: np.ndarray) -> np.ndarray:
        """
        Resize image according to configured dimensions and method.
        
        Args:
            image: Input image to resize
            
        Returns:
            Resized image
        """
        if not self.enable_resize:
            return image
            
        try:
            original_height, original_width = image.shape[:2]
            
            # Skip resize if image is already smaller than target
            if original_width <= self.resize_width and original_height <= self.resize_height:
                return image
            
            # Choose interpolation method based on configuration
            if self.resize_method == 'high_quality':
                interpolation = cv2.INTER_LANCZOS4
            elif self.resize_method == 'fast':
                interpolation = cv2.INTER_LINEAR
            else:  # default
                interpolation = cv2.INTER_AREA
            
            # Resize image
            resized_image = cv2.resize(
                image, 
                (self.resize_width, self.resize_height), 
                interpolation=interpolation
            )
            
            self.stats['resized_images'] += 1
            self.logger.debug(f"Resized image from {original_width}x{original_height} to {self.resize_width}x{self.resize_height}")
            
            return resized_image
            
        except Exception as e:
            self.logger.error(f"Error resizing image: {e}")
            return image  # Return original image on error

    def update_resize_config(self, resize_config: Dict[str, Any]) -> None:
        """
        Update resize configuration dynamically.
        
        Args:
            resize_config: Dictionary with resize configuration
                - enable_image_resize: bool
                - image_resize_width: int
                - image_resize_height: int  
                - image_resize_method: str ('default', 'high_quality', 'fast')
        """
        try:
            self.enable_resize = resize_config.get('enable_image_resize', self.enable_resize)
            self.resize_width = resize_config.get('image_resize_width', self.resize_width)
            self.resize_height = resize_config.get('image_resize_height', self.resize_height)
            self.resize_method = resize_config.get('image_resize_method', self.resize_method)
            
            self.logger.info(f"Updated resize config: enabled={self.enable_resize}, "
                           f"size={self.resize_width}x{self.resize_height}, method={self.resize_method}")
                           
        except Exception as e:
            self.logger.error(f"Error updating resize config: {e}")

    def has_mask_violations(self, results: List[Dict]) -> bool:
        """
        Check if frame contains mask violations.
        
        Args:
            results: List of face recognition results
            
        Returns:
            bool: True if mask violations detected
        """
        if not results:
            return False
        
        for result in results:
            mask_status = result.get('mask_status')
            mask_conf = result.get('mask_confidence', 0)
            
            # Log ANY person without mask, regardless of recognition status
            if mask_status == 'no_mask' and mask_conf > 0.3:
                return True
        
        return False

    def _image_to_base64(self, image: np.ndarray, quality: int = None) -> str:
        """
        Convert OpenCV image to base64 encoded string.
        
        Args:
            image: OpenCV image (numpy array)
            quality: JPEG quality (1-100), uses self.base64_quality if None
            
        Returns:
            str: Base64 encoded JPEG image
        """
        if quality is None:
            quality = self.base64_quality
            
        try:
            # Encode image to JPEG in memory
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
            success, buffer = cv2.imencode('.jpg', image, encode_params)
            
            if not success:
                raise ValueError("Failed to encode image to JPEG")
            
            # Convert to base64
            image_base64 = base64.b64encode(buffer).decode('utf-8')
            return image_base64
            
        except Exception as e:
            self.logger.error(f"Error converting image to base64: {e}")
            raise

    def get_base64_image_data(self, image: np.ndarray, quality: int = None) -> Optional[str]:
        """
        Utility method to get base64 representation of an image without saving.
        
        Args:
            image: OpenCV image to convert
            quality: JPEG quality (1-100)
            
        Returns:
            Optional[str]: Base64 encoded image or None if failed
        """
        try:
            return self._image_to_base64(image, quality)
        except Exception as e:
            self.logger.error(f"Error getting base64 data: {e}")
            return None

    def _save_base64_image(self, image: np.ndarray, filename: str, 
                        subfolder: str = "violations", metadata: Dict = None) -> bool:
        """
        Save image as base64 encoded JSON file.
        
        Args:
            image: Image to save
            filename: Base filename (without extension)
            subfolder: Subfolder within base64 directory
            metadata: Additional metadata to include
            
        Returns:
            bool: True if save successful
        """
        if not self.enable_base64_logging or not self.image_log_folder:
            return False
            
        try:
            # Convert image to base64
            base64_data = self._image_to_base64(image)
            
            # Extract detected identities from metadata for top-level field
            detected_identities = []
            if metadata and 'violations' in metadata:
                for violation in metadata['violations']:
                    identity = violation.get('identity', 'Unknown')
                    # Convert numpy types to Python native types for JSON serialization
                    if hasattr(identity, 'item'):
                        identity = identity.item()
                    identity = str(identity) if identity and identity != 'Unknown' else 'Unknown'
                    if identity != 'Unknown':
                        detected_identities.append(identity)
            
            # Prepare data structure
            save_data = {
                "timestamp": datetime.datetime.now().isoformat(),
                "filename": filename,
                "image_format": "jpg",
                "image_data": base64_data,
                "detected_identities": detected_identities if detected_identities else ["No identified persons"],
                "cctv_name": self.cctv_name  
            }
            
            # Add metadata if provided
            if metadata:
                serializable_metadata = self._make_json_serializable(metadata)
                save_data["metadata"] = serializable_metadata
            
            # Save as JSON file
            base64_folder = self.image_log_folder / "base64" / subfolder
            base64_folder.mkdir(exist_ok=True, parents=True)  # Ensure directory exists
            json_filename = f"{filename}.json"
            json_path = base64_folder / json_filename
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
            
            self.stats['base64_saved'] += 1
            self.logger.debug(f"Saved base64 image: {json_filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving base64 image: {e}")
            self.stats['errors'] += 1
            return False
                        
    def _make_json_serializable(self, obj):
        """Recursively make object JSON serializable"""
        if isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        elif isinstance(obj, dict):
            return {key: self._make_json_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._make_json_serializable(item) for item in obj]
        elif isinstance(obj, (np.integer, np.floating)):
            return obj.item()
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return str(obj)

    def _prepare_violation_metadata(self, results: List[Dict]) -> Dict[str, Any]:
        """Prepare violation metadata that is JSON serializable"""
        violations = [r for r in results if r.get('mask_status') == 'no_mask']
        
        # Build serializable violations list
        serializable_violations = []
        for r in violations:
            violation_data = {
                "identity": str(r.get('identity', 'Unknown')),
                "mask_confidence": float(r.get('mask_confidence', 0)),
                "detection_confidence": float(r.get('detection_confidence', 0)),
                "recognition_confidence": float(r.get('recognition_confidence', 0)) if r.get('recognition_confidence') else None
            }
            serializable_violations.append(violation_data)
        
        return {
            "violations": serializable_violations,
            "total_violations": len(violations),
            "total_faces": len(results),
            "timestamp": datetime.datetime.now().isoformat()
        }

    def save_annotated_frame(self, frame: np.ndarray, results: List[Dict], 
                        original_frame: Optional[np.ndarray] = None) -> Tuple[bool, Optional[str]]:
        """
        Save annotated frame with bounding boxes, labels, and enhanced metadata overlay.
        Now returns both success status and base64 data if enabled.
        
        Args:
            frame: Frame to save (can be display frame)
            results: Face recognition results
            original_frame: Original high-quality frame (optional)
            
        Returns:
            Tuple[bool, Optional[str]]: (success_status, base64_data)
        """
        if not self.logging_enabled or not self.image_log_folder:
            return False, None
        
        # Check limits
        if self.saved_image_count >= self.max_images_per_session:
            self.logger.warning("Image log limit reached, disabling image logging")
            self.logging_enabled = False
            return False, None
        
        # Rate limiting
        current_time = datetime.datetime.now().timestamp()
        if current_time - self.last_image_save_time < self.min_save_interval:
            return False, None
        
        base64_data = None
        
        try:
            # Use original frame if available for better quality, otherwise use provided frame
            if original_frame is not None:
                save_frame = original_frame.copy()
            else:
                save_frame = frame.copy()
            
            # Apply annotations if enabled
            if self.annotate_images:
                save_frame = self._annotate_frame(save_frame, results)
            
            # Apply resize 
            save_frame = self._resize_image(save_frame)
            
            # Generate filename
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = f"violation_{timestamp}_{self.saved_image_count + 1:04d}.jpg"
            filepath = self.image_log_folder / "violations" / filename
            
            # Ensure directory exists
            filepath.parent.mkdir(exist_ok=True, parents=True)
            
            # Save as high-quality JPEG
            success = cv2.imwrite(
                str(filepath), 
                save_frame, 
                [cv2.IMWRITE_JPEG_QUALITY, self.image_quality]
            )
            
            if success:
                # Save base64 version if enabled - using the SAME processed frame
                if self.enable_base64_logging:
                    # Prepare metadata using the new method
                    metadata = self._prepare_violation_metadata(results)
                    
                    base64_filename = f"violation_{timestamp}_{self.saved_image_count + 1:04d}"
                    base64_success = self._save_base64_image(
                        save_frame, base64_filename, "violations", metadata
                    )
                    
                    # Get base64 data for return - using the SAME processed frame
                    if base64_success:
                        base64_data = self._image_to_base64(save_frame)
                
                self.saved_image_count += 1
                self.last_image_save_time = current_time
                self.stats['total_saved'] += 1
                self.stats['violations_logged'] += 1
                self.stats['last_save_time'] = datetime.datetime.now()
                
                # Log violation details
                violations = [r for r in results if r.get('mask_status') == 'no_mask']
                self.recent_violations.append({
                    'timestamp': timestamp,
                    'violations': len(violations),
                    'filepath': str(filepath),
                    'base64_saved': base64_data is not None,
                    'resized': self.enable_resize
                })
                
                self.logger.info(
                    f"Saved violation image #{self.saved_image_count}: {filename} "
                    f"(Violations: {len(violations)}, Base64: {base64_data is not None}, "
                    f"Resized: {self.enable_resize})"
                )
                
                return True, base64_data
            else:
                self.stats['errors'] += 1
                self.logger.error(f"Failed to save image: {filepath}")
                return False, None
                
        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(f"Error saving annotated frame: {e}")
            return False, None
        
    def get_dynamic_text_params(self, frame_width: int, frame_height: int, 
                            preset: str = "violation_summary") -> Tuple[int, int, float]:
        """
        Calculate dynamic text parameters with multiple presets.
        
        Args:
            frame_width: Current frame width
            frame_height: Current frame height  
            preset: Text preset type
                - "violation_summary": Main violation counter
                - "header": Large header text
                - "info": Small info text
                - "counter": Image counter
                
        Returns:
            Tuple of (x, y, scale) adjusted for current resolution
        """
        # Define presets for different text types (base 640x480)
        presets = {
            "violation_summary": {"x": 20, "y": 330, "scale": 0.5},
            "header": {"x": 20, "y": 40, "scale": 1.0},
            "info": {"x": 20, "y": 120, "scale": 0.6},
            "counter": {"x": 600, "y": 40, "scale": 0.7}
        }
        
        if preset not in presets:
            preset = "violation_summary"
        
        base_config = presets[preset]
        base_width, base_height = 640, 480
        
        # Calculate scaling factors
        width_ratio = frame_width / base_width
        height_ratio = frame_height / base_height
        
        # Use geometric mean for more balanced scaling
        scale_ratio = (width_ratio * height_ratio) ** 0.5
        
        # Adjust position and scale
        x = int(base_config["x"] * width_ratio)
        y = int(base_config["y"] * height_ratio)
        scale = base_config["scale"] * scale_ratio
        
        # Ensure reasonable bounds
        min_scale = 0.3
        max_scale = 2.0
        scale = max(min(scale, max_scale), min_scale)
        
        # For counter preset, keep it at right edge
        if preset == "counter":
            x = frame_width - int((base_width - base_config["x"]) * width_ratio)
        
        return x, y, scale

    def _annotate_frame(self, frame: np.ndarray, results: List[Dict]) -> np.ndarray:
        """Apply comprehensive annotations to the frame with dynamic scaling."""
        annotated_frame = frame.copy()
        h, w = annotated_frame.shape[:2]
        
        # Get dynamic text parameters based on current frame size
        text_x, text_y, text_scale = self.get_dynamic_text_params(w, h)
        
        # Initialize variables for summary text
        violations = [r for r in results if r.get('mask_status') == 'no_mask']
        
        # Draw bounding boxes and labels
        for result in results:
            bbox = result.get('bbox')
            if bbox is None:
                continue
                
            x1, y1, x2, y2 = bbox
            identity = result.get('identity', 'Unknown')
            rec_conf = result.get('recognition_confidence', 0)
            det_conf = result.get('detection_confidence', 0)
            mask_status = result.get('mask_status', 'unknown')  
            mask_conf = result.get('mask_confidence', 0.0)
            
            # Color coding
            if identity and identity != 'Unknown':
                if mask_status == "mask":
                    color = (0, 255, 0)  # Green
                    label_color = color
                    text_color = (0, 0, 0)
                else:
                    color = (0, 255, 255)  # Yellow
                    label_color = color
                    text_color = (0, 0, 0)                    
            else:
                if mask_status == "mask":
                    color = (255, 255, 0)  # Cyan
                    label_color = color
                    text_color = (0, 0, 0)                    
                else:
                    color = (0, 0, 255)    # Red
                    label_color = (0, 0, 255)
                    text_color = (255, 255, 255)
            
            # Draw bounding box (thickness scales with image size)
            box_thickness = max(2, int(3 * (w / 640)))  # Scale thickness
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, box_thickness)
            
            # Prepare label
            if identity and identity != "Unknown":
                base_label = f"{identity} (Rec:{rec_conf:.2f})"
            else:
                base_label = f"Unknown (Det:{det_conf:.2f})"
            
            # Add mask status to label
            mask_label = f" | Mask: {mask_status}({mask_conf:.2f})"
            full_label = base_label + mask_label
            
            # Draw label background with dynamic scaling
            label_scale = text_scale * 0.9  # Slightly smaller than main text
            label_size = cv2.getTextSize(full_label, cv2.FONT_HERSHEY_SIMPLEX, label_scale, 2)[0]
            
            # Ensure label stays within frame bounds
            label_x1 = max(0, x1)
            label_y1 = max(0, y1 - label_size[1] - 10)
            label_x2 = min(w, x1 + label_size[0])
            label_y2 = min(h, y1)
            
            if label_y1 >= 0 and label_x2 <= w:
                cv2.rectangle(annotated_frame, (label_x1, label_y1), 
                            (label_x2, label_y2), label_color, -1)
                
                # Draw label text with dynamic scale
                cv2.putText(annotated_frame, full_label, (x1, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, label_scale, text_color, 2)
        
        # Add violation summary with dynamic positioning and scaling
        violation_text = f"Violations: {len(violations)} | Total Faces: {len(results)}"
        vio_color = (0, 0, 255)
        
        cv2.putText(annotated_frame, violation_text, (text_x, text_y),
                cv2.FONT_HERSHEY_SIMPLEX, text_scale, vio_color, 2)  
        
        return annotated_frame

    def save_debug_frame(self, frame: np.ndarray, results: List[Dict], 
                        debug_info: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Save debug frame with additional debugging information.
        
        Args:
            frame: Frame to save
            results: Recognition results
            debug_info: Additional debug information
            
        Returns:
            Tuple[bool, Optional[str]]: (success_status, base64_data)
        """
        if not self.logging_enabled or not self.image_log_folder:
            return False, None
        
        base64_data = None
        
        try:
            debug_frame = frame.copy()
            
            # Add debug information overlay (BEFORE resize)
            y_offset = 30
            for key, value in debug_info.items():
                text = f"{key}: {value}"
                cv2.putText(debug_frame, text, (10, y_offset),
                          cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 1)
                y_offset += 20
            
            # Apply resize AFTER debug overlay for better text quality
            debug_frame = self._resize_image(debug_frame)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = f"debug_{timestamp}.jpg"
            filepath = self.image_log_folder / "debug" / filename
            
            # Ensure directory exists
            filepath.parent.mkdir(exist_ok=True, parents=True)
            
            success = cv2.imwrite(str(filepath), debug_frame)
            
            if success:
                # Save base64 version if enabled
                if self.enable_base64_logging:
                    base64_filename = f"debug_{timestamp}"
                    # Make debug info JSON serializable
                    serializable_debug_info = self._make_json_serializable(debug_info)
                    base64_success = self._save_base64_image(
                        debug_frame, base64_filename, "debug", serializable_debug_info
                    )
                    
                    if base64_success:
                        base64_data = self._image_to_base64(debug_frame)
                
                self.logger.debug(f"Saved debug frame: {filename} (Base64: {base64_data is not None}, Resized: {self.enable_resize})")
                return True, base64_data
            else:
                return False, None
                
        except Exception as e:
            self.logger.error(f"Error saving debug frame: {e}")
            return False, None
   
    def save_snapshot(self, frame: np.ndarray, description: str = "") -> Tuple[bool, Optional[str]]:
        """
        Save a snapshot with description.
        
        Args:
            frame: Frame to save
            description: Description of the snapshot
            
        Returns:
            Tuple[bool, Optional[str]]: (success_status, base64_data)
        """
        if not self.logging_enabled or not self.image_log_folder:
            return False, None
        
        base64_data = None
        
        try:
            snapshot_frame = frame.copy()
            
            # Apply resize to snapshots
            snapshot_frame = self._resize_image(snapshot_frame)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_description = "".join(c for c in description if c.isalnum() or c in (' ', '-', '_')).rstrip()
            filename = f"snapshot_{timestamp}_{safe_description}.jpg" if description else f"snapshot_{timestamp}.jpg"
            filepath = self.image_log_folder / "snapshots" / filename
            
            # Ensure directory exists
            filepath.parent.mkdir(exist_ok=True, parents=True)
            
            success = cv2.imwrite(str(filepath), snapshot_frame)
            
            if success:
                # Save base64 version if enabled
                if self.enable_base64_logging:
                    base64_filename = f"snapshot_{timestamp}_{safe_description}" if description else f"snapshot_{timestamp}"
                    metadata = {"description": description} if description else {}
                    base64_success = self._save_base64_image(
                        snapshot_frame, base64_filename, "snapshots", metadata
                    )
                    
                    if base64_success:
                        base64_data = self._image_to_base64(snapshot_frame)
                
                self.logger.info(f"Saved snapshot: {filename} (Base64: {base64_data is not None}, Resized: {self.enable_resize})")
                return True, base64_data
            else:
                return False, None
                
        except Exception as e:
            self.logger.error(f"Error saving snapshot: {e}")
            return False, None

    def get_logging_status(self) -> Dict[str, Any]:
        """Get current logging status and statistics."""
        status = {
            'enabled': self.logging_enabled,
            'image_log_folder': str(self.image_log_folder) if self.image_log_folder else None,
            'saved_image_count': self.saved_image_count,
            'max_images_per_session': self.max_images_per_session,
            'stats': self.stats.copy(),
            'recent_violations': list(self.recent_violations),
            'cctv_name': self.cctv_name  
        }
        
        # Add resize configuration to status
        status['resize_config'] = {
            'enabled': self.enable_resize,
            'width': self.resize_width,
            'height': self.resize_height,
            'method': self.resize_method
        }
        
        return status

    def disable_logging(self):
        """Disable image logging."""
        if self.logging_enabled:
            self.logger.info(
                f"Image logging disabled. Total images saved: {self.saved_image_count}, "
                f"Resized images: {self.stats['resized_images']}"
            )
        self.logging_enabled = False
        
        