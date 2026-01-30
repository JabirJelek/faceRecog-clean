# # alerting/violation_uploader.py

# """
# Violation data upload interface for sending violation information to a server.
# """

# import requests
# import threading
# import time
# import json
# import base64
# from typing import Optional, Dict, Any, List
# import logging
# import numpy as np
# import cv2

# class ViolationUploader:
#     """Handles violation data upload through HTTP requests."""
    
#     def __init__(self, config: Dict[str, Any]):
#         self.config = config
#         self.server_url = config.get('upload_server_url')
#         self.timeout = config.get('upload_timeout', 10)
#         self.max_retries = config.get('upload_max_retries', 3)
#         self.retry_delay = config.get('upload_retry_delay', 2.0)
#         self.enabled = config.get('enable_upload', False)  # Enable/disable flag
        
#         self.logger = logging.getLogger(__name__)
#         self.session = requests.Session()
        
#         # Set default headers for JSON upload
#         self.session.headers.update({
#             'User-Agent': 'FaceRecognitionSystem/1.0',
#             'Content-Type': 'application/json',
#             'Accept': 'application/json'
#         })
        
#         # Upload statistics
#         self.upload_count = 0
#         self.failed_uploads = 0
#         self.last_upload_time = 0
#         self.upload_cooldown = config.get('upload_cooldown', 5)  # Minimum seconds between uploads

#     def upload_violation_data(self, violation_data: Dict[str, Any]) -> bool:
#         """
#         Upload violation data as JSON to the server.
        
#         Args:
#             violation_data: The violation data in the specified JSON structure
            
#         Returns:
#             bool: True if upload was successful, False otherwise
#         """
#         # Check if uploader is disabled
#         if not self.enabled:
#             self.logger.debug("Violation uploader is disabled")
#             return False
        
#         if not self.server_url:
#             self.logger.warning("No violation upload server URL configured")
#             return False
        
#         if not violation_data:
#             self.logger.warning("Empty violation data provided for upload")
#             return False
        
#         # Check cooldown period
#         current_time = time.time()
#         if current_time - self.last_upload_time < self.upload_cooldown:
#             self.logger.debug(f"Upload skipped - in cooldown period: {self.upload_cooldown}s")
#             return False
        
#         try:
#             # Validate required fields in violation data
#             if not self._validate_violation_data(violation_data):
#                 self.logger.error("Invalid violation data structure")
#                 return False
            
#             # Send the request with retries
#             success = self._send_json_with_retry(violation_data)
            
#             if success:
#                 self.upload_count += 1
#                 self.last_upload_time = current_time
#                 self.logger.info(f"Violation data uploaded successfully: {violation_data['filename']}")
#             else:
#                 self.failed_uploads += 1
#                 self.logger.error(f"Failed to upload violation data: {violation_data['filename']}")
                
#             return success
            
#         except Exception as e:
#             self.failed_uploads += 1
#             self.logger.error(f"Error uploading violation data: {e}")
#             return False

#     def _validate_violation_data(self, data: Dict[str, Any]) -> bool:
#         """Validate that the violation data has required structure."""
#         required_fields = ['timestamp', 'filename', 'image_data']
        
#         for field in required_fields:
#             if field not in data:
#                 self.logger.error(f"Missing required field: {field}")
#                 return False
        
#         # Validate image_data is base64
#         try:
#             if isinstance(data['image_data'], str):
#                 base64.b64decode(data['image_data'], validate=True)
#         except Exception:
#             self.logger.error("Invalid base64 image data")
#             return False
        
#         return True

#     def _send_json_with_retry(self, data: Dict[str, Any]) -> bool:
#         """Send JSON data with retry logic."""
#         for attempt in range(self.max_retries + 1):
#             try:
#                 response = self.session.post(
#                     self.server_url, 
#                     json=data,
#                     timeout=self.timeout
#                 )
                
#                 if response.status_code in [200, 201]:
#                     self.logger.debug(f"Upload successful, response: {response.text}")
#                     return True
#                 else:
#                     self.logger.warning(
#                         f"Upload server returned status {response.status_code} "
#                         f"(attempt {attempt + 1}/{self.max_retries + 1}): {response.text}"
#                     )
                    
#             except requests.exceptions.Timeout:
#                 self.logger.warning(
#                     f"Upload request timeout (attempt {attempt + 1}/{self.max_retries + 1})"
#                 )
#             except requests.exceptions.ConnectionError:
#                 self.logger.warning(
#                     f"Upload connection error (attempt {attempt + 1}/{self.max_retries + 1})"
#                 )
#             except requests.exceptions.RequestException as e:
#                 self.logger.warning(
#                     f"Upload request error: {e} "
#                     f"(attempt {attempt + 1}/{self.max_retries + 1})"
#                 )
            
#             # Wait before retry (except on last attempt)
#             if attempt < self.max_retries:
#                 time.sleep(self.retry_delay)
        
#         return False

#     def upload_violation_data_async(self, violation_data: Dict[str, Any]) -> threading.Thread:
#         """
#         Upload violation data in a background thread to avoid blocking.
        
#         Returns:
#             threading.Thread: The background thread
#         """
#         thread = threading.Thread(
#             target=self.upload_violation_data,
#             args=(violation_data,),
#             daemon=True,
#             name="ViolationUploadThread"
#         )
#         thread.start()
#         return thread

#     def test_connection(self) -> bool:
#         """Test connection to the violation upload server."""
#         if not self.enabled:
#             self.logger.debug("Uploader disabled, skipping connection test")
#             return False
            
#         if not self.server_url:
#             return False
        
#         # Create minimal test data
#         test_data = {
#             "timestamp": "2024-01-01T00:00:00.000000",
#             "filename": "test_connection",
#             "image_format": "jpg",
#             "image_data": base64.b64encode(b"test_image_data").decode('utf-8'),
#             "resolution": {"width": 100, "height": 100},
#             "resized": False,
#             "metadata": {
#                 "violation_count": 0,
#                 "total_faces": 0,
#                 "violations": []
#             }
#         }
        
#         return self.upload_violation_data(test_data)

#     def get_uploader_status(self) -> Dict[str, Any]:
#         """Get the status of the violation uploader."""
#         return {
#             'enabled': self.enabled,
#             'server_configured': bool(self.server_url),
#             'server_url': self.server_url,
#             'timeout': self.timeout,
#             'max_retries': self.max_retries,
#             'upload_cooldown': self.upload_cooldown,
#             'statistics': {
#                 'successful_uploads': self.upload_count,
#                 'failed_uploads': self.failed_uploads,
#                 'total_attempts': self.upload_count + self.failed_uploads
#             }
#         }

#     def enable_uploader(self):
#         """Enable the violation uploader."""
#         self.enabled = True
#         self.logger.info("Violation uploader ENABLED")

#     def disable_uploader(self):
#         """Disable the violation uploader."""
#         self.enabled = False
#         self.logger.info("Violation uploader DISABLED")

#     def toggle_uploader(self):
#         """Toggle the uploader enabled state."""
#         self.enabled = not self.enabled
#         status = "ENABLED" if self.enabled else "DISABLED"
#         self.logger.info(f"Violation uploader {status}")

#     def update_config(self, config: Dict[str, Any]):
#         """Update uploader configuration dynamically."""
#         self.server_url = config.get('upload_server_url', self.server_url)
#         self.timeout = config.get('upload_timeout', self.timeout)
#         self.max_retries = config.get('upload_max_retries', self.max_retries)
#         self.retry_delay = config.get('upload_retry_delay', self.retry_delay)
#         self.upload_cooldown = config.get('upload_cooldown', self.upload_cooldown)
        
#         # Update enabled state if provided
#         if 'enable_upload' in config:
#             self.enabled = config['enable_upload']
        
#         self.logger.info("Violation uploader configuration updated")

#     def prepare_violation_data(self, frame: np.ndarray, results: List[Dict], 
#                              filename: str, timestamp: str) -> Dict[str, Any]:
#         """
#         Prepare violation data in the required JSON structure.
        
#         Args:
#             frame: Original frame as numpy array
#             results: Face detection results
#             filename: Unique filename for this violation
#             timestamp: ISO format timestamp
            
#         Returns:
#             Dict with violation data in the required structure
#         """
#         try:
#             # Encode frame to base64
#             success, encoded_image = cv2.imencode('.jpg', frame)
#             if not success:
#                 self.logger.error("Failed to encode frame to JPEG")
#                 return None
                
#             image_base64 = base64.b64encode(encoded_image).decode('utf-8')
            
#             # Extract violations from results
#             violations = []
#             for result in results:
#                 if result.get('mask_status') == 'no_mask':
#                     violation = {
#                         "identity": result.get('identity', 'Unknown'),
#                         "mask_confidence": result.get('mask_confidence', 0.0),
#                         "recognition_confidence": result.get('recognition_confidence', 0.0),
#                         "detection_confidence": result.get('detection_confidence', 0.0),
#                         "bbox": result.get('bbox', [0, 0, 0, 0])
#                     }
#                     violations.append(violation)
            
#             # Build the complete violation data structure
#             violation_data = {
#                 "timestamp": timestamp,
#                 "filename": filename,
#                 "image_format": "jpg",
#                 "image_data": image_base64,
#                 "resolution": {
#                     "width": frame.shape[1],
#                     "height": frame.shape[0]
#                 },
#                 "resized": False,  # We're using the original frame
#                 "target_resolution": {
#                     "width": self.config.get('image_resize_width', 1024),
#                     "height": self.config.get('image_resize_height', 576)
#                 },
#                 "metadata": {
#                     "violation_count": len(violations),
#                     "total_faces": len(results),
#                     "violations": violations
#                 }
#             }
            
#             return violation_data
            
#         except Exception as e:
#             self.logger.error(f"Error preparing violation data: {e}")
#             return None

#     def upload_violation_with_audio_sync(self, frame: np.ndarray, results: List[Dict], 
#                                        filename: str, timestamp: str) -> bool:
#         """
#         Upload violation data synchronized with audio alerts.
#         This should be called when audio alerts are triggered.
        
#         Returns:
#             bool: True if upload was successful or not needed, False on error
#         """
#         if not self.enabled:
#             return True  # Not an error if disabled
            
#         # Only upload if there are actual violations
#         if not any(result.get('mask_status') == 'no_mask' for result in results):
#             return True
            
#         try:
#             violation_data = self.prepare_violation_data(frame, results, filename, timestamp)
#             if violation_data:
#                 # Upload in background thread to not block audio
#                 upload_thread = self.upload_violation_data_async(violation_data)
#                 self.logger.info(f"Violation upload started in background thread: {filename}")
#                 return True
#             else:
#                 self.logger.error("Failed to prepare violation data for upload")
#                 return False
                
#         except Exception as e:
#             self.logger.error(f"Error in synchronized upload: {e}")
#             return False
        
        