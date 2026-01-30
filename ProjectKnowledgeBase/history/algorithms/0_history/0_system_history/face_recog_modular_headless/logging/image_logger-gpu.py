# logging/image_logger.py

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
        self.base64_quality = config.get('base64_quality', 85)  # Lower quality for base64 to save space
        
        # Image resize configuration
        self.enable_resize = config.get('enable_image_resize', False)
        self.resize_width = config.get('image_resize_width', 640)
        self.resize_height = config.get('image_resize_height', 480)
        self.resize_method = config.get('image_resize_method', 'default')  # 'default', 'high_quality', 'fast'
        
        # Initialize logger FIRST
        self.logger = logging.getLogger(__name__)
        self.recent_violations = deque(maxlen=10)
        
        # GPU resizing support for GTX 1650 Ti (initialize AFTER logger)
        self.gpu_resizer = None
        self.gpu_available = False
        self._initialize_gpu_support()
        
        # Statistics
        self.stats = {
            'total_saved': 0,
            'violations_logged': 0,
            'base64_saved': 0,
            'errors': 0,
            'last_save_time': None,
            'resized_images': 0,
            'gpu_resized_images': 0,  # NEW: Track GPU resized images
            'cpu_resized_images': 0   # NEW: Track CPU fallback resizes
        }
        
    def _initialize_gpu_support(self) -> None:
        """Initialize GPU support for GTX 1650 Ti with enhanced detection."""
        try:
            # First, check if OpenCV was built with CUDA support
            if not hasattr(cv2, 'cuda'):
                self.logger.warning("⚠️  OpenCV was not built with CUDA support")
                self.gpu_available = False
                return
                
            # Check if CUDA modules are available
            if not hasattr(cv2, 'cuda_GpuMat') or not hasattr(cv2.cuda, 'createResize_GPU'):
                self.logger.warning("⚠️  Required CUDA modules not found in OpenCV")
                self.gpu_available = False
                return
            
            # Check CUDA device count with better error handling
            try:
                device_count = cv2.cuda.getCudaEnabledDeviceCount()
                self.logger.info(f"🔍 Found {device_count} CUDA-enabled device(s)")
                
                if device_count == 0:
                    self.logger.warning("⚠️  No CUDA-enabled devices detected")
                    
                    # Try to get more detailed device info
                    try:
                        # This might work even if getCudaEnabledDeviceCount returns 0
                        device_info = cv2.cuda.printCudaDeviceInfo(0)
                        self.logger.info(f"📊 Device 0 info: {device_info}")
                    except:
                        self.logger.info("📊 Could not retrieve detailed device info")
                    
                    self.gpu_available = False
                    return
                    
            except Exception as e:
                self.logger.warning(f"⚠️  Error checking CUDA devices: {e}")
                self.gpu_available = False
                return
            
            # Set CUDA device to the first available one
            try:
                cv2.cuda.setDevice(0)
                self.logger.info("✅ Set CUDA device to 0")
            except Exception as e:
                self.logger.warning(f"⚠️  Could not set CUDA device: {e}")
            
            # Enhanced GPU functionality test
            self.logger.info("🧪 Testing GPU functionality...")
            
            # Test 1: Basic GPU memory operations
            try:
                gpu_mat = cv2.cuda_GpuMat()
                test_frame = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
                gpu_mat.upload(test_frame)
                
                # Test 2: GPU resize operation
                test_resizer = cv2.cuda.createResize_GPU(50, 50, interpolation=cv2.INTER_AREA)
                test_resized = test_resizer.resize(gpu_mat)
                
                # Test 3: Download back to CPU
                downloaded_frame = test_resized.download()
                
                # Verify the result
                if downloaded_frame.shape == (50, 50, 3):
                    self.gpu_available = True
                    self.logger.info("✅ GPU acceleration test passed - GTX 1650 Ti ready for image resizing")
                    self.logger.info(f"📊 Test frame: {test_frame.shape} -> {downloaded_frame.shape}")
                else:
                    self.logger.warning("❌ GPU test failed - incorrect output dimensions")
                    self.gpu_available = False
                    
            except Exception as e:
                self.logger.warning(f"❌ GPU functionality test failed: {e}")
                self.gpu_available = False
            
            # Additional GPU info if available
            if self.gpu_available:
                try:
                    # Try to get GPU memory info
                    gpu_mat = cv2.cuda_GpuMat()
                    test_large = np.random.randint(0, 255, (1000, 1000, 3), dtype=np.uint8)
                    gpu_mat.upload(test_large)
                    self.logger.info("💾 GPU memory test passed - sufficient memory available")
                except cv2.error as e:
                    self.logger.warning(f"⚠️  GPU memory limitations detected: {e}")
                except Exception as e:
                    self.logger.debug(f"📊 Additional GPU info unavailable: {e}")
            
        except Exception as e:
            self.logger.warning(f"⚠️  GPU acceleration not available, falling back to CPU: {e}")
            self.gpu_available = False

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
            self.image_log_folder.mkdir(exist_ok=True)
            
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
            
            # Log GPU status in setup
            gpu_status = self.check_gpu_status()
            self.logger.info(f"🎯 Image logging ENABLED: {self.image_log_folder}")
            self.logger.info(f"  - Max images: {self.max_images_per_session}")
            self.logger.info(f"  - Quality: {self.image_quality}%")
            self.logger.info(f"  - Annotations: {self.annotate_images}")
            self.logger.info(f"  - Base64 logging: {self.enable_base64_logging}")
            self.logger.info(f"  - Resize enabled: {self.enable_resize}")
            
            if self.enable_resize:
                self.logger.info(f"  - Resize dimensions: {self.resize_width}x{self.resize_height}")
                self.logger.info(f"  - Resize method: {self.resize_method}")
                
                # Detailed GPU info
                if gpu_status['gpu_available']:
                    self.logger.info("  - GPU acceleration: ✅ Available (GTX 1650 Ti)")
                else:
                    self.logger.info("  - GPU acceleration: ❌ Not available")
                    if not gpu_status['cuda_support']:
                        self.logger.info("    ⚠️  OpenCV not built with CUDA support")
                    elif not gpu_status['gpu_modules_available']:
                        self.logger.info("    ⚠️  Required CUDA modules missing")
                    else:
                        self.logger.info(f"    ⚠️  CUDA devices detected: {gpu_status.get('cuda_device_count', 0)}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to setup image logging: {e}")
            self.logging_enabled = False
            self.image_log_folder = None
            return False
        
    def _resize_image_gpu(self, image: np.ndarray) -> np.ndarray:
        """
        Resize image using GPU acceleration via OpenCV's CUDA module for GTX 1650 Ti.
        
        Args:
            image: Input image to resize
            
        Returns:
            Resized image
        """
        if not self.gpu_available or not self.enable_resize:
            return self._resize_image_cpu(image)
            
        try:
            # Reinitialize GPU resizer if it doesn't exist or dimensions changed
            if (self.gpu_resizer is None or 
                (hasattr(self.gpu_resizer, 'dstSize') and 
                 (self.gpu_resizer.dstSize[0] != self.resize_width or 
                  self.gpu_resizer.dstSize[1] != self.resize_height))):
                
                self.gpu_resizer = cv2.cuda.createResize_GPU(
                    self.resize_width, 
                    self.resize_height,
                    interpolation=cv2.INTER_AREA
                )
                self.logger.debug(f"✅ Initialized CUDA image resizer: {self.resize_width}x{self.resize_height}")
            
            # Upload frame to GPU
            gpu_frame = cv2.cuda_GpuMat()
            gpu_frame.upload(image)
            
            # Perform resize on GPU
            resized_gpu = self.gpu_resizer.resize(gpu_frame)
            
            # Download the result back to CPU memory
            result = resized_gpu.download()
            
            self.stats['gpu_resized_images'] += 1
            self.stats['resized_images'] += 1
            
            return result
            
        except Exception as e:
            self.logger.warning(f"⚠️  GPU resize failed on GTX 1650 Ti, falling back to CPU: {e}")
            self.gpu_available = False  # Disable GPU on failure
            return self._resize_image_cpu(image)

    def _resize_image_cpu(self, image: np.ndarray) -> np.ndarray:
        """
        Resize image using CPU fallback.
        
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
            
            self.stats['cpu_resized_images'] += 1
            self.stats['resized_images'] += 1
            self.logger.debug(f"🖥️  CPU resized image from {original_width}x{original_height} to {self.resize_width}x{self.resize_height}")
            
            return resized_image
            
        except Exception as e:
            self.logger.error(f"❌ Error resizing image on CPU: {e}")
            return image  # Return original image on error

    def _resize_image(self, image: np.ndarray) -> np.ndarray:
        """
        Resize image according to configured dimensions and method.
        Uses GPU acceleration if available, falls back to CPU.
        
        Args:
            image: Input image to resize
            
        Returns:
            Resized image
        """
        if not self.enable_resize:
            return image
            
        # Use GPU if available, otherwise fall back to CPU
        if self.gpu_available:
            return self._resize_image_gpu(image)
        else:
            return self._resize_image_cpu(image)

    def check_gpu_status(self) -> Dict[str, Any]:
        """
        Check and return detailed GPU status information.
        
        Returns:
            Dictionary with GPU status information
        """
        gpu_status = {
            'gpu_available': self.gpu_available,
            'cuda_support': hasattr(cv2, 'cuda'),
            'gpu_modules_available': hasattr(cv2, 'cuda_GpuMat') and hasattr(cv2.cuda, 'createResize_GPU'),
            'gpu_resizer_initialized': self.gpu_resizer is not None,
            'resize_stats': {
                'gpu_resized': self.stats['gpu_resized_images'],
                'cpu_resized': self.stats['cpu_resized_images'],
                'total_resized': self.stats['resized_images']
            }
        }
        
        # Try to get CUDA device count if available
        if hasattr(cv2, 'cuda'):
            try:
                gpu_status['cuda_device_count'] = cv2.cuda.getCudaEnabledDeviceCount()
            except:
                gpu_status['cuda_device_count'] = 0
        
        return gpu_status
    
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
            
            # Prepare data structure
            save_data = {
                "timestamp": datetime.datetime.now().isoformat(),
                "filename": filename,
                "image_format": "jpg",
                "image_data": base64_data,
                "resolution": {
                    "width": image.shape[1],
                    "height": image.shape[0]
                },
                "resized": self.enable_resize,  # NEW: Include resize info
                "target_resolution": {
                    "width": self.resize_width,
                    "height": self.resize_height
                } if self.enable_resize else None
            }
            
            # Add metadata if provided
            if metadata:
                # Convert any non-serializable objects to strings
                serializable_metadata = {}
                for key, value in metadata.items():
                    if isinstance(value, (str, int, float, bool, type(None))):
                        serializable_metadata[key] = value
                    elif isinstance(value, (list, dict)):
                        # Recursively process nested structures
                        serializable_metadata[key] = self._make_json_serializable(value)
                    else:
                        serializable_metadata[key] = str(value)
                
                save_data["metadata"] = serializable_metadata
            
            # Save as JSON file
            base64_folder = self.image_log_folder / "base64" / subfolder
            json_filename = f"{filename}.json"
            json_path = base64_folder / json_filename
            
            with open(json_path, 'w') as f:
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
                "recognition_confidence": float(r.get('recognition_confidence', 0)),
                "detection_confidence": float(r.get('detection_confidence', 0)),
                "bbox": [int(coord) for coord in r.get('bbox', [0, 0, 0, 0])]
            }
            serializable_violations.append(violation_data)
        
        return {
            "violation_count": len(violations),
            "total_faces": len(results),
            "violations": serializable_violations
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
            
            # Apply annotations if enabled (BEFORE resize for better quality)
            if self.annotate_images:
                save_frame = self._annotate_frame(save_frame, results)
            
            # NEW: Apply resize AFTER annotation to maintain annotation quality
            save_frame = self._resize_image(save_frame)
            
            # Generate filename
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = f"violation_{timestamp}_{self.saved_image_count + 1:04d}.jpg"
            filepath = self.image_log_folder / "violations" / filename
            
            # Save as high-quality JPEG
            success = cv2.imwrite(
                str(filepath), 
                save_frame, 
                [cv2.IMWRITE_JPEG_QUALITY, self.image_quality]
            )
            
            if success:
                # Save base64 version if enabled
                if self.enable_base64_logging:
                    # Prepare metadata using the new method
                    metadata = self._prepare_violation_metadata(results)
                    
                    base64_filename = f"violation_{timestamp}_{self.saved_image_count + 1:04d}"
                    base64_success = self._save_base64_image(
                        save_frame, base64_filename, "violations", metadata
                    )
                    
                    # Get base64 data for return
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
                    'filepath': filepath,
                    'base64_saved': base64_data is not None,
                    'resized': self.enable_resize  # NEW: Track resize status
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

    def _annotate_frame(self, frame: np.ndarray, results: List[Dict]) -> np.ndarray:
        """Apply comprehensive annotations to the frame."""
        annotated_frame = frame.copy()
        h, w = annotated_frame.shape[:2]
        
        # Draw bounding boxes and labels
        for result in results:
            x1, y1, x2, y2 = result['bbox']
            identity = result.get('identity', 'Unknown')
            rec_conf = result.get('recognition_confidence', 0)
            det_conf = result.get('detection_confidence', 0)
            mask_status = result.get('mask_status', 'unknown')  
            mask_conf = result.get('mask_confidence', 0.0)
            
            # Initialize color variables with defaults
            color = (255, 255, 255)  # Default white
            label_color = color
            text_color = (255, 0, 255)  # Default magenta text
            
            # Color coding based on mask status and recognition
            if identity:
                if mask_status == "mask":
                    color = (0, 255, 0)  # Green for recognized with mask
                    label_color = color
                else:
                    color = (0, 255, 255)  # Yellow for recognized without mask
                    label_color = color
            else:
                if mask_status == "mask":
                    color = (255, 255, 0)  # Cyan for unknown with mask
                    label_color = color
                else:
                    color = (0, 0, 255)    # Red for unknown without mask
                    # Special styling for unknown + no_mask
                    label_color = (0, 0, 255)  # Red background
                    text_color = (255, 255, 255)  # White text
            
            # Draw bounding box
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 3)
            
            # Prepare label with comprehensive information
            if identity and identity != "Unknown":
                base_label = f"{identity} (Rec:{rec_conf:.2f})"
            else:
                base_label = f"Unknown (Det:{det_conf:.2f})"
            
            # Add mask status to label
            mask_label = f" | Mask: {mask_status}({mask_conf:.2f})"
            full_label = base_label + mask_label
            
            # Draw label background
            label_size = cv2.getTextSize(full_label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
            cv2.rectangle(annotated_frame, (x1, y1 - label_size[1] - 15), 
                        (x1 + label_size[0], y1), label_color, -1)
            
            # Draw label text
            cv2.putText(annotated_frame, full_label, (x1, y1 - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, text_color, 2)
        
        # Enhanced metadata overlay
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Add comprehensive header
        violations = [r for r in results if r.get('mask_status') == 'no_mask']
        header_text = f"MASK VIOLATION - {timestamp}"
        cv2.putText(annotated_frame, header_text, (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
        
        # Add violation summary
        violation_text = f"Violations: {len(violations)} | Total Faces: {len(results)}"
        cv2.putText(annotated_frame, violation_text, (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
        # Add resolution info
        res_text = f"Resolution: {w}x{h}"
        cv2.putText(annotated_frame, res_text, (20, 120),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Add resize info if enabled
        if self.enable_resize:
            resize_text = f"Will resize to: {self.resize_width}x{self.resize_height}"
            cv2.putText(annotated_frame, resize_text, (20, 150),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        
        # Draw violation counter on top right
        counter_text = f"#{self.saved_image_count + 1:04d}"
        counter_size = cv2.getTextSize(counter_text, cv2.FONT_HERSHEY_SIMPLEX, 1.5, 3)[0]
        cv2.putText(annotated_frame, counter_text, 
                (w - counter_size[0] - 20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
        
        return annotated_frame

    def save_debug_frame(self, frame: np.ndarray, results: List[Dict], 
                        debug_info: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Save debug frame with additional debugging information.
        Now returns both success status and base64 data if enabled.
        
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
            
            # NEW: Apply resize AFTER debug overlay for better text quality
            debug_frame = self._resize_image(debug_frame)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = f"debug_{timestamp}.jpg"
            filepath = self.image_log_folder / "debug" / filename
            
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
        Now returns both success status and base64 data if enabled.
        
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
            
            # NEW: Apply resize to snapshots (no annotation needed for snapshots)
            snapshot_frame = self._resize_image(snapshot_frame)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_description = "".join(c for c in description if c.isalnum() or c in (' ', '-', '_')).rstrip()
            filename = f"snapshot_{timestamp}_{safe_description}.jpg" if description else f"snapshot_{timestamp}.jpg"
            filepath = self.image_log_folder / "snapshots" / filename
            
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
            'recent_violations': list(self.recent_violations)
        }
        
        # Add detailed GPU status
        status['gpu_status'] = self.check_gpu_status()
        
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
            gpu_stats = self.check_gpu_status()['resize_stats']
            self.logger.info(
                f"🛑 Image logging disabled. Total images saved: {self.saved_image_count}, "
                f"Resized images: {self.stats['resized_images']}, "
                f"GPU resized: {gpu_stats['gpu_resized']}, "
                f"CPU resized: {gpu_stats['cpu_resized']}"
            )
        self.logging_enabled = False
        
        
        