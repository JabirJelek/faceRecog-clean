# alerting/alert_manager.py

# alerting/alert_manager.py

import threading
import requests
from urllib.parse import quote
from typing import Dict, List, Optional, Tuple
import time
import numpy as np

class DurationAwareAlertManager:
    """
    This class will be utilized with audio alerting, meaning, this class fully get utilized with audio push into server
    """
    def __init__(self, config: Dict):
        self.config = config
        self.server_url = config.get('alert_server_url')
        self.cooldown_seconds = config.get('alert_cooldown_seconds', 30)
        self.enabled = config.get('enable_voice_alerts', True)
        self.last_alert_time = 0
        self.alert_lock = threading.Lock()
        
        # 🆕 Duration tracking parameters
        self.min_violation_frames = config.get('min_violation_frames', 20)  # 2 seconds at 10 FPS
        self.min_violation_seconds = config.get('min_violation_seconds', 2.0)
        self.max_gap_frames = config.get('max_gap_frames', 5)  # Allow 5-frame gaps
        
        # 🆕 Violation duration tracking per identity
        self.violation_timers = {}  # identity -> {'start_time': timestamp, 'frame_count': int, 'start_frame': int, 'continuous': bool}
        self.alerted_identities = set()  # Track identities we've already alerted for
        
        # 🆕 NEW: Image logging synchronization
        self.image_log_interval = config.get('image_log_interval', 5)
        self.last_image_log_time = 0
        self.min_save_interval = config.get('min_save_interval', 2.0)
        
        self.last_alert_time_per_identity = {}  # identity -> last_alert_time        
        
        print(f"🔊 Duration-aware alerts: {self.min_violation_frames} frames / {self.min_violation_seconds}s threshold")

    def update_violation_duration(self, violations: List[Dict], current_frame_count: int):
        """Update violation duration tracking for each identity"""
        current_time = time.time()
        current_violators = set()
        
        for violation in violations:
            identity = violation.get('identity', 'Unknown')
            current_violators.add(identity)
            
            # Start or update timer for this identity
            if identity not in self.violation_timers:
                self.violation_timers[identity] = {
                    'start_time': current_time,
                    'start_frame': current_frame_count,
                    'frame_count': 1,
                    'continuous': True,
                    'last_frame': current_frame_count
                }
            else:
                # Update existing timer
                timer = self.violation_timers[identity]
                
                # Check for continuity
                frame_gap = current_frame_count - timer['last_frame']
                if frame_gap <= self.max_gap_frames + 1:  # Allow small gaps
                    timer['frame_count'] += 1
                    timer['continuous'] = True
                else:
                    # Large gap detected - reset but keep identity
                    timer['start_time'] = current_time
                    timer['start_frame'] = current_frame_count
                    timer['frame_count'] = 1
                    timer['continuous'] = True
                    # Remove from alerted set since it's a new violation period
                    if identity in self.alerted_identities:
                        self.alerted_identities.remove(identity)
                
                timer['last_frame'] = current_frame_count
        
        # Remove identities that are no longer violating
        expired_identities = []
        for identity, timer in self.violation_timers.items():
            if identity not in current_violators:
                # Check if we should keep tracking for small gaps
                frame_gap = current_frame_count - timer['last_frame']
                if frame_gap > self.max_gap_frames:
                    expired_identities.append(identity)
                # else: keep in timers for gap tolerance
        
        for identity in expired_identities:
            self._reset_violation_timer(identity)
            
    def update_config(self, config: Dict):
        """Update alert manager configuration from main pipeline"""
        try:
            # Basic alert settings
            if 'enable_voice_alerts' in config:
                self.enabled = config['enable_voice_alerts']
                
            if 'alert_server_url' in config:
                self.server_url = config['alert_server_url']
                
            if 'alert_cooldown_seconds' in config:
                self.cooldown_seconds = config['alert_cooldown_seconds']
            
            # Duration tracking parameters
            if 'min_violation_frames' in config:
                self.min_violation_frames = config['min_violation_frames']
                
            if 'min_violation_seconds' in config:
                self.min_violation_seconds = config['min_violation_seconds']
                
            if 'max_gap_frames' in config:
                self.max_gap_frames = config['max_gap_frames']
                
            # 🆕 NEW: Image logging synchronization parameters
            if 'image_log_interval' in config:
                self.image_log_interval = config['image_log_interval']
                
            if 'min_save_interval' in config:
                self.min_save_interval = config['min_save_interval']
                
            # Alert content configuration
            self.alert_language = config.get('alert_language', 'id')
            self.alert_style = config.get('alert_style', 'formal')
            self.enable_individual_alerts = config.get('enable_individual_alerts', True)
            self.enable_group_alerts = config.get('enable_group_alerts', True)
            self.alert_timeout_seconds = config.get('alert_timeout_seconds', 10)
            
            print(f"🔊 Alert config updated: {self.enabled}, Cooldown: {self.cooldown_seconds}s")
            print(f"   Duration: {self.min_violation_frames}frames/{self.min_violation_seconds}s")
            print(f"   Image sync: interval={self.image_log_interval}, min_save={self.min_save_interval}s")
            
        except Exception as e:
            print(f"❌ Error updating alert config: {e}")

    def get_alert_config(self) -> Dict:
        """Get current alert configuration"""
        return {
            'enabled': self.enabled,
            'server_url': self.server_url,
            'cooldown_seconds': self.cooldown_seconds,
            'min_violation_frames': self.min_violation_frames,
            'min_violation_seconds': self.min_violation_seconds,
            'max_gap_frames': self.max_gap_frames,
            'alert_language': getattr(self, 'alert_language', 'id'),
            'alert_style': getattr(self, 'alert_style', 'formal'),
            'enable_individual_alerts': getattr(self, 'enable_individual_alerts', True),
            'enable_group_alerts': getattr(self, 'enable_group_alerts', True),
            'alert_timeout_seconds': getattr(self, 'alert_timeout_seconds', 10),
            'tracked_identities_count': len(self.violation_timers),
            'alerted_identities_count': len(self.alerted_identities),
            # 🆕 NEW: Image logging sync info
            'image_log_interval': self.image_log_interval,
            'min_save_interval': self.min_save_interval,
            'last_image_log_time': self.last_image_log_time
        }            

    def _reset_violation_timer(self, identity: str):
        """Reset violation timer for an identity"""
        if identity in self.violation_timers:
            del self.violation_timers[identity]
        if identity in self.alerted_identities:
            self.alerted_identities.remove(identity)

    def should_trigger_alert(self, identity: str) -> bool:
        """Check if violation duration meets threshold for alert"""
        if identity not in self.violation_timers:
            return False
            
        timer = self.violation_timers[identity]
        
        # Check frame count threshold
        frame_condition = timer['frame_count'] >= self.min_violation_frames
        
        # Check time duration threshold  
        time_condition = (time.time() - timer['start_time']) >= self.min_violation_seconds
        
        # Check if violation is continuous
        continuous_condition = timer.get('continuous', True)
        
        # Check if we haven't already alerted for this identity in current violation
        not_already_alerted = identity not in self.alerted_identities
        
        return frame_condition and time_condition and continuous_condition and not_already_alerted

    def get_violation_duration_info(self, identity: str) -> Dict[str, float]:
        """Get duration information for an identity"""
        if identity not in self.violation_timers:
            return {'frames': 0, 'seconds': 0.0}
        
        timer = self.violation_timers[identity]
        return {
            'frames': timer['frame_count'],
            'seconds': time.time() - timer['start_time']
        }

    def trigger_duration_alert(self, violations: List[Dict], current_frame_count: int) -> bool:
        """Main method to check and trigger duration-based alerts"""
        if not self.enabled or not self.server_url:
            return False
        
        # Filter only verified violations from TrackingManager
        verified_violations = [
            v for v in violations 
            if v.get('violation_verified', False)  # ← Use TrackingManager's flag
        ]
        
        if not verified_violations:
            return False
        
        # Group by identity and check if we should alert
        alert_identities = set()
        for violation in verified_violations:
            identity = violation.get('identity', 'Unknown')
            
            # Use TrackingManager's duration and frames data
            violation_duration = violation.get('violation_duration', 0)
            violation_frames = violation.get('violation_frames', 0)
            
            # Check if meets minimum criteria (redundant but safe)
            if (violation_duration >= self.min_violation_seconds and 
                violation_frames >= self.min_violation_frames):
                
                # Check cooldown for this identity
                last_alert_time = self.last_alert_time_per_identity.get(identity, 0)
                if time.time() - last_alert_time >= self.cooldown_seconds:
                    alert_identities.add(identity)
        
        if not alert_identities:
            return False
        
        # Generate and send alert
        alert_violations = [
            v for v in verified_violations 
            if v.get('identity') in alert_identities
        ]
        
        success = self._send_violation_alert(alert_violations, list(alert_identities))
        
        # Update alert times
        if success:
            current_time = time.time()
            for identity in alert_identities:
                self.last_alert_time_per_identity[identity] = current_time
                print(f"🚨 Alert triggered for {identity} (verified: {success})")
        
        return success



    def _send_violation_alert(self, alert_identities: List[str], all_violations: List[Dict]) -> bool:
        """Send voice alert for violations that meet duration threshold with configurable messages"""
        # Filter violations to only those that triggered alerts
        alert_violations = [v for v in all_violations if v.get('identity') in alert_identities]
        
        if not alert_violations:
            return False
            
        # Generate message based on configuration
        message = self._generate_alert_message(alert_violations, alert_identities)
        
        # Send the alert
        return self.send_voice_alert(message)

    def _generate_alert_message(self, alert_violations: List[Dict], alert_identities: List[str]) -> str:
        """Generate alert message in Indonesian with flexible mixing of recognized and unknown violators"""
        current_time = time.time()
        
        # Track violators within time window and remove duplicates
        unique_violations = []
        seen_identities = set()
        
        for violation in alert_violations:
            identity = violation.get('identity', 'Unknown')
            
            # Only add each identity once
            if identity not in seen_identities:
                seen_identities.add(identity)
                unique_violations.append(violation)
        
        # Count recognized vs unknown violators from unique set
        recognized = [v for v in unique_violations if v['identity'] and v['identity'] != 'Unknown']
        unknown = [v for v in unique_violations if not v['identity'] or v['identity'] == 'Unknown']
        
        style = getattr(self, 'alert_style', 'formal')
        
        # Configuration for maximum names to list
        max_names_to_list = getattr(self, 'max_names_in_alert', 4)  # Default: list up to 4 names
        
        # Helper function to format Indonesian name lists
        def format_name_list_indonesian(names):
            """Format list of names in Indonesian"""
            if len(names) == 1:
                return names[0]
            elif len(names) <= max_names_to_list:
                return ", ".join(names[:-1]) + " dan " + names[-1]
            else:
                return f"{len(names)} orang dikenal"
        
        # Get counts for flexible message generation
        recognized_count = len(recognized)
        unknown_count = len(unknown)
        total_count = recognized_count + unknown_count
        
        # Extract recognized names
        recognized_names = [v['identity'] for v in recognized]
        
        # FLEXIBLE MESSAGE GENERATION: Handle all combinations in single output
        
        # Case 1: Only one person total (either recognized or unknown)
        if total_count == 1:
            if recognized_count == 1:
                name = recognized_names[0]
                if style == 'formal':
                    message = f"Perhatian, {name} terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
                else:  # informal
                    message = f"{name} tolong pakai masker, terima kasih."
            else:  # one unknown person
                if style == 'formal':
                    message = "Perhatian, satu orang tidak dikenal terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
                else:  # informal
                    message = "Satu orang tidak dikenal tolong pakai masker, terima kasih."
        
        # Case 2: Mixed - both recognized and unknown people (FLEXIBLE COMBINATION)
        elif recognized_count > 0 and unknown_count > 0:
            name_string = format_name_list_indonesian(recognized_names)
            
            if style == 'formal':
                if unknown_count == 1:
                    message = f"Perhatian, {name_string} dan satu orang tidak dikenal terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
                else:
                    message = f"Perhatian, {name_string} dan {unknown_count} orang tidak dikenal terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
            else:  # informal
                if unknown_count == 1:
                    message = f"{name_string} dan satu orang tidak dikenal tolong pakai masker, terima kasih."
                else:
                    message = f"{name_string} dan {unknown_count} orang tidak dikenal tolong pakai masker, terima kasih."
        
        # Case 3: Only recognized people (multiple)
        elif recognized_count > 0:
            name_string = format_name_list_indonesian(recognized_names)
            if style == 'formal':
                message = f"Perhatian, {name_string} terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
            else:  # informal
                message = f"{name_string} tolong pakai masker, terima kasih."
        
        # Case 4: Only unknown people (multiple)
        elif unknown_count > 0:
            if style == 'formal':
                if unknown_count == 1:
                    message = "Perhatian, satu orang tidak dikenal terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
                else:
                    message = f"Perhatian, {unknown_count} orang tidak dikenal terdeteksi tidak memakai masker. Tolong segera digunakan, terima kasih."
            else:  # informal
                if unknown_count == 1:
                    message = "Satu orang tidak dikenal tolong pakai masker, terima kasih."
                else:
                    message = f"{unknown_count} orang tidak dikenal tolong pakai masker, terima kasih."
        
        # Case 5: Fallback for any other scenario (should not normally happen)
        else:
            if style == 'formal':
                message = "Perhatian, terdeteksi pelanggaran masker."
            else:
                message = "Tolong pakai masker."
        
        # Add configuration option to the class if not exists
        if not hasattr(self, 'max_names_in_alert'):
            self.max_names_in_alert = max_names_to_list
        
        # Debug information about unique violators
        debug_info = f" [Unique: {len(unique_violations)} violators: {list(seen_identities)}]"
        if getattr(self, 'debug_mode', False):
            message += debug_info
            print(f"🔊 Alert generated: {len(unique_violations)} unique violators ({recognized_count} known, {unknown_count} unknown) from {len(alert_violations)} total violations")
        
        return message

    # Synchronized alert with image logging
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

            
    def toggle_alerts(self):
        """Toggle voice alerts on/off"""
        self.enabled = not self.enabled
        status = "ENABLED" if self.enabled else "DISABLED"
        print(f"🔊 Voice alerts: {status}")
        return self.enabled

    def get_duration_stats(self) -> Dict:
        """Get current duration tracking statistics"""
        stats = {
            'total_tracked_identities': len(self.violation_timers),
            'alerted_identities': list(self.alerted_identities),
            'violation_timers': {}
        }
        
        for identity, timer in self.violation_timers.items():
            stats['violation_timers'][identity] = {
                'frame_count': timer['frame_count'],
                'duration_seconds': time.time() - timer['start_time'],
                'continuous': timer.get('continuous', True)
            }
        
        return stats
