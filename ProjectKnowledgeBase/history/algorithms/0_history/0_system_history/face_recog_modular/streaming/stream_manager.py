import cv2
import time
import threading
from queue import Queue
from typing import Dict, Optional, Tuple, Any
import numpy as np
from pathlib import Path
import logging

class StreamManager:
    """
    Robust stream manager for handling various video sources (camera, RTSP, CCTV, video files)
    with automatic reconnection, health monitoring, and frame queue management.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # Stream properties
        self.cap = None
        self.stream_type = None
        self.source = None
        self.is_opened = False
        
        # Reconnection settings
        self.max_reconnect_attempts = self.config.get('max_reconnect_attempts', 5)
        self.reconnect_delay = self.config.get('reconnect_delay', 5)
        self.reconnect_attempts = 0
        self.last_reconnect_time = 0
        
        # Stream health monitoring
        self.frame_count = 0
        self.error_count = 0
        self.last_successful_frame_time = 0
        self.health_check_interval = self.config.get('health_check_interval', 10)  # Reduced to 10s
        self.max_frame_gap = self.config.get('max_frame_gap', 5)  # Reduced to 5 seconds
        
        # Performance metrics
        self.fps = 0
        self.avg_frame_time = 0
        self.start_time = time.time()
        
        # Threading for stability
        self.lock = threading.Lock()
        self.running = False
        self.health_monitor_thread = None
        self.capture_thread = None
        
        # Frame queue management
        self.frame_queue = Queue(maxsize=self.config.get('buffer_size', 3))
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        
        # Debug and status
        self.last_error_message = ""
        self.initialization_attempted = False
        
        # Stream-specific configurations
        self.stream_configs = {
            'rtsp': {
                'open_timeout': 10000,
                'read_timeout': 5000,
                'buffer_size': 1,
                'backend': cv2.CAP_FFMPEG
            },
            'camera': {
                'buffer_size': 1,
                'fps': 30,
                'resolution': (1920, 1080)
            },
            'video_file': {
                'buffer_size': 1
            },
            'cctv': {
                'open_timeout': 10000,
                'read_timeout': 10000,
                'buffer_size': 2,
                'backend': cv2.CAP_FFMPEG
            }
        }
        
        # Setup logging
        self.setup_logging()
        
        print("🎬 StreamManager initialized with robust reconnection handling")

    def setup_logging(self):
        """Setup logging for stream manager"""
        self.logger = logging.getLogger('StreamManager')
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    # ========== STREAM INITIALIZATION METHODS ==========
    
    def initialize_stream(self, source: str) -> bool:
        """
        Initialize video stream from various sources.
        
        Args:
            source: Can be:
                   - Camera index (0, 1, 2...)
                   - RTSP URL (rtsp://...)
                   - CCTV URL
                   - Video file path
                   - HTTP stream URL
        
        Returns:
            bool: True if stream initialized successfully
        """
        try:
            self.initialization_attempted = True
            self.source = source
            self.stream_type = self._detect_stream_type(source)
            
            print(f"🔍 Initializing {self.stream_type} stream: {source}")
            
            # Release existing stream if any
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            
            # Initialize based on stream type
            success = self._initialize_by_type(source)
            
            if success:
                self.is_opened = True
                self.reconnect_attempts = 0
                self.last_successful_frame_time = time.time()
                self._start_health_monitor()
                
                # Get stream info
                self._log_stream_info()
                print(f"✅ Stream initialized successfully: {source}")
                return True
            else:
                self.last_error_message = f"Failed to initialize {self.stream_type} stream"
                print(f"❌ {self.last_error_message}")
                return False
                
        except Exception as e:
            self.last_error_message = f"Stream initialization error: {e}"
            print(f"❌ {self.last_error_message}")
            return False

    def _detect_stream_type(self, source: str) -> str:
        """Detect the type of stream based on source string"""
        source_lower = str(source).lower()
        
        if source_lower.startswith('rtsp://'):
            return 'rtsp'
        elif source_lower.startswith('http://') or source_lower.startswith('https://'):
            return 'cctv'
        elif source_lower.endswith(('.mp4', '.avi', '.mov', '.mkv')):
            return 'video_file'
        elif source_lower.isdigit() or source_lower in ['0', '1', '2']:
            return 'camera'
        else:
            # Default to camera for numeric values, otherwise try as file/URL
            try:
                int(source)
                return 'camera'
            except ValueError:
                return 'cctv'  # Try as generic stream

    def _initialize_by_type(self, source: str) -> bool:
        """Initialize stream based on type with appropriate settings"""
        config = self.stream_configs.get(self.stream_type, {})
        
        try:
            if self.stream_type == 'camera':
                return self._initialize_camera(source, config)
            elif self.stream_type == 'rtsp':
                return self._initialize_rtsp(source, config)
            elif self.stream_type == 'cctv':
                return self._initialize_cctv(source, config)
            elif self.stream_type == 'video_file':
                return self._initialize_video_file(source, config)
            else:
                return self._initialize_generic(source)
                
        except Exception as e:
            print(f"❌ {self.stream_type} initialization failed: {e}")
            return False

    def _initialize_camera(self, source: str, config: Dict) -> bool:
        """Initialize local camera"""
        try:
            camera_id = int(source)
            backend = config.get('backend', cv2.CAP_ANY)
            
            print(f"📷 Attempting to open camera {camera_id} with backend {backend}")
            self.cap = cv2.VideoCapture(camera_id, backend)
            
            if not self.cap.isOpened():
                print(f"❌ Failed to open camera {camera_id}")
                return False
            
            # Set camera properties for best performance
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, config.get('buffer_size', 1))
            self.cap.set(cv2.CAP_PROP_FPS, config.get('fps', 30))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.get('resolution', (1920, 1080))[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.get('resolution', (1920, 1080))[1])
            self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
            
            # Test frame read
            ret, frame = self.cap.read()
            if ret and frame is not None:
                print(f"✅ Camera {camera_id} opened successfully")
                return True
            else:
                print(f"❌ Camera {camera_id} opened but cannot read frames")
                return False
                
        except Exception as e:
            print(f"❌ Camera initialization error: {e}")
            return False

    def _initialize_rtsp(self, source: str, config: Dict) -> bool:
        """Initialize RTSP stream with optimization"""
        try:
            optimized_url = self._optimize_rtsp_url(source)
            backend = config.get('backend', cv2.CAP_FFMPEG)
            
            print(f"🌐 Attempting to open RTSP stream: {optimized_url}")
            self.cap = cv2.VideoCapture(optimized_url, backend)
            
            if not self.cap.isOpened():
                print(f"❌ Failed to open RTSP stream")
                return False
            
            # Set RTSP properties for stability
            self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, config.get('open_timeout', 10000))
            self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, config.get('read_timeout', 5000))
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, config.get('buffer_size', 1))
            
            # Test frame read with timeout
            ret, frame = self._read_frame_with_timeout(10.0)
            if ret and frame is not None:
                print(f"✅ RTSP stream opened successfully")
                return True
            else:
                print(f"❌ RTSP stream opened but cannot read frames")
                return False
                
        except Exception as e:
            print(f"❌ RTSP initialization error: {e}")
            return False

    def _initialize_cctv(self, source: str, config: Dict) -> bool:
        """Initialize CCTV/HTTP stream"""
        try:
            backend = config.get('backend', cv2.CAP_FFMPEG)
            
            print(f"📡 Attempting to open CCTV stream: {source}")
            self.cap = cv2.VideoCapture(source, backend)
            
            if not self.cap.isOpened():
                print(f"❌ Failed to open CCTV stream")
                return False
            
            # Set CCTV properties
            self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, config.get('open_timeout', 10000))
            self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, config.get('read_timeout', 10000))
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, config.get('buffer_size', 2))
            
            # Test frame read
            ret, frame = self._read_frame_with_timeout(15.0)
            if ret and frame is not None:
                print(f"✅ CCTV stream opened successfully")
                return True
            else:
                print(f"❌ CCTV stream opened but cannot read frames")
                return False
                
        except Exception as e:
            print(f"❌ CCTV initialization error: {e}")
            return False

    def _initialize_video_file(self, source: str, config: Dict) -> bool:
        """Initialize video file"""
        try:
            if not Path(source).exists():
                print(f"❌ Video file not found: {source}")
                return False
                
            print(f"🎥 Attempting to open video file: {source}")
            self.cap = cv2.VideoCapture(source)
            
            if not self.cap.isOpened():
                print(f"❌ Failed to open video file")
                return False
            
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, config.get('buffer_size', 1))
            
            # Test frame read
            ret, frame = self.cap.read()
            if ret:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # Reset to beginning
                print(f"✅ Video file opened successfully")
                return True
            else:
                print(f"❌ Video file opened but cannot read frames")
                return False
                
        except Exception as e:
            print(f"❌ Video file initialization error: {e}")
            return False

    def _initialize_generic(self, source: str) -> bool:
        """Initialize generic stream with default settings"""
        try:
            print(f"🔗 Attempting to open generic stream: {source}")
            self.cap = cv2.VideoCapture(source)
            
            if not self.cap.isOpened():
                print(f"❌ Failed to open generic stream")
                return False
            
            # Test frame read
            ret, frame = self._read_frame_with_timeout(5.0)
            if ret and frame is not None:
                print(f"✅ Generic stream opened successfully")
                return True
            else:
                print(f"❌ Generic stream opened but cannot read frames")
                return False
                
        except Exception as e:
            print(f"❌ Generic stream initialization error: {e}")
            return False

    # ========== THREADING AND QUEUE MANAGEMENT ==========
    
    def start_capture(self):
        """Start background thread for frame capture"""
        if self.running:
            print("⚠️  Capture already running")
            return
            
        if not self.is_opened:
            print("❌ Cannot start capture - stream not initialized")
            return
            
        self.running = True
        self.capture_thread = threading.Thread(target=self._capture_frames, daemon=True)
        self.capture_thread.start()
        print("🎬 Frame capture started")

    def stop_capture(self):
        """Stop background frame capture"""
        self.running = False
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2.0)
            print("🛑 Frame capture stopped")

    def _capture_frames(self):
        """Background thread for continuous frame capture"""
        reconnect_attempts = 0
        max_queue_size = self.config.get('buffer_size', 3)
        
        print("🎥 Capture thread started")
        
        while self.running:
            try:
                # Read frame from stream
                success, frame = self.read_frame()
                
                if not success or frame is None:
                    print(f"⚠️  Frame capture failed (attempt {reconnect_attempts + 1})")
                    reconnect_attempts += 1
                    
                    if reconnect_attempts >= 3:  # Quick reconnection attempts
                        print("🔄 Attempting quick reconnection...")
                        if self._attempt_reconnection():
                            reconnect_attempts = 0
                            continue
                    
                    if reconnect_attempts >= self.max_reconnect_attempts:
                        print("❌ Max reconnection attempts reached in capture thread")
                        break
                    
                    time.sleep(1.0)  # Shorter sleep for faster recovery
                    continue
                
                reconnect_attempts = 0
                
                # Store latest frame
                with self.frame_lock:
                    self.latest_frame = frame
                
                # Manage frame queue - don't block if queue is full
                if self.frame_queue.qsize() >= max_queue_size:
                    try:
                        self.frame_queue.get_nowait()  # Discard oldest frame
                    except:
                        pass
                        
                try:
                    self.frame_queue.put(frame, block=False, timeout=0.01)
                except:
                    pass  # Skip frame if queue is full
                            
            except Exception as e:
                print(f"🚨 Capture thread error: {e}")
                time.sleep(1.0)

    def get_frame(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        """
        Get frame from queue with timeout.
        
        Args:
            timeout: Timeout in seconds
            
        Returns:
            Frame or None if no frame available
        """
        try:
            return self.frame_queue.get(block=True, timeout=timeout)
        except:
            return None

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Get the latest captured frame"""
        with self.frame_lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None

    def is_frame_available(self) -> bool:
        """Check if frames are available in queue"""
        return not self.frame_queue.empty()

    def clear_queue(self):
        """Clear the frame queue"""
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except:
                break

    # ========== FRAME PROCESSING METHODS ==========
    
    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read frame from stream with automatic reconnection.
        
        Returns:
            Tuple[bool, Optional[np.ndarray]]: (success, frame)
        """
        with self.lock:
            if not self.is_opened or self.cap is None:
                print("🚨 Stream not initialized in read_frame")
                return False, None
            
            try:
                ret, frame = self.cap.read()
                
                if not ret or frame is None:
                    self.error_count += 1
                    print(f"🚨 Frame read failed (error #{self.error_count})")
                    
                    # Attempt reconnection if needed
                    if self._should_reconnect():
                        self._attempt_reconnection()
                    return False, None
                
                # Validate frame
                if (frame.size == 0 or frame.shape[0] < 10 or frame.shape[1] < 10 or
                    np.mean(frame) < 10 or np.mean(frame) > 250):
                    self.error_count += 1
                    print(f"🚨 Invalid frame detected (error #{self.error_count})")
                    return False, None
                
                # Successful frame
                self.frame_count += 1
                self.error_count = 0
                self.last_successful_frame_time = time.time()
                
                # Update FPS calculation
                self._update_performance_metrics()
                
                return True, frame
                
            except Exception as e:
                print(f"🚨 Exception reading frame: {e}")
                self.error_count += 1
                
                if self._should_reconnect():
                    self._attempt_reconnection()
                return False, None

    # ========== RECONNECTION AND HEALTH MANAGEMENT ==========
    
    def _should_reconnect(self) -> bool:
        """Determine if reconnection should be attempted"""
        if self.stream_type == 'video_file':
            return False  # Don't reconnect for video files
            
        time_since_last_frame = time.time() - self.last_successful_frame_time
        needs_reconnect = (self.error_count >= 3 or 
                          time_since_last_frame > self.max_frame_gap)
        
        # Rate limiting for reconnections
        time_since_last_reconnect = time.time() - self.last_reconnect_time
        if needs_reconnect and time_since_last_reconnect < self.reconnect_delay:
            return False
            
        return needs_reconnect and self.reconnect_attempts < self.max_reconnect_attempts

    def _attempt_reconnection(self) -> bool:
        """Attempt to reconnect to the stream"""
        print(f"🔄 Attempting reconnection ({self.reconnect_attempts + 1}/{self.max_reconnect_attempts})")
        
        self.last_reconnect_time = time.time()
        self.reconnect_attempts += 1
        
        # Release existing stream
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        
        # Wait before reconnection
        time.sleep(self.reconnect_delay)
        
        # Reinitialize
        success = self.initialize_stream(self.source)
        
        if success:
            print("✅ Reconnection successful!")
            self.reconnect_attempts = 0
            return True
        else:
            print(f"❌ Reconnection attempt {self.reconnect_attempts} failed")
            return False

    def _start_health_monitor(self):
        """Start background health monitoring thread"""
        if self.health_monitor_thread is None or not self.health_monitor_thread.is_alive():
            self.health_monitor_thread = threading.Thread(target=self._health_monitor_loop, daemon=True)
            self.health_monitor_thread.start()
            print("❤️  Stream health monitor started")

    def _health_monitor_loop(self):
        """Background health monitoring loop"""
        while self.running:
            try:
                time.sleep(self.health_check_interval)
                self._check_stream_health()
            except Exception as e:
                print(f"🚨 Health monitor error: {e}")

    def _check_stream_health(self):
        """Check stream health and trigger reconnection if needed"""
        if not self.is_opened:
            return
            
        time_since_last_frame = time.time() - self.last_successful_frame_time
        
        if time_since_last_frame > self.max_frame_gap:
            print(f"⚠️  Stream health check: No frames for {time_since_last_frame:.1f}s")
            if self._should_reconnect():
                print("🔄 Health monitor triggering reconnection...")
                self._attempt_reconnection()

    # ========== UTILITY METHODS ==========
    
    def _optimize_rtsp_url(self, url: str) -> str:
        """Add optimization parameters to RTSP URL"""
        if '?' in url:
            return f"{url}&tcp=True&buffer_size=65535&rtsp_transport=tcp"
        else:
            return f"{url}?tcp=True&buffer_size=65535&rtsp_transport=tcp"

    def _read_frame_with_timeout(self, timeout: float = 5.0) -> Tuple[bool, Optional[np.ndarray]]:
        """Read frame with timeout protection"""
        result = [None, None]
        
        def read_frame():
            try:
                result[0], result[1] = self.cap.read()
            except Exception as e:
                result[0] = False
                print(f"🚨 Frame read exception: {e}")
        
        thread = threading.Thread(target=read_frame)
        thread.daemon = True
        thread.start()
        thread.join(timeout)
        
        if thread.is_alive():
            print(f"⏰ Frame read timeout after {timeout}s")
            return False, None
        
        return result[0], result[1]

    def _update_performance_metrics(self):
        """Update performance metrics like FPS"""
        current_time = time.time()
        elapsed = current_time - self.start_time
        
        if elapsed > 1.0:  # Update FPS every second
            self.fps = self.frame_count / elapsed
            self.frame_count = 0
            self.start_time = current_time

    def _log_stream_info(self):
        """Log stream information"""
        if self.cap is None:
            return
            
        try:
            width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = self.cap.get(cv2.CAP_PROP_FPS)
            
            print(f"📊 Stream Info:")
            print(f"   Type: {self.stream_type}")
            print(f"   Resolution: {width}x{height}")
            print(f"   FPS: {fps:.1f}")
            print(f"   Source: {self.source}")
            
        except Exception as e:
            print(f"⚠️  Could not get stream info: {e}")

    # ========== PUBLIC INTERFACE ==========
    
    def get_stream_info(self) -> Dict[str, Any]:
        """Get comprehensive stream information"""
        info = {
            'stream_type': self.stream_type,
            'source': self.source,
            'is_opened': self.is_opened,
            'queue_size': self.frame_queue.qsize(),
            'health_metrics': {
                'frame_count': self.frame_count,
                'error_count': self.error_count,
                'reconnections': self.reconnect_attempts,
                'last_successful_frame': self.last_successful_frame_time
            },
            'performance': {
                'fps': self.fps,
                'avg_frame_time': self.avg_frame_time
            },
            'last_error': self.last_error_message
        }
        
        if self.cap is not None and self.is_opened:
            try:
                info.update({
                    'resolution': {
                        'width': int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                        'height': int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    },
                    'fps': self.cap.get(cv2.CAP_PROP_FPS),
                    'backend': self.cap.getBackendName()
                })
            except:
                pass
        
        return info

    def is_healthy(self) -> bool:
        """Check if stream is healthy"""
        if not self.is_opened:
            return False
            
        time_since_last_frame = time.time() - self.last_successful_frame_time
        is_healthy = (time_since_last_frame < self.max_frame_gap and 
                     self.error_count < 5)
        
        return is_healthy

    def get_success_rate(self) -> float:
        """Calculate stream success rate"""
        total_operations = self.frame_count + self.error_count
        if total_operations == 0:
            return 0.0
        return self.frame_count / total_operations

    def get_debug_info(self) -> Dict[str, Any]:
        """Get detailed debug information"""
        return {
            'initialization_attempted': self.initialization_attempted,
            'is_opened': self.is_opened,
            'stream_type': self.stream_type,
            'source': self.source,
            'running': self.running,
            'queue_size': self.frame_queue.qsize(),
            'frames_processed': self.frame_count,
            'errors': self.error_count,
            'reconnection_attempts': self.reconnect_attempts,
            'last_successful_frame': self.last_successful_frame_time,
            'time_since_last_frame': time.time() - self.last_successful_frame_time,
            'last_error': self.last_error_message,
            'capture_thread_alive': self.capture_thread.is_alive() if self.capture_thread else False,
            'health_monitor_alive': self.health_monitor_thread.is_alive() if self.health_monitor_thread else False
        }

    def release(self):
        """Release stream resources"""
        print("🔴 Releasing StreamManager...")
        self.running = False
        
        # Stop capture thread
        self.stop_capture()
        
        # Stop health monitor
        if self.health_monitor_thread and self.health_monitor_thread.is_alive():
            self.health_monitor_thread.join(timeout=2.0)
        
        # Release capture
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        
        # Clear queue
        self.clear_queue()
        
        self.is_opened = False
        print("🔴 StreamManager released")

    def __del__(self):
        """Destructor to ensure proper cleanup"""
        self.release()
        
        