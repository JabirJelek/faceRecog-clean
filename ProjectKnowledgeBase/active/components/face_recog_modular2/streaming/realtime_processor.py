# streaming/realtime_processor.py

import cv2
from pathlib import Path
from threading import Lock
import datetime
import csv
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
import time

from face_recog_modular2.visualization.display_resizer import DisplayResizer
from face_recog_modular2.processing.scene_analysis import ContextAwareDynamicScaling
from face_recog_modular2.tracking.tracking_manager import TrackingManager
from face_recog_modular2.alerting.alert_manager import DurationAwareAlertManager
from face_recog_modular2.logging.image_logger import ImageLogger
# REMOVED: ViolationUploader import

# Import new modular components
from face_recog_modular2.streaming.base_processor import BaseProcessor
from face_recog_modular2.streaming.performance_manager import PerformanceManager
from face_recog_modular2.streaming.frame_utils import FrameUtils
from face_recog_modular2.streaming.control_handler import ControlHandler
from face_recog_modular2.streaming.stream_manager import StreamManager

class RealTimeProcessor(BaseProcessor):
    def __init__(self, face_system, config: Dict, processing_interval: int = 5, buffer_size: int = 3):
        # Initialize base class
        super().__init__(face_system, config)
        
        # Store configuration
        self.config = config
        
        # Initialize modular components
        self.stream_manager = StreamManager(self.config)
        self.performance_manager = PerformanceManager(self.config)
        self.frame_utils = FrameUtils()
        self.control_handler = ControlHandler(self)
        
        # REMOVED: Duplicate threading and queue management
        # StreamManager now handles all frame capture and queuing
        self.processing_lock = Lock()  # Keep only processing lock
        self.running = False
        
        # Enhanced display resizing
        self.resizer = DisplayResizer()
        self.show_resize_info = False
        self.original_frame_size = None
        
        # 🆕 CONTEXT-AWARE SCALING SYSTEM
        self.context_aware_scaler = ContextAwareDynamicScaling(self.config)
        self.enable_context_awareness = True
        self.context_debug_mode = False

        # Debug controls
        self.debug_mode = False
        self.show_detection_debug = False
        self.show_performance_stats = False
        self.save_debug_frames = False
        self.debug_frame_count = 0
        self.max_debug_frames = 100
        
        # Stream health monitoring (now delegated to StreamManager)
        self.consecutive_good_frames = 0
        
        # Enhanced control attributes
        self.face_tracking_enabled = False
        self.current_preset_index = 0
                    
        # 🆕 REPLACE custom image logging with proper ImageLogger module
        self.image_logger = ImageLogger(self.config)
        self.image_logging_enabled = False
        
        # 🆕 VOICE ALERT SYSTEM
        self.alert_manager = DurationAwareAlertManager(self.config)
        self.sent_alerts = set()  # Track alerted identities to avoid duplicates
        
        # 🆕 ENHANCED: TrackingManager with ByteTrack integration
        self.tracking_manager = TrackingManager(self.config)
        
        # ADD OTHER MISSING ATTRIBUTES FROM BaseProcessor
        self.processing_width = 640  # Default processing width
        self.processing_height = 480  # Default processing height
        self.processing_scale = 1.0  # Default processing scale
        self.frame_count = 0  # Total frames processed
        self.processing_count = 0  # Frames actually sent for face processing
        self.fps = 0  # Current FPS
        self.last_fps_time = time.time()
        self.fps_frame_count = 0
        
        # 🆕 REMOVED: ViolationUploader - Now using ImageLogger for server pushes
        
        print("📤 Image logging server push system READY")        
        
        # 🆕 NEW: Person detection tracking
        self.person_detections = []  # Store YOLO person detections
        self.enable_person_tracking = self.config.get('tracking', {}).get('enable_person_tracking', True)
        
        print("🎯 RealTimeProcessor initialized with modular components")
        print("🎯 Context-aware dynamic scaling ENABLED")
        print("🎮 Enhanced keyboard controls LOADED")
        print("📊 Enhanced logging system READY")
        print("🖼️  Enhanced image logging system READY") 
        print("🔊 Voice alert system READY")
        print("👤 Enhanced TrackingManager with ByteTrack INITIALIZED")
        print("📤 Server push via ImageLogger CONFIGURED")
    
    # ========== STREAM MANAGEMENT (Delegated to StreamManager) ==========
    
    def initialize_stream(self, source: str):
        """Initialize camera or RTSP stream using StreamManager"""
        success = self.stream_manager.initialize_stream(source)
        if success:
            print(f"✅ Stream initialized: {source}")
        else:
            print(f"❌ Failed to initialize stream: {source}")
        return success
    
    def start_frame_capture(self):
        """Start background frame capture using StreamManager"""
        self.stream_manager.start_capture()
        print("🎬 Frame capture started via StreamManager")
    
    def get_frame_for_processing(self) -> Optional[np.ndarray]:
        """Get frame using StreamManager with validation"""
        try:
            # Get frame from StreamManager's queue
            frame = self.stream_manager.get_frame(timeout=0.05)
            
            if frame is None:
                return None
                
            # Validate frame integrity using FrameUtils
            if not self.frame_utils.validate_frame(frame):
                return None
                
            return frame
                
        except Exception as e:
            if self.config.get('debug', {}).get('verbose', False):
                print(f"Frame acquisition skipped: {e}")
            return None

    # ========== FRAME PROCESSING (Using FrameUtils) ==========
    
    def enhanced_resize_for_processing(self, frame: np.ndarray) -> np.ndarray:
        """Resize frame for processing using FrameUtils"""
        return self.frame_utils.enhanced_resize_for_processing(
            frame, 
            self.performance_manager.current_processing_scale
        )
    
    def resize_frame_for_display(self, frame: np.ndarray) -> np.ndarray:
        """Apply resizing to frame for display"""
        if self.original_frame_size is None:
            self.original_frame_size = frame.shape[:2]
        
        return self.resizer.resize_frame(frame)
    
    # ========== FPS CALCULATION ==========
    
    def calculate_fps(self):
        """Calculate current FPS"""
        self.frame_count += 1
        self.fps_frame_count += 1
        
        current_time = time.time()
        elapsed = current_time - self.last_fps_time
        
        if elapsed >= 1.0:  # Update FPS every second
            self.fps = self.fps_frame_count / elapsed
            self.fps_frame_count = 0
            self.last_fps_time = current_time
    
    def should_process_frame(self) -> bool:
        """Determine if current frame should be processed"""
        return self.frame_count % self.processing_interval == 0

    # 🆕 NEW: Extract person detections from YOLO results
    def extract_person_detections(self, yolo_results: List[Dict]) -> List[Dict]:
        """Extract person detections from YOLO results for ByteTrack"""
        person_detections = []
        
        for result in yolo_results:
            # Check if this is a person detection (class 0 in COCO dataset)
            if result.get('class_id') == 0 and result.get('confidence', 0) > 0.5:
                person_detection = {
                    'bbox': result['bbox'],
                    'confidence': result['confidence'],
                    'class_name': 'person',
                    'class_id': 0
                }
                person_detections.append(person_detection)
        
        return person_detections
    
    def apply_logging_config(self, config: Dict):
        """Apply logging configuration from main pipeline"""
        try:
            # Apply CSV logging configuration
            if 'enable_logging' in config:
                self.logging_enabled = config['enable_logging']
                if self.logging_enabled:
                    print("📊 CSV logging configured: ENABLED")
                else:
                    print("📊 CSV logging configured: DISABLED")
            
            # Apply image logging configuration  
            if 'enable_image_logging' in config:
                self.image_logging_enabled = config['enable_image_logging']
                if self.image_logging_enabled:
                    print("🖼️  Image logging configured: ENABLED")
                else:
                    print("🖼️  Image logging configured: DISABLED")
            
            # Apply log intervals
            if 'log_interval' in config:
                self.log_interval = config['log_interval']
                print(f"⏱️  Log interval configured: every {self.log_interval} processed frames")
                
            if 'image_log_interval' in config:
                self.image_logger.image_log_interval = config['image_log_interval']
                print(f"🖼️  Image log interval: every {self.image_logger.image_log_interval} violations")
                
            # Apply image logging limits
            if 'max_images_per_session' in config:
                self.image_logger.max_images_per_session = config['max_images_per_session']
                print(f"📸 Max images per session: {self.image_logger.max_images_per_session}")
                
            if 'min_save_interval' in config:
                self.image_logger.min_save_interval = config['min_save_interval']
                print(f"⏰ Minimum save interval: {self.image_logger.min_save_interval}s")
            
            # 🆕 NEW: Apply server push configuration to ImageLogger
            if 'server_push_enabled' in config:
                server_config = {
                    'server_push_enabled': config.get('server_push_enabled', False),
                    'server_endpoint': config.get('server_endpoint', ''),
                    'server_push_cooldown': config.get('server_push_cooldown', 30),
                    'server_timeout': config.get('server_timeout', 10),
                    'server_retry_attempts': config.get('server_retry_attempts', 3),
                    'server_retry_delay': config.get('server_retry_delay', 2)
                }
                self.image_logger.update_server_config(server_config)
                print(f"📤 Server push via ImageLogger: {'ENABLED' if server_config['server_push_enabled'] else 'DISABLED'}")
                
            # Auto-setup logging if enabled
            if self.logging_enabled:
                self.setup_logging()
                
            if self.image_logging_enabled:
                self.setup_image_logging()
                
        except Exception as e:
            print(f"❌ Error applying logging configuration: {e}")      
            
    # 🆕 REMOVED: apply_upload_config method - No longer using ViolationUploader
    
    # 🆕 REMOVED: get_upload_config method
    
    # 🆕 REMOVED: print_upload_status method
    
    # 🆕 REMOVED: toggle_uploader method
    
    # ========== PERFORMANCE MANAGEMENT (Delegated to PerformanceManager) ==========
    
    def analyze_detection_performance(self, results: List[Dict], original_frame_shape: Tuple[int, int]) -> Dict:
        """Analyze detection performance using PerformanceManager"""
        return self.performance_manager.analyze_detection_performance(results, original_frame_shape)
    
    def apply_dynamic_adjustment(self, performance: Dict):
        """Apply resolution adjustment using PerformanceManager"""
        self.performance_manager.apply_dynamic_adjustment(performance)
    
    def update_dynamic_system(self):
        """Update dynamic adjustment system using PerformanceManager"""
        self.performance_manager.update_dynamic_system()
    
    def toggle_dynamic_adjustment(self):
        """Toggle dynamic adjustment using PerformanceManager"""
        self.performance_manager.toggle_dynamic_adjustment()
    
    def reset_dynamic_scaling(self):
        """Reset dynamic scaling using PerformanceManager"""
        self.performance_manager.reset_dynamic_scaling()
    
    def enable_small_face_mode(self):
        """Enable optimized settings for small face detection"""
        # Update detection parameters
        self.face_system.detection_confidence = 0.4
        self.face_system.detection_iou = 0.3
        self.face_system.min_face_size = 20
        
        # Use PerformanceManager for processing parameters
        self.performance_manager.enable_small_face_mode()
        
        # Update multi-scale processor if available
        if hasattr(self.face_system, 'multi_scale_processor'):
            self.face_system.multi_scale_processor.scale_factors = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75]
        
        print("🔍 Small face detection mode ENABLED")
        print("   - Lower confidence threshold: 0.4")
        print("   - Lower IoU threshold: 0.3")
        print("   - Minimum face size: 20px")
        print("   - Higher processing scale: 1.5x")
        print("   - Enhanced multi-scale processing")
    
    # ========== LOGGING SYSTEM (Enhanced with BaseProcessor) ==========
    
    def setup_logging(self, filename: str = None):
        """Setup CSV logging"""
        try:
            if filename is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"face_recognition_log_{timestamp}.csv"
            
            self.log_file = filename
            self.log_start_time = datetime.datetime.now()
            self.log_counter = 0
            
            # Create CSV file with headers
            with open(self.log_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'identity', 'mask_status', 'recognition_confidence', 'detection_confidence'])
            
            self.logging_enabled = True
            print(f"📝 Logging enabled: {self.log_file}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to setup logging: {e}")
            self.logging_enabled = False
            return False
    
    def setup_image_logging(self, csv_filename: str = None):
        """Setup image logging using the proper ImageLogger module"""
        try:
            success = self.image_logger.setup_image_logging(csv_filename)
            if success:
                self.image_logging_enabled = True
                print(f"🖼️  Image logging ENABLED using ImageLogger module")
                return True
            else:
                self.image_logging_enabled = False
                return False
        except Exception as e:
            print(f"❌ Failed to setup image logging: {e}")
            self.image_logging_enabled = False
            return False
    
    def collect_log_data(self, results: List[Dict]) -> List[List]:
        """Collect data for logging"""
        log_entries = []
        current_time = datetime.datetime.now().isoformat()
        
        for result in results:
            identity = result.get('identity', 'Unknown')
            mask_status = result.get('mask_status', 'unknown')
            rec_conf = result.get('recognition_confidence', 0.0)
            det_conf = result.get('detection_confidence', 0.0)
            
            log_entries.append([
                current_time,
                identity,
                mask_status,
                f"{rec_conf:.3f}",
                f"{det_conf:.3f}"
            ])
        
        return log_entries
    
    def write_log_entries(self, log_entries: List[List]):
        """Write log entries to CSV file"""
        try:
            with open(self.log_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerows(log_entries)
            self.log_counter += len(log_entries)
        except Exception as e:
            print(f"❌ Error writing to log file: {e}")
    
    def log_performance_data(self, results: List[Dict], display_frame: np.ndarray = None, original_frame: np.ndarray = None):
        """Enhanced logging with synchronized voice alerts and ImageLogger server pushes"""
        if not self.logging_enabled:
            return
        
        # Only log every X processed frames to reduce I/O
        if self.processing_count % self.log_interval != 0:
            return
        
        try:
            # CSV logging: Write entries for recognized faces (using BaseProcessor)
            log_entries = self.collect_log_data(results)
            
            # 🆕 USE SYNCHRONIZED ALERTS with image logging AND SERVER PUSHES via ImageLogger
            if (self.image_logging_enabled and 
                self.image_logger.has_mask_violations(results)):
                
                print("🚨 ATTEMPTING TO SAVE VIOLATION IMAGE, TRIGGER AUDIO, AND PUSH TO SERVER")
                
                # Check if we're due for image logging based on interval
                if (self.processing_count % self.image_logger.image_log_interval == 0 and
                    self.image_logger.saved_image_count < self.image_logger.max_images_per_session):
                    
                    current_time = time.time()
                    # Check minimum time between saves using ImageLogger's timing
                    if current_time - self.image_logger.last_image_save_time >= self.image_logger.min_save_interval:
                        
                        # 🆕 TRIGGER SYNCHRONIZED AUDIO ALERT
                        current_violations = []
                        for result in results:
                            if (result.get('mask_status') == 'no_mask' and 
                                result.get('mask_confidence', 0) > 0.3):
                                current_violations.append({
                                    'identity': result.get('identity', 'Unknown'),
                                    'mask_confidence': result.get('mask_confidence', 0),
                                    'bbox': result['bbox']
                                })
                        
                        # Send synchronized audio alert
                        if current_violations:
                            audio_success = self.alert_manager.trigger_synchronized_alert(
                                current_violations,
                                self.processing_count,
                                self.image_logger.saved_image_count,
                                self.image_logger.max_images_per_session
                            )
                            if audio_success:
                                print(f"🔊 Audio alert triggered synchronously with image logging")
                        
                        # 🆕 NEW: Save the image - ImageLogger will automatically handle server push if enabled
                        frame_to_save = original_frame if original_frame is not None else display_frame
                        if frame_to_save is not None:
                            success, base64_data = self.save_annotated_frame(display_frame, results, frame_to_save)
                            if success:
                                print(f"✅ Image saved successfully! Total: {self.image_logger.saved_image_count}")
                                if base64_data and self.image_logger.server_push_enabled:
                                    print(f"📤 Server push initiated via ImageLogger (cooldown: {self.image_logger.server_push_cooldown}s)")
                            else:
                                print("❌ Failed to save image")
                        else:
                            print("❌ No frame available for saving")
                    else:
                        print(f"⏰ Image save skipped - too soon since last save: {current_time - self.image_logger.last_image_save_time:.1f}s")
                else:
                    print(f"⏰ Image save skipped - interval or limit: count={self.image_logger.saved_image_count}, interval={self.image_logger.image_log_interval}")
            else:
                print("ℹ️  No image saved - conditions not met")
            
            # CSV logging (using BaseProcessor)
            if log_entries:
                self.write_log_entries(log_entries)
                print(f"📝 CSV: Logged {len(log_entries)} face entries")
            else:
                print("📝 CSV: No recognized faces to log")
                    
        except Exception as e:
            print(f"❌ Enhanced logging error: {e}")
                        
    def has_mask_violations(self, results: List[Dict]) -> bool:
        """Check if frame contains mask violations using ImageLogger"""
        return self.image_logger.has_mask_violations(results)
   
    def save_annotated_frame(self, frame: np.ndarray, results: List[Dict], original_frame: np.ndarray = None) -> Tuple[bool, Optional[str]]:
        """Save annotated frame using the proper ImageLogger module"""
        if not self.image_logging_enabled:
            return False, None
        
        # Use the ImageLogger's save method which now returns both success and base64 data
        # The ImageLogger will automatically handle server pushes if enabled
        return self.image_logger.save_annotated_frame(frame, results, original_frame)
    
    def toggle_logging(self, filename: str = None, force_state: bool = None):
        """Toggle both CSV and image logging with optional forced state"""
        if force_state is not None:
            # Force a specific state (from configuration)
            new_state = force_state
        else:
            # Toggle current state (from user input)
            new_state = not self.logging_enabled
        
        if new_state and not self.logging_enabled:
            # Enable both CSV and image logging
            self.setup_logging(filename)
            self.setup_image_logging(self.log_file)  # Use same base filename
            self.logging_enabled = True
            self.image_logging_enabled = True
            self.log_counter = 0
            print("🟢 Enhanced logging STARTED")
            print("   - CSV: timestamp, identity, mask_status")
            print("   - Images: jpeg frames for mask violations")
            print(f"   - Image folder: {self.image_logger.image_log_folder}")
            print(f"   - Server push: {'ENABLED' if self.image_logger.server_push_enabled else 'DISABLED'}")
        elif not new_state and self.logging_enabled:
            # Disable both
            if self.log_file:
                duration = datetime.datetime.now() - self.log_start_time
                print(f"🔴 Logging STOPPED: {self.log_file}")
                print(f"   - Duration: {duration}")
                print(f"   - CSV entries: {self.log_counter}")
                print(f"   - Violation images: {self.image_logger.saved_image_count}")
                print(f"   - Server pushes: {self.image_logger.stats.get('server_pushes', 0)}")
            
            self.logging_enabled = False
            self.image_logging_enabled = False
            self.log_file = None
            self.log_start_time = None
    
    def get_image_logging_status(self) -> Dict[str, Any]:
        """Get current image logging status from ImageLogger"""
        return self.image_logger.get_logging_status()
    
    # ========== ALERT MANAGEMENT ==========
    
    def apply_alert_config(self, config: Dict):
        """Apply audio alert configuration from main pipeline"""
        try:
            # Apply alert configuration to alert manager
            if hasattr(self, 'alert_manager') and self.alert_manager:
                self.alert_manager.update_config(config)
                
            print("🔊 Audio alert system configured from main pipeline")
            
        except Exception as e:
            print(f"❌ Error applying alert configuration: {e}")
    
    def toggle_voice_alerts(self, force_state: bool = None):
        """Toggle voice alerts with optional forced state"""
        if hasattr(self, 'alert_manager') and self.alert_manager:
            if force_state is not None:
                self.alert_manager.enabled = force_state
                status = "ENABLED" if force_state else "DISABLED"
                print(f"🔊 Voice alerts: {status}")
            else:
                self.alert_manager.toggle_alerts()
    
    def get_alert_config(self) -> Dict:
        """Get current alert configuration"""
        if hasattr(self, 'alert_manager') and self.alert_manager:
            return self.alert_manager.get_alert_config()
        return {}
    
    def print_alert_status(self):
        """Print current alert system status"""
        config = self.get_alert_config()
        print("\n" + "="*50)
        print("🔊 AUDIO ALERT SYSTEM STATUS")
        print("="*50)
        for key, value in config.items():
            if value is not None:
                print(f"  {key}: {value}")
        print("="*50)
    
    # ========== TRACKING MANAGEMENT ==========
    
    def apply_tracking_config(self, config: Dict):
        """Apply tracking configuration from main pipeline"""
        try:
            if hasattr(self, 'tracking_manager') and self.tracking_manager:
                self.tracking_manager.update_config(config)
                
            print("🎯 Tracking system configured from main pipeline")
            
        except Exception as e:
            print(f"❌ Error applying tracking configuration: {e}")
    
    def get_tracking_config(self) -> Dict:
        """Get current tracking configuration"""
        if hasattr(self, 'tracking_manager') and self.tracking_manager:
            return self.tracking_manager.get_config()
        return {}
    
    def print_tracking_status(self):
        """Print current tracking system status"""
        config = self.get_tracking_config()
        stats = self.tracking_manager.get_tracking_stats() if hasattr(self, 'tracking_manager') else {}
        
        print("\n" + "="*50)
        print("👤 TRACKING SYSTEM STATUS")
        print("="*50)
        
        if config.get('tracking'):
            for key, value in config['tracking'].items():
                if value is not None:
                    print(f"  {key}: {value}")
        
        if stats:
            print(f"\n  Active Tracks: {stats.get('face_tracker', {}).get('total_tracks', 0)}")
            print(f"  Person Tracks: {stats.get('person_tracker', {}).get('active_tracks', 0)}")
            print(f"  Frame Count: {stats.get('frame_count', 0)}")
            print(f"  ByteTrack: {'ENABLED' if stats.get('person_tracker', {}).get('bytetrack_initialized', False) else 'DISABLED'}")
        
        print("="*50)

    # 🆕 NEW: Toggle person tracking with ByteTrack
    def toggle_person_tracking(self, enabled: bool = None):
        """Toggle person tracking with ByteTrack"""
        if hasattr(self, 'tracking_manager') and self.tracking_manager:
            if enabled is None:
                self.tracking_manager.toggle_person_tracking()
            else:
                self.tracking_manager.person_tracking_enabled = enabled
                status = "ENABLED" if enabled else "DISABLED"
                print(f"👤 Person tracking: {status}")
    
    # ========== DISPLAY CONTROLS (Windowed-specific) ==========
    
    def set_display_size(self, width: int, height: int, method: str = "fixed_size"):
        """Set fixed display size"""
        self.resizer.target_width = width
        self.resizer.target_height = height
        self.resizer.resize_method = method
        print(f"🖼️  Display size set to {width}x{height} using {method} method")
    
    def set_display_scale(self, scale: float):
        """Set display scale factor"""
        self.resizer.current_scale = scale
        self.resizer.resize_method = "scale"
        print(f"🔍 Display scale set to {scale:.2f}")
    
    def set_display_method(self, method: str):
        """Set resizing method"""
        valid_methods = ["fit_to_screen", "fixed_size", "scale", "crop", "letterbox"]
        if method in valid_methods:
            self.resizer.resize_method = method
            print(f"🔄 Resize method set to: {method}")
        else:
            print(f"❌ Invalid resize method. Choose from: {valid_methods}")
    
    def set_max_display_size(self, width: int, height: int):
        """Set maximum display size for fit_to_screen method"""
        self.resizer.max_display_size = (width, height)
        print(f"📏 Maximum display size set to {width}x{height}")
    
    def toggle_resize_info(self):
        """Toggle resize information display"""
        self.show_resize_info = not self.show_resize_info
        status = "ON" if self.show_resize_info else "OFF"
        print(f"📊 Resize info display: {status}")
    
    # ========== DEBUG CONTROLS ==========
    
    def toggle_debug_mode(self):
        """Toggle comprehensive debug mode"""
        self.debug_mode = not self.debug_mode
        status = "ON" if self.debug_mode else "OFF"
        print(f"🐛 Debug mode: {status}")
        
    def toggle_detection_debug(self):
        """Toggle detection visualization debug"""
        self.show_detection_debug = not self.show_detection_debug
        status = "ON" if self.show_detection_debug else "OFF"
        print(f"🎯 Detection debug: {status}")
        
    def toggle_performance_stats(self):
        """Toggle performance statistics display"""
        self.show_performance_stats = not self.show_performance_stats
        status = "ON" if self.show_performance_stats else "OFF"
        print(f"📈 Performance stats: {status}")
        
    def toggle_save_debug_frames(self):
        """Toggle saving debug frames"""
        self.save_debug_frames = not self.save_debug_frames
        status = "ON" if self.save_debug_frames else "OFF"
        print(f"💾 Save debug frames: {status}")
    
    # ========== CONTEXT-AWARE SCALING ==========
    
    def toggle_context_awareness(self):
        """Toggle context-aware scaling"""
        self.enable_context_awareness = not self.enable_context_awareness
        status = "ENABLED" if self.enable_context_awareness else "DISABLED"
        print(f"🎯 Context-aware scaling: {status}")
    
    def print_context_statistics(self):
        """Print detailed context analysis statistics"""
        if not hasattr(self, 'context_aware_scaler'):
            print("❌ Context-aware scaling not available")
            return
        
        stats = self.context_aware_scaler.get_scaling_statistics()
        
        print("\n" + "="*60)
        print("📊 CONTEXT-AWARE SCALING STATISTICS")
        print("="*60)
        print(f"Current Scale: {stats['current_scale']:.2f}")
        print(f"Total Decisions: {stats['total_decisions']}")
        print(f"Context Influence: {stats['context_influence']:.0%}")
        
        if 'recent_context_stats' in stats and stats['recent_context_stats']:
            print(f"\n📈 Recent Context Analysis:")
            for metric, values in stats['recent_context_stats'].items():
                print(f"   {metric:20}: {values['mean']:.3f} ± {values['std']:.3f}")
        
        if 'common_recommendations' in stats:
            print(f"\n🎯 Common Recommendations:")
            for reason, count in stats['common_recommendations'].items():
                print(f"   {count:2}x {reason}")
        
        print("="*60)
    
    # ========== VISUALIZATION METHODS (Windowed-specific) ==========
    
    def draw_resize_info(self, frame: np.ndarray):
        """Display resize information on frame"""
        if not self.show_resize_info:
            return
        
        original_h, original_w = self.original_frame_size or frame.shape[:2]
        display_h, display_w = frame.shape[:2]
        
        info_lines = [
            f"Original: {original_w}x{original_h}",
            f"Display: {display_w}x{display_h}",
            f"Method: {self.resizer.resize_method}",
            f"Scale: {self.resizer.current_scale:.2f}" if self.resizer.resize_method == "scale" else "",
            f"Processing: {self.processing_width}x{self.processing_height}"
        ]
        
        info_lines = [line for line in info_lines if line.strip()]
        
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 130), (350, 130 + len(info_lines) * 25 + 10), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        for i, line in enumerate(info_lines):
            y_position = 150 + (i * 25)
            cv2.putText(frame, line, (20, y_position),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    def draw_debug_info(self, frame: np.ndarray, results: List[Dict]):
        """Draw comprehensive debug information on frame"""
        if not self.debug_mode and not self.show_performance_stats:
            return
            
        # Get debug stats from face system
        stats = {}
        if hasattr(self.face_system, 'get_debug_stats'):
            stats = self.face_system.get_debug_stats()
        else:
            # Fallback stats if face_system doesn't have get_debug_stats
            stats = {
                'recognition_rate': 0.0,
                'avg_detection_time': 0.0,
                'avg_embedding_time': 0.0,
                'avg_recognition_time': 0.0,
                'total_faces_detected': len(results),
                'total_faces_recognized': len([r for r in results if r.get('identity')])
            }
        
        # Performance metrics
        performance_lines = []
        if self.show_performance_stats:
            performance_lines = [
                f"FPS: {self.fps:.1f}",
                f"Frame: {self.frame_count}",
                f"Processed: {self.processing_count}",
                f"Interval: 1/{self.processing_interval}",
                f"Recognition: {stats.get('recognition_rate', 0):.1f}%",
            ]
        
        # Debug information
        debug_lines = []
        if self.debug_mode:
            debug_lines = [
                f"Detection: {stats.get('avg_detection_time', 0):.1f}ms",
                f"Embedding: {stats.get('avg_embedding_time', 0):.1f}ms",
                f"Recognition: {stats.get('avg_recognition_time', 0):.1f}ms",
                f"Total Faces: {stats.get('total_faces_detected', 0)}",
                f"Recognized: {stats.get('total_faces_recognized', 0)}",
            ]
        
        all_lines = performance_lines + debug_lines
        if not all_lines:
            return
            
        # Draw background for all info
        overlay = frame.copy()
        start_y = 10
        end_y = start_y + len(all_lines) * 25 + 20
        cv2.rectangle(overlay, (10, start_y), (350, end_y), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # Draw performance stats (green)
        for i, line in enumerate(performance_lines):
            y_position = 30 + (i * 25)
            cv2.putText(frame, line, (20, y_position),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        # Draw debug info (cyan)
        debug_start_y = 30 + len(performance_lines) * 25
        for i, line in enumerate(debug_lines):
            y_position = debug_start_y + (i * 25)
            cv2.putText(frame, line, (20, y_position),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
    
    def draw_detection_debug(self, frame: np.ndarray, results: List[Dict]):
        """Draw detailed detection debugging information"""
        if not self.show_detection_debug:
            return
            
        for i, result in enumerate(results):
            x1, y1, x2, y2 = result['bbox']
            
            # Draw detailed information near each detection
            info_text = f"Det: {result['detection_confidence']:.2f}"
            if result['identity']:
                info_text += f" | Rec: {result['identity']} ({result['recognition_confidence']:.2f})"
            
            # Calculate position for debug text (below the bounding box)
            text_y = y2 + 20
            
            # Draw background for text
            text_size = cv2.getTextSize(info_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
            cv2.rectangle(frame, (x1, text_y - text_size[1] - 5), 
                         (x1 + text_size[0], text_y + 5), (0, 0, 0), -1)
            
            # Draw debug text
            cv2.putText(frame, info_text, (x1, text_y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 1)
    
    def draw_results(self, frame: np.ndarray, results: List[Dict]):
        """Enhanced visualization with mask status and tracking info"""
        if self.original_frame_size is None:
            self.original_frame_size = frame.shape[:2]
        
        # Draw bounding boxes and labels
        for result in results:
            x1, y1, x2, y2 = result['bbox']
            identity = result['identity']
            rec_conf = result['recognition_confidence']
            det_conf = result['detection_confidence']
            mask_status = result.get('mask_status', 'unknown')  
            mask_conf = result.get('mask_confidence', 0.0)
            track_id = result.get('track_id', None)
            tracking_method = result.get('tracking_method', 'unknown')
            
            # Initialize color variables with defaults
            color = (255, 255, 255)  # Default white
            label_color = color
            text_color = (255, 0, 255)  # Default magenta text
            
            # Color coding based on mask status and recognition
            if identity:
                if mask_status == "mask":
                    color = (0, 255, 0)  # Green for recognized with mask
                    text_color = (0,0,0)
                    label_color = color
                else:  # No mask
                    color = (0, 255, 255)  # Yellow for recognized without mask
                    text_color = (0,0,0)
                    label_color = color
                    
            else:  # identity is None or doesn't exist
                if mask_status == "mask":
                    color = (255, 255, 0)  # Cyan for unknown with mask
                    text_color = (0,0,0)
                    label_color = color
                else:  # No mask
                    color = (0, 0, 255)    # Red for unknown without mask
                    # Special styling for unknown + no_mask
                    label_color = (0, 0, 255)  # Red background
                    text_color = (255, 255, 255)  # White text
            
            # 🆕 NEW: Different border style for ByteTrack tracks
            if tracking_method == 'bytetrack':
                # Dashed line for ByteTrack tracks
                self.draw_dashed_rectangle(frame, (x1, y1), (x2, y2), color, 2)
            else:
                # Solid line for basic tracking
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Prepare label with tracking information
            if identity:
                base_label = f"{identity} ({rec_conf:.2f})"
            else:
                base_label = f"Unknown ({det_conf:.2f})"
            
            # Add tracking ID if available
            if track_id is not None:
                base_label = f"ID:{track_id} " + base_label
            
            # Add mask status to label
            mask_label = f" | Mask: {mask_status}({mask_conf:.2f})"
            full_label = base_label + mask_label
            
            # Draw label background with appropriate color
            label_size = cv2.getTextSize(full_label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
            cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                        (x1 + label_size[0], y1), label_color, -1)
            
            # Draw label text with appropriate color
            cv2.putText(frame, full_label, (x1, y1 - 5), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)
    
    def draw_dashed_rectangle(self, frame: np.ndarray, pt1: Tuple[int, int], pt2: Tuple[int, int], color: Tuple[int, int, int], thickness: int = 1, dash_length: int = 10):
        """Draw a dashed rectangle for ByteTrack visual distinction"""
        x1, y1 = pt1
        x2, y2 = pt2
        
        # Draw top line
        for x in range(x1, x2, dash_length * 2):
            cv2.line(frame, (x, y1), (min(x + dash_length, x2), y1), color, thickness)
        
        # Draw bottom line
        for x in range(x1, x2, dash_length * 2):
            cv2.line(frame, (x, y2), (min(x + dash_length, x2), y2), color, thickness)
        
        # Draw left line
        for y in range(y1, y2, dash_length * 2):
            cv2.line(frame, (x1, y), (x1, min(y + dash_length, y2)), color, thickness)
        
        # Draw right line
        for y in range(y1, y2, dash_length * 2):
            cv2.line(frame, (x2, y), (x2, min(y + dash_length, y2)), color, thickness)
            
    def draw_enhanced_results(self, frame: np.ndarray, results: List[Dict], performance: Dict):
        """Enhanced drawing with tracking information"""
        # Existing drawing logic
        self.draw_results(frame, results)
        
        
        # Add mask debug info
        self.draw_mask_debug_info(frame, results)
        
        # Add dynamic adjustment info if available
        if performance and self.show_performance_stats:
            self.draw_dynamic_adjustment_info(frame, performance)
       
    def draw_mask_debug_info(self, frame: np.ndarray, results: List[Dict]):
        """Draw mask detection debug information"""
        if not self.debug_mode:
            return
            
        for i, result in enumerate(results):
            x1, y1, x2, y2 = result['bbox']
            mask_status = result.get('mask_status', 'unknown')
            mask_conf = result.get('mask_confidence', 0.0)
            
            # Draw mask status above bounding box
            status_text = f"Mask: {mask_status}({mask_conf:.2f})"
            
            # Calculate position (above the bounding box)
            text_y = y1 - 35
            
            # Draw background for text
            text_size = cv2.getTextSize(status_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
            cv2.rectangle(frame, (x1, text_y - text_size[1] - 5), 
                        (x1 + text_size[0], text_y + 5), (0, 0, 0), -1)
            
            # Color code based on mask status
            if mask_status == "mask":
                color = (0, 255, 0)  # Green
            elif mask_status == "no_mask":
                color = (0, 0, 255)  # Red
            else:
                color = (255, 255, 0)  # Yellow
                
            # Draw mask status text
            cv2.putText(frame, status_text, (x1, text_y), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    
    def draw_dynamic_adjustment_info(self, frame: np.ndarray, performance: Dict):
        """Display dynamic adjustment metrics"""
        info_lines = [
            f"Dynamic Scale: {self.performance_manager.current_processing_scale:.2f}",
            f"Faces: {performance.get('detection_count', 0)}",
            f"Avg Size: {performance.get('avg_face_size', 0):.0f}px",
            f"Quality: {performance.get('detection_quality', 0):.2f}",
        ]
        
        if performance.get('needs_adjustment', False):
            direction = performance.get('adjustment_direction', 0)
            if direction > 0:
                info_lines.append("Status: NEEDS INCREASE ↗")
            elif direction < 0:
                info_lines.append("Status: CAN DECREASE ↘")
            else:
                info_lines.append("Status: OPTIMAL ✓")
        
        # Draw background
        overlay = frame.copy()
        start_y = frame.shape[0] - len(info_lines) * 25 - 20
        end_y = frame.shape[0] - 10
        cv2.rectangle(overlay, (10, start_y), (300, end_y), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # Draw text
        for i, line in enumerate(info_lines):
            y_position = start_y + 20 + (i * 20)
            color = (0, 255, 255) if "NEEDS" in line else (255, 255, 255)
            cv2.putText(frame, line, (20, y_position),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    
    # ========== KEYBOARD CONTROLS (Using ControlHandler) ==========
    
    def handle_key_controls(self, key: int, display_frame: np.ndarray = None):
        """Comprehensive keyboard controls using ControlHandler"""
        # First, try to handle common controls
        if self.control_handler.handle_common_controls(key):
            return
        
        # Handle windowed-specific controls
        if key == ord('s'):
            # Save current frame
            timestamp = int(time.time())
            filename = f'captured_frame_{timestamp}.jpg'
            cv2.imwrite(filename, display_frame)
            print(f"💾 Frame saved: {filename}")
                    
        elif key == ord('i'):  # Toggle resize info display
            self.toggle_resize_info()
            
        elif key == ord('d'):  # Toggle debug mode
            self.toggle_debug_mode()
            
        elif key == ord('p'):  # Toggle performance stats
            self.toggle_performance_stats()
            
        elif key == ord('b'):  # Toggle detection debug
            self.toggle_detection_debug()
            
        elif key == ord('f'):  # Toggle save debug frames
            self.toggle_save_debug_frames()
            
        elif key == ord('w'):  # Decrease processing resolution
            old_w, old_h = self.processing_width, self.processing_height
            self.processing_width = max(320, self.processing_width - 160)
            self.processing_height = max(240, self.processing_height - 120)
            print(f"📐 Processing resolution: {old_w}x{old_h} → {self.processing_width}x{self.processing_height}")
            
        elif key == ord('e'):  # Increase processing resolution
            old_w, old_h = self.processing_width, self.processing_height
            self.processing_width = min(1920, self.processing_width + 160)
            self.processing_height = min(1080, self.processing_height + 120)
            print(f"📐 Processing resolution: {old_w}x{old_h} → {self.processing_width}x{self.processing_height}")
            
        elif key == ord('c'):  # Force increase processing scale
            old_scale = self.performance_manager.current_processing_scale
            self.performance_manager.current_processing_scale = min(
                self.performance_manager.max_processing_scale, 
                self.performance_manager.current_processing_scale + 0.2
            )
            print(f"🔼 Manual scale increase: {old_scale:.2f} → {self.performance_manager.current_processing_scale:.2f}")
            
        elif key == ord('v'):  # Force decrease processing scale
            old_scale = self.performance_manager.current_processing_scale
            self.performance_manager.current_processing_scale = max(
                self.performance_manager.min_processing_scale, 
                self.performance_manager.current_processing_scale - 0.2
            )
            print(f"🔽 Manual scale decrease: {old_scale:.2f} → {self.performance_manager.current_processing_scale:.2f}")
            
        elif key == ord('n'):  # Toggle between fixed and dynamic processing
            if self.processing_scale == 1.0:  # Currently using fixed resolution
                self.processing_scale = 0.0  # Switch to dynamic scaling
                print("🎯 Switched to DYNAMIC processing scale")
            else:  # Currently using dynamic scaling
                self.processing_scale = 1.0  # Switch to fixed resolution
                print("📐 Switched to FIXED processing resolution")
                
        elif key == ord('t'):  # Toggle face tracking (if implemented)
            self.toggle_face_tracking()
            
        # 🆕 NEW: Toggle person tracking with ByteTrack
        elif key == ord('y'):  
            self.toggle_person_tracking()
            
        elif key == ord('k'):  # Take snapshot with metadata
            self.take_annotated_snapshot(display_frame)
            
        # Display resize methods (1-8, 0)
        elif key == ord('1'):
            self.set_display_method("fit_to_screen")
        elif key == ord('2'):
            self.set_display_size(1280, 720, "fixed_size")
        elif key == ord('3'):
            self.set_display_scale(0.5)
        elif key == ord('4'):
            self.set_display_scale(0.75)
        elif key == ord('5'):
            self.set_display_scale(1.0)
        elif key == ord('6'): 
            self.set_display_scale(1.5)
        elif key == ord('7'):
            self.set_display_size(1280, 720, "crop")
        elif key == ord('8'):
            self.set_display_size(1280, 720, "letterbox")
        elif key == ord('0'):
            self.set_display_method("fit_to_screen")
            self.set_max_display_size(3840, 2160)
            print("📺 Displaying original size")
            
        # Number pad controls for fine-grained adjustments
        elif key == ord('.'):  # Fine increase processing interval
            old_interval = self.processing_interval
            self.processing_interval = min(self.processing_interval + 5, 60)
            print(f"⏱️  Processing interval: 1/{old_interval} → 1/{self.processing_interval}")
            
        elif key == ord(','):  # Fine decrease processing interval
            old_interval = self.processing_interval
            self.processing_interval = max(self.processing_interval - 5, 1)
            print(f"⏱️  Processing interval: 1/{old_interval} → 1/{self.processing_interval}")
    
    def print_control_reference(self):
        """Print comprehensive control reference using ControlHandler"""
        self.control_handler.print_control_reference(headless=False)
        # 🆕 NEW: Add ByteTrack controls
        print("🎯 ByteTrack Controls:")
        print("  [y] - Toggle person tracking with ByteTrack")
    
    # ========== MAIN PROCESSING LOOP ==========
    
    def run(self, source: str = "0"):
        """Main loop using StreamManager for frame capture with ByteTrack integration"""
        try:
            # Initialize and start stream using StreamManager
            print(f"🔄 Initializing stream: {source}")
            if not self.initialize_stream(source):
                print("❌ Failed to initialize stream")
                return
                
            self.running = True
            self.start_frame_capture()
            
            print("🎮 Starting processing with StreamManager")
            self.print_control_reference()
            
            last_results = []
            last_performance = {}
            
            while self.running:
                # Get frame from StreamManager
                original_frame = self.get_frame_for_processing()
                if original_frame is None:
                    time.sleep(0.005)
                    continue
                
                self.calculate_fps()
                self.update_dynamic_system()
                
                # Store original frame size
                original_h, original_w = original_frame.shape[:2]
                
                # Resize for processing using dynamic scale
                processing_frame = self.enhanced_resize_for_processing(original_frame)
                processed_h, processed_w = processing_frame.shape[:2]
                
                # Resize for display
                display_frame = self.resize_frame_for_display(original_frame)
                
                should_process = self.should_process_frame()
                
                if should_process:
                    # Process frame through face system
                    raw_results = self.face_system.process_frame(processing_frame)
                    
                    # 🆕 ENHANCED: Extract person detections for ByteTrack
                    person_detections = []
                    if hasattr(self.face_system, 'get_person_detections'):
                        # If face system provides person detections
                        person_detections = self.face_system.get_person_detections()
                    else:
                        # Extract from YOLO results if available
                        person_detections = self.extract_person_detections(raw_results)
                    
                    # 🎯 ENHANCED: Use tracking manager with ByteTrack integration
                    processing_results = self.tracking_manager.process_frame(
                        raw_results,
                        (original_h, original_w),
                        (processed_h, processed_w),
                        person_detections=person_detections,  # 🆕 NEW: Pass person detections
                        frame=original_frame                  # 🆕 NEW: Pass frame for visual tracking
                    )
                    
                    # Enhanced logging with image support
                    self.log_performance_data(processing_results, display_frame, original_frame)
                    
                    last_results = processing_results
                    self.processing_count += 1
                    
                    # Dynamic adjustment using PerformanceManager
                    if (self.performance_manager.dynamic_adjustment_enabled and 
                        self.frame_count % self.performance_manager.adaptive_check_interval == 0):
                        performance = self.analyze_detection_performance(processing_results, (original_h, original_w))
                        self.performance_manager.performance_history.append(performance)
                        last_performance = performance
                        self.apply_dynamic_adjustment(performance)
                
                # Use cached results if not processing this frame
                # Scale results to display coordinates using tracking manager
                display_results = self.tracking_manager.scale_to_display(
                    last_results, 
                    (original_h, original_w), 
                    display_frame.shape[:2]
                )
                
                # Enhanced drawing with tracking info
                self.draw_enhanced_results(display_frame, display_results, last_performance)
                self.draw_resize_info(display_frame)
                self.draw_debug_info(display_frame, display_results)
                self.draw_detection_debug(display_frame, display_results)
                
                cv2.imshow('Dynamic Face Recognition System', display_frame)
                
                # Handle key controls
                key = cv2.waitKey(1) & 0xFF
                self.handle_key_controls(key, display_frame)
                            
        except Exception as e:
            print(f"❌ Error in main loop: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.stop()
    
    # ========== SYSTEM MANAGEMENT ==========
    
    def stop(self):
        """Cleanup resources with image logging summary"""
        print("🛑 Stopping RealTimeProcessor...")
        
        # Print final log summary
        if self.logging_enabled and self.log_file:
            duration = datetime.datetime.now() - self.log_start_time
            print(f"\n📊 ENHANCED LOGGING SUMMARY:")
            print(f"   CSV entries: {self.log_counter}")
            print(f"   Violation images: {self.image_logger.saved_image_count}")
            print(f"   Server pushes: {self.image_logger.stats.get('server_pushes', 0)}")
            print(f"   Duration: {duration}")
            print(f"   CSV file: {self.log_file}")
            print(f"   Image folder: {self.image_logger.image_log_folder}")
        
        self.logging_enabled = False
        self.image_logging_enabled = False
        self.running = False
        
        # Clean up trackers
        if hasattr(self, 'tracking_manager'):
            self.tracking_manager.cleanup()
        
        # Clean up stream manager
        if hasattr(self, 'stream_manager'):
            self.stream_manager.release()
        
        cv2.destroyAllWindows()
        
        # Print final statistics
        print("\n📊 FINAL STATISTICS:")
        print(f"   Total frames: {self.frame_count}")
        print(f"   Processed frames: {self.processing_count}")
        print(f"   Final FPS: {self.fps:.1f}")
        if hasattr(self, 'tracking_manager'):
            stats = self.tracking_manager.get_tracking_stats()
            print(f"   Face tracks: {stats.get('face_tracker', {}).get('total_tracks', 0)}")
            print(f"   Person tracks: {stats.get('person_tracker', {}).get('active_tracks', 0)}")
        print(f"   Server pushes: {self.image_logger.stats.get('server_pushes', 0)}")
        print("🛑 System stopped gracefully")
    
    def get_stability_metrics(self) -> Dict:
        """Monitor system stability metrics including tracking"""
        base_metrics = {
            'frame_count': self.frame_count,
            'processing_count': self.processing_count,
            'fps': self.fps,
            'logging_enabled': self.logging_enabled,
            'log_entries': self.log_counter if hasattr(self, 'log_counter') else 0
        }
        
        # Add stream manager metrics
        if hasattr(self, 'stream_manager'):
            stream_info = self.stream_manager.get_stream_info()
            base_metrics.update({
                'stream_health': stream_info['health_metrics'],
                'stream_performance': stream_info['performance'],
                'stream_type': stream_info['stream_type']
            })
        
        # Add performance manager metrics
        if hasattr(self, 'performance_manager'):
            perf_stats = self.performance_manager.get_performance_stats()
            base_metrics.update({
                'current_scale': perf_stats['current_scale'],
                'dynamic_adjustment_enabled': perf_stats['dynamic_adjustment_enabled']
            })
        
        # Add tracking metrics
        if hasattr(self, 'tracking_manager'):
            tracking_stats = self.tracking_manager.get_tracking_stats()
            base_metrics.update({
                'tracking_active_tracks': tracking_stats['face_tracker'].get('total_tracks', 0),
                'person_tracking_active': tracking_stats['person_tracker'].get('active_tracks', 0),
                'tracking_enabled': tracking_stats['tracking_enabled'],
                'person_tracking_enabled': tracking_stats['person_tracking_enabled'],
                'fairness_enabled': tracking_stats['fairness_enabled'],
                'bytetrack_initialized': tracking_stats['person_tracker'].get('bytetrack_initialized', False)
            })
        
        # Add ImageLogger server push metrics
        if hasattr(self, 'image_logger'):
            base_metrics.update({
                'server_push_enabled': self.image_logger.server_push_enabled,
                'server_pushes': self.image_logger.stats.get('server_pushes', 0),
                'server_errors': self.image_logger.stats.get('server_errors', 0)
            })
        
        return base_metrics
    
    def print_stability_report(self):
        """Print current stability status"""
        metrics = self.get_stability_metrics()
        print("\n" + "="*50)
        print("📊 STABILITY REPORT - Enhanced System with ByteTrack")
        print("="*50)
        print(f"Frame Count: {metrics['frame_count']}")
        print(f"Processing Count: {metrics['processing_count']}")
        print(f"FPS: {metrics['fps']:.1f}")
        
        if 'stream_health' in metrics:
            print(f"Stream Health: {metrics['stream_health']['frame_count']} frames, {metrics['stream_health']['error_count']} errors")
        
        if 'current_scale' in metrics:
            print(f"Processing Scale: {metrics['current_scale']:.2f}")
        
        if 'tracking_active_tracks' in metrics:
            print(f"Face Tracks: {metrics['tracking_active_tracks']}")
            print(f"Person Tracks: {metrics['person_tracking_active']}")
            print(f"ByteTrack: {'ENABLED' if metrics['bytetrack_initialized'] else 'DISABLED'}")
        
        print(f"Logging: {'ENABLED' if metrics['logging_enabled'] else 'DISABLED'}")
        if metrics['logging_enabled']:
            print(f"Log Entries: {metrics['log_entries']}")
        
        print(f"Server Push: {'ENABLED' if metrics.get('server_push_enabled', False) else 'DISABLED'}")
        if metrics.get('server_push_enabled', False):
            print(f"Server Pushes: {metrics.get('server_pushes', 0)}")
            print(f"Server Errors: {metrics.get('server_errors', 0)}")
        print("="*50)