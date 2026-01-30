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
import requests
import time  # 🆕 FIX: Changed from 'from datetime import time'

class ImageLogger:
    """Handles image logging for mask violations and system events."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logging_enabled = False
        self.image_log_folder: Optional[Path] = None
        self.saved_image_count = 0
        self.last_image_save_time = 0
        
        # Annotation configuration
        self.base_box_thickness = config.get('annotation_box_thickness', 1)
        self.base_text_thickness = config.get('annotation_text_thickness', 1)
        self.min_text_scale = config.get('annotation_min_text_scale', 0.3)
        self.max_text_scale = config.get('annotation_max_text_scale', 0.8)
        
        # Configuration parameters
        self.image_log_interval = config.get('image_log_interval', 3)
        self.max_images_per_session = config.get('max_images_per_session', 500)
        self.min_save_interval = config.get('min_save_interval', 2.0)
        self.image_quality = config.get('image_quality', 95)
        self.annotate_images = config.get('annotate_images', True)
        self.enable_base64_logging = config.get('enable_base64_logging', True)
        self.base64_quality = config.get('base64_quality', 85)
        
        # Image resize configuration
        self.enable_resize = config.get('enable_image_resize', False)
        self.resize_width = config.get('image_resize_width', 640)
        self.resize_height = config.get('image_resize_height', 480)
        self.resize_method = config.get('image_resize_method', 'default')
        
        # 🆕 FIX: Enhanced CCTV name configuration with better fallback
        self.cctv_name = config.get('cctv_name')
        if not self.cctv_name or self.cctv_name == 'Unknown-Camera':
            # Try to extract from URL or other config parameters
            self.cctv_name = self._extract_cctv_name_from_config(config)
        print(f"📹 ImageLogger initialized with CCTV name: {self.cctv_name}")
        
        # Server push configuration
        self.server_push_enabled = config.get('server_push_enabled', False)
        self.server_endpoint = config.get('server_endpoint', '')
        self.server_push_cooldown = config.get('server_push_cooldown', 30)  # seconds
        self.last_server_push_time = 0
        self.server_timeout = config.get('server_timeout', 10)  # seconds
        self.server_retry_attempts = config.get('server_retry_attempts', 3)
        self.server_retry_delay = config.get('server_retry_delay', 2)  # seconds
        
        # Statistics
        self.stats = {
            'total_saved': 0,
            'violations_logged': 0,
            'base64_saved': 0,
            'errors': 0,
            'last_save_time': None,
            'resized_images': 0,
            'server_pushes': 0,
            'server_errors': 0,
            'last_server_push': None
            # REMOVE violation verification stats
        }
        
        self.logger = logging.getLogger(__name__)
        self.recent_violations = deque(maxlen=10)
        self.pending_server_violations = deque(maxlen=50)

    def _extract_cctv_name_from_config(self, config: Dict[str, Any]) -> str:
        """
        Extract CCTV name from configuration with enhanced fallback logic.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            str: Extracted CCTV name
        """
        try:
            # First, try to get from config directly
            cctv_name = config.get('cctv_name')
            if cctv_name and cctv_name != 'Unknown-Camera':
                return cctv_name
            
            # Try to extract from URL
            url = config.get('url', '')
            if url:
                extracted_name = self._extract_name_from_url(url)
                if extracted_name and extracted_name != 'Unknown-Camera':
                    return extracted_name
            
            # Try from description
            description = config.get('description', '')
            if description and description != 'Unknown Source':
                safe_name = self._create_safe_name(description)
                if safe_name:
                    return safe_name
            
            # Use source_id if available
            source_id = config.get('source_id')
            if source_id:
                return f"Camera-{source_id}"
            
            # Final fallback with timestamp
            timestamp = datetime.datetime.now().strftime("%H%M%S")
            return f"Camera-{timestamp}"
            
        except Exception as e:
            self.logger.warning(f"Could not extract CCTV name from config: {e}")
            return "Unknown-Camera"

    def _extract_name_from_url(self, url: str) -> str:
        """
        Extract camera name from URL.
        
        Args:
            url: Camera URL
            
        Returns:
            str: Extracted name
        """
        try:
            import re
            from urllib.parse import urlparse
            
            parsed = urlparse(url)
            
            # Enhanced pattern matching for various CCTV URL formats
            patterns = [
                r'/(?:Channels|channels|CHANNELS)/(\d+)',
                r'/(?:channel|Channel|CHANNEL)[/_]?(\d+)',
                r'/(?:cam|Cam|CAM)[/_]?(\d+)',
                r'/(?:stream|Stream|STREAM)[/_]?(\d+)',
                r'/(\d+)$',
                r'/(\d+)/?$',
                r'[Cc]hannel[_-]?(\d+)',
                r'[Cc]am[_-]?(\d+)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, parsed.path)
                if match:
                    channel_num = match.group(1)
                    return f"Camera-{channel_num}"
            
            # Try hostname-based naming
            if parsed.hostname:
                if re.match(r'\d+\.\d+\.\d+\.\d+', parsed.hostname):
                    return f"IP-Camera-{parsed.hostname}"
                else:
                    # Use subdomain or domain name
                    parts = parsed.hostname.split('.')
                    if len(parts) > 1 and parts[0] not in ['www', 'api']:
                        return f"Camera-{parts[0].title()}"
            
            # Use last part of path
            path_parts = [part for part in parsed.path.split('/') if part]
            if path_parts:
                last_part = path_parts[-1]
                clean_part = re.sub(r'\.\w+$', '', last_part)
                if clean_part and clean_part not in ['live', 'stream', 'video', 'main']:
                    return f"Camera-{clean_part.title()}"
            
            return "Unknown-Camera"
            
        except Exception as e:
            self.logger.warning(f"Error extracting name from URL: {e}")
            return "Unknown-Camera"

    def _create_safe_name(self, name: str) -> str:
        """
        Create filesystem-safe name.
        
        Args:
            name: Original name
            
        Returns:
            str: Safe name
        """
        try:
            import re
            # Replace problematic characters
            safe_name = re.sub(r'[^\w\-_.]', '_', name)
            # Remove multiple underscores
            safe_name = re.sub(r'_+', '_', safe_name)
            # Remove leading/trailing underscores
            safe_name = safe_name.strip('_')
            return safe_name if safe_name else "Unknown-Camera"
        except:
            return "Unknown-Camera"

    # 🆕 NEW: Method to update CCTV name dynamically
    def update_cctv_name(self, cctv_name: str) -> None:
        """
        Update CCTV name dynamically.
        
        Args:
            cctv_name: New CCTV name
        """
        if cctv_name and cctv_name != 'Unknown-Camera':
            old_name = self.cctv_name
            self.cctv_name = cctv_name
            self.config['cctv_name'] = cctv_name
            self.logger.info(f"🔄 Updated CCTV name: {old_name} → {cctv_name}")
        else:
            self.logger.warning(f"⚠️ Invalid CCTV name provided: {cctv_name}")
                     
    def debug_server_push(self, violation_data: Dict[str, Any]) -> None:
        """Debug method to check why server push isn't working"""
        print(f"🔍 DEBUG SERVER PUSH:")
        print(f"  - Server push enabled: {self.server_push_enabled}")
        print(f"  - Server endpoint: {self.server_endpoint}")
        print(f"  - Base64 data available: {bool(violation_data.get('image_data'))}")
        print(f"  - Base64 data length: {len(violation_data.get('image_data', ''))}")
        print(f"  - Filename: {violation_data.get('filename')}")
        print(f"  - Detected name: {violation_data.get('detected_name')}")
        print(f"  - CCTV name: {self.cctv_name}")
        
        # Check cooldown
        current_time = time.time()
        time_since_last_push = current_time - self.last_server_push_time
        print(f"  - Time since last push: {time_since_last_push:.1f}s")
        print(f"  - Cooldown period: {self.server_push_cooldown}s")
        print(f"  - Can push: {time_since_last_push >= self.server_push_cooldown}")      
    
    def push_violation_to_server(self, violation_data: Dict[str, Any]) -> bool:
        """
        Push violation data to configured server endpoint with cooldown.
        
        Args:
            violation_data: Dictionary containing violation data including base64 image
            
        Returns:
            bool: True if push successful, False otherwise
        """
        # Check if server push is enabled
        if not self.server_push_enabled:
            self.logger.debug("Server push disabled")
            return False
        
        # Check cooldown
        current_time = time.time()  # 🆕 FIX: Use time.time() instead of datetime.time
        if current_time - self.last_server_push_time < self.server_push_cooldown:
            remaining = self.server_push_cooldown - (current_time - self.last_server_push_time)
            self.logger.debug(f"Server push cooldown active. Skipping push. Next push in {remaining:.1f}s")
            return False
        
        # Validate endpoint
        if not self.server_endpoint:
            self.logger.error("Server endpoint not configured")
            return False
        
        try:
            # 🆕 UPDATED: Prepare the payload with ONLY required fields
            payload = {
                'filename': violation_data.get('filename', ''),
                'image_format': violation_data.get('image_format', 'jpg'),
                'image_data': violation_data.get('image_data', ''),
                'detected_name': violation_data.get('detected_name', 'Unknown'),
                'cctv_name': self.cctv_name  # 🆕 FIX: Use the instance's CCTV name
            }
            
            # Validate required fields
            if not payload['image_data']:
                self.logger.error("No image data available for server push")
                return False
                
            if not payload['filename']:
                # Generate a filename if not provided
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                payload['filename'] = f"violation_{timestamp}"
            
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': f'FaceRecognition-Logger/1.0 ({self.cctv_name})'
            }
            
            # Retry logic
            for attempt in range(self.server_retry_attempts):
                try:
                    self.logger.info(f"Pushing violation to server (attempt {attempt + 1}/{self.server_retry_attempts})...")
                    
                    response = requests.post(
                        self.server_endpoint,
                        json=payload,
                        headers=headers,
                        timeout=self.server_timeout
                    )
                    
                    if response.status_code == 200:
                        self.last_server_push_time = current_time
                        self.stats['server_pushes'] += 1
                        self.stats['last_server_push'] = datetime.datetime.now()
                        
                        self.logger.info(f"✅ Successfully pushed violation to server. Response: {response.status_code}")
                        self.logger.debug(f"📤 Payload sent: filename={payload['filename']}, detected_name={payload['detected_name']}, cctv_name={payload['cctv_name']}")
                        return True
                    else:
                        self.logger.warning(f"Server returned error status: {response.status_code} - {response.text}")
                        
                        # If it's a client error (4xx), don't retry
                        if 400 <= response.status_code < 500:
                            self.logger.error(f"Client error {response.status_code}, stopping retries")
                            break
                        
                except requests.exceptions.Timeout:
                    self.logger.warning(f"Server request timeout (attempt {attempt + 1}/{self.server_retry_attempts})")
                except requests.exceptions.ConnectionError:
                    self.logger.warning(f"Server connection error (attempt {attempt + 1}/{self.server_retry_attempts})")
                except requests.exceptions.RequestException as e:
                    self.logger.warning(f"Server request error: {e} (attempt {attempt + 1}/{self.server_retry_attempts})")
                
                # Wait before retry (except on last attempt)
                if attempt < self.server_retry_attempts - 1:
                    time.sleep(self.server_retry_delay)
            
            # If we get here, all attempts failed
            self.stats['server_errors'] += 1
            self.logger.error(f"❌ Failed to push violation to server after {self.server_retry_attempts} attempts")
            return False
            
        except Exception as e:
            self.stats['server_errors'] += 1
            self.logger.error(f"❌ Unexpected error during server push: {e}")
            return False
                
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
        current_time = time.time()  # 🆕 FIX: Use time.time() for consistency
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
            
            # Apply resize AFTER annotation to maintain annotation quality
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
                        self.logger.info(f"✅ Base64 data generated: {len(base64_data)} characters")
                
                self.saved_image_count += 1
                self.last_image_save_time = current_time
                self.stats['total_saved'] += 1
                self.stats['violations_logged'] += 1
                self.stats['last_save_time'] = datetime.datetime.now()
                
                # Only save violations that are verified by TrackingManager
                violations = [
                    r for r in results 
                    if r.get('mask_status') == 'no_mask' 
                    and r.get('violation_verified', False)  # ← CRITICAL: Use TrackingManager's flag
                ]
                
                # Skip if no verified violations
                if not violations:
                    return False, None   
                             
                violation_record = {
                    'timestamp': timestamp,
                    'violations': len(violations),
                    'filepath': filepath,
                    'base64_saved': base64_data is not None,
                    'resized': self.enable_resize
                }
                self.recent_violations.append(violation_record)
                                                
                # 🆕 UPDATED: Push to server if enabled and we have base64 data
                if self.server_push_enabled and base64_data:
                    detected_names = []
                    for result in violations:  # Only include verified violations
                        identity = result.get('identity', 'Unknown')
                        # Add additional verification metadata from TrackingManager
                        violation_duration = result.get('violation_duration', 0)
                        violation_frames = result.get('violation_frames', 0)
                        verification_level = result.get('verification_level', 'unknown')
                        
                        # Append with verification metadata
                        detected_names.append(f"{identity} ({verification_level}, {violation_duration:.1f}s)")
                    
                    # 🆕 IMPROVED: Create comma-separated string of ALL detected names
                    if detected_names:
                        # Join with comma separation, each identity is clearly separated
                        detected_name_str = ', '.join(detected_names)
                    else:
                        detected_name_str = "Unknown"
                    
                    # 🆕 UPDATED: Prepare violation data with ONLY required fields
                    violation_data = {
                        'filename': filename.replace('.jpg', ''),  # Remove extension for server
                        'image_format': 'jpg',
                        'image_data': base64_data,
                        'detected_name': detected_name_str  # 🆕 Now properly formatted
                        # cctv_name is added automatically in push_violation_to_server
                    }
                    
                    # Log the detected names for debugging
                    self.logger.info(f"👤 Detected names for server push: {detected_name_str}")
                    
                    # Attempt to push to server (runs in background, doesn't block)
                    server_success = self.push_violation_to_server(violation_data)
                    violation_record['server_pushed'] = server_success
                    if server_success:
                        self.logger.info(f"📤 Server push successful for {detected_name_str}")
                    else:
                        self.logger.warning(f"❌ Server push failed for {detected_name_str}")
                else:
                    if not self.server_push_enabled:
                        self.logger.debug("Server push disabled, skipping")
                    if not base64_data:
                        self.logger.debug("No base64 data available for server push")
                
                self.logger.info(
                    f"✅ Saved violation image #{self.saved_image_count}: {filename} "
                    f"(Violations: {len(violations)}, Base64: {base64_data is not None}, "
                    f"Resized: {self.enable_resize}, Server Push: {self.server_push_enabled and base64_data})"
                )
                
                return True, base64_data
            else:
                self.stats['errors'] += 1
                self.logger.error(f"❌ Failed to save image: {filepath}")
                return False, None
                
        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(f"❌ Error saving annotated frame: {e}")
            return False, None
        
    def update_server_config(self, server_config: Dict[str, Any]) -> None:
        """
        Update server push configuration dynamically.
        
        Args:
            server_config: Dictionary with server configuration
                - server_push_enabled: bool
                - server_endpoint: str
                - server_push_cooldown: float (seconds)
                - server_timeout: int (seconds)
                - server_retry_attempts: int
                - server_retry_delay: float (seconds)
        """
        try:
            self.server_push_enabled = server_config.get('server_push_enabled', self.server_push_enabled)
            self.server_endpoint = server_config.get('server_endpoint', self.server_endpoint)
            self.server_push_cooldown = server_config.get('server_push_cooldown', self.server_push_cooldown)
            self.server_timeout = server_config.get('server_timeout', self.server_timeout)
            self.server_retry_attempts = server_config.get('server_retry_attempts', self.server_retry_attempts)
            self.server_retry_delay = server_config.get('server_retry_delay', self.server_retry_delay)
            
            self.logger.info(f"🔄 Updated server config: enabled={self.server_push_enabled}, "
                           f"endpoint={self.server_endpoint}, cooldown={self.server_push_cooldown}s")
                           
        except Exception as e:
            self.logger.error(f"❌ Error updating server config: {e}")
                    
    def get_logging_status(self) -> Dict[str, Any]:
        """Get current logging status and statistics."""
        status = {
            'enabled': self.logging_enabled,
            'image_log_folder': str(self.image_log_folder) if self.image_log_folder else None,
            'saved_image_count': self.saved_image_count,
            'max_images_per_session': self.max_images_per_session,
            'stats': self.stats.copy(),
            'recent_violations': list(self.recent_violations),
            'cctv_name': self.cctv_name  # 🆕 FIX: Use the instance's CCTV name
        }
        
        # Add resize configuration to status
        status['resize_config'] = {
            'enabled': self.enable_resize,
            'width': self.resize_width,
            'height': self.resize_height,
            'method': self.resize_method
        }
        
        # Add server push configuration to status
        status['server_config'] = {
            'enabled': self.server_push_enabled,
            'endpoint': self.server_endpoint,
            'cooldown': self.server_push_cooldown,
            'timeout': self.server_timeout,
            'retry_attempts': self.server_retry_attempts,
            'retry_delay': self.server_retry_delay,
            'last_push_time': self.last_server_push_time,
            'time_since_last_push': time.time() - self.last_server_push_time if self.last_server_push_time > 0 else None
        }
        
        return status

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
            
            self.logger.info(f"Image logging ENABLED: {self.image_log_folder}")
            self.logger.info(f"  - Max images: {self.max_images_per_session}")
            self.logger.info(f"  - Quality: {self.image_quality}%")
            self.logger.info(f"  - Annotations: {self.annotate_images}")
            self.logger.info(f"  - Base64 logging: {self.enable_base64_logging}")
            self.logger.info(f"  - Resize enabled: {self.enable_resize}")
            self.logger.info(f"  - CCTV Name: {self.cctv_name}")  # 🆕 FIX: Use the instance's CCTV name
            self.logger.info(f"  - Server push: {self.server_push_enabled}")
            if self.server_push_enabled:
                self.logger.info(f"  - Server endpoint: {self.server_endpoint}")
                self.logger.info(f"  - Push cooldown: {self.server_push_cooldown}s")
            if self.enable_resize:
                self.logger.info(f"  - Resize dimensions: {self.resize_width}x{self.resize_height}")
                self.logger.info(f"  - Resize method: {self.resize_method}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to setup image logging: {e}")
            self.logging_enabled = False
            self.image_log_folder = None
            return False
        
    def _resize_image(self, image: np.ndarray) -> np.ndarray:
        """
        Resize image according to configured dimensions and method.
        
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
            
            self.stats['resized_images'] += 1
            self.logger.debug(f"Resized image from {original_width}x{original_height} to {self.resize_width}x{self.resize_height}")
            
            return resized_image
            
        except Exception as e:
            self.logger.error(f"Error resizing image: {e}")
            return image  # Return original image on error
        
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
        
    def _prepare_violation_metadata(self, results: List[Dict]) -> Dict[str, Any]:
        """Prepare violation metadata that is JSON serializable"""
        violations = [r for r in results if r.get('mask_status') == 'no_mask']
        
        # 🆕 UPDATED: Build serializable violations list with ALL identities
        serializable_violations = []
        for r in violations:
            identity = r.get('identity', 'Unknown')
            # 🆕 UPDATED: Keep "Unknown" as a valid identity
            violation_data = {
                "identity": str(identity),  # Keep as string, including "Unknown"
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
    
    def _annotate_frame(self, frame: np.ndarray, results: List[Dict]) -> np.ndarray:
        """Apply comprehensive annotations to the frame with dynamic scaling."""
        annotated_frame = frame.copy()
        h, w = annotated_frame.shape[:2]
        
        # Get dynamic text parameters based on current frame size
        text_x, text_y, text_scale = self.get_dynamic_text_params(w, h)
        
        # Initialize variables for summary text
        violations = [r for r in results if r.get('mask_status') == 'no_mask']
        
        # Draw bounding boxes and labels
        for result in results:
            x1, y1, x2, y2 = result['bbox']
            identity = result.get('identity', 'Unknown')
            rec_conf = result.get('recognition_confidence', 0)
            det_conf = result.get('detection_confidence', 0)
            mask_status = result.get('mask_status', 'unknown')  
            mask_conf = result.get('mask_confidence', 0.0)
            
            # Color coding
            if identity and identity != "Unknown":
                if mask_status == "mask":
                    color = (0, 255, 0)  # Green
                    label_color = color
                    text_color = (0, 0, 0)
                else:
                    color = (0, 255, 255)  # Yellow
                    label_color = color
                    text_color = (0, 0, 0)                    
            else:
                if mask_status == "mask":
                    color = (255, 255, 0)  # Cyan
                    label_color = color
                    text_color = (0, 0, 0)                    
                else:
                    color = (0, 0, 255)    # Red
                    label_color = (0, 0, 255)
                    text_color = (255, 255, 255)  # White text on red background
            
            # NEW: Optimized box thickness for 640x288 resolution
            # Scale thickness based on resolution - much thinner for smaller frames
            base_thickness = 1  # Reduced from 3
            box_thickness = max(1, int(base_thickness * (w / 640)))  # Much thinner scaling
            
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, box_thickness)
            
            # Prepare label
            if identity and identity != "Unknown":
                base_label = f"{identity} (Rec:{rec_conf:.2f})"
            else:
                base_label = f"Unknown (Det:{det_conf:.2f})"
            
            # Add mask status to label
            mask_label = f" | Mask: {mask_status}({mask_conf:.2f})"
            full_label = base_label + mask_label
            
            # NEW: Optimized text parameters for better readability
            label_scale = text_scale * 0.7  # Smaller scale for labels
            label_thickness = 1  # Reduced from 2 - much thinner text
            
            # Calculate text size for background
            label_size = cv2.getTextSize(full_label, cv2.FONT_HERSHEY_SIMPLEX, label_scale, label_thickness)[0]
            
            # Draw label background
            cv2.rectangle(annotated_frame, (x1, y1 - label_size[1] - 10),  # Reduced padding
                        (x1 + label_size[0], y1), label_color, -1)
            
            # Draw label text with optimized thickness
            cv2.putText(annotated_frame, full_label, (x1, y1 - 5),  # Reduced offset
                    cv2.FONT_HERSHEY_SIMPLEX, label_scale, text_color, label_thickness)
        
        # Add violation summary with optimized parameters
        violation_text = f"Violations: {len(violations)} | Total Faces: {len(results)}"
        vio_color = (0, 0, 255)
        
        # NEW: Optimized summary text
        summary_thickness = 1  # Reduced from 2
        cv2.putText(annotated_frame, violation_text, (text_x, text_y),
                cv2.FONT_HERSHEY_SIMPLEX, text_scale, vio_color, summary_thickness)  
        
        return annotated_frame

    def get_dynamic_text_params(self, frame_width: int, frame_height: int, 
                            preset: str = "violation_summary") -> Tuple[int, int, float]:
        """
        Calculate dynamic text parameters optimized for 640x288 resolution.
        
        Args:
            frame_width: Current frame width
            frame_height: Current frame height  
            preset: Text preset type
                    
        Returns:
            Tuple of (x, y, scale) adjusted for current resolution
        """
        # Define presets optimized for 640x288 resolution
        presets = {
            "violation_summary": {"x": 10, "y": frame_height - 20, "scale": 0.4},  # Bottom-left
            "header": {"x": 10, "y": 25, "scale": 0.5},
            "info": {"x": 10, "y": 50, "scale": 0.35},
            "counter": {"x": frame_width - 100, "y": 25, "scale": 0.4}  # Top-right
        }
        
        if preset not in presets:
            preset = "violation_summary"
        
        base_config = presets[preset]
        
        # For small resolutions like 640x288, use more conservative scaling
        base_width, base_height = 640, 480  # Reference resolution
        
        # Calculate scaling factors with limits for small frames
        width_ratio = frame_width / base_width
        height_ratio = frame_height / base_height
        
        # Use more conservative scaling for small frames
        scale_ratio = min(width_ratio, height_ratio)  # Use the smaller ratio
        
        # Adjust scale - more aggressive reduction for small frames
        scale = base_config["scale"] * scale_ratio
        
        # Ensure reasonable bounds for small resolutions
        min_scale = 0.3
        max_scale = 0.8  # Reduced maximum scale for small frames
        scale = max(min(scale, max_scale), min_scale)
        
        # Use preset positions (already optimized for 640x288)
        x = base_config["x"]
        y = base_config["y"]
        
        return x, y, scale
 
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

    def disable_logging(self):
        """Disable image logging."""
        if self.logging_enabled:
            self.logger.info(
                f"Image logging disabled. Total images saved: {self.saved_image_count}, "
                f"Resized images: {self.stats['resized_images']}"
            )
        self.logging_enabled = False

###############################

    def update_annotation_config(self, annotation_config: Dict[str, Any]) -> None:
        """
        Update annotation configuration dynamically.
        
        Args:
            annotation_config: Dictionary with annotation configuration
                - base_box_thickness: int (default: 1)
                - base_text_thickness: int (default: 1) 
                - min_text_scale: float (default: 0.3)
                - max_text_scale: float (default: 0.8)
        """
        try:
            self.base_box_thickness = annotation_config.get('base_box_thickness', 1)
            self.base_text_thickness = annotation_config.get('base_text_thickness', 1)
            self.min_text_scale = annotation_config.get('min_text_scale', 0.3)
            self.max_text_scale = annotation_config.get('max_text_scale', 0.8)
            
            self.logger.info(f"Updated annotation config: box_thickness={self.base_box_thickness}, "
                        f"text_thickness={self.base_text_thickness}, "
                        f"text_scale_range=({self.min_text_scale}, {self.max_text_scale})")
                        
        except Exception as e:
            self.logger.error(f"Error updating annotation config: {e}")
            
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
        Save image as base64 encoded JSON file with ONLY required fields.
        
        Args:
            image: Image to save
            filename: Base filename (without extension)
            subfolder: Subfolder within base64 directory
            metadata: Additional metadata to include (for detected_name extraction)
            
        Returns:
            bool: True if save successful
        """
        if not self.enable_base64_logging or not self.image_log_folder:
            return False
            
        try:
            # Convert image to base64
            base64_data = self._image_to_base64(image)
            
            # 🆕 IMPROVED: Extract ALL detected names from violations, including Unknown
            detected_names = []
            if metadata and 'violations' in metadata:
                # Extract ALL identities from violations, keep "Unknown" as separate entries
                for violation in metadata['violations']:
                    identity = violation.get('identity', 'Unknown')
                    # 🆕 FIX: Include ALL identities, don't filter out 'Unknown'
                    # Also handle None values properly
                    if identity is None:
                        identity = 'Unknown'
                    detected_names.append(identity)
            
            # 🆕 IMPROVED: Create comma-separated string of ALL detected names
            if detected_names:
                # Join with comma separation, each identity is clearly separated
                detected_name_str = ', '.join(detected_names)
            else:
                detected_name_str = "Unknown"
            
            # 🆕 UPDATED: Save ONLY the required fields
            save_data = {
                "filename": filename,
                "image_format": "jpg", 
                "image_data": base64_data,
                "detected_name": detected_name_str,  # 🆕 Now properly formatted
                "cctv_name": self.cctv_name  # 🆕 FIX: Use the instance's CCTV name
            }
            
            # Save as JSON file
            base64_folder = self.image_log_folder / "base64" / subfolder
            json_filename = f"{filename}.json"
            json_path = base64_folder / json_filename
            
            with open(json_path, 'w') as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
            
            self.stats['base64_saved'] += 1
            self.logger.debug(f"💾 Saved base64 image with required fields: {json_filename}")
            self.logger.debug(f"👤 Detected names: {detected_name_str}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error saving base64 image: {e}")
            self.stats['errors'] += 1
            return False
        
        