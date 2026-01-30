# streaming/realtime_processing_headless.py

import cv2
import time
from typing import Optional, List, Dict
from threading import Lock, Thread
import numpy as np
from queue import Queue
import datetime
import signal
import sys

from face_recog_modular.streaming.realtime_processor import RealTimeProcessor

class RealTimeProcessorHeadless(RealTimeProcessor):
    def __init__(self, face_system, processing_interval: int = 5, buffer_size: int = 3):
        # Call parent constructor
        super().__init__(face_system, processing_interval, buffer_size)
        
        # Headless-specific attributes
        self.headless_mode = True  # Mark as headless
        self.show_performance_stats = True  # Headless default - show in console
        
        # Headless-specific stream stability attributes
        self.frame_queue = Queue(maxsize=buffer_size)
        self.latest_frame = None
        self.frame_lock = Lock()
        self.capture_thread = None
        
        # Headless performance monitoring
        self.last_status_update = time.time()
        self.status_update_interval = 5  # seconds
        
        # Signal handling for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        print("🎯 RealTimeProcessorHeadless initialized - optimized for headless operation")
        print("💡 Running in HEADLESS MODE - no display windows will be created")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        print(f"🛑 Received signal {signum}, shutting down gracefully...")
        self.stop()
        sys.exit(0)

    # ========== OVERRIDE ONLY HEADLESS-SPECIFIC METHODS ==========
    
    def get_frame_for_processing(self) -> Optional[np.ndarray]:
        """Headless-specific frame acquisition with enhanced stability"""
        try:
            # Quick check without lock first
            if self.frame_queue.empty():
                return None
                
            with self.processing_lock:  # PREVENTS parallel processing
                frame = self.frame_queue.get(block=True, timeout=0.05)  # Short timeout
                
                # Validate frame integrity using FrameUtils
                if not self.frame_utils.validate_frame(frame):
                    return None
                    
                self.consecutive_good_frames += 1
                return frame
                
        except Exception as e:
            if self.config.get('verbose', False):
                print(f"Frame acquisition skipped: {e}")
            return None
    
    def _capture_frames(self):
        """Enhanced stable frame capture with memory protection - HEADLESS SPECIFIC"""
        reconnect_attempts = 0
        max_queue_size = 2  # Conservative limit
        
        while self.running:
            try:
                # Use StreamManager to read frame
                success, frame = self.stream_manager.read_frame()
                
                if not success or frame is None:
                    print("⚠️  Frame capture failed, attempting to reconnect...")
                    reconnect_attempts += 1
                    
                    if reconnect_attempts >= self.stream_manager.max_reconnect_attempts:
                        print("❌ Max reconnection attempts reached")
                        break
                    
                    time.sleep(self.stream_manager.reconnect_delay)
                    self._reconnect_stream()
                    continue
                
                reconnect_attempts = 0
                
                # Validate frame using FrameUtils
                if not self.frame_utils.validate_frame(frame):
                    continue
                
                with self.frame_lock:
                    self.latest_frame = frame
                
                # Conservative queue management
                if self.frame_queue.qsize() >= max_queue_size:
                    try:
                        self.frame_queue.get_nowait()  # Discard oldest frame
                    except:
                        pass
                        
                try:
                    self.frame_queue.put(frame, block=False, timeout=0.01)
                except:
                    pass  # Skip frame if queue is full
                            
            except Exception as e:
                print(f"🚨 Capture thread error: {e}")
                time.sleep(0.1)  # Shorter sleep for faster recovery
    
    def _reconnect_stream(self):
        """Enhanced stream reconnection using StreamManager - HEADLESS SPECIFIC"""
        return self.stream_manager._attempt_reconnection()
    
    def start_frame_capture(self):
        """Start background thread for frame capture - HEADLESS SPECIFIC"""
        self.capture_thread = Thread(target=self._capture_frames, daemon=True)
        self.capture_thread.start()
        print("🎬 Headless frame capture started with enhanced stability")
    
    # ========== OVERRIDE DISPLAY-SPECIFIC METHODS TO DO NOTHING ==========
    
    def resize_frame_for_display(self, frame: np.ndarray) -> np.ndarray:
        """In headless mode, return original frame - no display resizing"""
        return frame
    
    def draw_resize_info(self, frame: np.ndarray):
        """No resize info in headless mode"""
        pass
    
    def draw_debug_info(self, frame: np.ndarray, results: List[Dict]):
        """No debug drawing in headless mode"""
        pass
    
    def draw_detection_debug(self, frame: np.ndarray, results: List[Dict]):
        """No detection debug drawing in headless mode"""
        pass
    
    def draw_results(self, frame: np.ndarray, results: List[Dict]):
        """No result drawing in headless mode - but we still want to process results"""
        pass
    
    def draw_enhanced_results(self, frame: np.ndarray, results: List[Dict], performance: Dict):
        """No enhanced drawing in headless mode"""
        pass
    
    def draw_mask_debug_info(self, frame: np.ndarray, results: List[Dict]):
        """No mask debug in headless mode"""
        pass
    
    def draw_dynamic_adjustment_info(self, frame: np.ndarray, performance: Dict):
        """No dynamic adjustment info in headless mode"""
        pass
    
    def set_display_size(self, width: int, height: int, method: str = "fixed_size"):
        """No display size setting in headless mode"""
        print("⚠️  Display controls disabled in headless mode")
    
    def set_display_scale(self, scale: float):
        """No display scaling in headless mode"""
        print("⚠️  Display scaling disabled in headless mode")
    
    def set_display_method(self, method: str):
        """No display methods in headless mode"""
        print("⚠️  Display methods disabled in headless mode")
    
    def set_max_display_size(self, width: int, height: int):
        """No max display size in headless mode"""
        print("⚠️  Display size controls disabled in headless mode")
    
    def toggle_resize_info(self):
        """No resize info toggling in headless mode"""
        print("⚠️  Resize info disabled in headless mode")
    
    # ========== OVERRIDE KEYBOARD CONTROLS ==========
    
    def handle_key_controls(self, key: int):
        """Headless-specific keyboard controls - only process common controls"""
        return self.control_handler.handle_common_controls(key)
    
    def print_control_reference(self):
        """Headless control reference"""
        self.control_handler.print_control_reference(headless=True)
    
    # ========== OVERRIDE MAIN PROCESSING LOOP ==========
    
    def run(self, source: str = "0"):
        """Headless-specific main loop - optimized for background processing"""
        try:
            # Use parent's stream initialization
            if not self.initialize_stream(source):
                print("❌ Failed to initialize stream")
                return
                
            self.running = True
            self.start_frame_capture()  # Headless version
            
            print("🎮 Starting HEADLESS MODE - Enhanced with TrackingManager")
            print("💡 No display window will be created")
            print("📊 Processing frames in background with enhanced tracking and logging")
            self.print_control_reference()
            
            last_results = []
            last_performance = {}
            
            while self.running:
                # Use headless frame acquisition
                original_frame = self.get_frame_for_processing()
                if original_frame is None:
                    time.sleep(0.005)
                    continue
                
                self.calculate_fps()  # Inherited from parent
                self.update_dynamic_system()  # Inherited from parent
                
                # Store original frame size
                original_h, original_w = original_frame.shape[:2]
                
                # Resize for processing using dynamic scale (inherited)
                processing_frame = self.enhanced_resize_for_processing(original_frame)
                processed_h, processed_w = processing_frame.shape[:2]
                
                should_process = self.should_process_frame()  # Inherited from parent
                
                if should_process:
                    # Processing is already protected by processing_lock in get_frame_for_processing
                    raw_results = self.face_system.process_frame(processing_frame)
                    
                    # Use tracking manager (inherited from parent)
                    processing_results = self.tracking_manager.process_frame(
                        raw_results,
                        (original_h, original_w),
                        (processed_h, processed_w)
                    )
                    
                    # Enhanced logging with image support (inherited from parent)
                    # Pass original_frame for both display and original since we don't have display frame
                    self.log_performance_data(processing_results, original_frame, original_frame)
                    
                    last_results = processing_results
                    self.processing_count += 1
                    
                    # Dynamic adjustment (protected by processing lock)
                    if (self.performance_manager.dynamic_adjustment_enabled and 
                        self.frame_count % self.performance_manager.adaptive_check_interval == 0):
                        performance = self.analyze_detection_performance(processing_results, (original_h, original_w))
                        self.performance_manager.performance_history.append(performance)
                        last_performance = performance
                        self.apply_dynamic_adjustment(performance)
                
                # Headless status updates (less frequent to avoid console spam)
                current_time = time.time()
                if current_time - self.last_status_update >= self.status_update_interval:
                    stats = self.face_system.get_debug_stats() if hasattr(self.face_system, 'get_debug_stats') else {}
                    recognized_count = len([r for r in last_results if r.get('identity')])
                    
                    print(f"📊 Headless Status: Frame {self.frame_count}, FPS: {self.fps:.1f}, "
                          f"Processed: {self.processing_count}, Faces: {len(last_results)}, "
                          f"Recognized: {recognized_count}")
                    
                    # Log performance metrics if available
                    if stats:
                        print(f"   Detection: {stats.get('avg_detection_time', 0):.1f}ms, "
                              f"Recognition: {stats.get('recognition_rate', 0):.1f}%")
                    
                    self.last_status_update = current_time
                
                # Minimal keyboard check for headless controls (non-blocking)
                try:
                    # In headless mode, we use a very short timeout to avoid blocking
                    key = cv2.waitKey(1) & 0xFF
                    if key != 255:  # Only process if a key was actually pressed
                        if self.handle_key_controls(key):
                            # If handle_key_controls returns True, it means we should exit
                            break
                except Exception as e:
                    # Ignore key errors in headless mode - they're expected when no window exists
                    pass
                            
        except KeyboardInterrupt:
            print("🛑 Received KeyboardInterrupt, shutting down...")
        except Exception as e:
            print(f"❌ Error in headless main loop: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.stop()
    
    # ========== OVERRIDE STOP METHOD ==========
    
    def stop(self):
        """Headless-specific cleanup"""
        print("🛑 Stopping RealTimeProcessorHeadless...")
        
        # Print final log summary using parent's method
        if hasattr(self, 'logging_enabled') and self.logging_enabled and hasattr(self, 'log_file') and self.log_file:
            duration = datetime.datetime.now() - self.log_start_time
            print(f"\n📊 ENHANCED LOGGING SUMMARY:")
            print(f"   CSV entries: {self.log_counter}")
            if hasattr(self, 'image_logger'):
                print(f"   Violation images: {self.image_logger.saved_image_count}")
            print(f"   Duration: {duration}")
            print(f"   CSV file: {self.log_file}")
            if hasattr(self, 'image_logger'):
                print(f"   Image folder: {self.image_logger.image_log_folder}")
        
        if hasattr(self, 'logging_enabled'):
            self.logging_enabled = False
        if hasattr(self, 'image_logging_enabled'):
            self.image_logging_enabled = False
        
        self.running = False
        
        # Clean up stream manager (inherited)
        if hasattr(self, 'stream_manager'):
            self.stream_manager.release()
        
        # Headless-specific thread cleanup
        if hasattr(self, 'capture_thread') and self.capture_thread and self.capture_thread.is_alive():
            print("🛑 Waiting for capture thread to finish...")
            self.capture_thread.join(timeout=2.0)
        
        # Don't call cv2.destroyAllWindows() in headless mode as it may cause issues
        
        # Print final statistics
        print("\n📊 FINAL HEADLESS STATISTICS:")
        print(f"   Total frames: {self.frame_count}")
        print(f"   Processed frames: {self.processing_count}")
        print(f"   Final FPS: {self.fps:.1f}")
        print("🛑 Headless system stopped gracefully")
    
    # ========== HEADLESS-SPECIFIC METHODS ==========
    
    def get_processing_stats(self) -> Dict:
        """Get headless-specific processing statistics"""
        base_stats = super().get_stability_metrics()
        
        # Add headless-specific stats
        headless_stats = {
            'headless_mode': True,
            'frame_queue_size': self.frame_queue.qsize() if hasattr(self, 'frame_queue') else 0,
            'capture_thread_alive': self.capture_thread.is_alive() if hasattr(self, 'capture_thread') and self.capture_thread else False,
        }
        
        base_stats.update(headless_stats)
        return base_stats
    
    def print_detailed_status(self):
        """Print detailed headless system status"""
        stats = self.get_processing_stats()
        
        print("\n" + "="*60)
        print("📊 HEADLESS SYSTEM STATUS - Detailed")
        print("="*60)
        print(f"Frame Processing: {stats['frame_count']} total, {stats['processing_count']} processed")
        print(f"Performance: {stats['fps']:.1f} FPS")
        
        if 'stream_health' in stats:
            stream_health = stats['stream_health']
            print(f"Stream Health: {stream_health['frame_count']} frames, {stream_health['error_count']} errors")
        
        if 'current_scale' in stats:
            print(f"Processing Scale: {stats['current_scale']:.2f}")
        
        if 'tracking_active_tracks' in stats:
            print(f"Active Tracks: {stats['tracking_active_tracks']}")
        
        print(f"Frame Queue: {stats.get('frame_queue_size', 0)} frames")
        print(f"Capture Thread: {'ALIVE' if stats.get('capture_thread_alive') else 'STOPPED'}")
        print(f"Logging: {'ENABLED' if stats.get('logging_enabled') else 'DISABLED'}")
        
        if stats.get('logging_enabled'):
            print(f"CSV Entries: {stats.get('log_entries', 0)}")
            if hasattr(self, 'image_logger'):
                print(f"Saved Images: {self.image_logger.saved_image_count}")
        
        print("="*60)

    def enable_high_performance_mode(self):
        """Enable headless-optimized high performance settings"""
        # Optimize for headless - no display overhead
        self.processing_interval = 1  # Process every frame
        self.performance_manager.dynamic_adjustment_enabled = True
        self.performance_manager.aggressive_scaling = True
        
        # Optimize face system for performance
        if hasattr(self.face_system, 'set_high_performance_mode'):
            self.face_system.set_high_performance_mode()
        
        print("🚀 High Performance Mode ENABLED for headless operation")
        print("   - Processing every frame")
        print("   - Aggressive dynamic scaling")
        print("   - Optimized for maximum throughput")
        
        
        