# streaming/base_processor.py
# Proposed file that can be utilized more in integrating modularity of realtime streaming

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
        
        # Common initialization
        self.fps = 0
        self.frame_count = 0
        self.processing_count = 0
        self.start_time = time.time()
        
        # Frame processing
        self.processing_interval = config.get('processing_interval', 5)
        self.last_processed_time = 0
        self.min_processing_delay = config.get('min_processing_delay', 0.1)
        
        # Processing resolution
        self.processing_width = config.get('processing_width', 1600)
        self.processing_height = config.get('processing_height', 900)
        self.processing_scale = config.get('processing_scale', 1.0)
        
        # Logging system (common to both)
        self.logging_enabled = False
        self.log_file = None
        self.log_start_time = None
        self.log_interval = config.get('log_interval', 5)
        self.log_counter = 0
        self.log_columns = ['timestamp', 'identity', 'mask_status']
        
        # Performance tracking
        self.performance_history = []
        
        print("⚙️ BaseProcessor initialized with common functionality")

    def calculate_fps(self):
        """Calculate and update FPS (common method)"""
        self.frame_count += 1
        if self.frame_count % 30 == 0:
            elapsed = time.time() - self.start_time
            self.fps = self.frame_count / elapsed
            self.frame_count = 0
            self.start_time = time.time()

    def should_process_frame(self) -> bool:
        """Adaptive frame processing based on system load (common method)"""
        current_time = time.time()
        
        # Base interval check
        if self.frame_count % self.processing_interval != 0:
            return False
        
        # Timing protection
        if current_time - self.last_processed_time < self.min_processing_delay:
            return False
        
        # Adaptive interval based on FPS
        if self.fps < 10:  # Low FPS - process fewer frames
            adaptive_interval = max(1, self.processing_interval + 2)
            if self.frame_count % adaptive_interval != 0:
                return False
        elif self.fps > 30:  # High FPS - can process more frames
            adaptive_interval = max(1, self.processing_interval - 1)
            if self.frame_count % adaptive_interval != 0:
                return False
        
        self.last_processed_time = current_time
        return True
    
    def cycle_processing_preset(self):
        """Cycle through different processing presets (common method)"""
        presets = [
            {"name": "SPEED", "interval": 10, "scale": 0.6, "width": 640, "height": 480},
            {"name": "BALANCED", "interval": 5, "scale": 1.0, "width": 1280, "height": 720},
            {"name": "QUALITY", "interval": 2, "scale": 1.3, "width": 1600, "height": 900},
            {"name": "MAX QUALITY", "interval": 1, "scale": 1.5, "width": 1920, "height": 1080}
        ]
        
        current_preset_index = getattr(self, 'current_preset_index', -1)
        self.current_preset_index = current_preset_index + 1
        
        if self.current_preset_index >= len(presets):
            self.current_preset_index = 0
            
        preset = presets[self.current_preset_index]
        
        self.processing_interval = preset["interval"]
        self.processing_scale = preset["scale"]
        self.processing_width = preset["width"]
        self.processing_height = preset["height"]
        
        print(f"🎛️  Preset: {preset['name']}")
        print(f"   - Interval: 1/{preset['interval']}")
        print(f"   - Scale: {preset['scale']:.1f}")
        print(f"   - Resolution: {preset['width']}x{preset['height']}")

    # Common logging methods
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
        """Get system stability metrics (common method)"""
        return {
            'frame_count': self.frame_count,
            'processing_count': self.processing_count,
            'fps': self.fps,
            'performance_history_size': len(self.performance_history),
            'logging_enabled': self.logging_enabled,
            'log_entries': self.log_counter
        }

    def print_detailed_stats(self):
        """Print detailed system statistics (common method)"""
        stats = self.face_system.get_debug_stats() if hasattr(self.face_system, 'get_debug_stats') else {}
        
        print("\n" + "="*50)
        print("📊 DETAILED SYSTEM STATISTICS")
        print("="*50)
        print(f"Total Frames Processed: {stats.get('total_frames_processed', 'N/A')}")
        print(f"Total Faces Detected: {stats.get('total_faces_detected', 'N/A')}")
        print(f"Total Faces Recognized: {stats.get('total_faces_recognized', 'N/A')}")
        print(f"Recognition Rate: {stats.get('recognition_rate', 'N/A'):.1f}%")
        print(f"Current FPS: {self.fps:.1f}")
        print(f"Processing Interval: 1/{self.processing_interval}")
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
        """Reset all processing counters"""
        self.frame_count = 0
        self.processing_count = 0
        self.start_time = time.time()
        self.performance_history = []
        print("🔄 Processing counters reset")

    def get_processing_config(self) -> Dict[str, Any]:
        """Get current processing configuration"""
        return {
            'processing_interval': self.processing_interval,
            'processing_width': self.processing_width,
            'processing_height': self.processing_height,
            'processing_scale': self.processing_scale,
            'fps': self.fps,
            'frame_count': self.frame_count,
            'processing_count': self.processing_count
        }
            
            