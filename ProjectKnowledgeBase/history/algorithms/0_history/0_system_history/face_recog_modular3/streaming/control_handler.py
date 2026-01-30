# streaming/control_handler.py
# Proposed file that can be utilized more in integrating modularity of realtime streaming

"""
Common control and status reporting functionality for both processors
"""
import time
from typing import Dict, Any

class ControlHandler:
    def __init__(self, processor):
        self.processor = processor
    
    def print_system_status(self):
        """Print comprehensive system status"""
        print("\n" + "="*60)
        print("🎯 SYSTEM STATUS SUMMARY")
        print("="*60)
        
        # Performance status
        if hasattr(self.processor, 'performance_manager'):
            perf_stats = self.processor.performance_manager.get_performance_stats()
            print(f"📊 Performance:")
            print(f"  Current Scale: {perf_stats['current_scale']:.2f}")
            print(f"  Good Detections: {perf_stats['consecutive_good_detections']}")
            print(f"  Poor Detections: {perf_stats['consecutive_poor_detections']}")
            print(f"  Dynamic Adjustment: {'ENABLED' if perf_stats['dynamic_adjustment_enabled'] else 'DISABLED'}")
        
        # Processing status
        if hasattr(self.processor, 'get_processing_config'):
            proc_config = self.processor.get_processing_config()
            print(f"⚙️ Processing:")
            print(f"  Interval: 1/{proc_config['processing_interval']}")
            print(f"  Resolution: {proc_config['processing_width']}x{proc_config['processing_height']}")
            print(f"  FPS: {proc_config['fps']:.1f}")
        
        # Logging status
        if hasattr(self.processor, 'logging_enabled'):
            status = "🟢 ENABLED" if self.processor.logging_enabled else "🔴 DISABLED"
            print(f"📝 Logging: {status}")
            if self.processor.logging_enabled:
                print(f"  Entries: {getattr(self.processor, 'log_counter', 0)}")
        
        # Alert status
        if hasattr(self.processor, 'alert_manager'):
            alert_config = self.processor.alert_manager.get_alert_config()
            status = "🟢 ENABLED" if alert_config.get('enabled', False) else "🔴 DISABLED"
            print(f"🔊 Alerts: {status}")
        
        # Tracking status
        if hasattr(self.processor, 'tracking_manager'):
            tracking_config = self.processor.tracking_manager.get_config()
            if tracking_config.get('tracking', {}).get('enabled', False):
                print(f"👤 Tracking: 🟢 ENABLED")
            else:
                print(f"👤 Tracking: 🔴 DISABLED")
        
        print("="*60)
    
    def handle_common_controls(self, key: int) -> bool:
        """
        Handle common keyboard controls for both windowed and headless modes
        Returns True if key was handled, False otherwise
        """
        if key == ord('q'):
            self.processor.running = False
            print("🛑 Quitting application...")
            return True
            
        elif key == ord('r'):  # Reset processing counters
            if hasattr(self.processor, 'reset_processing_counters'):
                self.processor.reset_processing_counters()
            return True
            
        elif key == ord('x'):  # Print detailed statistics
            if hasattr(self.processor, 'print_detailed_stats'):
                self.processor.print_detailed_stats()
            return True
            
        elif key == ord('y'):  # Stability report
            if hasattr(self.processor, 'print_stability_report'):
                self.processor.print_stability_report()
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
            
        elif key == ord(':'):  # Print log status
            if hasattr(self.processor, 'print_log_status'):
                self.processor.print_log_status()
            return True
            
        elif key == ord(';'):  # Change log interval
            if hasattr(self.processor, 'log_interval'):
                old_interval = self.processor.log_interval
                self.processor.log_interval = max(1, (self.processor.log_interval % 10) + 1)
                print(f"📊 Log interval: 1/{old_interval} → 1/{self.processor.log_interval}")
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
                    print(f"🔊 Test alert sent: {test_message}")
                else:
                    print("⏰ Test alert skipped - in cooldown period")
            return True
            
        elif key == ord('v'):  # Toggle voice alerts
            if hasattr(self.processor, 'toggle_voice_alerts'):
                self.processor.toggle_voice_alerts()
            return True
            
        elif key == ord('A'):  # Print alert status
            if hasattr(self.processor, 'print_alert_status'):
                self.processor.print_alert_status()
            return True
            
        elif key == ord('t'):  # Print tracking status
            if hasattr(self.processor, 'print_tracking_status'):
                self.processor.print_tracking_status()
            return True
            
        elif key == ord('C'):  # Toggle context awareness
            if hasattr(self.processor, 'toggle_context_awareness'):
                self.processor.toggle_context_awareness()
            return True
            
        elif key == ord('X'):  # Print context statistics
            if hasattr(self.processor, 'print_context_statistics'):
                self.processor.print_context_statistics()
            return True
            
        return False
    
    def print_control_reference(self, headless: bool = False):
        """Print control reference for the system"""
        print("\n" + "="*60)
        if headless:
            print("🎮 HEADLESS KEYBOARD CONTROLS")
        else:
            print("🎮 ENHANCED KEYBOARD CONTROLS")
        print("="*60)
        
        print("🎯 CORE CONTROLS:")
        print("  'q' - Quit application")
        print("  'r' - Reset processing counters")
        print("  'x' - Print detailed statistics")
        print("  'y' - Print stability report")
        
        print("\n⏱️  PROCESSING CONTROLS:")
        print("  '+' - Increase processing interval (process less)")
        print("  '-' - Decrease processing interval (process more)")
        print("  'm' - Cycle processing presets")
        
        print("\n🎯 DYNAMIC ADJUSTMENT CONTROLS:")
        print("  'a' - Toggle dynamic adjustment")
        print("  'z' - Reset dynamic scaling to 1.0")
        print("  'S' - Enable small face detection mode")
        
        print("\n📊 LOGGING & MONITORING:")
        print("  'l' - Toggle CSV logging")
        print("  ';' - Change log interval (1-10 frames)")
        print("  ':' - Print current log status")
        
        print("\n🔊 VOICE ALERT CONTROLS:")
        print("  'v' - Toggle voice alerts")
        print("  '9' - Test voice alert")
        print("  'A' - Print alert status")
        
        print("\n🎯 ADVANCED CONTROLS:")
        print("  'C' - Toggle context awareness")
        print("  'X' - Print context statistics")
        print("  't' - Print tracking status")
        
        if not headless:
            print("\n🖼️  DISPLAY CONTROLS (Windowed Only):")
            print("  '1-8' - Different display resize methods")
            print("  '0' - Original size")
            print("  'i' - Toggle resize info")
            print("  'd' - Toggle debug mode")
            print("  'p' - Toggle performance stats")
            print("  'b' - Toggle detection debug")
            print("  's' - Save current frame")
            print("  'k' - Take annotated snapshot")
        
        print("\n📈 STATUS:")
        print("  Press any of the above keys to see current status")
        print("="*60)
        print()


