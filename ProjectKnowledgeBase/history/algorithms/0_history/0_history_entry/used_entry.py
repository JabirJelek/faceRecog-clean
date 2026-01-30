# main/multi_example.py

 
from face_recog_modular2 import create_system, ConfigManager
from face_recog_modular2.streaming.multi_realtime import MultiSourceRealTimeProcessor
 
from face_recog_modular3 import create_system, ConfigManager
from face_recog_modular3.streaming.universal_processor import UniversalStreamProcessor
 
import time
import os
from typing import Dict
import datetime
import threading

def test_multi_stream_connections(sources_config: Dict[str, Dict]) -> bool:
    """Test if we can connect to all streams before starting main processing"""
    print(f"\n🔍 Testing multi-stream connections for {len(sources_config)} sources...")
    
 
    # FIXED: Use the correct module name
    from face_recog_modular2.streaming.stream_manager import StreamManager
 
    from  face_recog_modular3.streaming.stream_manager import StreamManager
 
    
    successful_sources = []
    failed_sources = []
    
    for source_id, source_config in sources_config.items():
        print(f"\n📹 Testing source: {source_id}")
        try:
            test_manager = StreamManager(source_config)
            success = test_manager.initialize_stream(source_config['url'])
            
            if success:
                # Test reading a few frames
                frame_success_count = 0
                for i in range(3):
                    frame_success, frame = test_manager.read_frame()
                    if frame_success and frame is not None:
                        frame_success_count += 1
                        print(f"   ✅ Frame {i+1}: {frame.shape}")
                    else:
                        print(f"   ❌ Failed to read frame {i+1}")
                
                if frame_success_count >= 2:  # Require at least 2 successful frames
                    successful_sources.append(source_id)
                    print(f"✅ Source {source_id} test successful")
                else:
                    failed_sources.append(source_id)
                    print(f"❌ Source {source_id} test failed - insufficient frames")
            else:
                failed_sources.append(source_id)
                print(f"❌ Source {source_id} test failed - initialization failed")
                
            test_manager.release()
            
        except Exception as e:
            failed_sources.append(source_id)
            print(f"❌ Source {source_id} test error: {e}")
    
    # Print summary
    print(f"\n📊 STREAM TEST SUMMARY:")
    print(f"   ✅ Successful: {len(successful_sources)} sources")
    print(f"   ❌ Failed: {len(failed_sources)} sources")
    
    if failed_sources:
        print(f"   Failed sources: {failed_sources}")
    
    # Return True if at least one source is successful
    return len(successful_sources) > 0

def check_gpu_availability(config: dict) -> dict:
    """Check and report GPU availability, updating config accordingly"""
    try:
        import torch
        if torch.cuda.is_available():
            device_count = torch.cuda.device_count()
            current_device = config.get('gpu_device', 0)
            
            if current_device < device_count:
                gpu_name = torch.cuda.get_device_name(current_device)
                memory_info = torch.cuda.get_device_properties(current_device)
                total_memory = memory_info.total_memory / (1024**3)  # Convert to GB
                
                print(f"🎮 GPU {current_device}: {gpu_name} available")
                print(f"🎮 CUDA version: {torch.version.cuda}")
                print(f"🎮 Total GPU Memory: {total_memory:.1f} GB")
                
                # Test GPU functionality
                test_tensor = torch.randn(1000, 1000).cuda()
                test_result = test_tensor * 2
                del test_tensor, test_result
                torch.cuda.empty_cache()
                
                print("✅ GPU functionality test passed")
                config['use_gpu'] = True
                return config
            else:
                print(f"⚠️  GPU device {current_device} not available, falling back to CPU")
                config['use_gpu'] = False
        else:
            print("⚠️  CUDA not available, falling back to CPU")
            config['use_gpu'] = False
            
    except Exception as e:
        print(f"⚠️  GPU check failed: {e}, falling back to CPU")
        config['use_gpu'] = False
    
    return config

def check_onnx_gpu_availability():
    """Check if ONNX Runtime can use GPU"""
    try:
        import onnxruntime as ort
        available_providers = ort.get_available_providers()
        print(f"🔧 Available ONNX Providers: {available_providers}")
        
        if 'CUDAExecutionProvider' in available_providers:
            print("✅ ONNX CUDA Execution Provider available")
            return True
        else:
            print("⚠️  ONNX CUDA Execution Provider not available")
            return False
            
    except Exception as e:
        print(f"⚠️  ONNX GPU check failed: {e}")
        return False

def print_system_info(config: dict):
    """Print comprehensive system information"""
    print("\n" + "="*60)
    print("🖥️  SYSTEM INFORMATION")
    print("="*60)
    
    # CPU Information
    try:
        import psutil
        cpu_count = psutil.cpu_count()
        memory_total = psutil.virtual_memory().total / (1024**3)  # GB
        print(f"💻 CPU Cores: {cpu_count}")
        print(f"💾 Total RAM: {memory_total:.1f} GB")
    except:
        print("💻 CPU: Information not available")
    
    # GPU Information
    try:
        import torch
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                gpu_name = torch.cuda.get_device_name(i)
                memory_info = torch.cuda.get_device_properties(i)
                total_memory = memory_info.total_memory / (1024**3)
                print(f"🎮 GPU {i}: {gpu_name} ({total_memory:.1f} GB)")
        else:
            print("🎮 GPU: No CUDA devices available")
    except:
        print("🎮 GPU: Information not available")
    
    # Python Information
    import sys
    print(f"🐍 Python Version: {sys.version.split()[0]}")
    
    # Library Versions
    try:
        import torch
        print(f"🔥 PyTorch Version: {torch.__version__}")
    except:
        pass
        
    try:
        import cv2
        print(f"👁️  OpenCV Version: {cv2.__version__}")
    except:
        pass
        
    try:
        import onnxruntime as ort
        print(f"🔧 ONNX Runtime Version: {ort.__version__}")
    except:
        pass
    
    print("="*60)

def verify_gpu_usage(face_system):
    """Verify that GPU is actually being used by the models"""
    print("\n🔍 Verifying GPU usage...")
    
    try:
        # Check YOLO model device
        if hasattr(face_system, 'detection_model') and face_system.detection_model:
            yolo_device = next(face_system.detection_model.model.parameters()).device
            print(f"🎯 YOLO Model Device: {yolo_device}")
        
        # Check ONNX mask detector
        if hasattr(face_system, 'mask_detector') and face_system.mask_detector:
            providers = face_system.mask_detector.get_providers()
            print(f"🎯 ONNX Mask Detector Providers: {providers}")
            
        # Check DeepFace backend
        try:
            from deepface.commons import functions
            backend = functions.get_backend()
            print(f"🎯 DeepFace Backend: {backend}")
        except:
            print("🎯 DeepFace Backend: Could not determine")
            
    except Exception as e:
        print(f"⚠️  GPU verification failed: {e}")

def get_default_config():
    """Return the complete default configuration"""
    return {
        # ========== MODEL PATHS ==========        
 
        'detection_model_path': r'A:\SCMA\3-APD\fromAraya\Computer-Vision-CV\3.1_FaceRecog\run_py\modular\0_0_model\yolov12m-face.pt',
        'embeddings_db_path': r'A:\SCMA\3-APD\fromAraya\Computer-Vision-CV\3.1_FaceRecog\run_py\modular\0_dataset\arcface_person_512.json',
        'mask_model_path': r'A:\SCMA\3-APD\fromAraya\Computer-Vision-CV\3.1_FaceRecog\run_py\modular\0_0_model\md_base3.onnx',
        
                                                # PLEASE FIX THE STABILITY OF THE VERIFICATION 
                                                # VALUE BEFORE TRYING TO CHANGE THE TYPE OF mask MODEL USED.        
 
        'detection_model_path': r'D:\RaihanFarid\Dokumen\Object Detection\3.1_FaceRecog\run_py\modular\0_0_model\yolov12m-face.pt',
        'embeddings_db_path': r'D:\RaihanFarid\Dokumen\Object Detection\3.1_FaceRecog\run_py\modular\0_dataset\arcface_person_512.json',
        'mask_model_path': r'D:\RaihanFarid\Dokumen\Object Detection\3.1_FaceRecog\run_py\modular\0_0_model\mask_detector_cus5.onnx',
 
        
        # ========== CORE DETECTION PARAMETERS ==========
        'detection_confidence': 0.5,
        'recognition_threshold': 0.8,
 
        'mask_detection_threshold': 0.6,  # INCREASED from 0.5 - makes mask detection more conservative
        'detection_iou': 0.3,
        'min_face_size': 10, # Min face height in pixels
 
        'mask_detection_threshold': 0.6,
        'detection_iou': 0.3,
        'min_face_size': 10,
 
        'max_faces_per_frame': 15,
        'enable_person_detection': True,
        'person_detection_confidence_threshold': 0.4,        
        
        # ========== PROCESSING PARAMETERS ==========
        'processing_interval': 7,
        'buffer_size': 200,
        'min_processing_scale': 0.3,
        'max_processing_scale': 4.5,
        'adaptive_check_interval': 30,
        'default_processing_width': 1280,
        'default_processing_height': 1080,
        'default_processing_scale': 1.0,
        
        # ========== CCTV CONFIGURATION ==========
        'cctv_name': 'Default',  
 
        # ========== UNIVERSAL PROCESSOR CONFIGURATION ==========
        'multi_source_mode': False,  # Will be set based on command line argument
        'headless_mode': False,      # Will be set based on command line argument
        
 
        # ========== MULTI-SOURCE DISPLAY CONFIGURATION ==========
        'display_layout': 'grid',  # 'grid', 'horizontal', 'vertical'
        'max_display_sources': 4,
        
        # ========== MULTI-SOURCE PROCESSING CONFIGURATION ==========
        'processing_width': 640,
        'processing_height': 480,
        'processing_scale': 1.0,
        
        # ========== STREAM HEALTH MONITORING ==========
        'stream_health': {
            'check_interval': 30.0,  # seconds
            'success_rate_threshold': 0.3,  # 30%
            'unhealthy_retry_delay': 2.0,  # seconds
            'max_consecutive_errors': 10,
        },
        
        # ========== MAINTENANCE CONFIGURATION ==========
        'maintenance_interval': 300.0,  # 5 minutes in seconds
        
        # ========== VIOLATION VERIFICATION (PROCESSOR LEVEL) ==========
        'violation_verification_enabled': True,
        'min_violation_duration': 0.1,  # seconds
        'min_violation_frames': 1,
        'violation_confidence_threshold': 0.4,
        
        # ========== LOGGING INTERVALS ==========
        'log_interval': 1,  # Process every Nth frame
        'enable_logging': True,
        'enable_image_logging': True,
        
        # ========== RESOURCE MANAGEMENT ==========
        'resource_monitoring': {
            'memory_threshold_mb': 1024,  # Warn at 1GB
            'cleanup_interval': 60.0,  # seconds
            'max_open_files': 100,
            'max_threads': 50,
        },
        
        # ========== TRACKING BUFFER SIZES ==========
        'tracking_buffers': {
            'max_track_age': 500,  # seconds
            'max_violation_history': 100,
            'cleanup_old_tracks_interval': 60.0,
        },
        
        # ========== GRID LAYOUT CONFIGURATION ==========
        'grid_layout': {
            'target_height': 360,
            'target_width': 480,
            'max_grid_size': 4,  # 2x2 grid max
        },
        
        # ========== HORIZONTAL LAYOUT CONFIGURATION ==========
        'horizontal_layout': {
            'target_height': 360,
            'maintain_aspect_ratio': True,
        },
        
        # ========== VERTICAL LAYOUT CONFIGURATION ==========
        'vertical_layout': {
            'target_width': 480,
            'maintain_aspect_ratio': True,
        },
        
        # ========== SOURCE OVERLAY CONFIGURATION ==========
        'source_overlay': {
            'show_source_id': True,
            'show_cctv_name': True,
            'show_violation_count': True,
            'font_scale': 0.5,
            'font_thickness': 2,
            'text_color': (255, 255, 255),  # White
            'background_color': (0, 0, 0),  # Black with transparency
            'background_alpha': 0.7,
        },        
            
        # ========== ENHANCED TRACKING CONFIGURATION ==========
        'tracking': {
            'enabled': True,
            'fairness_enabled': True,
            'confidence_frames': 3,
            'cooldown_seconds': 5,
            'min_iou': 0.3,
            'max_recognitions_per_person': 10,
            'recent_window_size': 300,
            'enable_velocity_prediction': True,
            'enable_appearance_matching': True,
            'max_track_age': 500,
            
            # ByteTrack person tracking configuration
            'enable_person_tracking': True,
 
            'enabled':True,
           'enabled': True,
 
            'person_track_confidence': 0.55,
            'person_track_max_age': 90,
            'person_iou_threshold': 0.3,
            'bytetrack_track_thresh': 0.5,
            'bytetrack_track_buffer': 100,
            'bytetrack_match_thresh': 0.8,
            'bytetrack_min_box_area': 10,
            
            # 🎯 Progressive mask detection configuration
            'progressive_mask': {          
 
                
                # Buffer and temporal parameters
                'mask_buffer_size': 200,
                'min_mask_frames': 10,
                'occlusion_timeout': 3.0,
                
                # Confidence and stability thresholds  
                'mask_confidence_threshold': 0.6,
                'mask_consistency_threshold': 0.6,
                
                # Require higher stability before committing
                'min_stability_to_commit': 0.15,
                
                # State holding parameters
                'state_hold_duration': 10.0,
 
                # Buffer and temporal parameters
                'mask_buffer_size': 200,
                'min_mask_frames': 2,
                'occlusion_timeout': 3.0,
                
                # Confidence and stability thresholds  
                'mask_confidence_threshold': 0.1,
                'mask_consistency_threshold': 0.1,
                
                # Require higher stability before committing
                'min_stability_to_commit': 0.1,
                
                # State holding parameters
                'state_hold_duration': 15.0,
 
                'verification_grace_ratio': 0.1,
                
                # Spatial consistency parameters
                'spatial_consistency_weight': 0.3,
                'max_bbox_variation': 0.45,
                
                # Extreme confidence handling
                'extreme_confidence_threshold': 0.95,
                'extreme_mask_penalty': 0.8,
                'extreme_no_mask_boost': 0.9,
                
                # Initial weight parameters
                'initial_mask_weight': 0.2,
                'initial_no_mask_weight': 0.2,
                
 
                # Weight adjustment parameters (NEW - optional to expose)
 
                # Weight adjustment parameters
 
                'weight_increase_high_conf': 0.4,
                'weight_decrease_low_conf': 0.3,
                'weight_increase_opposite': 0.1,
                
                'confidence_smoothing_factor': 0.3,
                'stability_smoothing_factor': 0.2,                
            },
 
            # 🎯 **MODIFIED** Violation verification configuration
            'violation_verification_enabled': True,
            'min_violation_duration': 1,       # DECREASED from 20.0 - quicker to detect violations
            'min_violation_frames': 5,           # DECREASED from 35 - quicker to detect violations
            'violation_confidence_threshold': 0.15, # DECREASED from 0.9 - more sensitive to violations
 
            # Violation verification configuration
            'violation_verification_enabled': True,
            'min_violation_duration': 1,
            'min_violation_frames': 1,
            'violation_confidence_threshold': 0.15,
 
        },    
        
        # ========== VIOLATION VERIFICATION CONFIGURATION ==========
        'violation_verification': {
            'enabled': True,
 
            'min_duration_seconds': 0.1,           # DECREASED from 30 - faster verification
            'min_frames': 1 ,                     # DECREASED from 50 - faster verification
            'confidence_threshold': 0.1,         # DECREASED from 0.85 - more sensitive
            'progressive_verification': True,
            'log_unverified_violations': True,
            'unverified_log_cooldown': 10,        # DECREASED from 15 - more frequent logging
            'false_negative_monitoring': True,
            # 🆕 Modified multi-level verification
            'verification_levels': {
                'low': {'duration': 1.5, 'frames': 1},      # Quicker initial detection
                'medium': {'duration': 2.0, 'frames': 2},  # Medium confidence
                'high': {'duration': 3.0, 'frames': 3},    # High confidence (verified)
 
            'min_duration_seconds': 0.1,
            'min_frames': 1,
            'confidence_threshold': 0.1,
            'progressive_verification': True,
            'log_unverified_violations': True,
            'unverified_log_cooldown': 10,
            'false_negative_monitoring': True,
            # Multi-level verification
            'verification_levels': {
                'low': {'duration': 1.5, 'frames': 1},
                'medium': {'duration': 2.0, 'frames': 2},
                'high': {'duration': 3.0, 'frames': 3}
 
            }
        },  
                
        # ========== LOGGING CONFIGURATION ==========
        'enable_logging': True,
        'enable_image_logging': True,
        'log_interval': 5,
        'image_log_interval': 5,
        'max_images_per_session': 5000,
        'min_save_interval': 1.0,
        
        # ========== SERVER PUSH CONFIGURATION ==========        
        'server_push_enabled': True,
        'server_endpoint': 'https://vps.casda.my.id/accounting/public/api/submit_ai_detection',
        'server_push_cooldown': 5,
        'server_timeout': 10,
 
        'server_retry_attempts': 1,
 
        'server_retry_attempts': 10,
 
        'server_retry_delay': 2,
        
        # ========== IMAGE RESIZE CONFIGURATION ==========
        'enable_image_resize': True,
        'image_resize_width': 1024,
        'image_resize_height': 576,
        'image_resize_method': 'default',
        
        # ========== ALERT CONFIGURATION ==========
        'enable_voice_alerts': True,
        'alert_server_url': "https://vps.casda.my.id/actions/a_notifikasi_suara_speaker.php",
  
        'alert_cooldown_seconds': 15,            # DECREASED from 20 - more responsive alerts
        'min_violation_frames': 1,              # DECREASED from 20 - more sensitive
        'min_violation_seconds': 1,              # DECREASED from 12 - faster alerts
        'max_gap_frames': 10,                    # INCREASED from 8 - more tolerant to gaps
 
        'alert_cooldown_seconds': 15,
        'min_violation_frames': 1,
        'min_violation_seconds': 1,
        'max_gap_frames': 10,
  
        'alert_language': 'id',
        'alert_style': 'formal',
        'enable_individual_alerts': True,
        'enable_group_alerts': True,
 
        'alert_timeout_seconds': 2,              # DECREASED from 3 - faster alert processing
        # 🆕 Modified alert verification requirements
        'alert_verification_required': True,
        'min_alert_confidence': 0.85,            # DECREASED from 0.9 - more sensitive alerts
        'alert_buffer_size': 100,                 # DECREASED from 25 - faster alert decisions
 
        'alert_timeout_seconds': 2,
        'alert_verification_required': True,
        'min_alert_confidence': 0.85,
        'alert_buffer_size': 100,
 
        
        # ========== STREAM MANAGEMENT CONFIGURATION ==========
        'stream_manager': {
            'max_reconnect_attempts': 10,
            'reconnect_delay': 3,
            'health_check_interval': 10,
            'max_frame_gap': 5,
            'buffer_size': 100,
            'open_timeout': 10000,
            'read_timeout': 5000,
        },
        
        # ========== DISPLAY CONFIGURATION ==========
        'display': {
            'default_width': 1280,
            'default_height': 720,
            'max_display_width': 1920,
            'max_display_height': 1080,
            'resize_method': 'fit_to_screen',
            'show_resize_info': False,
            'show_performance_stats': False,
        },
        
        # ========== DEBUG CONFIGURATION ==========
        'debug': {
            'enabled': False,
            'show_detection_debug': False,
            'save_debug_frames': False,
            'max_debug_frames': 100,
            'verbose': False,
        },
        
        # ========== CONTEXT-AWARE SCALING ==========
        'context_aware_scaling': {
            'enabled': True,
            'debug_mode': False,
            'min_context_samples': 10,
            'max_context_samples': 100,
        },
        
        # ========== ADVANCED FEATURES ==========
        'enable_multi_scale': True,
        'enable_temporal_fusion': True,
        'enable_quality_aware': True,
        'embedding_model': 'Facenet512',
        
        # ========== BASE64 CONFIGURATION ==========
        'enable_base64_logging': True,
        'base64_quality': 50,
        
        # ========== SYSTEM MODE ==========
 
        'headless_mode': False,
 
 
        'use_gpu': False,
        'gpu_device': 0,
        
        # ========== ANNOTATION CONFIGURATION ==========
        'annotation_box_thickness': 1,
        'annotation_text_thickness': 1, 
        'annotation_min_text_scale': 0.3,
        'annotation_max_text_scale': 0.8,
        
        # ========== PERFORMANCE TUNING ==========
        'performance': {
            'fps_update_interval': 5.0,
            'dynamic_adjustment_enabled': True,
            'quality_threshold_high': 0.8,
            'quality_threshold_low': 0.3,
            'face_size_threshold_small': 50,
            'face_size_threshold_large': 200,
        }
    }
    
    def get_advanced_sources_config():
        """Return advanced sources configuration with parameters"""
        return {
            '1': {
    
                'url': 'rtsp://admin:Admin888@192.168.0.2:554/Streaming/Channels/501',
                'description': 'Ruang Lab',
                'priority': 'medium',
                'processing_scale': 1,
                'buffer_size': 100,
                'cctv_name':None,            
            },
            
            
            # '2': {
            #     'url': 'rtsp://admin:Admin888@192.168.0.2:554/Streaming/Channels/601',
            #     'description': 'Area Produksi',
            #     'priority': 'medium',
            #     'processing_scale':1,            
            #     'buffer_size': 100,
            #     'cctv_name':None,
            # },
            
            # '3': {
            #     'url': 'rtsp://admin:admin@192.168.110.124:1935',
            #     'description': 'Rtsp HP',
            #     'priority': 'medium',
            #     'processing_scale':1,            
            #     'buffer_size': 100,
            #     'cctv_name':None,
            # },
            
            # '4': {
            #     'url': 'rtsp://admin:admin888@192.168.110.36:554/Streaming/Channels/601',
            #     'description': 'Rtsp HP',
            #     'priority': 'medium',
            #     'processing_scale':1,            
            #     'buffer_size': 100,
            #     'cctv_name':None,
            # },                
                '2':{
                'url': 'rtsp://admin:admin888@192.168.110.34:554/Streaming/Channels/601',
                'description': 'Dekat meja IT',
                'priority': 'low',
                'processing_scale': 1,
                'buffer_size': 100,
                'cctv_name': None,            
            },
            
            '3': {
                'url': 'rtsp://admin:admin888@192.168.110.34:554/Streaming/Channels/501',
                'description': 'Dekat meja bu Dyah',
                'priority': 'medium',
                'processing_scale': 1,            
                'buffer_size': 100,
                'cctv_name': None,
            },
    
        }
        
def load_custom_config(config_path: str = None) -> Dict:
    """Load custom configuration from file if provided"""
    if config_path and os.path.exists(config_path):
        try:
            import json
            with open(config_path, 'r') as f:
                custom_config = json.load(f)
            print(f"✅ Loaded custom configuration from: {config_path}")
            return custom_config
        except Exception as e:
            print(f"❌ Failed to load custom configuration: {e}")
            print("🔄 Using default configuration")
    
    return get_default_config()

def test_server_connection(config: dict) -> bool:
    """Test connection to the violation server"""
    if not config.get('server_push_enabled', False):
        print("📤 Server push disabled, skipping server connection test")
        return True
        
    server_endpoint = config.get('server_endpoint', '')
    if not server_endpoint:
        print("❌ No server endpoint configured")
        return False
        
    try:
        import requests
        print(f"🔍 Testing server connection: {server_endpoint}")
        
        # Test health endpoint
        health_url = server_endpoint.replace('/api/violations', '/api/health')
        response = requests.get(health_url, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ Server connection successful: {health_url}")
            return True
        else:
            print(f"❌ Server health check failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Server connection test failed: {e}")
        print("💡 Make sure the test server is running: python test_upload_server.py")
        return False

def print_server_push_info(config: dict):
    """Print server push configuration information"""
    if config.get('server_push_enabled', False):
        print("\n📤 SERVER PUSH CONFIGURATION")
        print("="*40)
        print(f"   Endpoint: {config.get('server_endpoint')}")
        print(f"   Cooldown: {config.get('server_push_cooldown')}s")
        print(f"   Timeout: {config.get('server_timeout')}s")
        print(f"   Retry Attempts: {config.get('server_retry_attempts')}")
        print(f"   CCTV Name: {config.get('cctv_name')}")
        print("   JSON Structure:")
        print("     {")
        print('       "filename": "string",')
        print('       "image_format": "jpg",')
        print('       "image_data": "base64_string",')
        print('       "detected_name": "string",')
        print('       "cctv_name": "string"')
        print("     }")
        print("="*40)

def print_multi_source_info(sources_config: Dict[str, Dict]):
    """Print multi-source configuration information"""
    print("\n🎯 MULTI-SOURCE CONFIGURATION")
    print("="*50)
    for source_id, source_config in sources_config.items():
        print(f"📹 {source_id}:")
        print(f"   URL: {source_config.get('url', 'N/A')}")
        print(f"   Description: {source_config.get('description', 'No description')}")
        print(f"   Priority: {source_config.get('priority', 'medium')}")
        print(f"   CCTV Name: {source_config.get('cctv_name', 'Unknown')}")
        print(f"   Processing Scale: {source_config.get('processing_scale', 1.0)}")
    print("="*50)

def print_verification_summary(processor):
    """Print comprehensive verification summary from TrackingManager"""
    try:
        if hasattr(processor, 'get_verification_stats'):
            stats = processor.get_verification_stats()
            
            print("\n" + "="*60)
            print("✅ TRACKING MANAGER VERIFICATION SUMMARY")
            print("="*60)
            
            # Aggregate stats
            aggregate = stats.get('aggregate', {})
            print(f"\n📊 AGGREGATE STATISTICS:")
            print(f"   Total Detected: {aggregate.get('total_detected', 0)}")
            print(f"   Total Verified: {aggregate.get('total_verified', 0)}")
            print(f"   Total Rejected: {aggregate.get('total_rejected', 0)}")
            print(f"   False Positives Prevented: {aggregate.get('false_positives_prevented', 0)}")
            print(f"   Active Violation Tracks: {aggregate.get('active_tracks', 0)}")
            print(f"   Currently Verified: {aggregate.get('currently_verified', 0)}")
            
            # Calculate rates
            total_detected = max(1, aggregate.get('total_detected', 1))
            verification_rate = (aggregate.get('total_verified', 0) / total_detected) * 100
            rejection_rate = (aggregate.get('total_rejected', 0) / total_detected) * 100
            prevention_rate = (aggregate.get('false_positives_prevented', 0) / total_detected) * 100
            
            print(f"\n📈 VERIFICATION RATES:")
            print(f"   Verification Rate: {verification_rate:.1f}%")
            print(f"   Rejection Rate: {rejection_rate:.1f}%")
            print(f"   False Positive Prevention Rate: {prevention_rate:.1f}%")
            
            # Per-source stats
            per_source = stats.get('per_source', {})
            if per_source:
                print(f"\n📊 PER-SOURCE STATISTICS:")
                for source_id, source_stats in per_source.items():
                    print(f"\n   📹 Source: {source_id}")
                    print(f"      Detected: {source_stats.get('total_detected', 0)}")
                    print(f"      Verified: {source_stats.get('total_verified', 0)}")
                    print(f"      Rejected: {source_stats.get('total_rejected', 0)}")
                    print(f"      Active Tracks: {source_stats.get('active_violation_tracks', 0)}")
            
            # System stats
            system_stats = stats.get('system_stats', {})
            if system_stats:
                print(f"\n📊 SYSTEM STATISTICS:")
                print(f"   Total Logged: {system_stats.get('total_logged', 0)}")
                print(f"   Verified Logged: {system_stats.get('verified_logged', 0)}")
                
                if system_stats.get('last_verified_time'):
                    last_time = datetime.datetime.fromtimestamp(system_stats['last_verified_time'])
                    print(f"   Last Verified: {last_time.strftime('%H:%M:%S')}")
            
            print("="*60)
            
    except Exception as e:
        print(f"⚠️ Error printing verification summary: {e}")

def monitor_verification_performance(processor, interval_seconds=30):
    """Monitor verification performance periodically"""
    def monitor_worker():
        while getattr(processor, 'running', False):
            try:
                print_verification_summary(processor)
                time.sleep(interval_seconds)
            except Exception as e:
                print(f"⚠️ Verification monitoring error: {e}")
                time.sleep(interval_seconds)
    
    monitor_thread = threading.Thread(target=monitor_worker, daemon=True, name="verification_monitor")
    monitor_thread.start()
    print(f"📊 Started verification performance monitoring (interval: {interval_seconds}s)")


def main():
    # Load configuration
    import argparse
    parser = argparse.ArgumentParser(description='Run modular face recognition system')
    parser.add_argument('--config', type=str, help='Path to custom configuration JSON file')
    parser.add_argument('--multi-source', action='store_true', help='Enable multi-camera processing')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode (no display windows)')
    parser.add_argument('--sources-config', type=str, help='Path to multi-source configuration JSON file')
    parser.add_argument('--camera', type=str, default='0', help='Camera source (default: 0)')
    parser.add_argument('--rtsp', type=str, help='RTSP stream URL')
    parser.add_argument('--no-gpu', action='store_true', help='Disable GPU acceleration')
    parser.add_argument('--cctv-name', type=str, help='Override CCTV name')
    parser.add_argument('--no-server-push', action='store_true', help='Disable server push')
    parser.add_argument('--test-server', action='store_true', help='Test server connection before starting')
    args = parser.parse_args()
    
    # Load configuration
    config = load_custom_config(args.config)
    
    # Override GPU setting if requested
    if args.no_gpu:
        config['use_gpu'] = False
        print("🎮 GPU acceleration disabled via command line")
    
    # Override server push setting if requested
    if args.no_server_push:
        config['server_push_enabled'] = False
        print("📤 Server push disabled via command line")
    
    # Determine headless mode
    headless_mode = args.headless or config.get('headless_mode', False)
    print(f"🎯 Mode: {'HEADLESS' if headless_mode else 'WINDOWED'}")
    
    # Determine multi-source mode
    config['multi_source_mode'] = args.multi_source
    
    # Print system information
    print_system_info(config)
    
    # Check GPU availability and update config
    print("\n🔍 Checking GPU availability...")
    config = check_gpu_availability(config)
    check_onnx_gpu_availability()
    
    # Set environment variables for GPU optimization
    if config.get('use_gpu', False):
        os.environ['CUDA_VISIBLE_DEVICES'] = str(config.get('gpu_device', 0))
        # Optimize for GPU
        os.environ['TF_FORCE_GPU_ALLOW_GROWTH'] = 'true'
        os.environ['TF_GPU_THREAD_MODE'] = 'gpu_private'
        print("🎯 Set GPU environment variables")
    
    # Load multi-source configuration if enabled
    if args.multi_source:
        if args.sources_config and os.path.exists(args.sources_config):
            try:
                import json
                with open(args.sources_config, 'r') as f:
                    sources_config = json.load(f)
                print(f"✅ Loaded multi-source configuration from: {args.sources_config}")
            except Exception as e:
                print(f"❌ Failed to load multi-source configuration: {e}")
                print("🔄 Using default multi-source configuration")
                sources_config = get_advanced_sources_config()
        else:
            print("🔄 Using default multi-source configuration")
            sources_config = get_advanced_sources_config()
        
        print_multi_source_info(sources_config)
        
        # Test multi-stream connections
        if not test_multi_stream_connections(sources_config):
            print("❌ Multi-stream connection test failed. Please check:")
            print("   - Camera connections")
            print("   - RTSP URLs and credentials") 
            print("   - Network connectivity")
            return
    else:
        # Single source mode
 
        #camera_source = args.camera
        rtsp_source = args.rtsp

        print(f"\n📹 Single Source Mode:")
        print(f"CURRENTLY DISABLED!")
        #print(f"   Camera Source: {camera_source}")
        print(f"   RTSP Source: {rtsp_source}")
 
        if args.rtsp:
            source_url = args.rtsp
            source_type = "RTSP"
        else:
            source_url = args.camera
            source_type = "Camera"
 
        
        print(f"\n📹 Single Source Mode:")
        print(f"   {source_type} Source: {source_url}")
        
        # For single source, pass the URL directly
        sources_config = source_url
        
        # Test single stream connection
        test_config = {'main_camera': {'url': source_url}} if isinstance(source_url, str) else source_url
        if not test_multi_stream_connections(test_config if isinstance(test_config, dict) else {'main': {'url': test_config}}):
            print("❌ Stream connection test failed.")
            return
    
    # Test server connection if enabled and requested
    if config.get('server_push_enabled', False) and args.test_server:
        if not test_server_connection(config):
            print("❌ Server connection test failed. Continue without server push? (y/n)")
            choice = input().strip().lower()
            if choice != 'y':
                print("🛑 Exiting...")
                return
            else:
                config['server_push_enabled'] = False
                print("⚠️  Continuing without server push")
                
    
    # Create robust face recognition system using factory
    print("\n🔄 Creating face recognition system...")
    try:
        face_system = create_system(config, system_type="robust")
        
        # Verify GPU usage
        verify_gpu_usage(face_system)
        
    except Exception as e:
        print(f"❌ Failed to create face recognition system: {e}")
        print("🔄 Falling back to CPU mode...")
        config['use_gpu'] = False
        face_system = create_system(config, system_type="robust")
 
    # Apply multi-source specific configurations
    multi_source_config = {
        'display_layout': config.get('display_layout', 'grid'),
        'max_display_sources': config.get('max_display_sources', 4),
        'processing_width': config.get('processing_width', 640),
        'processing_height': config.get('processing_height', 480),
        'processing_scale': config.get('processing_scale', 1.0),
        'violation_verification_enabled': config.get('violation_verification_enabled', True),
        'min_violation_duration': config.get('min_violation_duration', 0.5),
        'min_violation_frames': config.get('min_violation_frames', 1),
        'violation_confidence_threshold': config.get('violation_confidence_threshold', 0.6),
        'log_interval': config.get('log_interval', 1),
        'enable_logging': config.get('enable_logging', True),
        'enable_image_logging': config.get('enable_image_logging', True),
    }

    # Merge with existing config
    full_config = {**config, **multi_source_config}

    # Initialize processor with full config
    processor = MultiSourceRealTimeProcessor(
        face_system, 
        full_config  # Use the merged config
    )
    
    # Apply configurations to processor
    processor.apply_alert_config(config)
    processor.apply_tracking_config(config)
    processor.apply_logging_config(config)
    
    # 🆕 Apply violation verification configuration to all tracking managers
    if 'tracking' in config and 'violation_verification_enabled' in config['tracking']:
        verification_config = {
            'violation_verification_enabled': config['tracking']['violation_verification_enabled'],
            'min_violation_duration': config['tracking'].get('min_violation_duration', 5.0),
            'min_violation_frames': config['tracking'].get('min_violation_frames', 5),
            'violation_confidence_threshold': config['tracking'].get('violation_confidence_threshold', 0.85)
        }
        processor.apply_verification_config(verification_config)
    
    # Print comprehensive configuration status
    print("\n" + "="*60)
    print("🎯 MULTI-SOURCE SYSTEM CONFIGURATION STATUS")
    print("="*60)
    print(f"📊 Sources: {len(sources_config)} cameras configured")
 
    # ========== SIMPLIFIED: Initialize UniversalStreamProcessor ==========
    print("\n🎯 Initializing UniversalStreamProcessor...")
    
    # Initialize the Universal Processor once
    processor = UniversalStreamProcessor(
        face_system=face_system,
        config=config,
        headless_mode=headless_mode
    )
    
    # Set debug flags directly from config
    processor.debug_mode = config['debug']['enabled']
    processor.show_performance_stats = config['display']['show_performance_stats']
    processor.show_resize_info = config['display']['show_resize_info']
    processor.show_detection_debug = config['debug'].get('show_detection_debug', False)
    
    # Print comprehensive configuration status
    print("\n" + "="*60)
    print("🎯 UNIVERSAL PROCESSOR CONFIGURATION STATUS")
    print("="*60)
    print(f"🎮 Mode: {'Multi-source' if args.multi_source else 'Single source'}")
    print(f"📊 Display: {'Headless' if headless_mode else 'Windowed'}")
 
    print(f"📊 Processing: Interval={config['processing_interval']}, Buffer={config['buffer_size']}")
    print(f"🔍 Detection: Confidence={config['detection_confidence']}, Recognition Threshold={config['recognition_threshold']}")
    print(f"🎯 Face Tracking: {'ENABLED' if config['tracking']['enabled'] else 'DISABLED'}")
    
    # 🆕 NEW: Print verification configuration
    if config['tracking'].get('violation_verification_enabled', False):
        print(f"✅ Violation Verification: ENABLED")
        print(f"   - Min Duration: {config['tracking'].get('min_violation_duration', 5.0)}s")
        print(f"   - Min Frames: {config['tracking'].get('min_violation_frames', 5)}")
        print(f"   - Confidence Threshold: {config['tracking'].get('violation_confidence_threshold', 0.85)}")
    else:
        print(f"✅ Violation Verification: DISABLED")
    
    print(f"📝 Logging: {'ENABLED' if config['enable_logging'] else 'DISABLED'}")
    print(f"🔊 Alerts: {'ENABLED' if config['enable_voice_alerts'] else 'DISABLED'}")
    print(f"📤 Server Push: {'ENABLED' if config['server_push_enabled'] else 'DISABLED'}")
    print(f"🐛 Debug: {'ENABLED' if config['debug']['enabled'] else 'DISABLED'}")
 
    print(f"🖼️  Display Layout: {getattr(processor, 'display_layout', 'grid')}")
 
    print(f"🎮 GPU Acceleration: {'ENABLED' if config['use_gpu'] else 'DISABLED'}")
    if config['use_gpu']:
        print(f"🎮 GPU Device: {config['gpu_device']}")
    print("="*60)
    
 
    # Print server push details if enabled
    if config.get('server_push_enabled', False):
        print_server_push_info(config)
    
 
    # Print module-specific status
    processor.print_tracking_status()
    processor.print_alert_status()
    
    # Apply display configuration
    if hasattr(processor, 'set_display_size'):
        processor.set_display_size(
            config['display']['default_width'],
            config['display']['default_height'],
            config['display']['resize_method']
        )
    
    # Apply debug configuration
    if config['debug']['enabled']:
        processor.toggle_debug_mode()
    if config['display']['show_performance_stats']:
        processor.toggle_performance_stats()
    if config['display']['show_resize_info']:
        processor.toggle_resize_info()    
    
    
    
    
    # Final system readiness check
    print("\n🔍 FINAL SYSTEM READINESS CHECK")
    print("="*40)
    print(f"📹 Sources: {len(sources_config)} cameras ready")
    for source_id in sources_config.keys():
        print(f"   - {source_id}")
 
    # Final system readiness check
    print("\n🔍 FINAL SYSTEM READINESS CHECK")
    print("="*40)
    print(f"🎯 Processor: UniversalStreamProcessor READY")
    print(f"📹 Mode: {'Multi-source' if args.multi_source else 'Single source'}")
 
    print(f"🎮 GPU: {'READY' if config['use_gpu'] else 'CPU MODE'}")
    print(f"📤 Server Push: {'READY' if config['server_push_enabled'] else 'DISABLED'}")
    print(f"🔊 Audio Alerts: {'READY' if config['enable_voice_alerts'] else 'DISABLED'}")
    print(f"🎯 Tracking: {'READY' if config['tracking']['enabled'] else 'DISABLED'}")
    print(f"✅ Violation Verification: {'READY' if config['tracking'].get('violation_verification_enabled', False) else 'DISABLED'}")
    print("="*40)
 
    
    # 🆕 NEW: Print verification-specific controls
    print("\n🎮 VERIFICATION CONTROLS:")
    print("   [V] - Toggle violation verification")
    print("   [S] - Show verification statistics")
    print("   [M] - Start verification monitoring")    
    
    # Print multi-source controls
    print("\n🎮 MULTI-SOURCE CONTROLS:")
    print("   [m] - Cycle through display layouts (grid, horizontal, vertical)")
    print("   [n] - Toggle source health display")
    print("   [0] - Show source health report")
    print("   [l] - Toggle logging")
    print("   [v] - Toggle voice alerts")
    print("   [p] - Toggle performance stats")
    print("   [d] - Toggle debug mode")
    print("   [q] - Quit")
 
    
    # Add a small delay to ensure everything is ready
    print("\n⏳ Starting processing in 3 seconds...")
    time.sleep(3)
    
 
    # 🆕 CRITICAL: Ensure ImageLoggers are created for all sources
    print("\n🔍 ENSURING IMAGE LOGGERS ARE CREATED FOR ALL SOURCES")
    for source_id in sources_config.keys():
        if source_id in processor.active_sources:
            print(f"🔄 Ensuring ImageLogger for: {source_id}")
            success = processor.force_create_image_logger(source_id)
            if success:
                print(f"✅ ImageLogger created for: {source_id}")
            else:
                print(f"❌ Failed to create ImageLogger for: {source_id}")

    # 🆕 DEBUG: Check CCTV names before starting
    print("\n🔍 PRE-START CCTV NAME CHECK")
    processor.debug_cctv_names()
        
    # Start multi-source processing
    try:
        # 🆕 ONLY ONE SOURCE ADDITION BLOCK
        print("\n🎯 ADDING SOURCES WITH DYNAMIC CCTV NAMING")
        print("="*50)

        # First, remove any existing sources to start fresh
        existing_sources = list(processor.stream_managers.keys())
        for source_id in existing_sources:
            print(f"🔄 Removing existing source: {source_id}")
            processor.remove_source(source_id)

        # Now add the sources with proper dynamic naming
        for source_id, source_config in sources_config.items():
            print(f"📹 Adding source: {source_id}")
            
            # 🆕 DEBUG: Test CCTV naming before adding
            test_url = source_config.get('url', '')
            if test_url:
                extracted_name = processor._extract_cctv_name_from_url(test_url, source_id)
                print(f"   🔍 CCTV name extraction test: {extracted_name}")
            
            success = processor.add_source(source_id, source_config)
            if success:
                # Verify the CCTV name was set correctly
                source_info = processor.get_source_info(source_id)
                if source_info:
                    actual_cctv_name = source_info.get('cctv_name', 'Unknown')
                    print(f"✅ Successfully added {source_id} → {actual_cctv_name}")
            else:
                print(f"❌ Failed to add {source_id}")

        print("="*50)
        
        # Print all sources information
        processor.print_all_sources_info()
        
        # Print CCTV mapping
        processor.print_cctv_mapping()
        
        # 🆕 CRITICAL: Setup logging ONLY ONCE after all sources are added
        print("\n🔄 Setting up multi-source logging with dynamic CCTV names...")
        processor.setup_multi_source_logging()
        
        # Run the multi-source processing
        processor.run_multi_source_stable(sources_config)
        
        # 🆕 NEW: Start verification performance monitoring
        print("\n📊 Starting verification performance monitoring...")
        monitor_verification_performance(processor, interval_seconds=60)
        
        # Run the multi-source processing
        processor.run_multi_source_stable(sources_config)
 
    # ========== SIMPLIFIED: Run the processor ==========
    try:
        # 🆕 NEW: Use context manager for automatic cleanup
        print("\n🎬 Starting UniversalStreamProcessor...")
        
        # Streamline the run() call
        if args.multi_source:
            # Use your existing sources_config dictionary directly
            print(f"🚀 Starting multi-source processing with {len(sources_config)} sources")
            processor.run(sources_config)
        else:
            # Single source mode - pass the URL directly
            print(f"🚀 Starting single source processing: {sources_config}")
            processor.run(sources_config)
 
        
    except KeyboardInterrupt:
        print("\n🛑 Shutting down by user request...")
        
        # 🆕 NEW: Print final verification summary
        print("\n📊 FINAL VERIFICATION SUMMARY:")
        print_verification_summary(processor)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean shutdown is handled automatically by the processor
        print("🛑 Processing completed")

if __name__ == "__main__":
    main()
    