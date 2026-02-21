# streaming/control_handler.py
# Proposed file that can be utilized more in integrating modularity of realtime streaming

"""
Common control and status reporting functionality for both processors
"""
import time
from typing import Dict, Any
import logging

class ControlHandler:
    def __init__(self, processor):
        self.processor = processor
        self.logger = logging.getLogger(__name__)
    
    def print__system_status(self):
        """self.logger.info comprehensive system status"""
        self.logger.info("\n" + "="*60)
        self.logger.info("🎯 SYSTEM STATUS SUMMARY")
        self.logger.info("="*60)
        
        # Performance status
        if hasattr(self.processor, 'performance_manager'):
            perf_stats = self.processor.performance_manager.get_performance_stats()
            self.logger.info(f"📊 Performance:")
            self.logger.info(f"  Current Scale: {perf_stats['current_scale']:.2f}")
            self.logger.info(f"  Good Detections: {perf_stats['consecutive_good_detections']}")
            self.logger.info(f"  Poor Detections: {perf_stats['consecutive_poor_detections']}")
            self.logger.info(f"  Dynamic Adjustment: {'ENABLED' if perf_stats['dynamic_adjustment_enabled'] else 'DISABLED'}")
        
        # Processing status
        if hasattr(self.processor, 'get_processing_config'):
            proc_config = self.processor.get_processing_config()
            self.logger.info(f"⚙️ Processing:")
            self.logger.info(f"  Interval: 1/{proc_config['processing_interval']}")
            self.logger.info(f"  Resolution: {proc_config['processing_width']}x{proc_config['processing_height']}")
            self.logger.info(f"  FPS: {proc_config['fps']:.1f}")
        
        # Logging status
        if hasattr(self.processor, 'logging_enabled'):
            status = "🟢 ENABLED" if self.processor.logging_enabled else "🔴 DISABLED"
            self.logger.warning(f"📝 Logging: {status}")
            if self.processor.logging_enabled:
                self.logger.info(f"  Entries: {getattr(self.processor, 'log_counter', 0)}")
        
        # Alert status
        if hasattr(self.processor, 'alert_manager'):
            alert_config = self.processor.alert_manager.get_alert_config()
            status = "🟢 ENABLED" if alert_config.get('enabled', False) else "🔴 DISABLED"
            self.logger.warning(f"🔊 Alerts: {status}")
        
        # Tracking status
        if hasattr(self.processor, 'tracking_manager'):
            tracking_config = self.processor.tracking_manager.get_config()
            if tracking_config.get('tracking', {}).get('enabled', False):
                self.logger.info(f"👤 Tracking: 🟢 ENABLED")
            else:
                self.logger.warning(f"👤 Tracking: 🔴 DISABLED")
        
        self.logger.info("="*60)
    
    def handle_common_controls(self, key: int) -> bool:
        """
        Handle common keyboard controls for both windowed and headless modes
        Returns True if key was handled, False otherwise
        """
        if key == ord('q'):
            self.processor.running = False
            self.logger.warning("🛑 Quitting application...")
            return True
            
        elif key == ord('r'):  # Reset processing counters
            if hasattr(self.processor, 'reset_processing_counters'):
                self.processor.reset_processing_counters()
            return True
            
        elif key == ord('x'):  # self.logger.info detailed statistics
            if hasattr(self.processor, 'self.logger.info_detailed_stats'):
                self.processor.self.logger.info_detailed_stats()
            return True
            
        elif key == ord('y'):  # Stability report
            if hasattr(self.processor, 'self.logger.info_stability_report'):
                self.processor.self.logger.info_stability_report()
            return True
            
        elif key == ord('+'):  # Increase processing interval
            if hasattr(self.processor, 'update_processing_interval'):
                self.processor.update_processing_interval(1)
            return True
            
        elif key == ord('-'):  # Decrease processing interval  
            if hasattr(self.processor, 'update_processing_interval'):
                self.processor.update_processing_interval(-1)
            return True
            
        elif key == ord('l'):  # Toggle logging
            if hasattr(self.processor, 'toggle_logging'):
                self.processor.toggle_logging()
            return True
            
        elif key == ord(':'):  # self.logger.info log status
            if hasattr(self.processor, 'self.logger.info_log_status'):
                self.processor.self.logger.info_log_status()
            return True
            
        elif key == ord(';'):  # Change log interval
            if hasattr(self.processor, 'log_interval'):
                old_interval = self.processor.log_interval
                self.processor.log_interval = max(1, (self.processor.log_interval % 10) + 1)
                self.logger.info(f"📊 Log interval: 1/{old_interval} → 1/{self.processor.log_interval}")
            return True
            
        elif key == ord('a'):  # Toggle dynamic adjustment
            if hasattr(self.processor, 'performance_manager'):
                self.processor.performance_manager.toggle_dynamic_adjustment()
            return True
            
        elif key == ord('z'):  # Reset dynamic scaling
            if hasattr(self.processor, 'performance_manager'):
                self.processor.performance_manager.reset_dynamic_scaling()
            return True
            
        elif key == ord('S'):  # Enable small face mode
            if hasattr(self.processor, 'performance_manager'):
                self.processor.performance_manager.enable_small_face_mode()
            return True
            
        elif key == ord('m'):  # Cycle processing presets
            if hasattr(self.processor, 'cycle_processing_preset'):
                self.processor.cycle_processing_preset()
            return True
            
        elif key == ord('9'):  # Test voice alert
            if hasattr(self.processor, 'alert_manager'):
                test_message = "Test suara dari sistem pengawasan masker"
                success = self.processor.alert_manager.send_voice_alert(test_message)
                if success:
                    self.logger.info(f"🔊 Test alert sent: {test_message}")
                else:
                    self.logger.info("⏰ Test alert skipped - in cooldown period")
            return True
            
        elif key == ord('v'):  # Toggle voice alerts
            if hasattr(self.processor, 'toggle_voice_alerts'):
                self.processor.toggle_voice_alerts()
            return True
            
        elif key == ord('A'):  # self.logger.info alert status
            if hasattr(self.processor, 'self.logger.info_alert_status'):
                self.processor.self.logger.info_alert_status()
            return True
            
        elif key == ord('t'):  # self.logger.info tracking status
            if hasattr(self.processor, 'self.logger.info_tracking_status'):
                self.processor.self.logger.info_tracking_status()
            return True
            
        elif key == ord('C'):  # Toggle context awareness
            if hasattr(self.processor, 'toggle_context_awareness'):
                self.processor.toggle_context_awareness()
            return True
            
        elif key == ord('X'):  # self.logger.info context statistics
            if hasattr(self.processor, 'self.logger.info_context_statistics'):
                self.processor.self.logger.info_context_statistics()
            return True
            
        return False
    
    def print_control_reference(self, headless: bool = False):
        """self.logger.info control reference for the system"""
        self.logger.info("\n" + "="*60)
        if headless:
            self.logger.info("🎮 HEADLESS KEYBOARD CONTROLS")
        else:
            self.logger.info("🎮 ENHANCED KEYBOARD CONTROLS")
        self.logger.info("="*60)
        
        self.logger.info("🎯 CORE CONTROLS:")
        self.logger.info("  'q' - Quit application")
        self.logger.info("  'r' - Reset processing counters")
        self.logger.info("  'x' - self.logger.info detailed statistics")
        self.logger.info("  'y' - self.logger.info stability report")
        
        self.logger.info("\n⏱️  PROCESSING CONTROLS:")
        self.logger.info("  '+' - Increase processing interval (process less)")
        self.logger.info("  '-' - Decrease processing interval (process more)")
        self.logger.info("  'm' - Cycle processing presets")
        
        self.logger.info("\n🎯 DYNAMIC ADJUSTMENT CONTROLS:")
        self.logger.info("  'a' - Toggle dynamic adjustment")
        self.logger.info("  'z' - Reset dynamic scaling to 1.0")
        self.logger.info("  'S' - Enable small face detection mode")
        
        self.logger.info("\n📊 LOGGING & MONITORING:")
        self.logger.info("  'l' - Toggle CSV logging")
        self.logger.info("  ';' - Change log interval (1-10 frames)")
        self.logger.info("  ':' - self.logger.info current log status")
        
        self.logger.info("\n🔊 VOICE ALERT CONTROLS:")
        self.logger.info("  'v' - Toggle voice alerts")
        self.logger.info("  '9' - Test voice alert")
        self.logger.info("  'A' - self.logger.info alert status")
        
        self.logger.info("\n🎯 ADVANCED CONTROLS:")
        self.logger.info("  'C' - Toggle context awareness")
        self.logger.info("  'X' - self.logger.info context statistics")
        self.logger.info("  't' - self.logger.info tracking status")
        
        if not headless:
            self.logger.info("\n🖼️  DISPLAY CONTROLS (Windowed Only):")
            self.logger.info("  '1-8' - Different display resize methods")
            self.logger.info("  '0' - Original size")
            self.logger.info("  'i' - Toggle resize info")
            self.logger.info("  'd' - Toggle debug mode")
            self.logger.info("  'p' - Toggle performance stats")
            self.logger.info("  'b' - Toggle detection debug")
            self.logger.info("  's' - Save current frame")
            self.logger.info("  'k' - Take annotated snapshot")
        
        self.logger.info("\n📈 STATUS:")
        self.logger.info("  Press any of the above keys to see current status")
        self.logger.info("="*60)
        self.logger.info()


