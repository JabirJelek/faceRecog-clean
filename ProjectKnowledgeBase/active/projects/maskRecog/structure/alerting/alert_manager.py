# alerting/alert_manager.py

import threading
import requests
from urllib.parse import quote
from typing import Dict, List, Optional, Tuple, Set
import time
import numpy as np
from collections import defaultdict

class DurationAwareAlertManager:
    """
    Enhanced alert manager with batch logic and intelligent sentence construction
    for multiple violators in a single spoken alert.
    """
    def __init__(self, config: Dict):
        self.config = config
        self.server_url = config.get('alert_server_url')
        self.cooldown_seconds = config.get('alert_cooldown_seconds', 0)
        self.enabled = config.get('enable_voice_alerts', False)
        self.last_alert_time = 0
        self.alert_lock = threading.Lock()
        
        # Duration tracking parameters
        self.min_violation_frames = config.get('min_violation_frames', 0)
        self.min_violation_seconds = config.get('min_violation_seconds', 0)
        self.max_gap_frames = config.get('max_gap_frames', 5)
        
        # 🆕 PHASE 1: Batch Logic Parameters
        self.max_names_in_alert = config.get('max_names_in_alert', 4)
        self.batch_window_seconds = config.get('batch_window_seconds', 5)
        self.min_batch_size = config.get('min_batch_size', 2)
        
        # Violation tracking
        self.violation_timers = {}
        self.alerted_identities = set()
        
        # 🆕 PHASE 1: Batch tracking for multiple violators
        self.batch_violators = defaultdict(list)  # identity -> list of violation entries
        self.batch_start_time = 0
        self.pending_batch = set()  # Identities pending in current batch
        
        # Image logging synchronization
        self.image_log_interval = config.get('image_log_interval', 5)
        self.last_image_log_time = 0
        self.min_save_interval = config.get('min_save_interval', 2.0)
        
        self.last_alert_time_per_identity = {}
        
        print(f"🔊 Duration-aware batch alerts: {self.min_violation_frames} frames threshold")
        print(f"   Batch logic: window={self.batch_window_seconds}s, min={self.min_batch_size}")

    def update_batch_violators(self, violations: List[Dict], current_frame_count: int):
        """
        Update batch tracking for multiple violators
        Implements Phase 1: Foundation - Batch Logic
        """
        current_time = time.time()
        
        # Start new batch if none exists or window expired
        if not self.batch_start_time or (current_time - self.batch_start_time > self.batch_window_seconds):
            self._reset_batch_tracking(current_time)
        
        # Process current violations for batch
        current_identities = set()
        for violation in violations:
            identity = violation.get('identity', 'Unknown')
            current_identities.add(identity)
            
            # Only add to batch if meets duration criteria
            if self._check_violation_duration(violation):
                # Check if this identity is already in current batch
                if identity in self.pending_batch:
                    # Update existing entry with latest violation
                    existing_entries = self.batch_violators[identity]
                    if existing_entries:
                        existing_entries[-1].update(violation)
                else:
                    # Add new violation to batch
                    self.batch_violators[identity].append(violation)
                    self.pending_batch.add(identity)
        
        # Remove identities no longer violating
        expired_identities = [id for id in self.pending_batch if id not in current_identities]
        for identity in expired_identities:
            self.pending_batch.discard(identity)
    
    def _reset_batch_tracking(self, current_time: float):
        """Reset batch tracking for new batch window"""
        self.batch_start_time = current_time
        self.batch_violators.clear()
        self.pending_batch.clear()
    
    def _check_violation_duration(self, violation: Dict) -> bool:
        """Check if violation meets duration threshold"""
        duration = violation.get('violation_duration', 0)
        frames = violation.get('violation_frames', 0)
        
        return (duration >= self.min_violation_seconds and 
                frames >= self.min_violation_frames)
    
    def should_trigger_batch_alert(self) -> Tuple[bool, List[Dict]]:
        """
        Check if batch alert should be triggered
        Returns: (should_trigger, list_of_violations)
        """
        if not self.enabled:
            return False, []
        
        current_time = time.time()
        
        # Check batch window expiration
        if current_time - self.batch_start_time > self.batch_window_seconds:
            # Batch window expired, trigger if we have violations
            if self.batch_violators:
                violations = self._compile_batch_violations()
                if violations:
                    return True, violations
            return False, []
        
        # Check if we have enough violators for batch
        unique_identities = len(self.batch_violators)
        if unique_identities >= self.min_batch_size:
            violations = self._compile_batch_violations()
            return True, violations
        
        return False, []
    
    def _compile_batch_violations(self) -> List[Dict]:
        """
        Compile all violations in current batch into a single list
        Removes duplicates and keeps only latest violation per identity
        """
        compiled = []
        seen_identities = set()
        
        for identity, violations_list in self.batch_violators.items():
            if violations_list and identity not in seen_identities:
                # Take the most recent violation for each identity
                latest_violation = violations_list[-1]
                compiled.append(latest_violation)
                seen_identities.add(identity)
        
        return compiled
    
    def _send_alert_thread(self, message: str, identity: str, mask_status: str):
        """Background thread for sending alerts with configurable timeout"""
        try:
            encoded_message = quote(message)
            alert_url = f"{self.server_url}?pesan={encoded_message}"
            timeout = getattr(self, 'alert_timeout_seconds', 10)
            
            response = requests.get(alert_url, timeout=timeout)
            
            if response.status_code == 200:
                print(f"🔊 Voice alert sent: {message}")
            else:
                print(f"❌ Alert server returned status: {response.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"⏰ Alert request timed out after {timeout} seconds")
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to send voice alert: {e}")
        except Exception as e:
            print(f"❌ Unexpected error in alert thread: {e}")
    
    def send_voice_alert(self, message: str, identity: str = None, mask_status: str = None) -> bool:
        """Send voice alert to server in non-blocking thread"""
        if not self.enabled or not self.server_url:
            return False
            
        current_time = time.time()
        with self.alert_lock:
            if current_time - self.last_alert_time < self.cooldown_seconds:
                return False
            self.last_alert_time = current_time
        
        thread = threading.Thread(
            target=self._send_alert_thread,
            args=(message, identity, mask_status),
            daemon=True
        )
        thread.start()
        return True
    
    # 🆕 PHASE 1 HELPER FUNCTIONS FOR INDONESIAN GRAMMAR
    
    def _format_name_list_indonesian(self, names: List[str]) -> str:
        """
        Format list of names in Indonesian using proper grammar
        Example: ["Budi", "Sari", "Rudi"] -> "Budi, Sari dan Rudi"
        """
        if not names:
            return ""
        
        # Remove duplicates while preserving order
        unique_names = []
        seen = set()
        for name in names:
            if name not in seen:
                seen.add(name)
                unique_names.append(name)
        
        # Limit to max names to list
        names_to_format = unique_names[:self.max_names_in_alert]
        
        if len(names_to_format) == 1:
            return names_to_format[0]
        elif len(names_to_format) == 2:
            return f"{names_to_format[0]} dan {names_to_format[1]}"
        else:
            # For 3 or more names: "A, B, C dan D"
            all_but_last = ", ".join(names_to_format[:-1])
            return f"{all_but_last} dan {names_to_format[-1]}"
    
    def _format_unknown_count_indonesian(self, count: int) -> str:
        """
        Format unknown person count into Indonesian words
        Example: 2 -> "dua orang", 3 -> "tiga orang"
        """
        # Indonesian number words
        number_words = {
            1: "satu",
            2: "dua",
            3: "tiga",
            4: "empat",
            5: "lima",
            6: "enam",
            7: "tujuh",
            8: "delapan",
            9: "sembilan",
            10: "sepuluh"
        }
        
        if count in number_words:
            if count == 1:
                return f"{number_words[count]} orang"
            else:
                return f"{number_words[count]} orang"
        else:
            return f"{count} orang"
    
    def _generate_batch_alert_message(self, violations: List[Dict]) -> str:
        """
        Generate alert message for multiple violators using intelligent
        sentence construction in Indonesian
        """
        if not violations:
            return ""
        
        # 🆕 Phase 1: Unique Identity Filtering
        unique_violations = []
        seen_identities = set()
        
        for violation in violations:
            identity = violation.get('identity', 'Unknown')
            if identity not in seen_identities:
                seen_identities.add(identity)
                unique_violations.append(violation)
        
        # 🆕 Phase 1: Dynamic Categorization
        recognized = []
        unknown_count = 0
        
        for violation in unique_violations:
            identity = violation.get('identity', 'Unknown')
            if identity and identity != 'Unknown':
                recognized.append(identity)
            else:
                unknown_count += 1
        
        # Get configuration
        style = getattr(self, 'alert_style', 'formal')
        total_count = len(recognized) + unknown_count
        
        # 🆕 Phase 1: Flexible Message Generation with cases
        
        # Case 1: Only recognized people
        if recognized and unknown_count == 0:
            if len(recognized) == 1:
                # Single recognized person
                name = recognized[0]
                if style == 'formal':
                    return f"Perhatian, {name} terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
                else:
                    return f"{name} tolong pakai masker, terima kasih."
            else:
                # Multiple recognized people
                name_string = self._format_name_list_indonesian(recognized)
                if style == 'formal':
                    return f"Perhatian, {name_string} terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
                else:
                    return f"{name_string} tolong pakai masker, terima kasih."
        
        # Case 2: Only unknown people
        elif not recognized and unknown_count > 0:
            if unknown_count == 1:
                # Single unknown person
                unknown_text = self._format_unknown_count_indonesian(unknown_count)
                if style == 'formal':
                    return f"Perhatian, {unknown_text} tidak dikenal terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
                else:
                    return f"{unknown_text} tidak dikenal tolong pakai masker, terima kasih."
            else:
                # Multiple unknown people
                unknown_text = self._format_unknown_count_indonesian(unknown_count)
                if style == 'formal':
                    return f"Perhatian, {unknown_text} tidak dikenal terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
                else:
                    return f"{unknown_text} tidak dikenal tolong pakai masker, terima kasih."
        
        # Case 3: Mixed - both recognized and unknown
        elif recognized and unknown_count > 0:
            name_string = self._format_name_list_indonesian(recognized)
            unknown_text = self._format_unknown_count_indonesian(unknown_count)
            
            if len(recognized) == 1 and unknown_count == 1:
                # 1 recognized + 1 unknown
                if style == 'formal':
                    return f"Perhatian, {name_string} dan {unknown_text} tidak dikenal terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
                else:
                    return f"{name_string} dan {unknown_text} tidak dikenal tolong pakai masker, terima kasih."
            elif len(recognized) == 1:
                # 1 recognized + multiple unknown
                if style == 'formal':
                    return f"Perhatian, {name_string} dan {unknown_text} tidak dikenal terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
                else:
                    return f"{name_string} dan {unknown_text} tidak dikenal tolong pakai masker, terima kasih."
            else:
                # Multiple recognized + unknown
                if style == 'formal':
                    return f"Perhatian, {name_string} dan {unknown_text} tidak dikenal terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
                else:
                    return f"{name_string} dan {unknown_text} tidak dikenal tolong pakai masker, terima kasih."
        
        # Fallback case
        if style == 'formal':
            return "Perhatian, terdeteksi pelanggaran masker."
        else:
            return "Tolong pakai masker."
    
    def process_frame_violations(self, violations: List[Dict], current_frame_count: int) -> bool:
        """
        Main processing method for each frame
        Implements complete Phase 1 batch logic
        """
        if not self.enabled or not violations:
            return False
        
        # Update batch tracking
        self.update_batch_violators(violations, current_frame_count)
        
        # Check if batch alert should be triggered
        should_trigger, batch_violations = self.should_trigger_batch_alert()
        
        if should_trigger and batch_violations:
            # Generate batch message
            message = self._generate_batch_alert_message(batch_violations)
            
            # Send alert
            success = self.send_voice_alert(message)
            
            if success:
                print(f"🔊 Batch alert triggered for {len(batch_violations)} violators")
                print(f"   Message: {message}")
                
                # Mark identities as alerted
                for violation in batch_violations:
                    identity = violation.get('identity', 'Unknown')
                    self.alerted_identities.add(identity)
                    self.last_alert_time_per_identity[identity] = time.time()
                
                # Reset batch tracking
                self._reset_batch_tracking(time.time())
                
            return success
        
        return False
    
    # Existing methods (keeping for compatibility)
    
    def update_config(self, config: Dict):
        """Update alert manager configuration"""
        try:
            # Basic alert settings
            self.enabled = config.get('enable_voice_alerts', self.enabled)
            self.server_url = config.get('alert_server_url', self.server_url)
            self.cooldown_seconds = config.get('alert_cooldown_seconds', self.cooldown_seconds)
            
            # Duration tracking
            self.min_violation_frames = config.get('min_violation_frames', self.min_violation_frames)
            self.min_violation_seconds = config.get('min_violation_seconds', self.min_violation_seconds)
            self.max_gap_frames = config.get('max_gap_frames', self.max_gap_frames)
            
            # 🆕 Phase 1: Batch configuration
            self.max_names_in_alert = config.get('max_names_in_alert', self.max_names_in_alert)
            self.batch_window_seconds = config.get('batch_window_seconds', self.batch_window_seconds)
            self.min_batch_size = config.get('min_batch_size', self.min_batch_size)
            
            # Image logging
            self.image_log_interval = config.get('image_log_interval', self.image_log_interval)
            self.min_save_interval = config.get('min_save_interval', self.min_save_interval)
            
            # Alert content
            self.alert_language = config.get('alert_language', 'id')
            self.alert_style = config.get('alert_style', 'formal')
            self.alert_timeout_seconds = config.get('alert_timeout_seconds', 10)
            
            print(f"🔊 Alert config updated with batch logic")
            print(f"   Batch: window={self.batch_window_seconds}s, min={self.min_batch_size}")
            print(f"   Names: max={self.max_names_in_alert}")
            
        except Exception as e:
            print(f"❌ Error updating alert config: {e}")
    
    def get_alert_config(self) -> Dict:
        """Get current alert configuration"""
        config = {
            'enabled': self.enabled,
            'server_url': self.server_url,
            'cooldown_seconds': self.cooldown_seconds,
            'min_violation_frames': self.min_violation_frames,
            'min_violation_seconds': self.min_violation_seconds,
            'max_gap_frames': self.max_gap_frames,
            'alert_language': getattr(self, 'alert_language', 'id'),
            'alert_style': getattr(self, 'alert_style', 'formal'),
            'alert_timeout_seconds': getattr(self, 'alert_timeout_seconds', 10),
            # 🆕 Phase 1: Batch configuration
            'max_names_in_alert': self.max_names_in_alert,
            'batch_window_seconds': self.batch_window_seconds,
            'min_batch_size': self.min_batch_size,
            'image_log_interval': self.image_log_interval,
            'min_save_interval': self.min_save_interval,
            'current_batch_size': len(self.pending_batch),
            'batch_violators': list(self.pending_batch)
        }
        return config
    
    def get_batch_stats(self) -> Dict:
        """Get batch processing statistics"""
        return {
            'current_batch_size': len(self.pending_batch),
            'batch_window_start': self.batch_start_time,
            'batch_window_remaining': max(0, self.batch_window_seconds - (time.time() - self.batch_start_time)),
            'violators_in_batch': list(self.pending_batch),
            'total_alerted_identities': len(self.alerted_identities)
        }
    
    def reset_batch(self):
        """Manually reset current batch (for testing/debugging)"""
        self._reset_batch_tracking(time.time())
        print("🔊 Batch tracking reset")
    
    # Legacy methods for backward compatibility
    
    def trigger_duration_alert(self, violations: List[Dict], current_frame_count: int) -> bool:
        """Legacy method - now uses batch processing"""
        return self.process_frame_violations(violations, current_frame_count)
    
    def _generate_alert_message(self, alert_violations: List[Dict], alert_identities: List[str]) -> str:
        """Legacy method - redirect to new batch message generator"""
        return self._generate_batch_alert_message(alert_violations)
    
    def trigger_synchronized_alert(self, violations: List[Dict], processing_count: int, saved_image_count: int, max_images: int) -> bool:
        """
        Trigger audio alert synchronized with image logging conditions
        
        Args:
            violations: List of current violations
            processing_count: Current processing frame count
            saved_image_count: Number of images already saved
            max_images: Maximum images allowed per session
            
        Returns:
            bool: True if alert was sent
        """
        if not self.enabled or not self.server_url:
            return False
            
        # Check if we have violations
        if not violations:
            return False
            
        # 🆕 Apply the same conditions as image logging
        current_time = time.time()
        
        # Check image log interval (same as image logger)
        if processing_count % self.image_log_interval != 0:
            return False
            
        # Check maximum images limit (same as image logger)
        if saved_image_count >= max_images:
            return False
            
        # Check minimum time between saves (same as image logger)
        if current_time - self.last_image_log_time < self.min_save_interval:
            return False
            
        # Check rate limiting for audio alerts
        if current_time - self.last_alert_time < self.cooldown_seconds:
            return False
        
        # Generate and send alert for all current violations
        message = self._generate_alert_message(violations, [v.get('identity', 'Unknown') for v in violations])
        success = self.send_voice_alert(message)
        
        if success:
            self.last_image_log_time = current_time
            print(f"🔊 Synchronized audio alert sent with image logging: {message}")
            
            # Mark identities as alerted to avoid duplicate alerts
            for violation in violations:
                identity = violation.get('identity', 'Unknown')
                self.alerted_identities.add(identity)
        
        return success
    