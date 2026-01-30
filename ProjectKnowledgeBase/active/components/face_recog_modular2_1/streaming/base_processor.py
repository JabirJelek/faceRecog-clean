# streaming/base_processor.py
# Updated to strictly use PerformanceManager and ContextAwareDynamicScaling for all scale adjustments

"""
Base processor class with common functionality for both windowed and headless modes
"""
import time
import datetime
import csv
from typing import Dict, List, Optional, Any, Tuple
import numpy as np

class BaseProcessor:
    """Base class with shared functionality for both processors"""
    
    def __init__(self, face_system, config: Dict):
        self.face_system = face_system
        self.config = config
        
        # Initialize performance management system
        from  face_recog_modular2.streaming.performance_manager import PerformanceManager
        from  face_recog_modular2.processing.scene_analysis import ContextAwareDynamicScaling
        
        self.performance_manager = PerformanceManager(config)
        self.context_scaling = ContextAwareDynamicScaling(config)
        
        # Common initialization
        self.fps = 0
        self.frame_count = 0
        self.processing_count = 0
        self.start_time = time.time()
        
        # Frame processing - now controlled by performance manager
        self.processing_interval = config.get('processing_interval', 5)
        self.last_processed_time = 0
        self.min_processing_delay = config.get('min_processing_delay', 0.1)
        
        # Processing resolution - now managed by performance system
        self.processing_width = config.get('processing_width', 1600)
        self.processing_height = config.get('processing_height', 900)
        
        # Get initial scale from performance manager
        self.processing_scale = self.performance_manager.current_processing_scale
        
        # Logging system (common to both)
        self.logging_enabled = False
        self.log_file = None
        self.log_start_time = None
        self.log_interval = config.get('log_interval', 5)
        self.log_counter = 0
        self.log_columns = ['timestamp', 'identity', 'mask_status']
        
        # Performance tracking
        self.performance_history = []
        
        print("⚙️ BaseProcessor initialized with mandatory performance-managed scaling")
        print(f"🎯 Initial scale: {self.processing_scale:.2f} (from PerformanceManager)")

    def calculate_fps(self):
        """Calculate and update FPS (common method)"""
        self.frame_count += 1
        if self.frame_count % 30 == 0:
            elapsed = time.time() - self.start_time
            self.fps = self.frame_count / elapsed
            self.frame_count = 0
            self.start_time = time.time()

    def process_frame(self) -> bool:
        """Adaptive frame processing with performance-managed scaling"""
        current_time = time.time()
        
        # Base interval check
        if self.frame_count % self.processing_interval != 0:
            return False
        
        # Timing protection
        if current_time - self.last_processed_time < self.min_processing_delay:
            return False
        
        # Adaptive interval based on FPS and current scale
        # Higher scales require longer intervals for stability
        scale_factor = max(0.5, min(2.0, self.processing_scale))
        adaptive_interval = max(1, int(self.processing_interval * scale_factor))
        
        if self.frame_count % adaptive_interval != 0:
            return False
        
        self.last_processed_time = current_time
        return True

    def apply_performance_managed_scale(self, frame: np.ndarray, detection_results: List[Dict]) -> float:
        """Apply scale adjustment strictly from PerformanceManager and ContextAwareDynamicScaling"""
        
        # Get performance metrics for dynamic adjustment
        if detection_results:
            original_shape = frame.shape[:2] if len(frame.shape) == 3 else frame.shape
            performance_metrics = self.performance_manager.analyze_detection_performance(
                detection_results, original_shape
            )
            
            # Apply dynamic adjustment based on performance
            self.performance_manager.apply_dynamic_adjustment(performance_metrics)
            
            # Get context-aware optimal scale
            optimal_scale = self.context_scaling.compute_optimal_scale(
                frame, detection_results, performance_metrics
            )
            
            # Apply the scale adjustment with cooldown consideration
            if self.context_scaling.apply_scale_adjustment(optimal_scale):
                # Update processing scale from context scaling system
                self.processing_scale = self.context_scaling.current_scale
                print(f"📐 Scale updated to: {self.processing_scale:.2f}")
            else:
                # Use performance manager scale if context scaling didn't apply
                self.processing_scale = self.performance_manager.current_processing_scale
        
        # Update dynamic system state
        self.performance_manager.update_dynamic_system()
        
        # Ensure scale stays within bounds
        self.processing_scale = max(
            self.performance_manager.min_processing_scale,
            min(self.performance_manager.max_processing_scale, self.processing_scale)
        )
        
        return self.processing_scale

    def enforce_scale_compliance(self):
        """Enforce that current scale matches performance manager's scale"""
        pm_scale = self.performance_manager.current_processing_scale
        cs_scale = self.context_scaling.current_scale
        
        # Use the more conservative (lower) scale for performance
        compliant_scale = min(pm_scale, cs_scale)
        
        if abs(self.processing_scale - compliant_scale) > 0.01:
            old_scale = self.processing_scale
            self.processing_scale = compliant_scale
            print(f"⚠️  Scale compliance enforced: {old_scale:.2f} → {compliant_scale:.2f}")

    # Common logging methods (unchanged)
    def collect_log_data(self, results: List[Dict]) -> List[Dict]:
        """Collect individual face recognition and mask status data"""
        log_entries = []
        
        if not isinstance(results, list):
            print(f"❌ Logging error: Expected list, got {type(results)}")
            return log_entries
        
        for result in results:
            if isinstance(result, dict):
                identity = result.get('identity')
                mask_status = result.get('mask_status', 'unknown')
                
                # Only log recognized faces with valid identities
                if identity is not None and identity != "Unknown":
                    log_entries.append({
                        'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                        'identity': str(identity),
                        'mask_status': str(mask_status)
                    })
            else:
                print(f"❌ Skipping non-dictionary result: {type(result)}")
        
        return log_entries
    
    def write_log_entries(self, log_entries: List[Dict]):
        """Write multiple log entries to CSV"""
        if not self.logging_enabled or not self.log_file or not log_entries:
            return
        
        try:
            with open(self.log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                for log_data in log_entries:
                    row = [
                        log_data['timestamp'],
                        log_data['identity'],
                        log_data['mask_status']
                    ]
                    writer.writerow(row)
                    
            self.log_counter += len(log_entries)
            
            # Periodic status update
            if self.log_counter % 10 == 0:
                print(f"📊 Logged {self.log_counter} face entries")
                
        except Exception as e:
            print(f"❌ Log write error: {e}")

    def setup_logging(self, filename: str = None):
        """Setup CSV logging with face names and mask status"""
        try:
            if filename is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"face_recognition_detailed_{timestamp}.csv"
            
            self.log_file = filename
            self.log_start_time = datetime.datetime.now()
            
            # Write simplified header
            with open(self.log_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(self.log_columns)
            
            print(f"📊 Detailed face logging ENABLED: {filename}")
            print(f"   - Columns: {self.log_columns}")
            print(f"   - Logging: Recognized faces with mask status")
            print(f"   - Interval: Every {self.log_interval} processed frames")
            
        except Exception as e:
            print(f"❌ Failed to setup logging: {e}")
            self.logging_enabled = False
            self.log_file = None

    def toggle_logging(self, filename: str = None, force_state: bool = None):
        """Toggle both CSV logging with optional forced state"""
        if force_state is not None:
            # Force a specific state (from configuration)
            new_state = force_state
        else:
            # Toggle current state (from user input)
            new_state = not self.logging_enabled
        
        if new_state and not self.logging_enabled:
            # Enable logging
            self.setup_logging(filename)
            self.logging_enabled = True
            self.log_counter = 0
            print("🟢 CSV logging STARTED")
        elif not new_state and self.logging_enabled:
            # Disable logging
            if self.log_file:
                duration = datetime.datetime.now() - self.log_start_time
                print(f"🔴 Logging STOPPED: {self.log_file}")
                print(f"   - Duration: {duration}")
                print(f"   - CSV entries: {self.log_counter}")
            
            self.logging_enabled = False
            self.log_file = None
            self.log_start_time = None

    def print_log_status(self):
        """Print current logging status"""
        status = "🟢 ENABLED" if self.logging_enabled else "🔴 DISABLED"
        print(f"\n📊 LOGGING STATUS: {status}")
        
        if self.logging_enabled:
            duration = datetime.datetime.now() - self.log_start_time
            print(f"   File: {self.log_file}")
            print(f"   Entries: {self.log_counter}")
            print(f"   Duration: {duration}")
            print(f"   Interval: Every {self.log_interval} processed frames")
            print(f"   Columns: {', '.join(self.log_columns)}")
        else:
            print("   Use 'l' to enable detailed face logging")

    def get_stability_metrics(self) -> Dict[str, Any]:
        """Get system stability metrics including scaling info"""
        pm_stats = self.performance_manager.get_performance_stats()
        cs_stats = self.context_scaling.get_scaling_statistics()
        
        return {
            'frame_count': self.frame_count,
            'processing_count': self.processing_count,
            'fps': self.fps,
            'processing_scale': self.processing_scale,
            'performance_scale': pm_stats.get('current_scale', 1.0),
            'context_scale': cs_stats.get('current_scale', 1.0),
            'scaling_decisions': cs_stats.get('total_decisions', 0),
            'dynamic_adjustment_enabled': pm_stats.get('dynamic_adjustment_enabled', False),
            'adjustment_cooldown': pm_stats.get('adjustment_cooldown', 0),
            'logging_enabled': self.logging_enabled,
            'log_entries': self.log_counter
        }

    def print_detailed_stats(self):
        """Print detailed system statistics with scaling compliance info"""
        stats = self.face_system.get_debug_stats() if hasattr(self.face_system, 'get_debug_stats') else {}
        pm_stats = self.performance_manager.get_performance_stats()
        cs_stats = self.context_scaling.get_scaling_statistics()
        
        print("\n" + "="*50)
        print("📊 DETAILED SYSTEM STATISTICS")
        print("="*50)
        print(f"Total Frames Processed: {stats.get('total_frames_processed', 'N/A')}")
        print(f"Total Faces Detected: {stats.get('total_faces_detected', 'N/A')}")
        print(f"Total Faces Recognized: {stats.get('total_faces_recognized', 'N/A')}")
        print(f"Recognition Rate: {stats.get('recognition_rate', 'N/A'):.1f}%")
        print(f"Current FPS: {self.fps:.1f}")
        print(f"Processing Scale: {self.processing_scale:.2f}")
        print(f"Performance Manager Scale: {pm_stats.get('current_scale', 'N/A')}")
        print(f"Context Scaling Scale: {cs_stats.get('current_scale', 'N/A')}")
        print(f"Scaling Decisions Made: {cs_stats.get('total_decisions', 'N/A')}")
        print(f"Dynamic Adjustment: {'ENABLED' if pm_stats.get('dynamic_adjustment_enabled') else 'DISABLED'}")
        print(f"Adjustment Cooldown: {pm_stats.get('adjustment_cooldown', 0)}")
        print(f"Processing Resolution: {self.processing_width}x{self.processing_height}")
        print(f"Logging: {'ENABLED' if self.logging_enabled else 'DISABLED'}")
        if self.logging_enabled:
            print(f"Log Entries: {self.log_counter}")
        print("="*50)

    def update_processing_interval(self, change: int):
        """Update processing interval with bounds checking"""
        new_interval = self.processing_interval + change
        new_interval = max(1, min(30, new_interval))  # Bound between 1 and 30
        
        if new_interval != self.processing_interval:
            old_interval = self.processing_interval
            self.processing_interval = new_interval
            print(f"⏱️  Processing interval: 1/{old_interval} → 1/{new_interval}")

    def reset_processing_counters(self):
        """Reset all processing counters and scaling systems"""
        self.frame_count = 0
        self.processing_count = 0
        self.start_time = time.time()
        self.performance_history = []
        
        # Reset scaling systems
        self.performance_manager.reset_dynamic_scaling()
        self.processing_scale = self.performance_manager.current_processing_scale
        
        print("🔄 Processing counters and scaling systems reset")
        print(f"   Scale reset to: {self.processing_scale:.2f}")

    def get_processing_config(self) -> Dict[str, Any]:
        """Get current processing configuration with scaling info"""
        pm_stats = self.performance_manager.get_performance_stats()
        
        return {
            'processing_interval': self.processing_interval,
            'processing_width': self.processing_width,
            'processing_height': self.processing_height,
            'processing_scale': self.processing_scale,
            'performance_manager_scale': pm_stats.get('current_scale', 1.0),
            'context_scaling_scale': self.context_scaling.current_scale,
            'fps': self.fps,
            'frame_count': self.frame_count,
            'processing_count': self.processing_count,
            'dynamic_adjustment_enabled': pm_stats.get('dynamic_adjustment_enabled', False)
        }

    def toggle_dynamic_adjustment(self):
        """Toggle dynamic adjustment on/off"""
        self.performance_manager.toggle_dynamic_adjustment()
        
    def enable_small_face_mode(self):
        """Enable optimized settings for small face detection"""
        self.performance_manager.enable_small_face_mode()
        self.processing_scale = self.performance_manager.current_processing_scale
        print(f"🔍 Small face mode enabled. Scale set to: {self.processing_scale:.2f}")
        