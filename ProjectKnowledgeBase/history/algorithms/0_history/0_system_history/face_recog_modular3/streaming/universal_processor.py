# streaming/universal_processor.py

"""
UniversalStreamProcessor - Consolidated stream processor for all modes
"""


""" 
Usage Example

# Single source windowed mode
processor = UniversalStreamProcessor(face_system, config, headless_mode=False)
processor.run("0")  # Camera index

# Single source headless mode
processor = UniversalStreamProcessor(face_system, config, headless_mode=True)
processor.run("rtsp://camera-url")

# Multi-source windowed mode
config['multi_source_mode'] = True
sources = {
    'cam1': {'url': '0', 'description': 'Front Camera'},
    'cam2': {'url': 'rtsp://url', 'description': 'Back Camera'}
}
processor = UniversalStreamProcessor(face_system, config, headless_mode=False)
processor.run(sources)

"""
import cv2
import time
import datetime
import csv
import threading
import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Union
from queue import Queue
import signal
import sys
import re
from urllib.parse import urlparse
from pathlib import Path
from threading import Lock, RLock, Event
import traceback
import gc

# Import modular components
from  face_recog_modular3.visualization.display_resizer import DisplayResizer
from  face_recog_modular3.processing.scene_analysis import ContextAwareDynamicScaling
from  face_recog_modular3.tracking.tracking_manager import TrackingManager
from  face_recog_modular3.alerting.alert_manager import DurationAwareAlertManager
from  face_recog_modular3.logging.image_logger import ImageLogger
from  face_recog_modular3.streaming.performance_manager import PerformanceManager
from  face_recog_modular3.streaming.frame_utils import FrameUtils
from  face_recog_modular3.streaming.control_handler import ControlHandler
from  face_recog_modular3.streaming.stream_manager import StreamManager


class UniversalStreamProcessor:
    """Unified processor for all streaming modes (headless, windowed, multi-source)"""
    
    def __init__(self, face_system, config: Dict, headless_mode: bool = False):
        """
        Initialize universal processor
        
        Args:
            face_system: The face recognition system
            config: Configuration dictionary
            headless_mode: If True, runs without display windows
        """
        self.face_system = face_system
        self.config = config
        self.headless_mode = headless_mode
        
        # 🎯 CRITICAL: Initialize shutdown event FIRST for thread safety
        self._shutdown_event = Event()
        self.running = False
        self._cleanup_completed = False
        
        # ========== CORE COMPONENTS ==========
        # Performance and scaling systems
        self.performance_manager = PerformanceManager(config)
        self.context_scaling = ContextAwareDynamicScaling(config)
        self.frame_utils = FrameUtils(config)
        
        # Stream and control systems
        self.control_handler = ControlHandler(self)
        
        # Conditional display components
        if not self.headless_mode:
            self.resizer = DisplayResizer()
            self.show_resize_info = False
        else:
            self.resizer = None
            self.show_resize_info = False

        # ========== PROCESSING STATE ==========
        # Frame and performance tracking
        self.original_frame_size = None        
        self.fps = 0
        self.frame_count = 0
        self.processing_count = 0
        self.start_time = time.time()
        self.last_fps_time = time.time()
        self.fps_frame_count = 0
        
        # Frame processing settings
        self.processing_interval = config.get('processing_interval', 5)
        self.last_processed_time = 0
        self.min_processing_delay = config.get('min_processing_delay', 0.1)
        self.processing_width = config.get('processing_width', 1600)
        self.processing_height = config.get('processing_height', 900)
        self.processing_scale = self.performance_manager.current_processing_scale
        
        # ========== MULTI-SOURCE SUPPORT ==========
        self.multi_source_mode = config.get('multi_source_mode', False)
        if self.multi_source_mode:
            # Multi-source structures
            self.stream_managers: Dict[str, StreamManager] = {}
            self.active_sources: List[str] = []
            self.source_configs: Dict[str, Dict] = {}
            self.tracking_managers: Dict[str, TrackingManager] = {}
            self.image_loggers: Dict[str, ImageLogger] = {}
            self.frame_queues: Dict[str, Queue] = {}
            
            # Multi-source configuration
            self.display_layout = config.get('display_layout', 'grid')
            self.max_display_sources = config.get('max_display_sources', 4)
            
            # Health monitoring configuration
            self.health_success_rate_threshold = config.get('health_success_rate_threshold', 0.3)
            self.stream_recovery_wait_time = config.get('stream_recovery_wait_time', 2.0)            
            
            # Thread safety
            self._stream_lock = RLock()
            self._tracking_lock = RLock()
            self._logging_lock = RLock()
        else:
            # Single source structures
            self.stream_manager = None
            self.tracking_manager = TrackingManager(config)
            self.image_logger = ImageLogger(config)
            self.frame_queue = Queue(maxsize=config.get('buffer_size', 3))
            
        # ========== LOGGING SYSTEM ==========
        self.logging_enabled = False
        self.image_logging_enabled = False
        self.log_file = None
        self.log_start_time = None
        self.log_interval = config.get('log_interval', 5)
        self.log_counter = 0
        self.log_columns = ['timestamp', 'identity', 'mask_status']
        self.current_log_session = None
        
        # ========== ALERT SYSTEM ==========
        self.alert_manager = DurationAwareAlertManager(config)
        self.sent_alerts = set()
        
        # ========== DEBUG CONTROLS ==========
        self.debug_mode = False
        self.show_detection_debug = False
        self.show_performance_stats = False if headless_mode else True
        self.show_source_health = False
        self.save_debug_frames = False
        self.debug_frame_count = 0
        self.max_debug_frames = 100
        
        # ========== VIOLATION VERIFICATION ==========
        self.violation_verification_enabled = config.get('violation_verification_enabled', False)
        self.min_violation_duration = config.get('min_violation_duration', 0.0)
        self.min_violation_frames = config.get('min_violation_frames', 0)
        self.violation_confidence_threshold = config.get('violation_confidence_threshold', 0.0)
        
        # Violation statistics
        self.violation_stats = {
            'total_detected': 0,
            'total_verified': 0,
            'total_logged': 0,
            'verified_logged': 0,
            'unverified_logged': 0,
            'false_positives_prevented': 0,
            'last_verified_time': None
        }
        
        # ========== THREAD MANAGEMENT ==========
        self.capture_thread = None
        self.health_monitor_thread = None
        self.maintenance_thread = None
        self._thread_stop_events = {}
        
        # ========== SIGNAL HANDLING ==========
        if not self.headless_mode:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        
        # ========== INITIALIZATION MESSAGE ==========
        print(f"🎯 UniversalStreamProcessor initialized in {'HEADLESS' if headless_mode else 'WINDOWED'} mode")
        if self.multi_source_mode:
            print("   📹 Multi-source mode: ENABLED")
        print(f"   ⚙️  Initial scale: {self.processing_scale:.2f}")
        print(f"   🎮 PerformanceManager: READY")
        print(f"   🎯 ContextAwareDynamicScaling: READY")
        
    # ========== CORE PROCESSING METHODS ==========
    
    def calculate_fps(self):
        """Calculate current FPS"""
        self.frame_count += 1
        self.fps_frame_count += 1
        
        current_time = time.time()
        elapsed = current_time - self.last_fps_time
        
        if elapsed >= 1.0:
            self.fps = self.fps_frame_count / elapsed
            self.fps_frame_count = 0
            self.last_fps_time = current_time
    
    def should_process_frame(self) -> bool:
        """Determine if current frame should be processed"""
        return self.frame_count % self.processing_interval == 0
    
    def enhanced_resize_for_processing(self, frame: np.ndarray) -> np.ndarray:
        """Resize frame for processing using performance-managed scale"""
        # Use FrameUtils for backward compatibility
        return self.frame_utils.process_frame_pipeline(
            frame=frame,
            current_scale=self.processing_scale,
            target_format='rgb'  # Most face systems expect RGB
        )
    
    def resize_frame_for_display(self, frame: np.ndarray) -> np.ndarray:
        """Apply resizing to frame for display"""
        if hasattr(self, 'resizer'):
            if self.original_frame_size is None:
                self.original_frame_size = frame.shape[:2]
            return self.resizer.resize_frame(frame)
        else:
            return frame
        
    
    def apply_performance_managed_scale(self, frame: np.ndarray, detection_results: List[Dict]) -> float:
        """Apply scale adjustment from PerformanceManager and ContextAwareDynamicScaling"""
        if detection_results:
            original_shape = frame.shape[:2] if len(frame.shape) == 3 else frame.shape
            performance_metrics = self.performance_manager.analyze_detection_performance(
                detection_results, original_shape
            )
            
            self.performance_manager.apply_dynamic_adjustment(performance_metrics)
            
            optimal_scale = self.context_scaling.compute_optimal_scale(
                frame, detection_results, performance_metrics
            )
            
            if self.context_scaling.apply_scale_adjustment(optimal_scale):
                self.processing_scale = self.context_scaling.current_scale
                print(f"📐 Scale updated to: {self.processing_scale:.2f}")
            else:
                self.processing_scale = self.performance_manager.current_processing_scale
        
        self.performance_manager.update_dynamic_system()
        
        self.processing_scale = max(
            self.performance_manager.min_processing_scale,
            min(self.performance_manager.max_processing_scale, self.processing_scale)
        )
        
        return self.processing_scale
    
    # ========== STREAM MANAGEMENT ==========
    
    def initialize_stream(self, source: Union[str, Dict]) -> bool:
        """Initialize stream(s) based on mode"""
        if self.multi_source_mode:
            return self._initialize_multi_source(source)
        else:
            return self._initialize_single_source(source)
    
    def _initialize_single_source(self, source: str) -> bool:
        """Initialize single source stream"""
        self.stream_manager = StreamManager(self.config)
        success = self.stream_manager.initialize_stream(source)
        if success:
            print(f"✅ Stream initialized: {source}")
        else:
            print(f"❌ Failed to initialize stream: {source}")
        return success
    
    def _initialize_multi_source(self, sources_config: Dict) -> bool:
        """Initialize multiple sources"""
        success_count = 0
        for source_id, config in sources_config.items():
            with self._stream_lock:
                if self._add_source_internal(source_id, config):
                    success_count += 1
        
        print(f"✅ Initialized {success_count}/{len(sources_config)} sources")
        return success_count > 0
    
    # ========== MULTI-SOURCE MANAGEMENT ==========
    
    def _add_source_internal(self, source_id: str, config: Dict) -> bool:
        """Internal method to add a source with CCTV naming"""
        try:
            # Store configuration
            self.source_configs[source_id] = config
            
            # 🆕 Calculate and store CCTV name
            cctv_name = self._get_dynamic_cctv_name(source_id)
            self.source_configs[source_id]['cctv_name'] = cctv_name
            
            # Initialize stream manager
            stream_manager = StreamManager(config)
            success = stream_manager.initialize_stream(config['url'])
            
            if not success:
                print(f"❌ Failed to initialize stream for {source_id}")
                return False
            
            # Store managers
            self.stream_managers[source_id] = stream_manager
            self.frame_queues[source_id] = Queue(maxsize=config.get('buffer_size', 3))
            
            # Initialize tracking manager
            tracking_config = config.get('tracking', self.config.get('tracking', {}))
            self.tracking_managers[source_id] = TrackingManager(tracking_config)
            
            # 🆕 Pre-initialize image logger if logging is enabled
            if self.image_logging_enabled and self.current_log_session:
                logger = ImageLogger(self.config)
                base_filename = f"{self.current_log_session}_{cctv_name}"
                logger.setup_image_logging(base_filename)
                self.image_loggers[source_id] = logger
            
            # Add to active sources
            self.active_sources.append(source_id)
            
            # Start capture
            stream_manager.start_capture()
            
            print(f"✅ Added source: {source_id} ({cctv_name})")
            return True
            
        except Exception as e:
            print(f"❌ Failed to add source {source_id}: {e}")
            traceback.print_exc()
            return False
        
    def _add_source_overlay(self, frame: np.ndarray, source_id: str, results: List[Dict]) -> np.ndarray:
        """Add source identifier overlay to frame with CCTV name """

        if self.violation_verification_enabled:
            verified_count = sum(1 for r in results if r.get('violation_verified', False))
            if verified_count > 0:
                cv2.putText(frame, f"Verified: {verified_count}", (10, 110), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # Draw results on this specific frame
        self.draw_results(frame, results)
        
        return frame
        
    # ========== MAIN PROCESSING LOOP ==========
    
    def run(self, source: Union[str, Dict] = "0"):
        """Main processing loop"""
        try:
            # Initialize stream(s)
            if not self.initialize_stream(source):
                print("❌ Failed to initialize stream(s)")
                return
            
            # Start background threads
            if not self.headless_mode:
                self.start_background_threads()
            
            print("🎮 Starting processing loop...")
            if not self.headless_mode:
                self.control_handler.print_control_reference(headless=False)
            else:
                self.control_handler.print_control_reference(headless=True)
            
            # Set running flag
            self.running = True
            
            # Main loop
            if self.multi_source_mode:
                self._run_multi_source_loop()
            else:
                self._run_single_source_loop()
                
        except KeyboardInterrupt:
            print("🛑 Received KeyboardInterrupt")
        except Exception as e:
            print(f"❌ Error in processing loop: {e}")
            traceback.print_exc()
        finally:
            self.close()
        
    def _run_single_source_loop(self):
        """Single source processing loop - SIMPLIFIED VERSION"""
        last_results = []
        last_performance = {}
        
        while self.running:
            # Get frame from stream manager
            frame = self.stream_manager.get_frame(timeout=0.05)
            if frame is None:
                time.sleep(0.005)
                continue
            
            self.calculate_fps()
            self.update_dynamic_system()
            
            # Resize for processing
            processing_frame = self.enhanced_resize_for_processing(frame)
            original_h, original_w = frame.shape[:2]
            processed_h, processed_w = processing_frame.shape[:2]
            
            # Check if we should process this frame
            if self.should_process_frame():
                # Process frame
                raw_results = self.face_system.process_frame(processing_frame)
                
                # Apply tracking with simplified parameters
                processing_results = self.tracking_manager.process_frame(
                    recognition_results=raw_results,
                    original_shape=(original_h, original_w),
                    processed_shape=(processed_h, processed_w)
                )
                
                # 🆕 CRITICAL: Use robust_process_multi_source_frame approach for single source
                # This ensures consistent logging across both modes
                source_id = "single_source"
                controlled_results = self.robust_process_multi_source_frame(source_id, frame)
                
                last_results = controlled_results
                self.processing_count += 1
                
                # Dynamic adjustment
                if (self.performance_manager.dynamic_adjustment_enabled and 
                    self.frame_count % self.performance_manager.adaptive_check_interval == 0):
                    performance = self.performance_manager.analyze_detection_performance(
                        controlled_results, (original_h, original_w)
                    )
                    self.performance_manager.performance_history.append(performance)
                    last_performance = performance
                    self.performance_manager.apply_dynamic_adjustment(performance)
            
            # Scale results to display
            display_results = self.tracking_manager.scale_to_display(
                last_results, 
                (original_h, original_w), 
                frame.shape[:2]
            )
            
            # Handle display
            if not self.headless_mode:
                display_frame = self.resize_frame_for_display(frame)
                self.draw_enhanced_results(display_frame, display_results, last_performance)
                self.draw_resize_info(display_frame)
                self.draw_debug_info(display_frame, display_results)
                self.draw_detection_debug(display_frame, display_results)
                
                cv2.imshow('Dynamic Face Recognition System', display_frame)
                
                # Handle keyboard input
                key = cv2.waitKey(1) & 0xFF
                if key != 255:
                    self.handle_key_controls(key, display_frame)
            else:
                # Headless mode - just process
                if time.time() - self.last_fps_time >= 5.0:
                    print(f"📊 Headless Status: Frame {self.frame_count}, FPS: {self.fps:.1f}, "
                        f"Processed: {self.processing_count}, Faces: {len(display_results)}")
                
                # Minimal keyboard check (non-blocking)
                try:
                    key = cv2.waitKey(1) & 0xFF
                    if key != 255:
                        self.handle_key_controls(key)
                except:
                    pass
                    
    def _run_multi_source_loop(self):
        """Multi-source processing loop with proper error handling"""
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        while self.running and consecutive_errors < max_consecutive_errors:
            try:
                if self._shutdown_event.is_set():
                    break
                
                # Get frames from all sources
                source_frames = self.get_multi_source_frames()
                
                if not any(frame is not None for frame in source_frames.values()):
                    time.sleep(0.05)
                    consecutive_errors += 1
                    continue
                
                consecutive_errors = 0
                
                # Process each source
                all_results = {}
                for source_id, frame in source_frames.items():
                    if frame is not None:
                        try:
                            # Use the new robust method
                            results = self.robust_process_multi_source_frame(source_id, frame)
                            all_results[source_id] = results
                        except Exception as e:
                            print(f"⚠️ Processing error for {source_id}: {e}")
                            all_results[source_id] = []
                
                # Create display
                if not self.headless_mode:
                    display_frame = self.create_multi_source_display(source_frames, all_results)
                    
                    # Show the frame
                    if display_frame is not None and display_frame.size > 0:
                        cv2.imshow('Multi-Source Face Recognition', display_frame)
                    
                    # Handle keyboard input
                    key = cv2.waitKey(1) & 0xFF
                    if key != 255:
                        self.handle_key_controls(key)
                
                self.calculate_fps()
                
            except Exception as e:
                consecutive_errors += 1
                print(f"❌ Main loop error: {e}")
                traceback.print_exc()
                time.sleep(1)
                
    def get_multi_source_frames(self, timeout: float = 0.1) -> Dict[str, Optional[np.ndarray]]:
        """Get latest frames from all active sources"""
        frames = {}
        
        for source_id in self.active_sources:
            try:
                frame = self.stream_managers[source_id].get_frame(timeout)
                frames[source_id] = frame
            except Exception as e:
                if self.config.get('debug', {}).get('verbose', False):
                    print(f"⚠️ Failed to get frame from {source_id}: {e}")
                frames[source_id] = None
        
        return frames
    
    def monitor_stream_health(self):
        """Monitor and recover unhealthy streams"""
        unhealthy_sources = []
        
        for source_id, stream_manager in self.stream_managers.items():
            try:
                health = stream_manager.get_stream_info()
                success_rate = stream_manager.get_success_rate()
                
                # Check stream health
                if not stream_manager.is_healthy() or success_rate < self.health_success_rate_threshold:
                    unhealthy_sources.append(source_id)
                    print(f"⚠️ Unhealthy stream detected: {source_id} (success rate: {success_rate:.1%})")
                    
            except Exception as e:
                print(f"❌ Health check error for {source_id}: {e}")
                unhealthy_sources.append(source_id)
        
        # Attempt recovery for unhealthy sources
        for source_id in unhealthy_sources:
            self._attempt_stream_recovery(source_id)
    
    def _attempt_stream_recovery(self, source_id: str) -> bool:
        """Attempt to recover a failed stream"""
        if source_id not in self.source_configs:
            print(f"❌ Cannot recover {source_id}: no configuration")
            return False
        
        print(f"🔄 Attempting recovery for {source_id}")
        
        try:
            # Save configuration BEFORE removal
            source_config = self.source_configs[source_id].copy()
            
            # Remove the unhealthy stream
            self._remove_source_internal(source_id)
            
            # Wait before reconnection
            time.sleep(self.stream_recovery_wait_time)
            
            # Re-add the source using saved configuration
            with self._stream_lock:
                return self._add_source_internal(source_id, source_config)
                
        except Exception as e:
            print(f"❌ Stream recovery error for {source_id}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _remove_source_internal(self, source_id: str):
        """Internal method to remove a source"""
        try:
            # Stop stream manager
            if source_id in self.stream_managers:
                stream_manager = self.stream_managers[source_id]
                if hasattr(stream_manager, 'stop_capture'):
                    stream_manager.stop_capture()
                time.sleep(0.1)
                if hasattr(stream_manager, 'release'):
                    stream_manager.release()
                del self.stream_managers[source_id]
            
            # Clean up tracking manager
            if source_id in self.tracking_managers:
                tracker = self.tracking_managers[source_id]
                if hasattr(tracker, 'cleanup'):
                    tracker.cleanup()
                del self.tracking_managers[source_id]
            
            # Clean up ImageLogger
            if source_id in self.image_loggers:
                logger = self.image_loggers[source_id]
                if hasattr(logger, 'close'):
                    logger.close()
                del self.image_loggers[source_id]
            
            # Clean up frame queue
            if source_id in self.frame_queues:
                queue = self.frame_queues[source_id]
                while not queue.empty():
                    try:
                        queue.get_nowait()
                    except:
                        break
                del self.frame_queues[source_id]
            
            # Remove from other collections
            if source_id in self.active_sources:
                self.active_sources.remove(source_id)
            
            if source_id in self.source_configs:
                del self.source_configs[source_id]
            
            print(f"✅ Removed source: {source_id}")
            return True
            
        except Exception as e:
            print(f"⚠️ Error removing source {source_id}: {e}")
            return False
    
    def _add_source_internal(self, source_id: str, config: Dict) -> bool:
        """Internal method to add a source"""
        try:
            # Store configuration
            self.source_configs[source_id] = config
            
            # Initialize stream manager
            stream_manager = StreamManager(config)
            success = stream_manager.initialize_stream(config['url'])
            
            if not success:
                print(f"❌ Failed to initialize stream for {source_id}")
                return False
            
            # Store managers
            self.stream_managers[source_id] = stream_manager
            self.frame_queues[source_id] = Queue(maxsize=config.get('buffer_size', 3))
            
            # Initialize tracking manager
            tracking_config = config.get('tracking', self.config.get('tracking', {}))
            self.tracking_managers[source_id] = TrackingManager(tracking_config)
            
            # Add to active sources
            self.active_sources.append(source_id)
            
            # Start capture
            stream_manager.start_capture()
            
            print(f"✅ Added source: {source_id}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to add source {source_id}: {e}")
            traceback.print_exc()
            return False
    # ========== VISUALIZATION METHODS ==========
        
    def draw_results(self, frame: np.ndarray, results: List[Dict], performance: Dict = None):
        """
        Draw bounding boxes and labels with enhanced identity transparency.
        Always shows known identities, shows "Verifying" for unknown during unverified phase.
        """
        for result in results:
            x1, y1, x2, y2 = result['bbox']
            
            identity = result.get('identity', 'Unknown')
            rec_conf = result.get('recognition_confidence', 0.0)
            
            # Get progressive mask data with fallback
            progressive_data = result.get('progressive_mask_data', {})
            
            if progressive_data:
                # Use progressive detection data
                mask_status = progressive_data.get('mask_status', result.get('mask_status', 'unknown'))
                mask_confidence = progressive_data.get('mask_confidence', result.get('mask_confidence', 0.0))
                verification_progress = progressive_data.get('verification_progress', 0.0)
                frames_processed = progressive_data.get('frames_processed', 0)
                is_stable = progressive_data.get('is_stable', False)
            else:
                # Fallback to raw data
                mask_status = result.get('mask_status', 'unknown')
                mask_confidence = result.get('mask_confidence', 0.0)
                verification_progress = 0.0
                frames_processed = 0
                is_stable = False
            
            violation_verified = result.get('violation_verified', False)
            
            # 🟡 VERIFYING STATE (Orange)
            if mask_status == 'verifying':
                color = (127, 0, 15)  # Orange
                verification_text = f" ⏳ {verification_progress:.0%}" if verification_progress > 0 else " ⏳"
                
                # Show identity during verification if known
                if identity and identity != "Unknown":
                    base_label = f"{identity}"
                    confidence_text = f" ({rec_conf:.2f})"
                else:
                    base_label = "Verifying"
                    confidence_text = ""
                
                full_label = f"{base_label}{confidence_text} | VERIFYING{verification_text}"
                
                # Draw bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                
                # Draw label background
                label_size = cv2.getTextSize(full_label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                            (x1 + label_size[0], y1), color, -1)
                
                # Draw label text
                cv2.putText(frame, full_label, (x1, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                # Draw progress bar
                if verification_progress > 0:
                    bar_width = x2 - x1
                    progress_width = int(bar_width * verification_progress)
                    cv2.rectangle(frame, (x1, y2 + 5), (x1 + progress_width, y2 + 10), (255, 255, 0), -1)
                    cv2.rectangle(frame, (x1, y2 + 5), (x2, y2 + 10), (255, 255, 255), 1)
                
                continue  # Skip the rest
            
            # 🟢 MASK STATE (Green)
            elif mask_status == "mask":
                color = (0, 255, 0)  # Green
                
                if identity and identity != "Unknown":
                    base_label = f"{identity}"
                    confidence_text = f" ({rec_conf:.2f})"
                else:
                    base_label = "Masked"
                    confidence_text = ""
                
                full_label = f"{base_label}{confidence_text} | MASK"
                
                # Draw bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                
                # Draw label background
                label_size = cv2.getTextSize(full_label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                            (x1 + label_size[0], y1), color, -1)
                
                # Draw label text
                cv2.putText(frame, full_label, (x1, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                continue
            
            # 🔴 NO_MASK STATE (Red/Orange) - IMPLEMENTED PROPOSED ALTERATION
            elif mask_status == 'no_mask':
                # Determine color and verification indicator
                color = (0, 0, 255)  # Red
                verification_text = ""
                box_thickness = 2
                
                if violation_verified:
                    color = (0, 0, 255)  # Red for verified violations
                    verification_text = " ✅"
                    box_thickness = 2
                
                # === PROPOSED ALTERATION: TRANSPARENT IDENTITY DISPLAY ===
                
                # 1. Check if the identity is known (No need to hide identity)
                if identity and identity != "Unknown":
                    base_label = f"{identity}"
                    confidence_text = f" ({rec_conf:.2f})"
                    
                # 2. Check if we are still verifying the *violation* and identity is unknown
                elif not violation_verified:
                    # Display "Verifying" if identity is unknown/none, removing prior suppression
                    base_label = "Verifying" 
                    confidence_text = ""
                    
                # 3. Final Fallback: Identity is unknown, but the violation is verified
                else:
                    base_label = "No Mask"
                    confidence_text = ""
                
                # =========================================================
                
                full_label = f"{base_label}{confidence_text} | NO_MASK{verification_text}"
                
                # Draw bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, box_thickness)
                
                # Draw label background
                label_size = cv2.getTextSize(full_label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                            (x1 + label_size[0], y1), color, -1)
                
                # Draw label text
                cv2.putText(frame, full_label, (x1, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                continue
            
            # ⚫ DEFAULT/UNKNOWN STATE (Gray)
            else:
                color = (135, 206, 235)  # Gray
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                default_label = f"Unknown: {mask_status}"
                
                label_size = cv2.getTextSize(default_label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                            (x1 + label_size[0], y1), color, -1)
                cv2.putText(frame, default_label, (x1, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                                                                                        
    def draw_enhanced_results(self, frame: np.ndarray, results: List[Dict], performance: Dict = None):
        """
        Enhanced drawing with tracking information - COMPATIBILITY WRAPPER
        This maintains compatibility with existing code that expects 3 parameters
        """
        # Simply delegate to the main draw_results method
        self.draw_results(frame, results, performance)
                                            
    def draw_resize_info(self, frame: np.ndarray):
        """Display resize information on frame"""
        if not self.show_resize_info:
            return
        
        original_h, original_w = self.original_frame_size or frame.shape[:2]
        display_h, display_w = frame.shape[:2]
        
        info_lines = [
            f"Original: {original_w}x{original_h}",
            f"Display: {display_w}x{display_h}",
            f"Sources: {len(self.active_sources)}",
            f"Layout: {self.display_layout}"
        ]
        
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 130), (350, 130 + len(info_lines) * 25 + 10), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        for i, line in enumerate(info_lines):
            y_position = 150 + (i * 25)
            cv2.putText(frame, line, (20, y_position),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    def draw_debug_info(self, frame: np.ndarray, results: List[Dict]):
        """Draw comprehensive debug information with identity control status"""
        if not self.debug_mode and not self.show_performance_stats:
            return
            
        lines = []
        if self.show_performance_stats:
            lines.extend([
                f"FPS: {self.fps:.1f}",
                f"Frame: {self.frame_count}",
                f"Sources: {len(self.active_sources)}",
                f"Active Tracks: {len(results)}"
            ])
        
        if self.debug_mode:
            lines.extend([
                f"Debug: ON",
                f"Sources: {list(self.active_sources)}"
            ])
        
        # 🆕 ENHANCED: Add identity control and verification stats
        if self.violation_verification_enabled:
            verified_count = sum(1 for r in results if r.get('violation_verified', False))
            unverified_count = sum(1 for r in results if r.get('mask_status') == 'no_mask' and not r.get('violation_verified', False))
            hidden_identities = sum(1 for r in results if r.get('identity_hidden', False))
            
            lines.extend([
                f"Verified: {verified_count}",
                f"Unverified: {unverified_count}",
                f"Hidden IDs: {hidden_identities}",
                f"Total Logged: {self.violation_stats['total_logged']}"
            ])
        
        if not lines:
            return
            
        # Draw background for all info
        overlay = frame.copy()
        start_y = 10
        end_y = start_y + len(lines) * 25 + 20
        cv2.rectangle(overlay, (10, start_y), (350, end_y), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # Draw info
        for i, line in enumerate(lines):
            y_position = 30 + (i * 25)
            color = (0, 255, 0) if "FPS" in line else (255, 255, 255)
            cv2.putText(frame, line, (20, y_position),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
       
    
    # ========== CONTROL METHODS ==========
    
    def handle_key_controls(self, key: int, display_frame: np.ndarray = None):
        """Handle keyboard controls"""
        if key == ord('q'):
            self.running = False
            print("🛑 Quitting...")
            return
        
        # Delegate to control handler
        if self.control_handler.handle_common_controls(key):
            return
        
        # Mode-specific controls
        if self.multi_source_mode:
            self._handle_multi_source_controls(key)
        elif not self.headless_mode:
            self._handle_windowed_controls(key, display_frame)
    
    def _handle_multi_source_controls(self, key: int):
        """Handle multi-source specific controls"""
        if key == ord('m'):
            layouts = ['grid', 'horizontal', 'vertical']
            current_idx = layouts.index(self.display_layout)
            self.display_layout = layouts[(current_idx + 1) % len(layouts)]
            print(f"🔄 Display layout: {self.display_layout}")
        elif key == ord('n'):
            self.show_source_health = not self.show_source_health
            status = "ON" if self.show_source_health else "OFF"
            print(f"📊 Source health display: {status}")
        elif key == ord('0'):
            self.print_source_health_report()
        elif key == ord('l'):
            self.toggle_logging()
        elif key == ord('L'):
            self.print_multi_source_logging_status()
    
    def _handle_windowed_controls(self, key: int, display_frame: np.ndarray):
        """Handle windowed-specific controls"""
        if key == ord('s'):
            timestamp = int(time.time())
            filename = f'captured_frame_{timestamp}.jpg'
            cv2.imwrite(filename, display_frame)
            print(f"💾 Frame saved: {filename}")
        elif key == ord('i'):
            self.show_resize_info = not self.show_resize_info
            status = "ON" if self.show_resize_info else "OFF"
            print(f"📊 Resize info display: {status}")
        elif key == ord('d'):
            self.debug_mode = not self.debug_mode
            status = "ON" if self.debug_mode else "OFF"
            print(f"🐛 Debug mode: {status}")
        elif key == ord('p'):
            self.show_performance_stats = not self.show_performance_stats
            status = "ON" if self.show_performance_stats else "OFF"
            print(f"📈 Performance stats: {status}")
    
    # ========== LOGGING METHODS ==========
    
    def setup_logging(self, filename: str = None):
        """Setup CSV logging"""
        try:
            if filename is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"face_recognition_log_{timestamp}.csv"
            
            self.log_file = filename
            self.log_start_time = datetime.datetime.now()
            self.log_counter = 0
            
            with open(self.log_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'identity', 'mask_status', 
                                'recognition_confidence', 'detection_confidence'])
            
            self.logging_enabled = True
            print(f"📝 Logging enabled: {self.log_file}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to setup logging: {e}")
            self.logging_enabled = False
            return False
        
    def setup_multi_source_logging(self, session_name: str = None):
        """
        Initialize logging for all active sources with session management
        
        Args:
            session_name: Custom session name, auto-generated if None
        """
        if not self.multi_source_mode:
            print("⚠️ setup_multi_source_logging called but not in multi-source mode")
            return
        
        if session_name is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            session_name = f"session_{timestamp}"
        
        self.current_log_session = session_name
        print(f"📁 Setting up logging session: {session_name}")
        
        # Ensure image logging is enabled
        if not self.image_logging_enabled:
            self.image_logging_enabled = True
            print("🔄 Auto-enabled image logging for multi-source mode")
        
        # Setup loggers for each active source
        with self._logging_lock:
            for source_id in self.active_sources:
                self._setup_source_logger(source_id, session_name)
        
        print(f"✅ Multi-source logging setup complete for {len(self.active_sources)} sources")

    def _setup_source_logger(self, source_id: str, session_name: str):
        """Initialize logger for a specific source"""
        try:
            # Create base filename
            cctv_name = self._get_dynamic_cctv_name(source_id)
            base_filename = f"{session_name}_{cctv_name}"
            
            # Create or get existing logger
            if source_id not in self.image_loggers:
                self.image_loggers[source_id] = ImageLogger(self.config)
            
            # Initialize the logger's file system
            self.image_loggers[source_id].setup_image_logging(base_filename)
            
            # Store CCTV name in config for future use
            if source_id in self.source_configs:
                self.source_configs[source_id]['cctv_name'] = cctv_name
            
            print(f"   ✅ {source_id}: {cctv_name}")
            
        except Exception as e:
            print(f"❌ Failed to setup logger for {source_id}: {e}")
            traceback.print_exc()        
    
    def log_performance_data(self, results: List[Dict], display_frame: np.ndarray = None, 
                           original_frame: np.ndarray = None):
        """Enhanced logging with synchronized voice alerts"""
        if not self.logging_enabled:
            return
        
        # Only log every X processed frames
        if self.processing_count % self.log_interval != 0:
            return
        
        try:
            # CSV logging
            log_entries = self.collect_log_data(results)
            if log_entries:
                self.write_log_entries(log_entries)
                print(f"📝 CSV: Logged {len(log_entries)} face entries")
            
            # Image logging for violations
            if (self.image_logging_enabled and 
                self.has_mask_violations(results) and
                self.processing_count % self.image_logger.image_log_interval == 0):
                
                print("🚨 ATTEMPTING TO SAVE VIOLATION IMAGE")
                
                current_time = time.time()
                if current_time - self.image_logger.last_image_save_time >= self.image_logger.min_save_interval:
                    
                    frame_to_save = original_frame if original_frame is not None else display_frame
                    if frame_to_save is not None:
                        success, base64_data = self.image_logger.save_annotated_frame(
                            frame_to_save, results, original_frame
                        )
                        if success:
                            print(f"✅ Image saved! Total: {self.image_logger.saved_image_count}")
                    
        except Exception as e:
            print(f"❌ Enhanced logging error: {e}")
    
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
    
    def has_mask_violations(self, results: List[Dict]) -> bool:
        """Check if frame contains mask violations"""
        if not results:
            return False
        
        for result in results:
            mask_status = result.get('mask_status')
            mask_conf = result.get('mask_confidence', 0)
            
            if mask_status == 'no_mask' and mask_conf > 0.3:
                return True
        
        return False
    
    # ========== THREAD MANAGEMENT ==========
    
    def start_background_threads(self):
        """Start background monitoring threads"""
        if self.multi_source_mode:
            self._start_multi_source_threads()
    
    def _start_multi_source_threads(self):
        """Start multi-source background threads"""
        # Health monitoring
        if not hasattr(self, 'health_monitor_thread') or not self.health_monitor_thread or not self.health_monitor_thread.is_alive():
            self.health_monitor_thread = threading.Thread(
                target=self._health_monitor_worker,
                daemon=True,
                name="health_monitor"
            )
            self.health_monitor_thread.start()
            print("🏥 Health monitoring started")
        
        # Maintenance thread
        if not hasattr(self, 'maintenance_thread') or not self.maintenance_thread or not self.maintenance_thread.is_alive():
            self.maintenance_thread = threading.Thread(
                target=self._maintenance_worker,
                daemon=True,
                name="maintenance_worker"
            )
            self.maintenance_thread.start()
            print("🧹 Periodic maintenance started")
    
    def _health_monitor_worker(self):
        """Background health monitoring"""
        time.sleep(0.5)
        
        while self.running:
            try:
                self.monitor_stream_health()
                time.sleep(self.config.get('health_check_interval', 30.0))
            except Exception as e:
                print(f"❌ Health monitoring error: {e}")
                traceback.print_exc()
                time.sleep(60)
    
    def _maintenance_worker(self):
        """Background maintenance tasks"""
        time.sleep(0.5)
        
        last_maintenance = time.time()
        maintenance_interval = self.config.get('maintenance_interval', 300.0)
        
        while self.running:
            current_time = time.time()
            if current_time - last_maintenance >= maintenance_interval:
                try:
                    self.optimize_memory_usage()
                    last_maintenance = current_time
                except Exception as e:
                    print(f"❌ Maintenance error: {e}")
            
            time.sleep(60)
    
    # ========== CLEANUP METHODS ==========
    
    def close(self):
        """Comprehensive cleanup"""
        if self._cleanup_completed:
            return
        
        print("🧹 Starting comprehensive cleanup...")
        
        # Signal shutdown
        self.running = False
        self._shutdown_event.set()
        
        # Stop all threads
        self._stop_all_threads_safe()
        
        # Close all resources
        if self.multi_source_mode:
            with self._stream_lock:
                self._close_all_multi_source_resources()
        else:
            self._close_single_source_resources()
        
        # Release OpenCV resources
        if not self.headless_mode:
            try:
                cv2.destroyAllWindows()
                cv2.waitKey(1)
            except:
                pass
        
        # Force garbage collection
        self._force_garbage_collection()
        
        # Print final statistics
        self.print_final_statistics()
        
        self._cleanup_completed = True
        print("✅ Cleanup completed")
    
    def _stop_all_threads_safe(self):
        """Stop all background threads safely"""
        threads_to_stop = [
            ('health_monitor_thread', 5.0),
            ('maintenance_thread', 5.0),
            ('capture_thread', 5.0),
        ]
        
        for thread_name, timeout in threads_to_stop:
            thread = getattr(self, thread_name, None)
            if thread and thread.is_alive():
                print(f"⏳ Stopping {thread_name}...")
                thread.join(timeout=timeout)
                if thread.is_alive():
                    print(f"⚠️ {thread_name} did not stop gracefully")
    
    def _close_all_multi_source_resources(self):
        """Close all multi-source resources"""
        # Close stream managers
        source_ids = list(self.stream_managers.keys())
        for source_id in source_ids:
            try:
                stream_manager = self.stream_managers.get(source_id)
                if stream_manager:
                    if hasattr(stream_manager, 'stop_capture'):
                        stream_manager.stop_capture()
                    time.sleep(0.1)
                    if hasattr(stream_manager, 'release'):
                        stream_manager.release()
                self.stream_managers.pop(source_id, None)
            except Exception as e:
                print(f"⚠️ Error closing stream {source_id}: {e}")
        
        # Close tracking managers
        for source_id, tracker in list(self.tracking_managers.items()):
            try:
                if hasattr(tracker, 'cleanup'):
                    tracker.cleanup()
                self.tracking_managers.pop(source_id, None)
            except Exception as e:
                print(f"⚠️ Error cleaning up tracker {source_id}: {e}")
        
        # Close image loggers
        for source_id, logger in list(self.image_loggers.items()):
            try:
                if hasattr(logger, 'close'):
                    logger.close()
                self.image_loggers.pop(source_id, None)
            except Exception as e:
                print(f"⚠️ Error cleaning up logger {source_id}: {e}")
        
        # Clear all data structures
        self._clear_all_queues()
    
    def _close_single_source_resources(self):
        """Close single source resources"""
        if self.stream_manager:
            try:
                self.stream_manager.release()
            except:
                pass
        
        if self.tracking_manager:
            try:
                self.tracking_manager.cleanup()
            except:
                pass
        
        if self.image_logger:
            try:
                if hasattr(self.image_logger, 'close'):
                    self.image_logger.close()
            except:
                pass
        
        # Clear queues
        if hasattr(self, 'frame_queue'):
            while not self.frame_queue.empty():
                try:
                    self.frame_queue.get_nowait()
                except:
                    break
    
    def _clear_all_queues(self):
        """Clear all queues"""
        if self.multi_source_mode:
            for queue in self.frame_queues.values():
                while not queue.empty():
                    try:
                        queue.get_nowait()
                    except:
                        break
        elif hasattr(self, 'frame_queue'):
            while not self.frame_queue.empty():
                try:
                    self.frame_queue.get_nowait()
                except:
                    break
    
    def _force_garbage_collection(self):
        """Force garbage collection"""
        try:
            collected = gc.collect()
            print(f"🧠 Garbage collection: {collected} objects collected")
        except:
            pass
    
    # ========== UTILITY METHODS ==========
    
    def get_stability_metrics(self) -> Dict[str, Any]:
        """Get system stability metrics"""
        metrics = {
            'frame_count': self.frame_count,
            'processing_count': self.processing_count,
            'fps': self.fps,
            'processing_scale': self.processing_scale,
            'logging_enabled': self.logging_enabled,
            'log_entries': self.log_counter,
            'headless_mode': self.headless_mode,
            'multi_source_mode': self.multi_source_mode,
        }
        
        # Add performance manager metrics
        if hasattr(self, 'performance_manager'):
            perf_stats = self.performance_manager.get_performance_stats()
            metrics.update({
                'current_scale': perf_stats.get('current_scale', 1.0),
                'dynamic_adjustment_enabled': perf_stats.get('dynamic_adjustment_enabled', False)
            })
        
        return metrics
    
    def print_final_statistics(self):
        """Print final processing statistics"""
        print("\n" + "="*60)
        print("📊 FINAL PROCESSING STATISTICS")
        print("="*60)
        
        print(f"🎯 Performance:")
        print(f"   Total frames: {self.frame_count}")
        print(f"   Processed frames: {self.processing_count}")
        print(f"   Final FPS: {self.fps:.1f}")
        print(f"   Final scale: {self.processing_scale:.2f}")
        
        if self.multi_source_mode:
            print(f"\n📹 Sources:")
            print(f"   Active sources: {len(self.active_sources)}")
        
        if self.logging_enabled:
            print(f"\n📝 Logging:")
            print(f"   CSV entries: {self.log_counter}")
        
        if self.image_logging_enabled:
            if self.multi_source_mode:
                total_images = sum(logger.saved_image_count for logger in self.image_loggers.values())
                print(f"   Total images saved: {total_images}")
            else:
                print(f"   Images saved: {self.image_logger.saved_image_count}")
        
        print("="*60)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        print(f"🛑 Received signal {signum}, shutting down gracefully...")
        self.close()
        sys.exit(0)
    
    # ========== CONTEXT MANAGER SUPPORT ==========
    
    def __enter__(self):
        """Support context manager protocol"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Automatic cleanup when used with 'with' statement"""
        self.close()
        return False
    
    def __del__(self):
        """Fallback cleanup in destructor"""
        try:
            if not self._cleanup_completed:
                self.close()
        except:
            pass
    
    # ========== SUPPORTING HELPER METHOD ==========
    
    def _validate_frame(self, frame: np.ndarray) -> bool:
        """Validate frame integrity"""
        if frame is None:
            return False
        if not isinstance(frame, np.ndarray):
            return False
        if frame.size == 0:
            return False
        if len(frame.shape) < 2 or frame.shape[0] == 0 or frame.shape[1] == 0:
            return False
        return True

    def _apply_identity_control_policy(self, results: List[Dict]) -> List[Dict]:
        """Apply identity control policy"""
        controlled_results = []
        
        for result in results:
            result_copy = result.copy()
            mask_status = result_copy.get('mask_status')
            violation_verified = result_copy.get('violation_verified', False)
            identity = result_copy.get('identity', 'Unknown')
            
            # Basic policy: show identity, mark unverified violations
            result_copy['identity_hidden'] = False
            
            if mask_status == 'no_mask' and not violation_verified:
                result_copy['identity_unverified'] = True
            elif mask_status == 'no_mask' and violation_verified:
                result_copy['identity_unverified'] = False
                result_copy['identity_revealed'] = True
            else:
                result_copy['identity_unverified'] = False
            
            controlled_results.append(result_copy)
        
        return controlled_results

    def _handle_violation_logging(self, source_id: str, frame: np.ndarray, results: List[Dict]):
        """Handle violation logging only for verified violations"""
        if not self.image_logging_enabled:
            return
        
        # 🆕 CRITICAL: Only log verified violations
        verified_violations = [
            r for r in results 
            if r.get('mask_status') == 'no_mask' 
            and r.get('violation_verified', False)
        ]
        
        if not verified_violations:
            return
        
        logger = self.get_source_image_logger(source_id)
        if not logger:
            print(f"⚠️ No logger available for {source_id}")
            return
        
        try:
            # Check save interval to prevent flooding
            current_time = time.time()
            if current_time - logger.last_image_save_time < logger.min_save_interval:
                return
            
            success, base64_data = logger.save_annotated_frame(
                frame, verified_violations, frame
            )
            
            if success:
                print(f"✅ Verified violation logged from {source_id}")
                # Update violation statistics
                self.violation_stats['total_logged'] += len(verified_violations)
                self.violation_stats['verified_logged'] += len(verified_violations)
                
        except Exception as e:
            print(f"❌ Verified violation logging error for {source_id}: {e}")

    def _get_dynamic_cctv_name(self, source_id: str) -> str:
        """
        Generate CCTV name from source configuration
        
        Priority:
        1. Explicit 'cctv_name' in config
        2. 'description' in config
        3. URL-based name (extract from RTSP/HTTP)
        4. Source ID fallback
        """
        config = self.source_configs.get(source_id, {})
        
        # 1. Check explicit cctv_name
        if 'cctv_name' in config:
            return config['cctv_name']
        
        # 2. Use description if available
        if 'description' in config:
            # Sanitize for filename
            name = config['description'].replace(' ', '_').replace('/', '_')
            return f"CCTV_{name}"
        
        # 3. Extract from URL
        url = config.get('url', '')
        if url:
            # Parse RTSP URL
            if url.startswith('rtsp://'):
                parsed = urlparse(url)
                if parsed.hostname:
                    # Try to extract camera name from path
                    path_parts = parsed.path.split('/')
                    for part in path_parts:
                        if part and 'cam' in part.lower():
                            return f"RTSP_{part.upper()}"
                    return f"RTSP_{parsed.hostname.split('.')[0]}"
            
            # Parse HTTP/HTTPS URL
            elif url.startswith(('http://', 'https://')):
                parsed = urlparse(url)
                if parsed.hostname:
                    return f"HTTP_{parsed.hostname.split('.')[0]}"
            
            # Local camera index
            elif url.isdigit() or url == '0':
                return f"CAM_{url}"
        
        # 4. Fallback to source ID
        return f"CCTV_{source_id}"            

    def _handle_violation_logging(self, source_id: str, frame: np.ndarray, results: List[Dict]):
        """Handle violation logging for a source"""
        # Find violations
        violations = [r for r in results if r.get('mask_status') == 'no_mask']
        
        if violations and self.image_logging_enabled:
            logger = self.get_source_image_logger(source_id)
            if logger:
                try:
                    success, _ = logger.save_annotated_frame(
                        frame, violations, frame
                    )
                    if success:
                        print(f"📸 Logged violation from {source_id}")
                except Exception as e:
                    print(f"❌ Image logging error for {source_id}: {e}")        
    
    
    # ========== OTHER UTILIZED FUNCTION ==========
    def robust_process_multi_source_frame(self, source_id: str, frame: np.ndarray) -> List[Dict]:
        """Robust frame processing with consolidated logging - ENHANCED"""
        if not self.frame_utils.validate_frame(frame):
            return []
        
        try:
            # Process frame
            processing_frame = self.frame_utils.process_frame_pipeline(
                frame=frame,
                current_scale=self.processing_scale,
                target_format='rgb'
            )
            
            # Get face recognition results
            raw_results = self.face_system.process_frame(processing_frame)
            
            # Scale results back to original frame coordinates
            processed_h, processed_w = processing_frame.shape[:2]
            original_h, original_w = frame.shape[:2]
            
            for result in raw_results:
                bbox = result.get('bbox', [])
                if len(bbox) == 4:
                    x1, y1, x2, y2 = bbox
                    scale_x = original_w / processed_w
                    scale_y = original_h / processed_h
                    result['bbox'] = [
                        int(x1 * scale_x), int(y1 * scale_y),
                        int(x2 * scale_x), int(y2 * scale_y)
                    ]
            
            # Apply tracking
            processing_results = []
            if self.multi_source_mode and source_id in self.tracking_managers:
                # Multi-source mode
                image_logger = self.get_source_image_logger(source_id)
                
                processing_results = self.tracking_managers[source_id].process_frame(
                    source_id=source_id,
                    recognition_results=raw_results,
                    original_shape=frame.shape[:2],
                    processed_shape=processing_frame.shape[:2],
                    frame=frame,
                    image_logger=image_logger
                )
            else:
                # Single source mode
                processing_results = self.tracking_manager.process_frame(
                    recognition_results=raw_results,
                    original_shape=frame.shape[:2],
                    processed_shape=processing_frame.shape[:2]
                )
            
            # 🆕 ALWAYS handle consolidated logging regardless of mode
            self._handle_consolidated_logging(source_id, frame, processing_results)
            
            # Apply identity control policy
            controlled_results = self._apply_identity_control_policy(processing_results)
            
            # Add source_id to each result
            for result in controlled_results:
                result['source_id'] = source_id
            
            return controlled_results
            
        except Exception as e:
            print(f"❌ Critical processing error for {source_id}: {e}")
            traceback.print_exc()
            return []
        
    def _handle_consolidated_logging(self, source_id: str, frame: np.ndarray, results: List[Dict]):
        """Handle all logging in one place - ENHANCED"""
        try:
            # CSV logging (if enabled)
            if self.logging_enabled and self.processing_count % self.log_interval == 0:
                log_entries = self.collect_log_data(results)
                if log_entries:
                    self.write_log_entries(log_entries)
                    if self.debug_mode:
                        print(f"📝 CSV logged {len(log_entries)} entries")
            
            # Image logging for verified violations only
            if self.image_logging_enabled and self.processing_count % self.log_interval == 0:
                # 🆕 STRICT: Only log verified violations
                verified_violations = [
                    r for r in results 
                    if r.get('mask_status') == 'no_mask' 
                    and r.get('violation_verified', False)
                ]
                
                if not verified_violations:
                    return
                
                # Get appropriate logger
                if self.multi_source_mode:
                    logger = self.get_source_image_logger(source_id)
                else:
                    logger = self.image_logger
                
                if logger and hasattr(logger, 'save_annotated_frame'):
                    # Check save interval
                    current_time = time.time()
                    if current_time - logger.last_image_save_time >= logger.min_save_interval:
                        success, base64_data = logger.save_annotated_frame(
                            frame, verified_violations, frame
                        )
                        if success:
                            print(f"📸 Verified violation logged from {source_id}")
                            # Update statistics
                            self.violation_stats['total_logged'] += len(verified_violations)
                            self.violation_stats['verified_logged'] += len(verified_violations)
                            self.violation_stats['last_verified_time'] = current_time
                            
                            # 🆕 Optional: Send to server if enabled
                            if hasattr(logger, 'send_to_server') and base64_data:
                                try:
                                    cctv_name = self._get_dynamic_cctv_name(source_id)
                                    logger.send_to_server(base64_data, "Verified Violation", cctv_name)
                                except Exception as e:
                                    print(f"⚠️ Server push failed: {e}")
                        else:
                            print(f"⚠️ Failed to save image for {source_id}")
                        
        except Exception as e:
            print(f"⚠️ Consolidated logging error for {source_id}: {e}")
            traceback.print_exc()
                                    
    def create_multi_source_display(self, source_frames: Dict[str, np.ndarray], 
                                source_results: Dict[str, List[Dict]]) -> np.ndarray:
        """Combine multiple source frames into a single display with proper result mapping"""
        
        if self.display_layout == 'grid':
            composite, regions = self._create_grid_layout(source_frames, source_results)
        elif self.display_layout == 'horizontal':
            composite, regions = self._create_horizontal_layout(source_frames, source_results)
        elif self.display_layout == 'vertical':
            composite, regions = self._create_vertical_layout(source_frames, source_results)
        else:
            # Default to grid
            composite, regions = self._create_grid_layout(source_frames, source_results)
        
        # Add results overlays to composite using region information
        for source_id, region in regions.items():
            if source_id in source_results:
                self._add_results_to_composite(composite, source_id, 
                                            source_results[source_id], region)
        
        return composite


    def _add_results_to_composite(self, composite: np.ndarray, source_id: str, 
                                results: List[Dict], region: Tuple[int, int, int, int]):
        """
        Add detection results to the correct region in composite display
        
        Args:
            composite: The combined display frame
            source_id: Identifier for the source
            results: Detection results for this source
            region: (x, y, width, height) where this source is placed in composite
        """
        if not results:
            return
        
        # Extract region coordinates
        region_x, region_y, region_w, region_h = region
        
        # Create a temporary overlay frame for this source's results
        overlay = np.zeros((region_h, region_w, 3), dtype=np.uint8)
        
        # Draw results on overlay (using original coordinates)
        for result in results:
            # Get bounding box in source coordinates
            x1, y1, x2, y2 = result['bbox']
            
            # Clip to source frame boundaries
            h, w = overlay.shape[:2]
            x1 = max(0, min(x1, w - 1))
            x2 = max(0, min(x2, w - 1))
            y1 = max(0, min(y1, h - 1))
            y2 = max(0, min(y2, h - 1))
            
            # Draw on overlay
            mask_status = result.get('mask_status', 'unknown')
            
            if mask_status == 'no_mask':
                color = (0, 0, 255)  # Red
                if result.get('violation_verified', False):
                    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 3)
                else:
                    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
            elif mask_status == 'mask':
                color = (0, 255, 0)  # Green
                cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
            elif mask_status == 'verifying':
                color = (127, 0, 15)  # Orange
                cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
            
            # Add label if there's space
            if y1 > 30:
                identity = result.get('identity', 'Unknown')
                if mask_status == 'no_mask' and not result.get('violation_verified', False):
                    label = f"{identity} | VERIFYING" if identity != 'Unknown' else "VERIFYING"
                else:
                    label = f"{identity} | {mask_status.upper()}" if identity != 'Unknown' else mask_status.upper()
                
                # Draw label background
                text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
                cv2.rectangle(overlay, (x1, y1 - text_size[1] - 10), 
                            (x1 + text_size[0], y1), color, -1)
                # Draw label text
                cv2.putText(overlay, label, (x1, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        
        # Blend overlay onto composite at the correct region
        composite_region = composite[region_y:region_y + region_h, 
                                region_x:region_x + region_w]
        
        # Create a mask from the overlay (non-black pixels)
        mask = overlay.sum(axis=2) > 0
        mask_3d = np.stack([mask, mask, mask], axis=2)
        
        # Blend: use overlay where there are annotations, keep composite elsewhere
        composite_region = np.where(mask_3d, overlay, composite_region)
        
        # Put back into composite
        composite[region_y:region_y + region_h, 
                region_x:region_x + region_w] = composite_region
        
        # Add source identifier overlay
        cctv_name = self._get_dynamic_cctv_name(source_id)
        cv2.putText(composite, cctv_name, (region_x + 10, region_y + 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        

    def get_source_image_logger(self, source_id: str) -> Optional[ImageLogger]:
        """Get ImageLogger for specific source with proper initialization"""
        if not self.multi_source_mode:
            return self.image_logger if hasattr(self, 'image_logger') else None
        
        # Return existing logger
        if source_id in self.image_loggers:
            return self.image_loggers[source_id]
        
        # Create on-demand with proper initialization
        if self.image_logging_enabled:
            try:
                logger = ImageLogger(self.config)
                
                # CRITICAL: Initialize directory structure
                if self.current_log_session:
                    cctv_name = self._get_dynamic_cctv_name(source_id)
                    base_filename = f"{self.current_log_session}_{cctv_name}"
                else:
                    # Create ad-hoc session
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    base_filename = f"on_demand_{timestamp}_{source_id}"
                
                logger.setup_image_logging(base_filename)
                
                # Store CCTV name
                if source_id in self.source_configs:
                    self.source_configs[source_id]['cctv_name'] = cctv_name
                
                self.image_loggers[source_id] = logger
                print(f"📁 Created on-demand logger for {source_id}: {base_filename}")
                return logger
                
            except Exception as e:
                print(f"⚠️ Failed to create image logger for {source_id}: {e}")
        
        return None

    def force_create_image_logger(self, source_id: str) -> bool:
        """Force create an ImageLogger for a source"""
        try:
            self.image_loggers[source_id] = ImageLogger(self.config)
            print(f"✅ Created ImageLogger for {source_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to force create ImageLogger: {e}")
            return False

    def get_source_config(self, source_id: str) -> Dict:
        """Get configuration for a specific source"""
        if self.multi_source_mode:
            return self.source_configs.get(source_id, {})
        return self.config            


    # ========== LAYOUT METHODS ==========
    def _create_grid_layout(self, frames: Dict[str, np.ndarray], 
                        results: Dict[str, List[Dict]]) -> Tuple[np.ndarray, Dict[str, Tuple]]:
        """Create grid layout for multiple sources and return region information"""
        source_ids = list(frames.keys())[:self.max_display_sources]
        grid_size = int(np.ceil(np.sqrt(len(source_ids))))
        
        # Get layout configuration
        target_h = self.config.get('grid_layout', {}).get('target_height', 360)
        target_w = self.config.get('grid_layout', {}).get('target_width', 480)
        
        resized_frames = []
        regions = {}  # Store region info: {source_id: (x, y, width, height)}
        
        for i, source_id in enumerate(source_ids):
            frame = frames[source_id]
            # Resize frame for grid
            resized = cv2.resize(frame, (target_w, target_h))
            resized_frames.append(resized)
            
            # Calculate region position in grid
            row = i // grid_size
            col = i % grid_size
            region_x = col * target_w
            region_y = row * target_h
            
            regions[source_id] = (region_x, region_y, target_w, target_h)
        
        # Create grid
        rows = []
        for i in range(0, len(resized_frames), grid_size):
            row_frames = resized_frames[i:i + grid_size]
            # Pad row if necessary
            while len(row_frames) < grid_size:
                row_frames.append(np.zeros((target_h, target_w, 3), dtype=np.uint8))
            rows.append(np.hstack(row_frames))
        
        composite = np.vstack(rows)
        return composite, regions

    def _create_horizontal_layout(self, frames: Dict[str, np.ndarray], 
                                results: Dict[str, List[Dict]]) -> Tuple[np.ndarray, Dict[str, Tuple]]:
        """Create horizontal strip layout with region information"""
        source_ids = list(frames.keys())[:self.max_display_sources]
        
        # Get layout configuration
        layout_config = self.config.get('horizontal_layout', {})
        target_h = layout_config.get('target_height', 360)
        
        resized_frames = []
        regions = {}
        current_x = 0
        
        for source_id in source_ids:
            frame = frames[source_id]
            
            # Maintain aspect ratio
            h, w = frame.shape[:2]
            aspect_ratio = w / h
            target_w = int(target_h * aspect_ratio)
            
            resized = cv2.resize(frame, (target_w, target_h))
            resized_frames.append(resized)
            
            # Store region information
            regions[source_id] = (current_x, 0, target_w, target_h)
            current_x += target_w
        
        composite = np.hstack(resized_frames)
        return composite, regions

    def _create_vertical_layout(self, frames: Dict[str, np.ndarray], 
                            results: Dict[str, List[Dict]]) -> Tuple[np.ndarray, Dict[str, Tuple]]:
        """Create vertical stack layout with region information"""
        source_ids = list(frames.keys())[:self.max_display_sources]
        
        # Get layout configuration
        layout_config = self.config.get('vertical_layout', {})
        target_w = layout_config.get('target_width', 480)
        
        resized_frames = []
        regions = {}
        current_y = 0
        
        for source_id in source_ids:
            frame = frames[source_id]
            
            # Maintain aspect ratio
            h, w = frame.shape[:2]
            aspect_ratio = h / w
            target_h = int(target_w * aspect_ratio)
            
            resized = cv2.resize(frame, (target_w, target_h))
            resized_frames.append(resized)
            
            # Store region information
            regions[source_id] = (0, current_y, target_w, target_h)
            current_y += target_h
        
        composite = np.vstack(resized_frames)
        return composite, regions
 
    