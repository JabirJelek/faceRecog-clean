# config/config_manager.py
from typing import Dict, List
from collections import  deque
import time
import json
import datetime
from pathlib import Path
from .validation_rules import ValidationRules


class ConfigManager:
    """Unified configuration manager for hierarchical configuration management"""
    
    def __init__(self, base_config: Dict):
        self.base = base_config.copy()  # Deep copy to prevent mutations
        self.derived = self._build_derived_configs()
        self.config_history = deque(maxlen=10)  # Track config changes
        
        # Validate base config
        is_valid, errors = ValidationRules.validate_configuration(self.base)
        if not is_valid:
                error_msg = "\n".join(errors)
                raise ValueError(f"Invalid base configuration: \n{error_msg}")
        
        
        print("✅ ConfigManager initialized with unified configuration system")
    
    def _build_derived_configs(self) -> Dict[str, Dict]:
        """Build all derived configurations from base"""
        derived_configs = {}
        
        # Robust Face Recognition Config
        derived_configs['robust_face_recognition'] = {
            **self.base,
            # Robustness enhancements
            'enable_multi_scale': True,
            'enable_temporal_fusion': True, 
            'enable_quality_aware': True,
            'enable_quality_adaptive_similarity': True,
            'min_face_quality': 0.3,
            'temporal_buffer_size': 10,
            
            # CRITICAL: Detection optimizations
            'detection_confidence': 0.7,      # Higher = fewer detections
            'detection_iou': 0.4,             # Lower = faster NMS
            'max_faces_per_frame': 5,        
            'min_face_size': 20,              
                       
            'recognition_threshold': 0.4,
            'mask_detection_threshold': 0.95,            
            
            # Multi-scale processing
            'scale_factors': [0.5, 0.75, 1.0, 1.25, 1.5],
            'rotation_angles': [-10, -5, 0, 5, 10],
            
            # Quality assessment weights
            'quality_weights': {
                'sharpness': 0.3,
                'brightness': 0.2, 
                'contrast': 0.15,
                'size': 0.2,
                'position': 0.1,
                'blur': 0.05
            },
            
            # Enhanced similarity configuration
            'similarity_method': 'voyager',
        }
        
        # Context-Aware Processing Config
        derived_configs['context_aware_processing'] = {
            **derived_configs['robust_face_recognition'],
            
            # Context-aware scaling parameters
            'min_processing_scale': 0.3,
            'max_processing_scale': 2.5,
            'scale_adjustment_step': 0.1,
            'context_weight': 0.4,
            'performance_weight': 0.6,
            
            # Enable context features
            'enable_context_aware_scaling': True,
        }
        
        # High Performance Config
        derived_configs['high_performance'] = {
            **self.base,
            'processing_interval': 10,
            'current_processing_scale': 0.6,
            'processing_width': 640,
            'processing_height': 480,
            'enable_multi_scale': False,
            'enable_temporal_fusion': False,
            'similarity_method': 'voyager',
        }
        
        # High Accuracy Config
        derived_configs['high_accuracy'] = {
            **derived_configs['robust_face_recognition'],
            'processing_interval': 2,
            'current_processing_scale': 1.5,
            'processing_width': 1920,
            'processing_height': 1080,
            'detection_confidence': 0.7,
            'recognition_threshold': 0.7,
        }
        
        # Balanced Config
        derived_configs['balanced'] = {
            **derived_configs['robust_face_recognition'],
            'processing_interval': 5,
            'current_processing_scale': 1.0,
            'processing_width': 1280,
            'processing_height': 720,
        }
        
                # Small Face Detection Config
        derived_configs['small_face_detection'] = {
            **derived_configs['robust_face_recognition'],
            
            # Enhanced detection for small faces
            'detection_confidence': 0.4,
            'detection_iou': 0.3,
            'min_face_size': 20,
            'max_faces_per_frame': 15,
            
            # Multi-scale enhancements
            'scale_factors': [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75],
            
            # Processing resolution
            'processing_width': 1600,
            'processing_height': 900,
            'current_processing_scale': 1.5,
            
            # Quality assessment adjustments
            'min_face_quality': 0.2,  # Lower threshold for small faces
            
            # Recognition thresholds
            'recognition_threshold': 0.5,  # Slightly lower for small faces
        }
        
        return derived_configs
    
 
 
    def get_component_config(self, component_name: str) -> Dict:
        if component_name in self.derived:
            config = self.derived[component_name]
            self.config_history.append({
                'component': component_name,
                'timestamp': time.time(),
                'config_keys': list(config.keys())[:5]
            })
            return config
        else:
            raise KeyError(f"Configuration profile '{component_name}' not found. "
                        f"Available profiles: {self.get_available_configs()}")
            
    def get_available_configs(self) -> List[str]:
        """Get list of available configuration profiles"""
        return ['base'] + list(self.derived.keys())
    
    def create_custom_config(self, profile_name: str, base_profile: str, overrides: Dict) -> bool:
        """Create a custom configuration profile"""
        if profile_name in self.derived:
            print(f"❌ Config profile '{profile_name}' already exists")
            return False
        
        # Get base profile
        if base_profile == 'base':
            base_config = self.base
        elif base_profile in self.derived:
            base_config = self.derived[base_profile]
        else:
            print(f"❌ Base profile '{base_profile}' not found")
            return False
        
        # Apply overrides
        custom_config = {**base_config, **overrides}
        
        # Validate
        if not ValidationRules.validate_configuration(custom_config):
            return False
        
        # Store
        self.derived[profile_name] = custom_config
        print(f"✅ Created custom config profile: '{profile_name}'")
        return True
    
    def update_config_value(self, profile_name: str, key: str, value: any) -> bool:
        """Update a specific configuration value"""
        if profile_name == 'base':
            config = self.base
        elif profile_name in self.derived:
            config = self.derived[profile_name]
        else:
            print(f"❌ Config profile '{profile_name}' not found")
            return False
        
        # Validate using ValidationRules
        all_rules = ValidationRules.get_validation_rules()
        if key in all_rules:
            is_valid, error = ValidationRules._validate_value(key, value, all_rules[key])
            if not is_valid:
                print(f"❌ {error}")
                return False
        
        # Apply update
        old_value = config.get(key)
        config[key] = value
        print(f"🔄 Updated {profile_name}.{key}: {old_value} → {value}")
        return True
    
    def get_config_info(self, profile_name: str = None) -> Dict:
        """Get information about configuration profiles"""
        if profile_name:
            if profile_name == 'base':
                config = self.base
            elif profile_name in self.derived:
                config = self.derived[profile_name]
            else:
                return {'error': f"Profile '{profile_name}' not found"}
            
            return {
                'profile_name': profile_name,
                'key_count': len(config),
                'sample_keys': list(config.keys())[:10],
                'validation_status': ValidationRules.validate_configuration(config)
            }
        else:
            # Return info for all profiles
            info = {
                'base': {
                    'key_count': len(self.base),
                    'validation_status': ValidationRules.validate_configuration(self.base)
                }
            }
            for name, config in self.derived.items():
                info[name] = {
                    'key_count': len(config),
                    'validation_status': ValidationRules.validate_configuration(config)
                }
            return info
    
    def export_config(self, profile_name: str, filepath: str = None) -> bool:
        """Export configuration to JSON file"""
        if profile_name == 'base':
            config = self.base
        elif profile_name in self.derived:
            config = self.derived[profile_name]
        else:
            print(f"❌ Config profile '{profile_name}' not found")
            return False
        
        try:
            if filepath is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = f"config_{profile_name}_{timestamp}.json"
            
            with open(filepath, 'w') as f:
                json.dump(config, f, indent=2)
            
            print(f"✅ Exported config '{profile_name}' to {filepath}")
            return True
        except Exception as e:
            print(f"❌ Failed to export config: {e}")
            return False
    
    def import_config(self, filepath: str, profile_name: str = None) -> bool:
        """Import configuration from JSON file"""
        try:
            with open(filepath, 'r') as f:
                imported_config = json.load(f)
            
            # Determine profile name
            if profile_name is None:
                profile_name = Path(filepath).stem
            
            # Validate imported config
            if not ValidationRules.validate_configuration(imported_config):
                return False
            
            # Store as custom profile
            self.derived[profile_name] = imported_config
            print(f"✅ Imported config as '{profile_name}' from {filepath}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to import config: {e}")
            return False
