# config/validation_rules.py

"""
Configuration validation rules and schema definitions.
"""

from typing import Dict, Any, List, Tuple, Optional, Union
import numbers

class ValidationRules:
    """Defines validation rules for configuration parameters."""
    
    # Base validation rules for all configuration parameters
    BASE_RULES = {
        'detection_confidence': {
            'type': (int, float),
            'range': (0.0, 1.0),
            'default': 0.6,
            'description': 'Confidence threshold for face detection'
        },
        'recognition_threshold': {
            'type': (int, float),
            'range': (0.0, 1.0),
            'default': 0.6,
            'description': 'Similarity threshold for face recognition'
        },
        'mask_detection_threshold': {
            'type': (int, float),
            'range': (0.0, 1.0),
            'default': 0.8,
            'description': 'Confidence threshold for mask detection'
        },
        'processing_interval': {
            'type': int,
            'range': (1, 60),
            'default': 5,
            'description': 'Frame processing interval (process every N frames)'
        },
        'min_processing_scale': {
            'type': (int, float),
            'range': (0.1, 1.0),
            'default': 0.3,
            'description': 'Minimum scale for dynamic processing'
        },
        'max_processing_scale': {
            'type': (int, float),
            'range': (1.0, 5.0),
            'default': 2.5,
            'description': 'Maximum scale for dynamic processing'
        },
        'min_face_quality': {
            'type': (int, float),
            'range': (0.0, 1.0),
            'default': 0.3,
            'description': 'Minimum face quality score for processing'
        },
        'temporal_buffer_size': {
            'type': int,
            'range': (1, 50),
            'default': 10,
            'description': 'Size of temporal fusion buffer'
        },
        'alert_cooldown_seconds': {
            'type': int,
            'range': (1, 300),
            'default': 30,
            'description': 'Cooldown period between voice alerts'
        },
        'min_violation_frames': {
            'type': int,
            'range': (1, 100),
            'default': 20,
            'description': 'Minimum frames for violation alert'
        },
        'min_violation_seconds': {
            'type': (int, float),
            'range': (0.5, 10.0),
            'default': 2.0,
            'description': 'Minimum seconds for violation alert'
        }
    }
    
    # Advanced rules for specific modules
    ADVANCED_RULES = {
        'voyager_space': {
            'type': str,
            'options': ['cosine', 'euclidean'],
            'default': 'cosine',
            'description': 'Space metric for Voyager vector search'
        },
        'embedding_model': {
            'type': str,
            'options': ['Facenet', 'Facenet512', 'VGGFace', 'OpenFace', 'DeepFace'],
            'default': 'Facenet512',
            'description': 'Model for face embedding extraction'
        },
        'enable_multi_scale': {
            'type': bool,
            'default': True,
            'description': 'Enable multi-scale face processing'
        },
        'enable_temporal_fusion': {
            'type': bool,
            'default': True,
            'description': 'Enable temporal fusion for recognition'
        },
        'enable_quality_aware': {
            'type': bool,
            'default': True,
            'description': 'Enable quality-aware processing'
        },
        'enable_voice_alerts': {
            'type': bool,
            'default': True,
            'description': 'Enable voice alerts'
        }
    }

    @classmethod
    def validate_configuration(cls, config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate a configuration dictionary against all rules.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            Tuple[bool, List[str]]: (is_valid, error_messages)
        """
        errors = []
        warnings = []
        
        # Merge all rules
        all_rules = {**cls.BASE_RULES, **cls.ADVANCED_RULES}
        
        for key, value in config.items():
            if key in all_rules:
                is_valid, error_msg = cls._validate_value(key, value, all_rules[key])
                if not is_valid:
                    errors.append(error_msg)
            else:
                warnings.append(f"Unknown configuration key: {key}")
        
        # Check for required keys
        required_keys = ['detection_model_path', 'embeddings_db_path']
        for req_key in required_keys:
            if req_key not in config:
                errors.append(f"Required configuration key missing: {req_key}")
        
        return len(errors) == 0, errors + warnings

    @classmethod
    def _validate_value(cls, key: str, value: Any, rules: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate a single configuration value against its rules."""
        # Type validation
        expected_type = rules.get('type')
        if expected_type and not isinstance(value, expected_type):
            return False, f"{key}: expected {expected_type}, got {type(value)}"
        
        # Range validation for numeric types
        if isinstance(value, (int, float)):
            min_val = rules.get('range', [None, None])[0]
            max_val = rules.get('range', [None, None])[1]
            
            if min_val is not None and value < min_val:
                return False, f"{key}: value {value} below minimum {min_val}"
            if max_val is not None and value > max_val:
                return False, f"{key}: value {value} above maximum {max_val}"
        
        # Options validation for string types
        if isinstance(value, str) and 'options' in rules:
            if value not in rules['options']:
                return False, f"{key}: value '{value}' not in allowed options {rules['options']}"
        
        # Boolean validation
        if rules.get('type') == bool and not isinstance(value, bool):
            return False, f"{key}: expected boolean, got {type(value)}"
        
        return True, ""

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """Get a configuration dictionary with all default values."""
        default_config = {}
        
        # Merge all rules and extract defaults
        all_rules = {**cls.BASE_RULES, **cls.ADVANCED_RULES}
        
        for key, rules in all_rules.items():
            if 'default' in rules:
                default_config[key] = rules['default']
        
        return default_config

    @classmethod
    def get_config_description(cls, key: str) -> Optional[str]:
        """Get description for a configuration key."""
        all_rules = {**cls.BASE_RULES, **cls.ADVANCED_RULES}
        return all_rules.get(key, {}).get('description')

    @classmethod
    def get_validation_rules(cls) -> Dict[str, Dict[str, Any]]:
        """Get all validation rules."""
        return {**cls.BASE_RULES, **cls.ADVANCED_RULES}

    @classmethod
    def suggest_correction(cls, key: str, invalid_value: Any) -> Any:
        """Suggest a corrected value for an invalid configuration."""
        all_rules = {**cls.BASE_RULES, **cls.ADVANCED_RULES}
        
        if key not in all_rules:
            return invalid_value
        
        rules = all_rules[key]
        
        # Return default if available
        if 'default' in rules:
            return rules['default']
        
        # For range violations, clamp to range
        if 'range' in rules and isinstance(invalid_value, (int, float)):
            min_val, max_val = rules['range']
            if min_val is not None and invalid_value < min_val:
                return min_val
            if max_val is not None and invalid_value > max_val:
                return max_val
        
        return invalid_value