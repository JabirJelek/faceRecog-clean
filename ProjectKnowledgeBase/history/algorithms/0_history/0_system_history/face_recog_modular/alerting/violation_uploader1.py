"""
Violation data upload interface with directory monitoring and file selection logic.
"""

import requests
import threading
import time
import json
import os
import glob
import re
import shutil
from typing import Optional, Dict, Any, List, Callable
import logging
from datetime import datetime, timedelta
import numpy as np

class ViolationUploader:
    """Handles reading JSON files from directory with selection logic and uploading to server."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.server_url = config.get('upload_server_url')
        self.timeout = config.get('upload_timeout', 10)
        self.max_retries = config.get('upload_max_retries', 3)
        self.retry_delay = config.get('upload_retry_delay', 2.0)
        self.enabled = config.get('enable_upload', False)
        
        # Directory monitoring settings
        self.watch_directory = config.get('watch_directory', './violations')
        self.file_pattern = config.get('file_pattern', 'violation_*.json')
        self.processed_dir = config.get('processed_directory', './processed')
        self.failed_dir = config.get('failed_directory', './failed')
        
        self.logger = logging.getLogger(__name__)
        self.session = requests.Session()
        
        # Set default headers for JSON upload
        self.session.headers.update({
            'User-Agent': 'FaceRecognitionSystem/1.0',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        
        # Upload statistics
        self.upload_count = 0
        self.failed_uploads = 0
        self.last_upload_time = 0
        self.upload_cooldown = config.get('upload_cooldown', 5)
        
        # File selection criteria
        self.selection_criteria = {
            'min_file_size': config.get('min_file_size', 100),  # bytes
            'max_file_age_hours': config.get('max_file_age_hours', 24),
            'required_fields': config.get('required_fields', ['timestamp', 'filename', 'image_data']),
            'filename_pattern': config.get('filename_pattern', r'violation_\d{8}_\d{6}_\d+_\d+\.json')
        }
        
        # Monitoring control
        self.monitoring = False
        self.monitor_thread = None
        
        # Create directories if they don't exist
        self._setup_directories()

    def _setup_directories(self):
        """Create necessary directories if they don't exist."""
        os.makedirs(self.watch_directory, exist_ok=True)
        os.makedirs(self.processed_dir, exist_ok=True)
        os.makedirs(self.failed_dir, exist_ok=True)

    def set_file_selection_criteria(self, criteria: Dict[str, Any]):
        """
        Set custom file selection criteria.
        
        Args:
            criteria: Dictionary with selection criteria:
                - min_file_size: Minimum file size in bytes
                - max_file_age_hours: Maximum file age in hours
                - required_fields: List of required JSON fields
                - filename_pattern: Regex pattern for valid filenames
                - custom_filter: Custom filter function
        """
        self.selection_criteria.update(criteria)
        self.logger.info("File selection criteria updated")

    def find_files_to_process(self) -> List[str]:
        """
        Find files in watch directory that match selection criteria.
        
        Returns:
            List of file paths ready for processing
        """
        try:
            # Find all files matching pattern
            search_path = os.path.join(self.watch_directory, self.file_pattern)
            all_files = glob.glob(search_path)
            
            if not all_files:
                self.logger.debug(f"No files found matching pattern: {search_path}")
                return []
            
            self.logger.info(f"Found {len(all_files)} files matching pattern")
            
            # Filter files based on criteria
            valid_files = []
            for file_path in all_files:
                if self._should_process_file(file_path):
                    valid_files.append(file_path)
                else:
                    self.logger.debug(f"Skipping file (doesn't meet criteria): {os.path.basename(file_path)}")
            
            self.logger.info(f"{len(valid_files)} files passed selection criteria")
            return valid_files
            
        except Exception as e:
            self.logger.error(f"Error finding files to process: {e}")
            return []

    def _should_process_file(self, file_path: str) -> bool:
        """
        Determine if a file should be processed based on selection criteria.
        
        Returns:
            bool: True if file should be processed
        """
        try:
            filename = os.path.basename(file_path)
            
            # Check filename pattern
            if not re.match(self.selection_criteria['filename_pattern'], filename):
                self.logger.debug(f"Filename pattern mismatch: {filename}")
                return False
            
            # Check file size
            file_size = os.path.getsize(file_path)
            if file_size < self.selection_criteria['min_file_size']:
                self.logger.debug(f"File too small: {filename} ({file_size} bytes)")
                return False
            
            # Check file age
            file_mtime = os.path.getmtime(file_path)
            file_age_hours = (time.time() - file_mtime) / 3600
            if file_age_hours > self.selection_criteria['max_file_age_hours']:
                self.logger.debug(f"File too old: {filename} ({file_age_hours:.1f} hours)")
                return False
            
            # Check JSON structure and required fields
            if not self._validate_json_file(file_path):
                self.logger.debug(f"JSON validation failed: {filename}")
                return False
            
            # Check custom filter if exists
            if hasattr(self, 'custom_filter') and callable(self.custom_filter):
                if not self.custom_filter(file_path):
                    self.logger.debug(f"Custom filter rejected: {filename}")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.warning(f"Error checking file {file_path}: {e}")
            return False

    def _validate_json_file(self, file_path: str) -> bool:
        """
        Validate JSON file structure and required fields.
        
        Returns:
            bool: True if JSON is valid and has required fields
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check required fields
            for field in self.selection_criteria['required_fields']:
                if field not in data:
                    self.logger.debug(f"Missing required field '{field}' in {os.path.basename(file_path)}")
                    return False
            
            # Additional validation for image_data
            if 'image_data' in data and not data['image_data']:
                self.logger.debug(f"Empty image_data in {os.path.basename(file_path)}")
                return False
            
            return True
            
        except json.JSONDecodeError as e:
            self.logger.debug(f"Invalid JSON in {os.path.basename(file_path)}: {e}")
            return False
        except Exception as e:
            self.logger.debug(f"Error validating JSON file {file_path}: {e}")
            return False

    def upload_json_file(self, json_file_path: str, move_after_upload: bool = True) -> bool:
        """
        Read an existing JSON file and upload its contents to the server.
        
        Args:
            json_file_path: Path to the JSON file to read and upload
            move_after_upload: Whether to move file after processing
            
        Returns:
            bool: True if upload was successful, False otherwise
        """
        if not self.enabled:
            self.logger.debug("Violation uploader is disabled")
            return False
        
        if not self.server_url:
            self.logger.warning("No violation upload server URL configured")
            return False
        
        if not os.path.exists(json_file_path):
            self.logger.error(f"JSON file not found: {json_file_path}")
            return False
        
        # Check cooldown period
        current_time = time.time()
        if current_time - self.last_upload_time < self.upload_cooldown:
            self.logger.debug(f"Upload skipped - in cooldown period: {self.upload_cooldown}s")
            return False
        
        try:
            # Read JSON data from file
            with open(json_file_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            self.logger.info(f"Read JSON data from: {json_file_path}")
            
            # Send the request with retries
            success = self._send_json_with_retry(json_data)
            
            if success:
                self.upload_count += 1
                self.last_upload_time = current_time
                self.logger.info(f"JSON data uploaded successfully from: {json_file_path}")
                
                # Move to processed directory
                if move_after_upload:
                    self._move_file(json_file_path, self.processed_dir)
                    
            else:
                self.failed_uploads += 1
                self.logger.error(f"Failed to upload JSON data from: {json_file_path}")
                
                # Move to failed directory
                if move_after_upload:
                    self._move_file(json_file_path, self.failed_dir)
                
            return success
            
        except json.JSONDecodeError as e:
            self.failed_uploads += 1
            self.logger.error(f"Invalid JSON in file {json_file_path}: {e}")
            if move_after_upload:
                self._move_file(json_file_path, self.failed_dir)
            return False
        except Exception as e:
            self.failed_uploads += 1
            self.logger.error(f"Error reading/uploading JSON file {json_file_path}: {e}")
            if move_after_upload:
                self._move_file(json_file_path, self.failed_dir)
            return False

    def _move_file(self, file_path: str, target_dir: str):
        """Move file to target directory using shutil for cross-device moves."""
        try:
            filename = os.path.basename(file_path)
            target_path = os.path.join(target_dir, filename)
            
            # Add timestamp if file already exists
            counter = 1
            while os.path.exists(target_path):
                name, ext = os.path.splitext(filename)
                target_path = os.path.join(target_dir, f"{name}_{counter}{ext}")
                counter += 1
            
            # Use shutil.move for cross-device compatibility
            shutil.move(file_path, target_path)
            self.logger.debug(f"Moved {filename} to {target_dir}")
            
        except Exception as e:
            self.logger.error(f"Error moving file {file_path}: {e}")

    def _send_json_with_retry(self, data: Dict[str, Any]) -> bool:
        """Send JSON data with retry logic."""
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.post(
                    self.server_url, 
                    json=data,
                    timeout=self.timeout
                )
                
                if response.status_code in [200, 201]:
                    self.logger.debug(f"Upload successful, response: {response.text}")
                    return True
                else:
                    self.logger.warning(
                        f"Upload server returned status {response.status_code} "
                        f"(attempt {attempt + 1}/{self.max_retries + 1}): {response.text}"
                    )
                    
                    # Don't retry on client errors (4xx) except 429 (Too Many Requests)
                    if 400 <= response.status_code < 500 and response.status_code != 429:
                        self.logger.warning(f"Client error {response.status_code}, not retrying")
                        return False
                    
            except requests.exceptions.Timeout:
                self.logger.warning(
                    f"Upload request timeout (attempt {attempt + 1}/{self.max_retries + 1})"
                )
            except requests.exceptions.ConnectionError:
                self.logger.warning(
                    f"Upload connection error (attempt {attempt + 1}/{self.max_retries + 1})"
                )
            except requests.exceptions.RequestException as e:
                self.logger.warning(
                    f"Upload request error: {e} "
                    f"(attempt {attempt + 1}/{self.max_retries + 1})"
                )
            
            # Wait before retry (except on last attempt)
            if attempt < self.max_retries:
                time.sleep(self.retry_delay)
        
        return False

    def process_directory(self, move_after_upload: bool = True) -> Dict[str, bool]:
        """
        Find and process all valid files in watch directory.
        
        Args:
            move_after_upload: Whether to move files after processing
            
        Returns:
            Dict with file paths as keys and success status as values
        """
        files_to_process = self.find_files_to_process()
        results = {}
        
        self.logger.info(f"Processing {len(files_to_process)} files from directory")
        
        for file_path in files_to_process:
            success = self.upload_json_file(file_path, move_after_upload)
            results[file_path] = success
            
            # Small delay between files to avoid server overload
            time.sleep(0.5)
        
        return results

    def start_directory_monitoring(self, interval: int = 30):
        """
        Start monitoring directory for new files at specified interval.
        
        Args:
            interval: Check interval in seconds
        """
        if self.monitoring:
            self.logger.warning("Directory monitoring is already running")
            return
            
        self.monitoring = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_directory,
            args=(interval,),
            daemon=True,
            name="DirectoryMonitor"
        )
        self.monitor_thread.start()
        self.logger.info(f"Started directory monitoring (interval: {interval}s)")

    def stop_directory_monitoring(self):
        """Stop directory monitoring."""
        self.monitoring = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
            if self.monitor_thread.is_alive():
                self.logger.warning("Monitor thread did not stop gracefully")
        self.logger.info("Stopped directory monitoring")

    def _monitor_directory(self, interval: int):
        """Background thread for directory monitoring."""
        while self.monitoring:
            try:
                self.process_directory()
                # Sleep in small increments to allow for quick shutdown
                for _ in range(interval):
                    if not self.monitoring:
                        break
                    time.sleep(1)
            except Exception as e:
                self.logger.error(f"Error in directory monitoring: {e}")
                if self.monitoring:  # Only sleep if we're still monitoring
                    time.sleep(interval)

    def add_custom_filter(self, filter_func: Callable[[str], bool]):
        """
        Add custom filter function for file selection.
        
        Args:
            filter_func: Function that takes file path and returns True/False
        """
        self.custom_filter = filter_func
        self.logger.info("Custom filter function added")

    def get_directory_status(self) -> Dict[str, Any]:
        """Get status of directory monitoring."""
        search_path = os.path.join(self.watch_directory, self.file_pattern)
        all_files = glob.glob(search_path)
        valid_files = self.find_files_to_process()
        
        return {
            'watch_directory': self.watch_directory,
            'file_pattern': self.file_pattern,
            'total_files_found': len(all_files),
            'files_meeting_criteria': len(valid_files),
            'processed_directory': self.processed_dir,
            'failed_directory': self.failed_dir,
            'selection_criteria': self.selection_criteria,
            'monitoring_active': self.monitoring
        }

    def upload_multiple_files(self, json_file_paths: List[str]) -> Dict[str, bool]:
        """Upload multiple JSON files and return results for each."""
        results = {}
        for file_path in json_file_paths:
            success = self.upload_json_file(file_path)
            results[file_path] = success
            time.sleep(0.1)
        return results

    def test_connection(self, test_file_path: Optional[str] = None) -> bool:
        """Test connection to the violation upload server."""
        if not self.enabled:
            self.logger.debug("Uploader disabled, skipping connection test")
            return False
            
        if not self.server_url:
            return False
        
        # Use provided test file or create minimal test data
        if test_file_path and os.path.exists(test_file_path):
            return self.upload_json_file(test_file_path, move_after_upload=False)
        else:
            # Create test file in watch directory
            test_data = {
                "timestamp": datetime.now().isoformat(),
                "filename": "test_connection.json",
                "image_format": "jpg",
                "image_data": "dGVzdF9pbWFnZV9kYXRh",  # "test_image_data" in base64
                "detected_identities": ["Test User"],
                "cctv_name": "Test-Camera"
            }
            
            test_file = os.path.join(self.watch_directory, "test_connection.json")
            try:
                with open(test_file, 'w') as f:
                    json.dump(test_data, f)
                
                success = self.upload_json_file(test_file, move_after_upload=False)
                
                # Clean up test file
                try:
                    os.remove(test_file)
                except:
                    pass
                    
                return success
            except Exception as e:
                self.logger.error(f"Error creating test file: {e}")
                return False

    def get_uploader_status(self) -> Dict[str, Any]:
        """Get the status of the violation uploader."""
        dir_status = self.get_directory_status()
        
        return {
            'enabled': self.enabled,
            'server_configured': bool(self.server_url),
            'server_url': self.server_url,
            'timeout': self.timeout,
            'max_retries': self.max_retries,
            'upload_cooldown': self.upload_cooldown,
            'directory_status': dir_status,
            'statistics': {
                'successful_uploads': self.upload_count,
                'failed_uploads': self.failed_uploads,
                'total_attempts': self.upload_count + self.failed_uploads,
                'success_rate': self.upload_count / (self.upload_count + self.failed_uploads) if (self.upload_count + self.failed_uploads) > 0 else 0
            }
        }

    def enable_uploader(self):
        """Enable the violation uploader."""
        self.enabled = True
        self.logger.info("Violation uploader ENABLED")

    def disable_uploader(self):
        """Disable the violation uploader."""
        self.enabled = False
        self.logger.info("Violation uploader DISABLED")
        
    def toggle_uploader(self):
        """Toggle the uploader state."""
        self.enabled = not self.enabled
        status = "ENABLED" if self.enabled else "DISABLED"
        self.logger.info(f"Violation uploader {status}")

    def update_config(self, config: Dict[str, Any]):
        """Update uploader configuration dynamically."""
        self.server_url = config.get('upload_server_url', self.server_url)
        self.timeout = config.get('upload_timeout', self.timeout)
        self.max_retries = config.get('upload_max_retries', self.max_retries)
        self.retry_delay = config.get('upload_retry_delay', self.retry_delay)
        self.upload_cooldown = config.get('upload_cooldown', self.upload_cooldown)
        
        # Update directory settings
        self.watch_directory = config.get('watch_directory', self.watch_directory)
        self.file_pattern = config.get('file_pattern', self.file_pattern)
        self.processed_dir = config.get('processed_directory', self.processed_dir)
        self.failed_dir = config.get('failed_directory', self.failed_dir)
        
        # Update enabled state if provided
        if 'enable_upload' in config:
            self.enabled = config['enable_upload']
        
        # Recreate directories if paths changed
        self._setup_directories()
        
        self.logger.info("Violation uploader configuration updated")
        
    def upload_violation_with_audio_sync(self, frame: np.ndarray, results: List[Dict], 
                                       filename: str, timestamp: str) -> bool:
        """
        Synchronized upload method for use with audio alerts.
        
        Args:
            frame: The frame image to upload
            results: Face recognition results
            filename: Base filename for the upload
            timestamp: Timestamp for the violation
            
        Returns:
            bool: True if upload was successful
        """
        if not self.enabled or not self.server_url:
            return False
            
        try:
            # Prepare violation data similar to image logger
            violations = [r for r in results if r.get('mask_status') == 'no_mask']
            
            # Convert image to base64
            import cv2
            import base64
            success, buffer = cv2.imencode('.jpg', frame)
            if not success:
                self.logger.error("Failed to encode frame for upload")
                return False
                
            image_data = base64.b64encode(buffer).decode('utf-8')
            
            # Prepare upload data
            upload_data = {
                "timestamp": timestamp,
                "filename": filename,
                "image_format": "jpg",
                "image_data": image_data,
                "violations": [
                    {
                        "identity": str(r.get('identity', 'Unknown')),
                        "mask_confidence": float(r.get('mask_confidence', 0)),
                        "detection_confidence": float(r.get('detection_confidence', 0))
                    } for r in violations
                ],
                "total_violations": len(violations),
                "total_faces": len(results),
                "cctv_name": "Unknown-Camera"  # This should come from config
            }
            
            # Send upload request
            return self._send_json_with_retry(upload_data)
            
        except Exception as e:
            self.logger.error(f"Error in synchronized violation upload: {e}")
            return False
        
        