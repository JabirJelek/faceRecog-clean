# logging/data_logger.py
"""
CSV data logging functionality.
"""

import csv
import datetime
from pathlib import Path
from typing import List, Dict, Optional

class DataLogger:
    """Handles CSV logging of recognition results."""
    
    def __init__(self):
        self.log_file = None
        self.logging_enabled = False
        self.log_start_time = None
        self.log_counter = 0
        self.log_interval = 5
        self.log_columns = ['timestamp', 'identity', 'mask_status']
    
    def setup_logging(self, filename: Optional[str] = None) -> bool:
        """Setup CSV logging with face names and mask status."""
        try:
            if filename is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"face_recognition_detailed_{timestamp}.csv"
            
            self.log_file = filename
            self.log_start_time = datetime.datetime.now()
            
            # Write header
            with open(self.log_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(self.log_columns)
            
            self.logging_enabled = True
            print(f"📊 Detailed face logging ENABLED: {filename}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to setup logging: {e}")
            self.logging_enabled = False
            self.log_file = None
            return False
    
    def collect_log_data(self, results: List[Dict]) -> List[Dict]:
        """Collect individual face recognition and mask status data."""
        log_entries = []
        
        if not isinstance(results, list):
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
        
        return log_entries
    
    def write_log_entries(self, log_entries: List[Dict]):
        """Write multiple log entries to CSV."""
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
    
    def toggle_logging(self, filename: Optional[str] = None):
        """Toggle logging on/off."""
        if not self.logging_enabled:
            self.setup_logging(filename)
            print("🟢 Enhanced logging STARTED")
        else:
            if self.log_file:
                duration = datetime.datetime.now() - self.log_start_time
                print(f"🔴 Logging STOPPED: {self.log_file}")
                print(f"   - Duration: {duration}")
                print(f"   - CSV entries: {self.log_counter}")
            
            self.logging_enabled = False
            self.log_file = None
            self.log_start_time = None
    
    def get_log_status(self) -> Dict:
        """Get current logging status."""
        return {
            'enabled': self.logging_enabled,
            'file': self.log_file,
            'entries': self.log_counter,
            'interval': self.log_interval,
            'start_time': self.log_start_time
        }