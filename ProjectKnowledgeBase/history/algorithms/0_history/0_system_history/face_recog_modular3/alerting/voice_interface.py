# alerting/voice_interface.py

"""
Voice alert interface for sending voice notifications.
"""

import requests
import threading
import time
from urllib.parse import quote
from typing import Optional, Dict, Any
import logging

class VoiceInterface:
    """Handles voice alert delivery through HTTP requests."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.server_url = config.get('alert_server_url')
        self.timeout = config.get('voice_timeout', 5)
        self.max_retries = config.get('voice_max_retries', 2)
        self.retry_delay = config.get('voice_retry_delay', 1.0)
        
        self.logger = logging.getLogger(__name__)
        self.session = requests.Session()
        
        # Set default headers
        self.session.headers.update({
            'User-Agent': 'FaceRecognitionSystem/1.0',
            'Accept': 'application/json'
        })

    def send_voice_alert(self, message: str, identity: Optional[str] = None, 
                        mask_status: Optional[str] = None) -> bool:
        """
        Send a voice alert with the given message.
        
        Args:
            message: The text message to be converted to speech
            identity: Optional identity of the person
            mask_status: Optional mask status
            
        Returns:
            bool: True if alert was sent successfully, False otherwise
        """
        if not self.server_url:
            self.logger.warning("No voice alert server URL configured")
            return False
        
        if not message or not message.strip():
            self.logger.warning("Empty message provided for voice alert")
            return False
        
        try:
            # Enhance message with context if available
            enhanced_message = self._enhance_message(message, identity, mask_status)
            
            # URL encode the message
            encoded_message = quote(enhanced_message)
            
            # Construct the alert URL
            alert_url = f"{self.server_url}?pesan={encoded_message}"
            
            # Send the request with retries
            success = self._send_request_with_retry(alert_url)
            
            if success:
                self.logger.info(f"Voice alert sent: {enhanced_message}")
            else:
                self.logger.error(f"Failed to send voice alert: {enhanced_message}")
                
            return success
            
        except Exception as e:
            self.logger.error(f"Error sending voice alert: {e}")
            return False

    def _enhance_message(self, message: str, identity: Optional[str], 
                        mask_status: Optional[str]) -> str:
        """Enhance the message with additional context."""
        enhanced_parts = [message]
        
        # Add identity context if available
        if identity and identity != "Unknown":
            enhanced_parts.append(f"Identitas: {identity}")
        
        # Add mask status context
        if mask_status:
            status_text = {
                "mask": "dengan masker",
                "no_mask": "tanpa masker", 
                "unknown": "status masker tidak diketahui"
            }.get(mask_status, mask_status)
            enhanced_parts.append(f"Status: {status_text}")
        
        return ". ".join(enhanced_parts)

    def _send_request_with_retry(self, url: str) -> bool:
        """Send HTTP request with retry logic."""
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout)
                
                if response.status_code == 200:
                    return True
                else:
                    self.logger.warning(
                        f"Voice alert server returned status {response.status_code} "
                        f"(attempt {attempt + 1}/{self.max_retries + 1})"
                    )
                    
            except requests.exceptions.Timeout:
                self.logger.warning(
                    f"Voice alert request timeout (attempt {attempt + 1}/{self.max_retries + 1})"
                )
            except requests.exceptions.ConnectionError:
                self.logger.warning(
                    f"Voice alert connection error (attempt {attempt + 1}/{self.max_retries + 1})"
                )
            except requests.exceptions.RequestException as e:
                self.logger.warning(
                    f"Voice alert request error: {e} "
                    f"(attempt {attempt + 1}/{self.max_retries + 1})"
                )
            
            # Wait before retry (except on last attempt)
            if attempt < self.max_retries:
                time.sleep(self.retry_delay)
        
        return False

    def send_async_voice_alert(self, message: str, identity: Optional[str] = None,
                              mask_status: Optional[str] = None) -> threading.Thread:
        """
        Send voice alert in a background thread to avoid blocking.
        
        Returns:
            threading.Thread: The background thread
        """
        thread = threading.Thread(
            target=self.send_voice_alert,
            args=(message, identity, mask_status),
            daemon=True,
            name="VoiceAlertThread"
        )
        thread.start()
        return thread

    def test_connection(self) -> bool:
        """Test connection to the voice alert server."""
        if not self.server_url:
            return False
        
        test_message = "Test suara dari sistem pengawasan masker"
        return self.send_voice_alert(test_message)

    def get_voice_interface_status(self) -> Dict[str, Any]:
        """Get the status of the voice interface."""
        return {
            'server_configured': bool(self.server_url),
            'server_url': self.server_url,
            'timeout': self.timeout,
            'max_retries': self.max_retries
        }
               
