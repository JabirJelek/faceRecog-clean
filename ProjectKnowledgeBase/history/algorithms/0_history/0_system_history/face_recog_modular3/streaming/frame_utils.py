"""
streaming/frame_utils.py

Enhanced FrameUtils with comprehensive configuration support
"""
import cv2
import numpy as np
from typing import Tuple, Optional, Dict, List, Any, Union
import time
from dataclasses import dataclass
from enum import Enum

class ColorSpace(Enum):
    BGR = 'bgr'
    RGB = 'rgb'
    GRAY = 'gray'
    HSV = 'hsv'
    LAB = 'lab'

class ContrastMethod(Enum):
    CLAHE = 'clahe'
    HISTOGRAM = 'histogram'
    NONE = 'none'

@dataclass
class FrameStats:
    """Dataclass for frame statistics"""
    valid: bool
    dimensions: Tuple[int, int]
    channels: int
    dtype: str
    mean_brightness: float
    std_brightness: float
    min_value: float
    max_value: float
    color_balance: Optional[Dict[str, float]]
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'valid': self.valid,
            'width': self.dimensions[1],
            'height': self.dimensions[0],
            'channels': self.channels,
            'dtype': self.dtype,
            'mean_brightness': self.mean_brightness,
            'std_brightness': self.std_brightness,
            'min_value': self.min_value,
            'max_value': self.max_value,
            'color_balance': self.color_balance,
            'timestamp': self.timestamp
        }


class FrameUtils:
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize FrameUtils with comprehensive configuration
        
        Args:
            config: Configuration dictionary with 'frame_processing' section
        """
        self.config = config or {}
        
        # Extract frame processing configuration with defaults
        frame_config = self.config.get('frame_processing', {})
        
        # Basic processing parameters
        self.processing_width = frame_config.get('processing_width', 640)
        self.processing_height = frame_config.get('processing_height', 480)
        self.min_processing_scale = frame_config.get('min_processing_scale', 0.3)
        self.max_processing_scale = frame_config.get('max_processing_scale', 4.5)
        self.default_processing_scale = frame_config.get('default_processing_scale', 1.0)
        
        # Color and normalization settings
        self.convert_to_rgb = frame_config.get('convert_to_rgb', True)
        self.normalize_values = frame_config.get('normalize_values', False)
        self.apply_mean_std_normalization = frame_config.get('apply_mean_std_normalization', False)
        self.normalization_mean = np.array(frame_config.get('normalization_mean', [0.485, 0.456, 0.406]), dtype=np.float32)
        self.normalization_std = np.array(frame_config.get('normalization_std', [0.229, 0.224, 0.225]), dtype=np.float32)
        
        # Debug and validation
        self.debug_mode = frame_config.get('debug_mode', False)
        self.validate_frames = frame_config.get('validate_frames', True)
        self.frame_validation_threshold = frame_config.get('frame_validation_threshold', 0.1)
        
        # Contrast enhancement
        contrast_config = frame_config.get('contrast_enhancement', {})
        self.contrast_enabled = contrast_config.get('enabled', True)
        self.contrast_method = ContrastMethod(contrast_config.get('method', 'clahe'))
        self.clahe_clip_limit = contrast_config.get('clahe_clip_limit', 3.0)
        self.clahe_grid_size = contrast_config.get('clahe_grid_size', 8)
        
        # ROI extraction
        roi_config = frame_config.get('roi_extraction', {})
        self.roi_enabled = roi_config.get('enabled', True)
        self.roi_default_padding = roi_config.get('default_padding', 10)
        self.min_roi_size = roi_config.get('min_roi_size', 32)
        
        # Composite creation
        composite_config = frame_config.get('composite_creation', {})
        self.grid_target_width = composite_config.get('grid_target_width', 480)
        self.grid_target_height = composite_config.get('grid_target_height', 360)
        self.horizontal_target_height = composite_config.get('horizontal_target_height', 360)
        self.vertical_target_width = composite_config.get('vertical_target_width', 480)
        self.maintain_aspect_ratio = composite_config.get('maintain_aspect_ratio', True)
        self.max_composite_width = composite_config.get('max_composite_width', 1920)
        self.max_composite_height = composite_config.get('max_composite_height', 1080)
        
        # Quality assessment
        quality_config = frame_config.get('quality_assessment', {})
        self.quality_enabled = quality_config.get('enabled', True)
        self.min_brightness = quality_config.get('min_brightness', 20.0)
        self.max_brightness = quality_config.get('max_brightness', 235.0)
        self.min_contrast = quality_config.get('min_contrast', 10.0)
        self.blur_threshold = quality_config.get('blur_threshold', 100.0)
        
        # Performance optimization
        perf_config = frame_config.get('performance', {})
        self.use_half_precision = perf_config.get('use_half_precision', False)
        self.enable_caching = perf_config.get('enable_caching', True)
        self.cache_size = perf_config.get('cache_size', 10)
        self.optimize_for_size = perf_config.get('optimize_for_size', True)
        
        # Color space conversion - handle string inputs
        color_config = frame_config.get('color_space_conversion', {})
        
        # Convert string to ColorSpace enum
        input_fmt_str = color_config.get('input_format', 'bgr')
        output_fmt_str = color_config.get('output_format', 'rgb')
        
        try:
            self.input_format = ColorSpace(input_fmt_str.lower())
        except ValueError:
            print(f"⚠️ Unknown input format: {input_fmt_str}, defaulting to BGR")
            self.input_format = ColorSpace.BGR
        
        try:
            self.output_format = ColorSpace(output_fmt_str.lower())
        except ValueError:
            print(f"⚠️ Unknown output format: {output_fmt_str}, defaulting to RGB")
            self.output_format = ColorSpace.RGB
        
        self.conversion_method = color_config.get('conversion_method', 'opencv')
                
        self.input_format = ColorSpace(color_config.get('input_format', 'bgr'))
        self.output_format = ColorSpace(color_config.get('output_format', 'rgb'))
        self.conversion_method = color_config.get('conversion_method', 'opencv')
        
        # Dynamic scaling
        scaling_config = frame_config.get('dynamic_scaling', {})
        self.dynamic_scaling_enabled = scaling_config.get('enabled', True)
        self.min_face_size = scaling_config.get('min_face_size', 50)
        self.max_face_size = scaling_config.get('max_face_size', 300)
        self.scale_adjustment_step = scaling_config.get('scale_adjustment_step', 0.1)
        self.stability_threshold = scaling_config.get('stability_threshold', 0.8)
        
        # Frame cache for performance
        self.frame_cache = {}
        self.stats_history = []
        self.last_stats_update = time.time()
        
        # Current processing state
        self.current_scale = self.default_processing_scale
        
        # Print configuration summary if debug mode
        if self.debug_mode:
            self.print_config_summary()
    
    def print_config_summary(self):
        """Print configuration summary"""
        print("\n" + "="*50)
        print("🎯 FRAME UTILS CONFIGURATION SUMMARY")
        print("="*50)
        print(f"📏 Processing size: {self.processing_width}x{self.processing_height}")
        print(f"📊 Scale range: {self.min_processing_scale:.1f} to {self.max_processing_scale:.1f}")
        print(f"🎨 Color conversion: {self.input_format.value} → {self.output_format.value}")
        print(f"✨ Contrast enhancement: {self.contrast_method.value} ({'Enabled' if self.contrast_enabled else 'Disabled'})")
        print(f"📊 Frame validation: {'Enabled' if self.validate_frames else 'Disabled'}")
        print(f"⚡ Performance caching: {'Enabled' if self.enable_caching else 'Disabled'}")
        print(f"📐 Dynamic scaling: {'Enabled' if self.dynamic_scaling_enabled else 'Disabled'}")
        print("="*50)

    def process_frame_pipeline(self, frame: np.ndarray, 
                            current_scale: Optional[float] = None,
                            target_format: Union[ColorSpace, str, None] = None) -> np.ndarray:
        """
        Complete frame processing pipeline with all configured steps
        
        Args:
            frame: Input frame
            current_scale: Dynamic processing scale
            target_format: Target color space (ColorSpace enum or string)
        
        Returns:
            Processed frame ready for AI inference
        """
        if frame is None:
            raise ValueError("Input frame is None")
        
        # Step 1: Validate frame
        if self.validate_frames and not self.validate_frame(frame):
            raise ValueError("Frame validation failed")
        
        # Step 2: Get processing parameters
        scale = current_scale if current_scale is not None else self.current_scale
        
        # Handle string format input
        if target_format is None:
            target_fmt = self.output_format
        elif isinstance(target_format, str):
            # Convert string to ColorSpace enum
            target_fmt = ColorSpace(target_format.lower())
        else:
            target_fmt = target_format
        
        # Check cache for performance
        cache_key = self._generate_cache_key(frame, scale, target_fmt)
        if self.enable_caching and cache_key in self.frame_cache:
            return self.frame_cache[cache_key].copy()
        
        # Step 3: Apply dynamic scaling
        scaled_frame = self._apply_dynamic_scaling(frame, scale)
        
        # Step 4: Apply contrast enhancement
        if self.contrast_enabled:
            scaled_frame = self._apply_contrast_enhancement(scaled_frame)
        
        # Step 5: Convert color space
        processed_frame = self._convert_color_space(scaled_frame, target_fmt)
        
        # Step 6: Apply normalization if needed
        if self.normalize_values:
            processed_frame = self._normalize_frame(processed_frame)
        
        # Step 7: Cache the result
        if self.enable_caching:
            self._update_cache(cache_key, processed_frame)
        
        return processed_frame

 
    def _generate_cache_key(self, frame: np.ndarray, scale: float, target_format: Union[ColorSpace, str]) -> str:
        """Generate cache key for frame"""
        h, w = frame.shape[:2]
        
        # Handle both ColorSpace enum and string
        if isinstance(target_format, ColorSpace):
            format_str = target_format.value
        else:
            format_str = str(target_format)
        
        return f"{h}_{w}_{scale:.2f}_{format_str}"

    def _apply_dynamic_scaling(self, frame: np.ndarray, scale: float) -> np.ndarray:
        """Apply controlled scaling with bounds checking"""
        # Clamp scale to safe range
        safe_scale = np.clip(scale, self.min_processing_scale, self.max_processing_scale)
        
        h, w = frame.shape[:2]
        
        # Calculate new dimensions with minimum size constraint
        new_w = max(32, int(w * safe_scale))
        new_h = max(32, int(h * safe_scale))
        
        # Use appropriate interpolation
        if safe_scale < 1.0:
            interpolation = cv2.INTER_AREA  # Better for shrinking
        elif safe_scale > 1.0:
            interpolation = cv2.INTER_CUBIC  # Better for enlarging
        else:
            return frame.copy()
        
        return cv2.resize(frame, (new_w, new_h), interpolation=interpolation)
    
    def _apply_contrast_enhancement(self, frame: np.ndarray) -> np.ndarray:
        """Apply configured contrast enhancement method"""
        if self.contrast_method == ContrastMethod.CLAHE:
            return self._apply_clahe(frame)
        elif self.contrast_method == ContrastMethod.HISTOGRAM:
            return self._apply_histogram_equalization(frame)
        else:
            return frame.copy()
    
    def _apply_clahe(self, frame: np.ndarray) -> np.ndarray:
        """Apply CLAHE contrast enhancement"""
        if len(frame.shape) == 3:
            # Convert to LAB color space
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            
            # Apply CLAHE to L-channel
            clahe = cv2.createCLAHE(
                clipLimit=self.clahe_clip_limit,
                tileGridSize=(self.clahe_grid_size, self.clahe_grid_size)
            )
            l = clahe.apply(l)
            
            # Merge back
            lab = cv2.merge([l, a, b])
            return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        else:
            # Grayscale image
            clahe = cv2.createCLAHE(
                clipLimit=self.clahe_clip_limit,
                tileGridSize=(self.clahe_grid_size, self.clahe_grid_size)
            )
            return clahe.apply(frame)
    
    def _apply_histogram_equalization(self, frame: np.ndarray) -> np.ndarray:
        """Apply histogram equalization"""
        if len(frame.shape) == 3:
            # Convert to YCrCb and equalize Y channel
            ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
            ycrcb[:, :, 0] = cv2.equalizeHist(ycrcb[:, :, 0])
            return cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)
        else:
            # Grayscale image
            return cv2.equalizeHist(frame)
        
    def _convert_color_space(self, frame: np.ndarray, target_format: Union[ColorSpace, str]) -> np.ndarray:
        """Convert between color spaces"""
        # Convert input to ColorSpace enum
        target_fmt = self._get_color_space(target_format)
        
        if target_fmt == self.input_format:
            return frame.copy()
        
        conversion_map = {
            (ColorSpace.BGR, ColorSpace.RGB): cv2.COLOR_BGR2RGB,
            (ColorSpace.RGB, ColorSpace.BGR): cv2.COLOR_RGB2BGR,
            (ColorSpace.BGR, ColorSpace.GRAY): cv2.COLOR_BGR2GRAY,
            (ColorSpace.RGB, ColorSpace.GRAY): cv2.COLOR_RGB2GRAY,
            (ColorSpace.BGR, ColorSpace.HSV): cv2.COLOR_BGR2HSV,
            (ColorSpace.RGB, ColorSpace.HSV): cv2.COLOR_RGB2HSV,
            (ColorSpace.BGR, ColorSpace.LAB): cv2.COLOR_BGR2LAB,
            (ColorSpace.RGB, ColorSpace.LAB): cv2.COLOR_RGB2LAB,
        }
        
        key = (self.input_format, target_fmt)
        if key in conversion_map:
            converted = cv2.cvtColor(frame, conversion_map[key])
            if len(converted.shape) == 2 and len(frame.shape) == 3:
                # Convert grayscale back to 3-channel if needed
                converted = cv2.cvtColor(converted, cv2.COLOR_GRAY2BGR)
            return converted
        
        # No conversion available, return original
        return frame.copy()
   
    def _normalize_frame(self, frame: np.ndarray) -> np.ndarray:
        """Normalize frame for model input"""
        # Convert to float32
        normalized = frame.astype(np.float32)
        
        # Normalize to [0, 1]
        normalized /= 255.0
        
        # Apply ImageNet normalization if requested
        if self.apply_mean_std_normalization and len(frame.shape) == 3:
            for i in range(3):
                normalized[:, :, i] = (normalized[:, :, i] - self.normalization_mean[i]) / self.normalization_std[i]
        
        # Convert to half precision if requested
        if self.use_half_precision:
            normalized = normalized.astype(np.float16)
        
        return normalized
    
    def _generate_cache_key(self, frame: np.ndarray, scale: float, target_format: ColorSpace) -> str:
        """Generate cache key for frame"""
        h, w = frame.shape[:2]
        return f"{h}_{w}_{scale:.2f}_{target_format.value}"
    
    def _get_color_space(self, color_space: Union[ColorSpace, str]) -> ColorSpace:
        """Convert color space input to ColorSpace enum"""
        if isinstance(color_space, ColorSpace):
            return color_space
        elif isinstance(color_space, str):
            try:
                return ColorSpace(color_space.lower())
            except ValueError:
                print(f"⚠️ Unknown color space: {color_space}, defaulting to BGR")
                return ColorSpace.BGR
        else:
            print(f"⚠️ Invalid color space type: {type(color_space)}, defaulting to BGR")
            return ColorSpace.BGR    
    
    def _update_cache(self, key: str, frame: np.ndarray):
        """Update frame cache with LRU strategy"""
        if len(self.frame_cache) >= self.cache_size:
            # Remove oldest entry
            if self.frame_cache:
                oldest_key = next(iter(self.frame_cache))
                del self.frame_cache[oldest_key]
        
        self.frame_cache[key] = frame.copy()
    
    def validate_frame(self, frame: np.ndarray) -> bool:
        """Comprehensive frame validation"""
        if frame is None:
            return False
        
        if not isinstance(frame, np.ndarray):
            return False
        
        if frame.size == 0:
            return False
        
        h, w = frame.shape[:2]
        if h < 10 or w < 10:
            return False
        
        # Check for corrupted frames (all black, all white, etc.)
        if self.quality_enabled:
            frame_mean = np.mean(frame)
            if frame_mean < self.min_brightness or frame_mean > self.max_brightness:
                return False
            
            # Check contrast
            frame_std = np.std(frame)
            if frame_std < self.min_contrast:
                return False
            
            # Check blur
            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame
            
            blur_value = cv2.Laplacian(gray, cv2.CV_64F).var()
            if blur_value < self.blur_threshold:
                return False
        
        return True
    
    def calculate_frame_stats(self, frame: np.ndarray) -> FrameStats:
        """Calculate comprehensive frame statistics"""
        if not self.validate_frame(frame):
            return FrameStats(
                valid=False,
                dimensions=(0, 0),
                channels=0,
                dtype='invalid',
                mean_brightness=0.0,
                std_brightness=0.0,
                min_value=0.0,
                max_value=0.0,
                color_balance=None,
                timestamp=time.time()
            )
        
        stats = FrameStats(
            valid=True,
            dimensions=frame.shape[:2],
            channels=frame.shape[2] if len(frame.shape) == 3 else 1,
            dtype=str(frame.dtype),
            mean_brightness=float(np.mean(frame)),
            std_brightness=float(np.std(frame)),
            min_value=float(np.min(frame)),
            max_value=float(np.max(frame)),
            color_balance=None,
            timestamp=time.time()
        )
        
        # Color-specific stats for color frames
        if stats.channels == 3:
            # Assume BGR format
            b_mean, g_mean, r_mean = np.mean(frame, axis=(0, 1))
            stats.color_balance = {
                'b_ratio': float(b_mean / (r_mean + 1e-6)),
                'g_ratio': float(g_mean / (r_mean + 1e-6)),
                'r_ratio': float(r_mean / (g_mean + 1e-6))
            }
        
        # Add to history
        self.stats_history.append(stats)
        
        # Trim history if too large
        if len(self.stats_history) > 1000:
            self.stats_history = self.stats_history[-1000:]
        
        # Update stats periodically
        current_time = time.time()
        if current_time - self.last_stats_update >= 30.0:  # Every 30 seconds
            self._update_performance_stats()
            self.last_stats_update = current_time
        
        return stats
    
    def _update_performance_stats(self):
        """Update and print performance statistics"""
        if not self.stats_history:
            return
        
        valid_stats = [s for s in self.stats_history if s.valid]
        if not valid_stats:
            return
        
        # Calculate average statistics
        avg_brightness = np.mean([s.mean_brightness for s in valid_stats])
        avg_contrast = np.mean([s.std_brightness for s in valid_stats])
        
        if self.debug_mode:
            print(f"📊 Frame Stats: Avg Brightness={avg_brightness:.1f}, Avg Contrast={avg_contrast:.1f}")
    
    def adjust_scale_based_on_faces(self, face_sizes: List[float], 
                                  current_scale: float) -> float:
        """
        Adjust processing scale based on detected face sizes
        """
        if not face_sizes or not self.dynamic_scaling_enabled:
            return current_scale
        
        avg_face_size = np.mean(face_sizes)
        
        # Adjust scale based on average face size
        if avg_face_size < self.min_face_size:
            # Faces are too small, increase scale
            new_scale = min(current_scale + self.scale_adjustment_step, 
                          self.max_processing_scale)
        elif avg_face_size > self.max_face_size:
            # Faces are too large, decrease scale
            new_scale = max(current_scale - self.scale_adjustment_step,
                          self.min_processing_scale)
        else:
            # Faces are in optimal range, maintain current scale
            new_scale = current_scale
        
        # Update current scale
        self.current_scale = new_scale
        
        if self.debug_mode and new_scale != current_scale:
            print(f"📐 Scale adjusted: {current_scale:.2f} → {new_scale:.2f} "
                  f"(avg face size: {avg_face_size:.1f}px)")
        
        return new_scale
    
    def extract_roi_with_validation(self, frame: np.ndarray, 
                                  bbox: Tuple[int, int, int, int],
                                  padding: Optional[int] = None) -> Optional[np.ndarray]:
        """
        Extract region of interest with comprehensive validation
        """
        if padding is None:
            padding = self.roi_default_padding
        
        x1, y1, x2, y2 = bbox
        
        # Add padding with bounds checking
        x1 = max(0, x1 - padding)
        y1 = max(0, y1 - padding)
        x2 = min(frame.shape[1], x2 + padding)
        y2 = min(frame.shape[0], y2 + padding)
        
        # Ensure valid region
        if x2 <= x1 or y2 <= y1:
            return None
        
        # Check minimum size
        roi_width = x2 - x1
        roi_height = y2 - y1
        if roi_width < self.min_roi_size or roi_height < self.min_roi_size:
            return None
        
        roi = frame[y1:y2, x1:x2]
        
        # Validate ROI
        if not self.validate_frame(roi):
            return None
        
        return roi
    
    def create_multi_source_composite(self, 
                                    source_frames: Dict[str, np.ndarray],
                                    layout: str = 'grid',
                                    max_sources: int = 4) -> np.ndarray:
        """
        Create composite display from multiple sources with validation
        """
        # Filter valid frames
        valid_frames = {}
        for source_id, frame in source_frames.items():
            if self.validate_frame(frame):
                valid_frames[source_id] = frame
        
        if not valid_frames:
            # Return black frame with error message
            error_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(error_frame, "No valid frames", (50, 240), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            return error_frame
        
        if len(valid_frames) == 1:
            return list(valid_frames.values())[0]
        
        # Limit number of sources
        source_ids = list(valid_frames.keys())[:max_sources]
        
        # Create composite based on layout
        if layout == 'grid':
            return self._create_grid_composite(valid_frames, source_ids)
        elif layout == 'horizontal':
            return self._create_horizontal_composite(valid_frames, source_ids)
        elif layout == 'vertical':
            return self._create_vertical_composite(valid_frames, source_ids)
        else:
            return self._create_grid_composite(valid_frames, source_ids)
    
    def _create_grid_composite(self, frames: Dict[str, np.ndarray], 
                             source_ids: List[str]) -> np.ndarray:
        """Create grid layout composite"""
        grid_size = int(np.ceil(np.sqrt(len(source_ids))))
        
        target_w = self.grid_target_width
        target_h = self.grid_target_height
        
        resized_frames = []
        for source_id in source_ids:
            frame = frames[source_id]
            if self.maintain_aspect_ratio:
                resized = self._resize_maintain_aspect(frame, (target_w, target_h))
            else:
                resized = cv2.resize(frame, (target_w, target_h))
            resized_frames.append(resized)
        
        # Create grid
        rows = []
        for i in range(0, len(resized_frames), grid_size):
            row_frames = resized_frames[i:i + grid_size]
            # Pad row if necessary
            while len(row_frames) < grid_size:
                blank_frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
                row_frames.append(blank_frame)
            rows.append(np.hstack(row_frames))
        
        composite = np.vstack(rows)
        
        # Ensure composite doesn't exceed maximum size
        h, w = composite.shape[:2]
        if w > self.max_composite_width or h > self.max_composite_height:
            composite = cv2.resize(composite, 
                                 (self.max_composite_width, self.max_composite_height))
        
        return composite
    
    def _create_horizontal_composite(self, frames: Dict[str, np.ndarray], 
                                   source_ids: List[str]) -> np.ndarray:
        """Create horizontal strip composite"""
        target_h = self.horizontal_target_height
        
        resized_frames = []
        for source_id in source_ids:
            frame = frames[source_id]
            if self.maintain_aspect_ratio:
                h, w = frame.shape[:2]
                aspect_ratio = w / h
                target_w = int(target_h * aspect_ratio)
                resized = cv2.resize(frame, (target_w, target_h))
            else:
                target_w = int(target_h * 1.777)  # 16:9 aspect ratio
                resized = cv2.resize(frame, (target_w, target_h))
            resized_frames.append(resized)
        
        composite = np.hstack(resized_frames)
        
        # Limit width
        if composite.shape[1] > self.max_composite_width:
            scale = self.max_composite_width / composite.shape[1]
            new_h = int(composite.shape[0] * scale)
            composite = cv2.resize(composite, (self.max_composite_width, new_h))
        
        return composite
    
    def _create_vertical_composite(self, frames: Dict[str, np.ndarray], 
                                 source_ids: List[str]) -> np.ndarray:
        """Create vertical stack composite"""
        target_w = self.vertical_target_width
        
        resized_frames = []
        for source_id in source_ids:
            frame = frames[source_id]
            if self.maintain_aspect_ratio:
                h, w = frame.shape[:2]
                aspect_ratio = h / w
                target_h = int(target_w * aspect_ratio)
                resized = cv2.resize(frame, (target_w, target_h))
            else:
                target_h = int(target_w * 0.5625)  # 16:9 aspect ratio
                resized = cv2.resize(frame, (target_w, target_h))
            resized_frames.append(resized)
        
        composite = np.vstack(resized_frames)
        
        # Limit height
        if composite.shape[0] > self.max_composite_height:
            scale = self.max_composite_height / composite.shape[0]
            new_w = int(composite.shape[1] * scale)
            composite = cv2.resize(composite, (new_w, self.max_composite_height))
        
        return composite
    
    def _resize_maintain_aspect(self, frame: np.ndarray, 
                               target_size: Tuple[int, int]) -> np.ndarray:
        """Resize while maintaining aspect ratio (adds padding if needed)"""
        h, w = frame.shape[:2]
        target_w, target_h = target_size
        
        # Calculate scaling factor
        scale = min(target_w / w, target_h / h)
        
        # Calculate new dimensions
        new_w = int(w * scale)
        new_h = int(h * scale)
        
        # Resize
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        
        # Calculate padding
        pad_w = (target_w - new_w) // 2
        pad_h = (target_h - new_h) // 2
        
        # Create padded frame
        if len(frame.shape) == 3:
            padded = np.full((target_h, target_w, 3), 0, dtype=np.uint8)
        else:
            padded = np.full((target_h, target_w), 0, dtype=np.uint8)
        
        padded[pad_h:pad_h+new_h, pad_w:pad_w+new_w] = resized
        
        return padded
    
    def clear_cache(self):
        """Clear frame cache"""
        self.frame_cache.clear()
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get configuration summary"""
        return {
            'processing_size': f"{self.processing_width}x{self.processing_height}",
            'scale_range': f"{self.min_processing_scale:.1f}-{self.max_processing_scale:.1f}",
            'color_conversion': f"{self.input_format.value}→{self.output_format.value}",
            'contrast_enhancement': self.contrast_method.value,
            'frame_validation': self.validate_frames,
            'dynamic_scaling': self.dynamic_scaling_enabled,
            'cache_enabled': self.enable_caching,
            'cache_size': len(self.frame_cache),
            'stats_history': len(self.stats_history),
            'current_scale': self.current_scale
        }