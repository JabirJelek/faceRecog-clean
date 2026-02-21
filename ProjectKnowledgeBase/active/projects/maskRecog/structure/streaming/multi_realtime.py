# streaming/multi_realtime.py

from typing import Dict, List, Optional, Union, Any, Tuple
from queue import Queue
import threading
import numpy as np
import cv2 
import time
import datetime
import csv
import re
from urllib.parse import urlparse
from threading import Lock, RLock, Event
import traceback
import gc
import os
import sys
import json
import zipfile
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import logging

from ..streaming.stream_manager import StreamManager
from ..streaming.base_processor import BaseProcessor
from ..visualization.display_resizer import DisplayResizer
from ..streaming.performance_manager import PerformanceManager
from ..streaming.frame_utils import FrameUtils
from ..streaming.control_handler import ControlHandler
from ..tracking.tracking_manager import TrackingManager
from ..alerting.alert_manager import DurationAwareAlertManager
from ..logging.image_logger import ImageLogger


logger = logging.getLogger(__name__)

class MultiSourceRealTimeProcessor(BaseProcessor):
    def __init__(self, face_system, config: Dict):
        super().__init__(face_system, config)
        
        # ==========   OUTPUT DIRECTORY CONFIGURATION ==========
        self.data_logger = None          # will be created if logging enabled
        output_cfg = config.get('output', {})
        self.output_root = output_cfg.get('root_dir', )
        self.create_timestamped_subdir = output_cfg.get('create_timestamped_subdir', True)
        self.enable_exit_status = output_cfg.get('enable_exit_status', True)
        self.run_dir = None          # will be set by _create_run_directory()
        self.image_log_dir = None
        self.csv_log_dir = None
        
        # ==========   HEADLESS CONFIGURATION ==========
        self.headless = config.get('headless', False)
        
        # Use Event for thread-safe shutdown signaling
        self._shutdown_event = Event()
        self.running = False
        
        # Shutdown variable
        self.shutdown_at = config.get('shutdown_at')
        self.shutdown_target_time = None   # will store datetime object
        self.shutdown_remaining = None      # initial seconds until shutdown        
        
        # Multi-source management with thread safety
        self.stream_managers: Dict[str, StreamManager] = {}
        self.active_sources: List[str] = []
        self.source_configs: Dict[str, Dict] = {}
        
        # Thread-safe data structures
        self.tracking_managers: Dict[str, TrackingManager] = {}
        self.image_loggers: Dict[str, ImageLogger] = {}
        self.frame_queues: Dict[str, Queue] = {}
        
        # Use RLock for complex operations
        self._stream_lock = RLock()
        self._tracking_lock = RLock()
        self._logging_lock = RLock()
        
        # Display management - MAKE CONFIGURABLE
        self.display_layout = config.get('display_layout', 'grid')
        self.max_display_sources = config.get('max_display_sources', 4)
        
        # Initialize modular components
        self.performance_manager = PerformanceManager(self.config)
        self.frame_utils = FrameUtils()
        self.control_handler = ControlHandler(self)
        self.resizer = DisplayResizer()
        
        # Debug controls
        self.debug_mode = False
        self.show_detection_debug = False
        self.show_performance_stats = False
        
        # Stream health monitoring
        self.consecutive_good_frames = 0
        
        # Enhanced control attributes
        self.face_tracking_enabled = False
        self.current_preset_index = 0
        
        # Voice alert system
        self.alert_manager = DurationAwareAlertManager(self.config)
        self.sent_alerts = set()
        
        # Violation verification - ALREADY CONFIGURABLE
        self.violation_verification_enabled = config.get('violation_verification_enabled', False)
        self.min_violation_duration = config.get('min_violation_duration', 0.0)
        self.min_violation_frames = config.get('min_violation_frames', 0)
        self.violation_confidence_threshold = config.get('violation_confidence_threshold', 0.0)
        
        # Violation statistics
        self.violation_stats = {
            'total_detected': 0,
            'total_verified': 0,
            'total_logged': 0,
            'verified_logged': 0,
            'unverified_logged': 0,
            'false_positives_prevented': 0,
            'last_verified_time': None
        }
            
        # Performance tracking - MAKE CONFIGURABLE
        self.processing_width = config.get('processing_width', 0)
        self.processing_height = config.get('processing_height', 0)
        self.processing_scale = config.get('processing_scale', 1.0)
        self.last_fps_time = time.time()
        self.fps_frame_count = 0
        
        # Thread management with proper shutdown control
        self.health_monitor_thread = None
        self.maintenance_thread = None
        self._thread_stop_events = {}
        
        # Cleanup tracking
        self._cleanup_completed = False
        
        # Logging and session management
        self.current_log_session = None
        self.log_interval = config.get('log_interval', 1)
        
        # Frame and performance tracking
        self.frame_count = 0
        self.fps = 0
        self.original_frame_size = None
        
        # Locks and synchronization
        self.sync_lock = Lock()
        self.log_lock = Lock()
        
        # Display settings
        self.show_resize_info = False
        self.show_source_health = False
        
        # ==========   EMAIL CONFIGURATION ==========
        email_cfg = config.get('email', {})
        
        # Handle both dict (legacy) and list (new) formats
        if isinstance(email_cfg, list):
            # List of recipient dicts
            self.email_recipients = email_cfg
            self.email_enabled = any(recip.get('enabled', False) for recip in self.email_recipients)
            # Set legacy single-recipient attributes to defaults (not used, but avoid AttributeError)
            self.email_recipient = ''
            self.smtp_server = 'smtp.gmail.com'
            self.smtp_port = 587
            self.smtp_user = ''
            self.smtp_password = ''
            self.email_use_tls = True
            self.email_send_on_exit = True
            self.email_max_attachment_mb = 25
        else:
            # Legacy dict format – convert to list internally
            self.email_enabled = email_cfg.get('enabled', False)
            self.email_recipient = email_cfg.get('recipient', '')
            self.smtp_server = email_cfg.get('smtp_server', 'smtp.gmail.com')
            self.smtp_port = email_cfg.get('smtp_port', 587)
            self.smtp_user = email_cfg.get('smtp_user', '')
            self.smtp_password = email_cfg.get('smtp_password', '')
            self.email_use_tls = email_cfg.get('use_tls', True)
            self.email_send_on_exit = email_cfg.get('send_on_exit', True)
            self.email_max_attachment_mb = email_cfg.get('max_attachment_size_mb', 25)
            
            # Build a list with one recipient if enabled
            if self.email_enabled and self.email_recipient:
                self.email_recipients = [{
                    'enabled': self.email_enabled,
                    'recipient': self.email_recipient,
                    'smtp_server': self.smtp_server,
                    'smtp_port': self.smtp_port,
                    'smtp_user': self.smtp_user,
                    'smtp_password': self.smtp_password,
                    'use_tls': self.email_use_tls,
                    'attach_zip': True,      # default for legacy
                    'language': 'en'          # default for legacy
                }]
            else:
                self.email_recipients = []
        
        # Override enabled flag based on actual recipients (ensures consistency)
        self.email_enabled = len(self.email_recipients) > 0  
            
        # Other configurations    
        self.image_logging_enabled = config.get('enable_image_logging', False)
        self.logging_enabled = config.get('enable_logging', False)
        
        # ADD NEW CONFIGURABLE PARAMETERS
        self.stream_recovery_wait_time = config.get('stream_recovery_wait_time', 2.0)
        self.health_check_interval = config.get('health_check_interval', 30.0)
        self.health_success_rate_threshold = config.get('health_success_rate_threshold', 0.3)
        self.maintenance_interval = config.get('maintenance_interval', 300.0)
        
        # Resource monitoring thresholds
        resource_config = config.get('resource_monitoring', {})
        self.memory_threshold_mb = resource_config.get('memory_threshold_mb', 1024)
        
        logger.info("🎯 MultiSourceRealTimeProcessor initialized with enhanced thread safety")
                               
                                
                                   

    # ========== NEW: RUN DIRECTORY MANAGEMENT ==========
    
    def _create_run_directory(self):
        """Create a timestamped directory for this run."""
        timestamp = datetime.datetime.now().strftime("Process-Python_%Y-%m-%d_%H-%M-%S")
        if self.create_timestamped_subdir:
            self.run_dir = os.path.join(self.output_root, timestamp)
        else:
            self.run_dir = self.output_root
        os.makedirs(self.run_dir, exist_ok=True)
        
        # Create subdirectories for different log types
        self.image_log_dir = os.path.join(self.run_dir, 'images')
        self.csv_log_dir = os.path.join(self.run_dir, 'csv_logs')
        os.makedirs(self.image_log_dir, exist_ok=True)
        os.makedirs(self.csv_log_dir, exist_ok=True)
        
        # Store in config for other components to use
        self.config['run_dir'] = self.run_dir
        self.config['image_log_dir'] = self.image_log_dir
        self.config['csv_log_dir'] = self.csv_log_dir
        
        logger.info(f"📁 Run directory created: {self.run_dir}")
    
    # def _setup_file_logging(self):
    #     """Redirect stdout/stderr to a log file inside run_dir."""
    #     log_file = os.path.join(self.run_dir, 'console.log')
    #     self.log_file_handle = open(log_file, 'w', encoding='utf-8')
    #     # Save original streams to restore later if needed
    #     self._original_stdout = sys.stdout
    #     self._original_stderr = sys.stderr
    #     sys.stdout = self.log_file_handle
    #     sys.stderr = self.log_file_handle
    #     logger.info(f"📄 Console output redirected to {log_file}")
    
    # def _restore_file_logging(self):
    #     """Restore original stdout/stderr and close log file."""
    #     if hasattr(self, 'log_file_handle') and self.log_file_handle:
    #         sys.stdout = self._original_stdout
    #         sys.stderr = self._original_stderr
    #         self.log_file_handle.close()
    #         logger.info("📄 Console logging restored")
    
    # ========== NEW: EXIT STATUS ==========
    
    def write_exit_status(self, exit_code=0, exit_message="Normal shutdown"):
        """Write exit status and final statistics to exit_status.json."""
        if not self.enable_exit_status or not self.run_dir:
            return
        
        status = {
            'exit_code': exit_code,
            'exit_message': exit_message,
            'timestamp': datetime.datetime.now().isoformat(),
            'run_directory': self.run_dir,
            'statistics': {
                'total_frames': self.frame_count,
                'average_fps': self.fps,
                'active_sources': len(self.active_sources),
                'violations_detected': self.violation_stats.get('total_detected', 0),
                'violations_verified': self.violation_stats.get('total_verified', 0),
                'images_saved': sum(
                    logger.get_logging_status()['saved_image_count']
                    for logger in self.image_loggers.values()
                ),
                'server_pushes': sum(
                    logger.get_logging_status()['stats']['server_pushes']
                    for logger in self.image_loggers.values()
                ),
            }
        }
        status_file = os.path.join(self.run_dir, 'exit_status.json')
        with open(status_file, 'w') as f:
            json.dump(status, f, indent=2)
        logger.info(f"📝 Exit status written to {status_file}")
    
    # ========== NEW: EMAIL HANDLING ==========
    
    def _zip_run_directory(self) -> Optional[str]:
        """Create a ZIP archive of the entire run directory."""
        if not self.run_dir or not os.path.exists(self.run_dir):
            return None
        zip_name = f"{os.path.basename(self.run_dir)}.zip"
        zip_path = os.path.join(os.path.dirname(self.run_dir), zip_name)
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(self.run_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, os.path.dirname(self.run_dir))
                        zipf.write(file_path, arcname)
            logger.info(f"🗜️ Run directory zipped: {zip_path}")
            return zip_path
        except Exception as e:
            logger.warning(f"❌ Failed to zip run directory: {e}")
            return None
    
    def _load_password(self, password_setting: str) -> str:
        """
        Resolve a password setting to an actual password.
        Supports:
        - Plain text
        - env:VAR_NAME  -> read from environment variable
        - /path/to/file  -> read first line of file
        """
        if not password_setting:
            return ""
        
        # Environment variable
        if password_setting.startswith("env:"):
            env_var = password_setting[4:]
            pwd = os.environ.get(env_var, "")
            if not pwd:
                logger.warning(f"⚠️ Environment variable {env_var} not set or empty")
            return pwd
        
        # File path (crude detection: contains path separator or ends with .txt/.xml)
        if ('/' in password_setting or '\\' in password_setting or 
            password_setting.endswith(('.txt', '.xml', '.pwd'))):
            if os.path.exists(password_setting):
                try:
                    with open(password_setting, 'r') as f:
                        pwd = f.readline().strip()
                    return pwd
                except Exception as e:
                    logger.warning(f"⚠️ Could not read password from {password_setting}: {e}")
                    return ""
            else:
                logger.warning(f"⚠️ Password file {password_setting} does not exist")
                return ""
        
        # Assume plain text password
        return password_setting

    def _generate_email_body(self, run_summaries: List[Dict], config: Dict,
                            schedule_start: str = None, schedule_end: str = None,
                            language: str = 'en') -> str:
        """
        Generate an HTML email body from a list of run summaries.
        
        Args:
            run_summaries: List of dicts, each containing:
                - CollectionType: 'SUMMARY_METADATA', 'METADATA_ONLY', or other
                - Status: 'SUCCESS', 'FAILED', or other
                - FolderName: name of the run folder
                - CreationTime: datetime object
                - ExitCode: int
                - Metadata: dict with optional keys worker_pid, python_pid, start_time, end_time
            config: Configuration dict (not used directly, kept for consistency)
            schedule_start: Optional start of schedule window
            schedule_end: Optional end of schedule window
            language: 'en' or 'id' (default 'en')
        
        Returns:
            HTML string ready for email body.
        """
        # Translations (embedded for clarity; could be a class constant)
        translations = {
            'en': {
                'ReportTitle': "=== Face Recognition Run Report ===",
                'SummaryTitle': "=== Summary ===",
                'DetailsTitle': "=== Run Details ===",
                'TotalRuns': "Total Runs:",
                'WithSummary': "With Completion Summary:",
                'MetadataOnly': "Metadata Only:",
                'NoData': "Incomplete Data:",
                'Successful': "Successful:",
                'Failed': "Prematurely-Success:",
                'UnknownStatus': "Unknown Status:",
                'ScheduleWindow': "Schedule Window:",
                'ReportTime': "Report Time:",
                'Created': "Created:",
                'ExitCode': "Exit Code:",
                'WorkerPID': "Worker PID:",
                'PythonPID': "Python PID:",
                'StartTime': "Start Time:",
                'EndTime': "End Time:",
                'Footer': "This report was automatically generated by the Face Recognition Monitoring System.",
                'System': "System: maskRecog | Version:",
                'StatusSuccess': "SUCCESS",
                'StatusFailed': "FAILED",
                'StatusUnknown': "UNKNOWN",
                'CollectionFull': "Full Data",
                'CollectionMetadata': "Metadata Only"
            },
            'id': {
                'ReportTitle': "=== Laporan Pengenalan Wajah ===",
                'SummaryTitle': "=== Ringkasan ===",
                'DetailsTitle': "=== Detail Proses ===",
                'TotalRuns': "Total Proses:",
                'WithSummary': "Dengan Ringkasan Lengkap:",
                'MetadataOnly': "Hanya Metadata:",
                'NoData': "Data Tidak Lengkap:",
                'Successful': "Berhasil:",
                'Failed': "Berhasil-Prematur:",
                'UnknownStatus': "Status Tidak Diketahui:",
                'ScheduleWindow': "Jadwal:",
                'ReportTime': "Waktu Laporan:",
                'Created': "Folder berhasil dibuat pada:",
                'ExitCode': "Kode Keluar:",
                'WorkerPID': "PID Worker:",
                'PythonPID': "PID Python:",
                'StartTime': "Waktu Proses dimulai:",
                'EndTime': "Waktu Selesai:",
                'Footer': "Laporan ini dibuat secara otomatis oleh Sistem Pemantauan Pengenalan Wajah.",
                'System': "Sistem: maskRecog | Versi:",
                'StatusSuccess': "BERHASIL",
                'StatusFailed': "Berhasil-Prematur",
                'StatusUnknown': "TIDAK DIKETAHUI",
                'CollectionFull': "Data Lengkap",
                'CollectionMetadata': "Hanya Metadata"
            }
        }
        t = translations.get(language, translations['en'])
        
        run_count = len(run_summaries)
        summary_count = sum(1 for r in run_summaries if r.get('CollectionType') == 'SUMMARY_METADATA')
        metadata_only_count = sum(1 for r in run_summaries if r.get('CollectionType') == 'METADATA_ONLY')
        no_data_count = run_count - summary_count - metadata_only_count
        
        success_count = sum(1 for r in run_summaries if r.get('Status') == 'SUCCESS')
        failed_count = sum(1 for r in run_summaries if r.get('Status') == 'FAILED')
        unknown_count = run_count - success_count - failed_count
        
        # Start building HTML
        html = f"""<!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
            h2 {{ color: #34495e; margin-top: 25px; }}
            .summary-box {{ background: #ecf0f1; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            .run-card {{ 
                background: #f8f9fa; 
                padding: 15px; 
                margin: 10px 0; 
                border-left: 4px solid #0078d4;
                border-radius: 3px;
            }}
            .run-success {{ border-left-color: #27ae60; }}
            .run-failed {{ border-left-color: #e74c3c; }}
            .run-unknown {{ border-left-color: #95a5a6; }}
            .run-metadata-only {{ border-left-color: #f39c12; }}
            .status-badge {{ 
                display: inline-block; 
                padding: 3px 8px; 
                border-radius: 12px; 
                font-size: 12px; 
                font-weight: bold;
                margin-right: 10px;
            }}
            .status-success {{ background: #d4edda; color: #155724; }}
            .status-failed {{ background: #f8d7da; color: #721c24; }}
            .status-unknown {{ background: #d1ecf1; color: #0c5460; }}
            .collection-badge {{
                display: inline-block;
                padding: 2px 6px;
                border-radius: 10px;
                font-size: 10px;
                margin-left: 8px;
            }}
            .collection-summary {{ background: #28a745; color: white; }}
            .collection-metadata {{ background: #ffc107; color: black; }}
            .metadata {{ font-size: 12px; color: #7f8c8d; margin-top: 5px; }}
            .timestamp {{ color: #95a5a6; font-size: 11px; }}
            .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #eee; font-size: 12px; color: #7f8c8d; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1> {t['ReportTitle']} </h1>
            
            <div class="summary-box">
                <h2> {t['SummaryTitle']} </h2>
                <p><strong>{t['TotalRuns']}</strong> {run_count}</p>
                <p><strong>{t['WithSummary']}</strong> <span style="color: #28a745;">{summary_count}</span></p>
                <p><strong>{t['MetadataOnly']}</strong> <span style="color: #ffc107;">{metadata_only_count}</span></p>
                <p><strong>{t['NoData']}</strong> <span style="color: #dc3545;">{no_data_count}</span></p>
                <p><strong>{t['Successful']}</strong> <span style="color: #28a745;">{success_count}</span></p>
                <p><strong>{t['Failed']}</strong> <span style="color: #dc3545;">{failed_count}</span></p>
                <p><strong>{t['UnknownStatus']}</strong> <span style="color: #6c757d;">{unknown_count}</span></p>
    """
        if schedule_start and schedule_end:
            html += f"""
                <p><strong>{t['ScheduleWindow']}</strong> {schedule_start} to {schedule_end}</p>
    """
        html += f"""
                <p><strong>{t['ReportTime']}</strong> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <h2> {t['DetailsTitle']} </h2>
    """

        for summary in run_summaries:
            status_class = "run-unknown"
            status_badge_class = "status-unknown"
            status_text = t['StatusUnknown']
            
            if summary.get('Status') == "SUCCESS":
                status_class = "run-success"
                status_badge_class = "status-success"
                status_text = t['StatusSuccess']
            elif summary.get('Status') == "FAILED":
                status_class = "run-failed"
                status_badge_class = "status-failed"
                status_text = t['StatusFailed']
            
            if summary.get('CollectionType') == "METADATA_ONLY":
                status_class = "run-metadata-only"
            
            collection_badge = ""
            collection_text = ""
            if summary.get('CollectionType') == "SUMMARY_METADATA":
                collection_badge = "collection-summary"
                collection_text = t['CollectionFull']
            elif summary.get('CollectionType') == "METADATA_ONLY":
                collection_badge = "collection-metadata"
                collection_text = t['CollectionMetadata']
            
            folder_name = summary.get('FolderName', 'Unknown')
            creation_time = summary.get('CreationTime')
            creation_str = creation_time.strftime('%Y-%m-%d %H:%M:%S') if creation_time else 'Unknown'
            exit_code = summary.get('ExitCode', 'N/A')
            
            html += f"""
            <div class="run-card {status_class}">
                <div>
                    <span class="status-badge {status_badge_class}">{status_text}</span>
                    <strong>{folder_name}</strong>
                    {f"<span class='collection-badge {collection_badge}'>{collection_text}</span>" if collection_badge else ""}
                </div>
                <div class="timestamp">{t['Created']} {creation_str}</div>
                <div class="metadata">
                    {t['ExitCode']} {exit_code}<br>
    """
            metadata = summary.get('Metadata', {})
            if metadata.get('worker_pid'):
                html += f"{t['WorkerPID']} {metadata['worker_pid']}<br>"
            if metadata.get('python_pid'):
                html += f"{t['PythonPID']} {metadata['python_pid']}<br>"
            if metadata.get('start_time'):
                html += f"{t['StartTime']} {metadata['start_time']}<br>"
            if metadata.get('end_time'):
                html += f"{t['EndTime']} {metadata['end_time']}<br>"
            
            html += f"""
                </div>
            </div>
    """
        
        html += f"""
            
            <div class="footer">
                <p><em>{t['Footer']}</em></p>
                <p>{t['System']} {datetime.datetime.now().strftime('%Y.%m.%d')}</p>
            </div>
        </div>
    </body>
    </html>
    """
        return html
        
    def _build_run_summaries(self) -> List[Dict]:
        """
        Build a list of run summaries from the current run directory.
        Returns a list containing one summary dict (compatible with _generate_email_body).
        """
        run_summaries = []
        status_file = os.path.join(self.run_dir, 'exit_status.json')

        if not os.path.exists(status_file):
            logger.warning("⚠️ exit_status.json not found, using fallback summary.")
            # Fallback minimal summary
            fallback = {
                'CollectionType': 'METADATA_ONLY',
                'Status': 'UNKNOWN',
                'FolderName': os.path.basename(self.run_dir),
                'CreationTime': datetime.datetime.fromtimestamp(os.path.getctime(self.run_dir)),
                'ExitCode': -1,
                'Metadata': {}
            }
            return [fallback]

        try:
            with open(status_file, 'r') as f:
                exit_data = json.load(f)

            # Determine CollectionType
            collection_type = 'METADATA_ONLY'
            if self.image_log_dir and os.path.exists(self.image_log_dir):
                if any(os.scandir(self.image_log_dir)):
                    collection_type = 'SUMMARY_METADATA'
            if self.csv_log_dir and os.path.exists(self.csv_log_dir):
                if any(os.scandir(self.csv_log_dir)):
                    collection_type = 'SUMMARY_METADATA'

            # Status based on exit code (0 = success, others = failed)
            exit_code = exit_data.get('exit_code', 1)
            status = 'SUCCESS' if exit_code == 0 else 'FAILED'

            # Folder creation time
            folder_name = os.path.basename(self.run_dir)
            creation_time = datetime.datetime.fromtimestamp(os.path.getctime(self.run_dir))

            # Metadata – can be extended with more fields from exit_data if desired
            metadata = {}

            summary = {
                'CollectionType': collection_type,
                'Status': status,
                'FolderName': folder_name,
                'CreationTime': creation_time,
                'ExitCode': exit_code,
                'Metadata': metadata
            }
            run_summaries.append(summary)

        except Exception as e:
            logger.warning(f"⚠️ Failed to read exit_status.json: {e}")
            # Fallback as above
            run_summaries = [{
                'CollectionType': 'METADATA_ONLY',
                'Status': 'UNKNOWN',
                'FolderName': os.path.basename(self.run_dir),
                'CreationTime': datetime.datetime.fromtimestamp(os.path.getctime(self.run_dir)),
                'ExitCode': -1,
                'Metadata': {}
            }]

        return run_summaries    

    def _send_email(self, attachment_path: str):
        """Send emails to all enabled recipients."""
        if not self.email_recipients:
            return

        # Only send to enabled recipients
        enabled_recipients = [r for r in self.email_recipients if r.get('enabled', False)]
        if not enabled_recipients:
            return

        run_summaries = self._build_run_summaries()

        for recip in enabled_recipients:
            try:
                self._send_single_email(recip, attachment_path, run_summaries)
            except Exception as e:
                logger.warning(f"❌ Failed to send email to {recip['recipient']}: {e}")
                                        
    def _send_email_async(self, attachment_path: str):
        """Send email in a non‑blocking thread."""
        def worker():
            self._send_email(attachment_path)
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        logger.info("📧 Email thread started")

    def _send_single_email(self, recip: dict, attachment_path: str, run_summaries: list):
        """Send a single email using the recipient's settings, falling back to first recipient's SMTP if needed."""
        # Get SMTP settings with fallback to first recipient's values
        if self.email_recipients:
            first = self.email_recipients[0]
            smtp_server = recip.get('smtp_server') or first.get('smtp_server')
            smtp_port = recip.get('smtp_port') or first.get('smtp_port')
            smtp_user = recip.get('smtp_user') or first.get('smtp_user')
            smtp_password = recip.get('smtp_password') or first.get('smtp_password')
            use_tls = recip.get('use_tls') if 'use_tls' in recip else first.get('use_tls', True)
        else:
            # Should not happen because we only call with enabled recipients
            logger.warning("⚠️ No email recipients configured, skipping.")
            return

        # Resolve password (file/env support)
        password = self._load_password(smtp_password)
        if not password:
            logger.warning(f"⚠️ No password for {recip['recipient']}, skipping.")
            return

        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = recip['recipient']
        msg['Subject'] = f"Face Recognition Run - {os.path.basename(self.run_dir)}"

        html_body = self._generate_email_body(
            run_summaries, self.config,
            language=recip.get('language', 'en')
        )
        from email.mime.text import MIMEText
        msg.attach(MIMEText(html_body, 'html'))

        if recip.get('attach_zip', False) and attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, 'rb') as f:
                part = MIMEBase('application', 'zip')
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(attachment_path)}"')
                msg.attach(part)

        server = smtplib.SMTP(smtp_server, smtp_port)
        if use_tls:
            server.starttls()
        server.login(smtp_user, password)
        server.send_message(msg)
        server.quit()
        logger.info(f"📧 Email sent to {recip['recipient']} (lang={recip.get('language','en')}, attach={recip.get('attach_zip', False)})")
                                  
    # ========== THREAD SAFE SHUTDOWN ==========
    
    def close(self):
        """Public method for explicit cleanup"""
        if self._cleanup_completed:
            return
            
        logger.info("🧹 Starting comprehensive resource cleanup...")
        
        # 1. Signal shutdown to all threads
        self.running = False
        self._shutdown_event.set()
        
        # 2. Stop all threads with timeout
        self._stop_all_threads_safe()
        
        # 3. Close all resources in proper order
        with self._stream_lock:
            self._close_all_streams()
            
        with self._tracking_lock:
            self._close_all_trackers()
            
        with self._logging_lock:
            self._close_all_loggers()
        
        # 4. Clear all data structures
        self._clear_all_queues()
        
        # 5. Release OpenCV resources
        try:
            cv2.destroyAllWindows()
            cv2.waitKey(1)
        except:
            pass
        
        # 6. Force garbage collection
        self._force_garbage_collection()
        
        self._cleanup_completed = True
        logger.info("✅ Resource cleanup completed")
                
    def _stop_all_threads_safe(self):
        """Stop all background threads safely - FIXED VERSION"""
        threads_to_stop = [
            ('health_monitor_thread', 5.0),
            ('maintenance_thread', 5.0),
        ]
        
        for thread_name, timeout in threads_to_stop:
            thread = getattr(self, thread_name, None)
            if thread and thread.is_alive():
                logger.info(f"⏳ Stopping {thread_name}...")
                thread.join(timeout=timeout)
                if thread.is_alive():
                    logger.warning(f"⚠️ {thread_name} did not stop gracefully")
                    # Remove the incorrect _stop.set() call
                    # Threads should exit when self.running = False
   
    def _close_all_streams(self):
        """Close all stream managers safely"""
        source_ids = list(self.stream_managers.keys())
        
        for source_id in source_ids:
            try:
                stream_manager = self.stream_managers.get(source_id)
                if stream_manager:
                    # Call stop_capture first to stop any running threads
                    if hasattr(stream_manager, 'stop_capture'):
                        stream_manager.stop_capture()
                    
                    # Wait briefly for threads to stop
                    time.sleep(0.1)
                    
                    # Release video capture
                    if hasattr(stream_manager, 'release'):
                        stream_manager.release()
                    
                    # Clear buffer
                    if hasattr(stream_manager, 'clear_buffer'):
                        stream_manager.clear_buffer()
                        
                # Remove from dictionary
                self.stream_managers.pop(source_id, None)
                logger.info(f"✅ Closed stream for {source_id}")
                
            except Exception as e:
                logger.warning(f"⚠️ Error closing stream {source_id}: {e}")
    
    def _close_all_trackers(self):
        """Close all tracking managers safely"""
        for source_id, tracker in list(self.tracking_managers.items()):
            try:
                if hasattr(tracker, 'cleanup'):
                    tracker.cleanup()
                elif hasattr(tracker, 'release'):
                    tracker.release()
                    
                # Clear violation tracker
                if hasattr(tracker, 'violation_tracker'):
                    tracker.violation_tracker.clear()
                    
                self.tracking_managers.pop(source_id, None)
                logger.info(f"✅ Cleaned up tracker for {source_id}")
                
            except Exception as e:
                logger.warning(f"⚠️ Error cleaning up tracker {source_id}: {e}")
    
    def _close_all_loggers(self):
        """Close all image loggers safely"""
        for source_id, img_logger in list(self.image_loggers.items()):
            try:
                # Close logger if it has close method
                if hasattr(img_logger, 'close'):
                    logger.close()
                    
                # Explicitly close CSV file if open
                if hasattr(logger, 'csv_file') and logger.csv_file:
                    try:
                        logger.csv_file.close()
                    except:
                        pass
                
                self.image_loggers.pop(source_id, None)
                logger.info(f"✅ Cleaned up logger for {source_id}")
                
            except Exception as e:
                logger.warning(f"⚠️ Error cleaning up logger {source_id}: {e}")
    
    def _clear_all_queues(self):
        """Clear all queues and data structures"""
        # Clear frame queues
        for queue_id, queue in list(self.frame_queues.items()):
            try:
                while not queue.empty():
                    try:
                        queue.get_nowait()
                    except:
                        break
                self.frame_queues.pop(queue_id, None)
            except:
                pass
        
        # Clear other collections
        self.active_sources.clear()
        self.source_configs.clear()
        self.sent_alerts.clear()
        
        # Clear caches
        if hasattr(self, '_cctv_name_cache'):
            self._cctv_name_cache.clear()
    
    def _force_garbage_collection(self):
        """Force garbage collection safely"""
        try:
            import psutil
            import os
            
            # Collect garbage
            collected = gc.collect()
            
            # Get memory usage safely
            try:
                process = psutil.Process(os.getpid())
                memory_info = process.memory_info()
                memory_mb = memory_info.rss / (1024 * 1024)
                logger.info(f"🧠 Garbage collection: {collected} objects collected")
                logger.info(f"📊 Memory usage: {memory_mb:.2f} MB")
            except:
                logger.info(f"🧠 Garbage collection: {collected} objects collected")
                
        except ImportError:
            gc.collect()
            logger.info("🧠 Garbage collection completed")   
                               
    def __enter__(self):
        """Support context manager protocol"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Automatic cleanup when used with 'with' statement"""
        self.close()
        return False  # Don't suppress exceptions
    
    def __del__(self):
        """Fallback cleanup in destructor"""
        try:
            if not self._cleanup_completed:
                self.close()
        except:
            pass  # Ignore errors during destruction            
            
    def monitor_resource_usage(self):
        """Periodic resource usage monitoring -  """
        import psutil
        import os
        
        try:
            process = psutil.Process(os.getpid())
            
            # Memory usage -   CALCULATION
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024  #  : 1024*1024
            
            # Open files
            open_files = len(process.open_files())
            
            # Thread count
            thread_count = process.num_threads()
            
            logger.info(f"📊 Resource Monitor:")
            logger.info(f"   Memory: {memory_mb:.2f} MB")
            logger.info(f"   Open files: {open_files}")
            logger.info(f"   Threads: {thread_count}")
            logger.info(f"   Active sources: {len(self.active_sources)}")
            logger.info(f"   Stream managers: {len(self.stream_managers)}")
            logger.info(f"   Image loggers: {len(self.image_loggers)}")
            
            # Check for resource leaks -   THRESHOLD
            if memory_mb > self.memory_threshold_mb:  #  : 1GB threshold
                logger.warning("⚠️  High memory usage detected!")
                self.optimize_memory_usage()
                
        except ImportError:
            logger.info("📊 Resource monitoring requires psutil")
        except Exception as e:
            logger.warning(f"⚠️ Resource monitoring error: {e}")
                        
    def print_info_final_statistics(self):
        """logger.info final processing statistics"""
        logger.info("\n" + "="*60)
        logger.info("📊 FINAL PROCESSING STATISTICS")
        logger.info("="*60)
        
        # Performance stats
        logger.info(f"\n🎯 Performance:")
        logger.info(f"   Total frames processed: {self.frame_count}")
        logger.info(f"   Average FPS: {self.fps:.2f}")
        
        # Source stats
        logger.info(f"\n📹 Sources:")
        logger.info(f"   Total sources configured: {len(self.source_configs)}")
        logger.info(f"   Active sources: {len(self.active_sources)}")
        
        # Violation stats
        if self.violation_verification_enabled:
            logger.info(f"\n✅ Violation Verification:")
            logger.info(f"   Total detected: {self.violation_stats.get('total_detected', 0)}")
            logger.info(f"   Total verified: {self.violation_stats.get('total_verified', 0)}")
            logger.info(f"   Total logged: {self.violation_stats.get('total_logged', 0)}")
            logger.info(f"   False positives prevented: {self.violation_stats.get('false_positives_prevented', 0)}")
        
        # Image logging stats
        if self.image_logging_enabled:
            total_images = 0
            total_server_pushes = 0
            
            for source_id, logger in self.image_loggers.items():
                status = logger.get_logging_status()
                total_images += status['saved_image_count']
                total_server_pushes += status['stats']['server_pushes']
            
            logger.info(f"\n🖼️  Image Logging:")
            logger.info(f"   Total images saved: {total_images}")
            logger.info(f"   Total server pushes: {total_server_pushes}")
        
        logger.info("="*60)            
                                                                                      
                                
                                
                                
                                
                                
    # ========== UNIFIED CONFIGURATION MANAGEMENT ==========

    def get_source_config(self, source_id: str, create_if_missing: bool = False) -> Dict[str, Any]:
        """
        Unified configuration access method.
        
        Returns the actual configuration dictionary (not a copy) for direct modification.
        Use create_if_missing=True for operations that should work with new sources.
        """
        if source_id in self.source_configs:
            return self.source_configs[source_id]
        
        if create_if_missing:
            # Create default configuration for new source
            default_config = {
                'url': f"unknown_{source_id}",
                'description': f"Source {source_id}",
                'priority': 'medium',
                'processing_scale': 1.0,
                'buffer_size': 3,
                'cctv_name': f"Camera-{source_id}"
            }
            self.source_configs[source_id] = default_config
            return default_config
        
        # Return empty dict for non-existent sources
        return {}

    def update_source_config(self, source_id: str, **kwargs) -> bool:
        """
        Unified configuration update method.
        """
        config = self.get_source_config(source_id, create_if_missing=True)
        
        # Store original URL for CCTV name detection
        original_url = config.get('url')
        
        # Update configuration
        config.update(kwargs)
        
        # Auto-update CCTV name if URL changed and no explicit name provided
        new_url = config.get('url')
        explicit_cctv_name = kwargs.get('cctv_name')
        
        if (new_url and new_url != original_url and 
            not explicit_cctv_name and 
            ('cctv_name' not in kwargs or not kwargs['cctv_name'])):
            
            new_cctv_name = self._get_dynamic_cctv_name(config, source_id)
            config['cctv_name'] = new_cctv_name
            
            # Update ImageLogger if exists
            if source_id in self.image_loggers:
                self.image_loggers[source_id].update_cctv_name(new_cctv_name)
                logger.info(f"🔄 Auto-updated CCTV name for {source_id}: {new_cctv_name}")
        
        logger.info(f"✅ Updated configuration for source: {source_id}")
        return True

    def remove_source_config(self, source_id: str):
        """
        Remove source configuration and clean up cache.
        """
        if source_id in self.source_configs:
            del self.source_configs[source_id]
        
        # Clean up cache
        if hasattr(self, '_cctv_name_cache') and source_id in self._cctv_name_cache:
            del self._cctv_name_cache[source_id]
        
        logger.info(f"🗑️ Removed configuration for source: {source_id}")
                                          
                                   
    # ========== ENHANCED: Multi-source ImageLogger Management ==========
        
    def setup_multi_source_logging(self, base_filename: str = None):
        """Setup logging for all active sources using source_configs"""
        try:
            # If logging already active, just return
            if self.image_logging_enabled and self.current_log_session:
                logger.info(f"📁 Multi-source logging already active: {self.current_log_session}")
                self.print_multi_source_logging_status()
                return True
            
            # ===== ENSURE RUN DIRECTORY EXISTS =====
            if self.run_dir is None:
                self._create_run_directory()
            
            if base_filename is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                base_filename = f"multi_source_{timestamp}"
            
            # After setting up image loggers, also setup data logger if needed
            if self.logging_enabled:
                self._setup_data_logging(base_filename)
                
            self.current_log_session = base_filename
            logger.info(f"📁 Setting up multi-source logging session: {base_filename}")
            
            # DEBUG: Check CCTV names before setup
            self.debug_cctv_names()
            
            # Ensure ALL sources have proper CCTV names BEFORE creating loggers
            for source_id in self.active_sources:
                if source_id in self.source_configs:
                    #   ENSURE: Dynamic CCTV name is set in source_configs
                    if 'cctv_name' not in self.source_configs[source_id] or not self.source_configs[source_id]['cctv_name']:
                        dynamic_name = self._get_dynamic_cctv_name(self.source_configs[source_id], source_id)
                        self.source_configs[source_id]['cctv_name'] = dynamic_name
                        logger.info(f"🔄 Set dynamic CCTV name for {source_id}: {dynamic_name}")
            
            #   SINGLE POINT: Setup logging for all active sources
            setup_count = 0
            for source_id in self.active_sources:
                if source_id in self.source_configs:
                    # Setup logging for this source
                    success = self._setup_source_logging(source_id)
                    if success:
                        setup_count += 1
                    else:
                        logger.warning(f"❌ Failed to setup logging for source: {source_id}")
                else:
                    logger.warning(f"⚠️ No configuration found for source: {source_id}")
            
            self.image_logging_enabled = True
            logger.info(f"🖼️  Multi-source image logging ENABLED for {setup_count} sources")
            
            #   DEBUG: Verify CCTV names after setup
            self.debug_cctv_names()
            
            return setup_count > 0  # Return True if at least one logger was created
            
        except Exception as e:
            logger.warning(f"❌ Error setting up multi-source logging: {e}")
            import traceback
            traceback.print_exc()
            self.image_logging_enabled = False
            return False
        
    # ========== NEW: Setup data logging ==========
    def _setup_data_logging(self, base_filename: str):
        """Initialize the data logger with the centralized CSV directory."""
        try:
            from ..logging.data_logger import DataLogger
            self.data_logger = DataLogger()
            # Use the same base filename, but inside csv_log_dir
            csv_path = os.path.join(self.csv_log_dir, base_filename)
            success = self.data_logger.setup_logging(csv_path)
            if success:
                logger.info(f"📊 Data logger initialized at: {csv_path}.csv")
            else:
                logger.warning("❌ Failed to initialize data logger")
        except Exception as e:
            logger.warning(f"❌ Error setting up data logger: {e}")
            self.data_logger = None        
                                  
    def print_cctv_mapping(self):
        """logger.info mapping of source IDs to CCTV names using source_configs - OPTIMIZED"""
        if not self.source_configs:
            logger.info("ℹ️  No CCTV mapping available - no sources configured")
            return
            
        logger.info("\n" + "="*50)
        logger.info("📹 CCTV NAME MAPPING")
        logger.info("="*50)
        for source_id, config in self.source_configs.items():
            #   FIX: Use cached name to prevent repeated extraction
            cctv_name = self._get_cached_cctv_name(source_id)
            status = "🟢" if source_id in self.active_sources else "🔴"
            logger_status = "🖼️" if source_id in self.image_loggers else "❌"
            logger.info(f"  {status} {source_id} → {cctv_name} {logger_status}")
        logger.info("="*50)
     
    def get_source_image_logger(self, source_id: str) -> Optional[ImageLogger]:
        """Get ImageLogger for specific source with fallback and automatic creation"""
        # If logger exists, return it
        if source_id in self.image_loggers:
            img_logger = self.image_loggers[source_id]
            #   VERIFY: Check if CCTV name is properly set
            if not img_logger.cctv_name or img_logger.cctv_name == 'Unknown-Camera':
                source_config = self.get_source_config(source_id)
                if source_config:
                    dynamic_cctv_name = self._get_dynamic_cctv_name(source_config, source_id)
                    img_logger.update_cctv_name(dynamic_cctv_name)
                    logger.info(f"🔄 Updated CCTV name for existing logger {source_id}: {dynamic_cctv_name}")
            return logger
        
        #   CRITICAL: If no logger exists but logging is enabled, try to create one on-demand
        if self.image_logging_enabled and source_id in self.active_sources:
            logger.info(f"🔄 Creating on-demand ImageLogger for source: {source_id}")
            success = self.force_create_image_logger(source_id)
            if success and source_id in self.image_loggers:
                return self.image_loggers[source_id]
        
        return None
       
    def debug_cctv_names(self):
        """Debug method to check CCTV name status for all sources - OPTIMIZED"""
        logger.info("\n🔍 DEBUG CCTV NAME STATUS")
        logger.info("="*50)
        
        logger.info(f"Active sources: {self.active_sources}")
        logger.info(f"Source configs: {list(self.source_configs.keys())}")
        logger.info(f"Image loggers: {list(self.image_loggers.keys())}")
        
        for source_id in self.active_sources:
            #   FIX: Use cached name to prevent repeated extraction
            cctv_name = self._get_cached_cctv_name(source_id)
            
            logger.info(f"\n📹 Source: {source_id}")
            logger.info(f"   Cached CCTV Name: {cctv_name}")
            
            if source_id in self.image_loggers:
                img_logger = self.image_loggers[source_id]
                status = img_logger.get_logging_status()
                logger.info(f"   ImageLogger CCTV: {status['cctv_name']}")
                logger.info(f"   ImageLogger Enabled: {status['enabled']}")
                logger.info(f"   Match: {'✅' if status['cctv_name'] == cctv_name else '❌'}")
            else:
                logger.info(f"   ImageLogger: ❌ NOT CREATED")
        
        logger.info("="*50)

    #   ADD: Method to force create ImageLogger for a source
    def force_create_image_logger(self, source_id: str) -> bool:
        """Force create ImageLogger for a specific source"""
        try:
            if source_id not in self.active_sources:
                logger.warning(f"❌ Source {source_id} is not active")
                return False
            
            # If no config exists, create a basic one
            if source_id not in self.source_configs:
                logger.warning(f"⚠️ No configuration found for source: {source_id}, creating default...")
                default_config = {
                    'url': f"source_{source_id}",
                    'cctv_name': f"Camera-{source_id}",
                    'description': f"Source {source_id}"
                }
                self.source_configs[source_id] = default_config
            
            # Ensure we have a logging session
            if not self.current_log_session:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                self.current_log_session = f"multi_source_{timestamp}"
                logger.info(f"🔄 Created new logging session: {self.current_log_session}")
            
            return self._setup_source_logging(source_id)
            
        except Exception as e:
            logger.warning(f"❌ Error forcing ImageLogger creation for {source_id}: {e}")
            return False        
    
    def get_multi_source_logging_status(self) -> Dict[str, Dict]:
        """Get logging status for all sources with CCTV names"""
        status_report = {}
        
        for source_id, logger in self.image_loggers.items():
            status_report[source_id] = logger.get_logging_status()
        
        return status_report
    
    def log_source_violation(self, source_id: str, frame: np.ndarray, results: List[Dict], original_frame: np.ndarray = None):
        """Log violation for specific source - UPDATED to use only verified violations"""
        if not self.image_logging_enabled:
            return False, None
        
        source_logger = self.get_source_image_logger(source_id)
        if not source_logger:
            logger.warning(f"❌ No ImageLogger available for source: {source_id}")
            return False, None
        
        try:
            #   ONLY check for verified violations using TrackingManager's flag
            verified_violations = [
                r for r in results 
                if r.get('mask_status') == 'no_mask' 
                and r.get('violation_verified', True)
            ]
            
            # Skip if no verified violations
            if not verified_violations:
                return False, None
            
            # Save annotated frame using source's ImageLogger
            success, base64_data = source_logger.save_annotated_frame(
                frame, results, original_frame  # Pass all results for annotation
            )
            
            if success:
                cctv_name = source_logger.cctv_name
                logger.info(f"✅ {cctv_name}: Verified violation logged (Total: {source_logger.saved_image_count})")
                
                #   Trigger synchronized audio alert ONLY for verified violations
                if hasattr(self, 'alert_manager'):
                    # Filter only verified violations for alerting
                    alert_violations = []
                    for result in verified_violations:
                        alert_violations.append({
                            'identity': result.get('identity', 'Unknown'),
                            'mask_confidence': result.get('mask_confidence', 0),
                            'bbox': result.get('bbox', []),
                            'violation_verified': True,
                            'violation_duration': result.get('violation_duration', 0),
                            'violation_frames': result.get('violation_frames', 0)
                        })
                    
                    if alert_violations:
                        audio_success = self.alert_manager.trigger_synchronized_alert(
                            alert_violations,
                            self.processing_count,
                            source_logger.saved_image_count,
                            source_logger.max_images_per_session
                        )
                        if audio_success:
                            logger.info(f"🔊 Audio alert triggered for {cctv_name}")
            
            return success, base64_data
            
        except Exception as e:
            logger.warning(f"❌ Error logging violation for source {source_id}: {e}")
            return False, None
                
    #   UPDATE: Remove old verification methods that are no longer needed
    def _get_verified_violations(self, results: List[Dict]) -> List[Dict]:
        """
        DEPRECATED - Use TrackingManager's violation_verified flag instead
        """
        logger.warning("⚠️  _get_verified_violations is deprecated - use violation_verified flag from TrackingManager")
        return [
            r for r in results 
            if r.get('mask_status') == 'no_mask' 
            and r.get('violation_verified', False)
        ]
            
    def print_multi_source_logging_status(self):
        """logger.info comprehensive logging status for all sources with CCTV names"""
        status_report = self.get_multi_source_logging_status()
        
        logger.info("\n" + "="*60)
        logger.info("🖼️ MULTI-SOURCE IMAGE LOGGING STATUS")
        logger.info("="*60)
        
        for source_id, status in status_report.items():
            cctv_name = status.get('cctv_name', 'Unknown')
            logger.info(f"\n📹 {cctv_name} (ID: {source_id})")
            logger.info(f"   Enabled: {status['enabled']}")
            logger.info(f"   Folder: {status['image_log_folder']}")
            logger.info(f"   Images Saved: {status['saved_image_count']}")
            logger.info(f"   Max Images: {status['max_images_per_session']}")
            logger.info(f"   Server Push: {status['server_config']['enabled']}")
            if status['server_config']['enabled']:
                logger.info(f"   Server Pushes: {status['stats']['server_pushes']}")
                logger.info(f"   Server Errors: {status['stats']['server_errors']}")
        
        logger.info("="*60)
        
    # ========== ENHANCED: Configuration Methods ==========

    def safe_remove_source(self, source_id: str):
        """Thread-safe source removal"""
        with self.sync_lock:
            self.remove_source(source_id)    
                
    def robust_process_multi_source_frame(self, source_id: str, frame: np.ndarray) -> List[Dict]:
        """Robust frame processing with comprehensive error handling"""
        if frame is None:
            return []
        
        try:
            source_config = self.get_source_config(source_id)
            
            # Validate frame
            if not self._validate_frame(frame):
                logger.warning(f"⚠️ Invalid frame from {source_id}")
                return []
            
            # Resize for processing with error handling
            try:
                processing_frame = self.enhanced_resize_for_processing(frame)
            except Exception as e:
                logger.warning(f"⚠️ Frame resize error for {source_id}: {e}")
                processing_frame = cv2.resize(frame, (640, 480))
            
            # Process through face system with timeout protection
            try:
                raw_results = self.face_system.process_frame(processing_frame)
                
                logger.debug(f"🔍 [1-FACE-SYSTEM] {len(raw_results)} raw detections")
                for i, res in enumerate(raw_results):
                    logger.info(f"    Raw {i}: bbox={res.get('bbox')}, mask='{res.get('mask_status', 'N/A')}', conf={res.get('mask_confidence', 0.0)}")
                    logger.info(f"    Raw {i}: bbox={res.get('bbox')}, identity='{res.get('identity', 'N/A')}', mask='{res.get('mask_status', 'N/A')}'")
        
            except Exception as e:
                logger.warning(f"❌ Face system processing error for {source_id}: {e}")
                raw_results = []
                
                
                        # After raw_results are obtained
            if len(raw_results) > 0 and self.debug_mode:
                logger.debug(f"🔍 RAW RESULTS IDENTITY CHECK:")
                for i, res in enumerate(raw_results):
                    logger.info(f"   Face {i}: identity={res.get('identity', 'NONE')}, "
                        f"rec_conf={res.get('recognition_confidence', 0):.3f}, "
                        f"has_identity_key={'identity' in res}")
            
            # Apply tracking with recovery
            if source_id in self.tracking_managers:
                try:
                    # Get image logger
                    image_logger = self.get_source_image_logger(source_id)
                    
                    logger.debug(f"🔍 [2-TO-TRACKER] Sending {len(raw_results)} results to tracker")
                    
                    # Call tracking manager with correct parameters
                    processing_results = self.tracking_managers[source_id].process_frame(
                        source_id=source_id,
                        recognition_results=raw_results,
                        original_shape=frame.shape[:2],
                        processed_shape=processing_frame.shape[:2],
                        frame=frame,
                        image_logger=image_logger
                    )

                    # Verify progressive data in results
                    progressive_count = 0
                    for i, result in enumerate(processing_results):
                        if 'progressive_mask_data' in result:
                            progressive_count += 1
                            prog_data = result['progressive_mask_data']
                            logger.info(f"✅ Result {i}: Progressive data exists - "
                                f"status={prog_data.get('mask_status')}, "
                                f"progress={prog_data.get('verification_progress', 0):.2f}, "
                                f"frames={prog_data.get('frames_processed', 0)}")
                        else:
                            logger.warning(f"❌ Result {i}: NO progressive data")

                    logger.info(f"📊 Progressive data coverage: {progressive_count}/{len(processing_results)} results")
                    
                    
                    logger.debug(f"🔍 [3-TRACKER-RESULTS] {len(processing_results)} processed results")
                    for i, res in enumerate(processing_results):
                        identity = res.get('identity', 'Unknown')
                        verified = res.get('violation_verified', False)
                        hidden = res.get('identity_hidden', False)
                        logger.info(f"    Tracked {i}: identity='{identity}', verified={verified}, hidden={hidden}")
                    
                    # Apply identity control
                    controlled_results = self._apply_identity_control_policy(processing_results)
                    
                    # Add source_id to each result
                    for result in controlled_results:
                        result['source_id'] = source_id
                    
                    # Handle logging with error protection
                    self._safe_handle_violation_logging(source_id, frame, controlled_results)
                    
                    return controlled_results
                    
                except Exception as e:
                    logger.warning(f"❌ Tracking error for {source_id}: {e}")
                    import traceback
                    traceback.print_exc()
                    # Fallback to raw results
                    for result in raw_results:
                        result['source_id'] = source_id
                    return raw_results
            else:
                # No tracking manager available
                for result in raw_results:
                    result['source_id'] = source_id
                return raw_results
                
        except Exception as e:
            logger.warning(f"❌ Critical processing error for {source_id}: {e}")
            import traceback
            traceback.print_exc()
            return []
                
    def _safe_handle_violation_logging(self, source_id: str, frame: np.ndarray, results: List[Dict]):
        """Safe violation logging with error handling"""
        try:
            if (self.image_logging_enabled and 
                self.processing_count % self.log_interval == 0):
                self._handle_violation_logging(source_id, frame, results)
        except Exception as e:
            logger.warning(f"⚠️ Violation logging error for {source_id}: {e}")

    def _validate_frame(self, frame: np.ndarray) -> bool:
        """Validate frame before processing"""
        if frame is None:
            return False
        if not hasattr(frame, 'shape'):
            return False
        if len(frame.shape) != 3:  # Should be HxWxC
            return False
        if frame.shape[0] < 10 or frame.shape[1] < 10:  # Minimum size
            return False
        return True
        
    def _attempt_stream_recovery(self, source_id: str) -> bool:
        """Attempt to recover a failed stream with thread safety - UPDATED"""
        with self.sync_lock:  # Add thread safety
            if source_id not in self.source_configs:
                logger.warning(f"❌ Cannot recover {source_id}: no configuration")
                return False
            
            logger.info(f"🔄 Attempting recovery for {source_id}")
            
            try:
                # Save configuration BEFORE removal
                source_config = self.source_configs[source_id].copy()  # Make a copy
                
                # Remove the unhealthy stream using the sync_lock
                self.remove_source(source_id)  
                
                # Wait before reconnection
                time.sleep(self.stream_recovery_wait_time)
                
                # Re-add the source using saved configuration
                success = self.add_source(source_id, source_config)
                
                if success:
                    logger.info(f"✅ Successfully recovered stream: {source_id}")
                    
                    # Re-establish logging if needed
                    if self.image_logging_enabled:
                        self.force_create_image_logger(source_id)
                        
                    return True
                else:
                    logger.warning(f"❌ Failed to recover stream: {source_id}")
                    # Consider implementing exponential backoff or max retries
                    return False
                    
            except Exception as e:
                logger.warning(f"❌ Stream recovery error for {source_id}: {e}")
                import traceback
                traceback.print_exc()
                return False
            
    def monitor_stream_health(self):
        """Monitor and recover unhealthy streams"""
        unhealthy_sources = []
        
        for source_id, stream_manager in self.stream_managers.items():
            try:
                health = stream_manager.get_stream_info()
                success_rate = stream_manager.get_success_rate()
                
                # Check stream health
                if not stream_manager.is_healthy() or success_rate < self.health_success_rate_threshold:
                    unhealthy_sources.append(source_id)
                    logger.warning(f"⚠️ Unhealthy stream detected: {source_id} (success rate: {success_rate:.1%})")
                    
            except Exception as e:
                logger.warning(f"❌ Health check error for {source_id}: {e}")
                unhealthy_sources.append(source_id)
        
        # Attempt recovery for unhealthy sources
        for source_id in unhealthy_sources:
            self._attempt_stream_recovery(source_id)

    def auto_health_monitoring(self):
        """Background health monitoring with safety checks"""
        def health_monitor():
            #   FIX: Wait briefly for running flag to be set
            time.sleep(0.5)
            
            while getattr(self, 'running', False):
                try:
                    self.monitor_stream_health()
                    time.sleep(self.health_check_interval)  # Configuratble interval
                except Exception as e:
                    logger.warning(f"❌ Health monitoring error: {e}")
                    #   ADD: Log the full traceback for debugging
                    import traceback
                    traceback.print_exc()
                    time.sleep(60)  # Longer delay on error
        
        #   ADD: Safety check to prevent multiple threads
        if hasattr(self, 'health_monitor_thread') and self.health_monitor_thread and self.health_monitor_thread.is_alive():
            logger.warning("⚠️ Health monitor thread already running")
            return
        
        self.health_monitor_thread = threading.Thread(target=health_monitor, daemon=True, name="health_monitor")
        self.health_monitor_thread.start()
        logger.info("🏥 Health monitoring started")
                
    def optimize_memory_usage(self):
        """Optimize memory usage across all components"""
        logger.info("🧠 Optimizing memory usage...")
        
        # Clear frame queues
        for source_id, queue in self.frame_queues.items():
            while not queue.empty():
                try:
                    queue.get_nowait()
                except:
                    break
        
        # Clean up old tracks
        current_time = time.time()
        for source_id, tracker in self.tracking_managers.items():
            try:
                # Clean up old face tracks
                tracker.face_tracker.cleanup_old_tracks(
                    tracker.frame_count, 
                    tracker.max_track_age
                )
                
                # Clean up violation tracks
                if hasattr(tracker, '_cleanup_old_violation_tracks'):
                    tracker._cleanup_old_violation_tracks(current_time)
                    
            except Exception as e:
                logger.warning(f"⚠️ Memory optimization error for {source_id}: {e}")
        
        # Clear verified violations history
        if hasattr(self, 'verified_violations'):
            if len(self.verified_violations) > 100:
                self.verified_violations = self.verified_violations[-50:]
        
        # Force garbage collection
        import gc
        gc.collect()
        
        logger.info("✅ Memory optimization completed")

    def periodic_maintenance(self):
        """Run periodic maintenance tasks with proper initialization check"""
        maintenance_interval = self.maintenance_interval  # 5 minutes
        
        def maintenance_worker():
            #   FIX: Wait briefly for running flag to be set
            time.sleep(0.5)
            
            last_maintenance = time.time()
            
            while getattr(self, 'running', False):
                current_time = time.time()
                if current_time - last_maintenance >= maintenance_interval:
                    try:
                        self.optimize_memory_usage()
                        last_maintenance = current_time
                    except Exception as e:
                        logger.warning(f"❌ Maintenance error: {e}")
                
                time.sleep(60)  # Check every minute
        
        if not hasattr(self, 'maintenance_thread') or not self.maintenance_thread or not self.maintenance_thread.is_alive():
            self.maintenance_thread = threading.Thread(target=maintenance_worker, daemon=True, name="maintenance_worker")
            self.maintenance_thread.start()
            logger.info("🧹 Periodic maintenance started")
                                    
    def source_log(self, source_id: str, message: str):
        """Thread-safe logging with source prefix"""
        with self.log_lock:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            logger.info(f"[{timestamp}] 📹 {source_id}: {message}")            
            
    def stop_all_sources_stable(self):
        
        """Stable shutdown procedure - enhanced"""
        logger.warning("🛑 Starting stable shutdown...")
        
        # logger.info final statistics
        self.print_final_statistics()
        
        # Call the enhanced cleanup
        self.close()
        
        logger.info("✅ Stable shutdown completed")        
                               
    def apply_logging_config(self, config: Dict):
        """Apply logging configuration to all source ImageLoggers"""
        try:
            # Apply CSV logging configuration
            if 'enable_logging' in config:
                self.logging_enabled = config['enable_logging']
            
            # Apply image logging configuration  
            if 'enable_image_logging' in config:
                self.image_logging_enabled = config['enable_image_logging']
            
            # Apply log intervals
            if 'log_interval' in config:
                self.log_interval = config['log_interval']
                
            # Apply server push configuration to all ImageLoggers
            if 'server_push_enabled' in config:
                server_config = {
                    'server_push_enabled': config.get('server_push_enabled', False),
                    'server_endpoint': config.get('server_endpoint', ''),
                    'server_push_cooldown': config.get('server_push_cooldown', 30),
                    'server_timeout': config.get('server_timeout', 10),
                    'server_retry_attempts': config.get('server_retry_attempts', 3),
                    'server_retry_delay': config.get('server_retry_delay', 2)
                }
                
                # Update all existing ImageLoggers
                for source_id, image_logger in self.image_loggers.items():
                    image_logger.update_server_config(server_config)
                
                logger.info(f"📤 Server push configured for {len(self.image_loggers)} sources")
                
            logger.info("📊 Multi-source logging system configured")
            
        except Exception as e:
            logger.warning(f"❌ Error applying logging configuration: {e}")
    
    def apply_alert_config(self, config: Dict):
        """Apply audio alert configuration"""
        try:
            if hasattr(self, 'alert_manager') and self.alert_manager:
                self.alert_manager.update_config(config)
            logger.info("🔊 Audio alert system configured")
        except Exception as e:
            logger.warning(f"❌ Error applying alert configuration: {e}")
    
    def apply_tracking_config(self, config: Dict):
        """Apply tracking configuration to all tracking managers"""
        try:
            # Ensure face tracking is properly configured
            tracking_config = {
                'tracking': {
                    'confidence_frames': config.get('confidence_frames', 3),
                    'cooldown_seconds': config.get('cooldown_seconds', 5),
                    'min_iou': config.get('min_iou', 0.3),
                    'max_track_age': config.get('max_track_age', 300),
                    'enable_appearance_matching': config.get('enable_appearance_matching', True),
                    'enable_velocity_prediction': config.get('enable_velocity_prediction', False),
                    'appearance_weight': config.get('appearance_weight', 0.4),
                    'spatial_weight': config.get('spatial_weight', 0.4),
                    'size_weight': config.get('size_weight', 0.2)
                }
            }
            
            # Apply to all tracking managers
            for source_id, tracking_manager in self.tracking_managers.items():
                tracking_manager.update_config(tracking_config)
                
            logger.info("🎯 Face tracking system configured for all sources")
        except Exception as e:
            logger.warning(f"❌ Error applying tracking configuration: {e}")
               
    def apply_verification_config(self, config: Dict):
        """Apply violation verification configuration to all tracking managers"""
        try:
            verification_config = {
                'violation_verification_enabled': config.get('violation_verification_enabled', True),
                'min_violation_duration': config.get('min_violation_duration', 0.0),
                'min_violation_frames': config.get('min_violation_frames', 0),
                'violation_confidence_threshold': config.get('violation_confidence_threshold', 0.7)
            }
            
            # Update global verification settings
            self.violation_verification_enabled = verification_config['violation_verification_enabled']
            self.min_violation_duration = verification_config['min_violation_duration']
            self.min_violation_frames = verification_config['min_violation_frames']
            self.violation_confidence_threshold = verification_config['violation_confidence_threshold']
            
            # Apply to all tracking managers
            for source_id, tracking_manager in self.tracking_managers.items():
                tracking_manager.update_violation_verification_config(verification_config)
            
            logger.info(f"✅ Violation verification configured: enabled={self.violation_verification_enabled}")
            
        except Exception as e:
            logger.warning(f"❌ Error applying verification configuration: {e}")

    def apply_multi_source_config(self, config: Dict):
        """Apply multi-source specific configuration"""
        try:
            # Display configuration
            if 'display_layout' in config:
                self.display_layout = config['display_layout']
            if 'max_display_sources' in config:
                self.max_display_sources = config['max_display_sources']
            
            # Processing configuration
            if 'processing_width' in config:
                self.processing_width = config['processing_width']
            if 'processing_height' in config:
                self.processing_height = config['processing_height']
            if 'processing_scale' in config:
                self.processing_scale = config['processing_scale']
            
            # Health monitoring configuration
            if 'stream_recovery_wait_time' in config:
                self.stream_recovery_wait_time = config['stream_recovery_wait_time']
            if 'health_check_interval' in config:
                self.health_check_interval = config['health_check_interval']
            if 'health_success_rate_threshold' in config:
                self.health_success_rate_threshold = config['health_success_rate_threshold']
            if 'maintenance_interval' in config:
                self.maintenance_interval = config['maintenance_interval']
            
            # Resource monitoring
            if 'memory_threshold_mb' in config:
                self.memory_threshold_mb = config['memory_threshold_mb']
            
            logger.info("✅ Multi-source specific configuration applied")
            
        except Exception as e:
            logger.warning(f"❌ Error applying multi-source configuration: {e}")
                            
    def print_tracking_status(self):
        """logger.info tracking status for all sources"""
        logger.info("\n" + "="*50)
        logger.info("👤 MULTI-SOURCE TRACKING SYSTEM STATUS")
        logger.info("="*50)
        
        for source_id, tracking_manager in self.tracking_managers.items():
            config = tracking_manager.get_config()
            stats = tracking_manager.get_tracking_stats()
            
            logger.info(f"\n📹 Source: {source_id}")
            if config.get('tracking'):
                logger.info(f"   Face Tracking: {'ENABLED' if config['tracking'].get('enabled', False) else 'DISABLED'}")
                logger.info(f"   Person Tracking: {'ENABLED' if config['tracking'].get('enable_person_tracking', False) else 'DISABLED'}")
                logger.info(f"   Violation Verification: {'ENABLED' if config['tracking'].get('violation_verification_enabled', False) else 'DISABLED'}")
            
            if stats:
                logger.info(f"   Active Face Tracks: {stats.get('face_tracker', {}).get('total_tracks', 0)}")
                logger.info(f"   Active Person Tracks: {stats.get('person_tracker', {}).get('active_tracks', 0)}")
                logger.info(f"   Verified Violations: {stats.get('violation_verification', {}).get('verified_violations', 0)}")
        
        logger.info("="*50)
           
    def print_alert_status(self):
        """logger.info current alert system status"""
        if hasattr(self, 'alert_manager') and self.alert_manager:
            config = self.alert_manager.get_alert_config()
            logger.info("\n" + "="*50)
            logger.info("🔊 AUDIO ALERT SYSTEM STATUS")
            logger.info("="*50)
            for key, value in config.items():
                if value is not None:
                    logger.info(f"  {key}: {value}")
            logger.info("="*50)
        else:
            logger.warning("❌ Alert manager not available")

    # ========== ENHANCED: Source Management ==========

    def remove_source(self, source_id: str, external_lock: bool = False):
        """Thread-safe source removal with optional external lock"""
        if not external_lock:
            # Use internal lock if no external lock provided
            with self._stream_lock:
                return self._remove_source_internal(source_id)
        else:
            # External lock already acquired by caller
            return self._remove_source_internal(source_id)
                    
    def _remove_source_internal(self, source_id: str):
        """Actual removal logic without lock - COMPLETE IMPLEMENTATION"""
        try:
            logger.info(f"🗑️  Removing source: {source_id}")
            
            # 1. Stop stream manager
            if source_id in self.stream_managers:
                stream_manager = self.stream_managers[source_id]
                
                # Stop capture thread first
                if hasattr(stream_manager, 'stop_capture'):
                    stream_manager.stop_capture()
                
                # Wait a bit for thread to stop
                time.sleep(0.1)
                
                # Release video capture
                if hasattr(stream_manager, 'release'):
                    stream_manager.release()
                
                # Clear frame buffer if exists
                if hasattr(stream_manager, 'clear_buffer'):
                    stream_manager.clear_buffer()
                
                del self.stream_managers[source_id]
                logger.info(f"   Stopped stream manager for {source_id}")
            
            # 2. Clean up tracking manager
            if source_id in self.tracking_managers:
                tracker = self.tracking_managers[source_id]
                if hasattr(tracker, 'cleanup'):
                    tracker.cleanup()
                elif hasattr(tracker, 'release'):
                    tracker.release()
                del self.tracking_managers[source_id]
                logger.info(f"   Cleaned up tracking manager for {source_id}")
            
            # 3. Clean up ImageLogger with file handle closure
            if source_id in self.image_loggers:
                img_logger = self.image_loggers[source_id]
                # Close any open files
                if hasattr(img_logger, 'close'):
                    img_logger.close()
                elif hasattr(img_logger, 'csv_file') and img_logger.csv_file:
                    try:
                        img_logger.csv_file.close()
                    except:
                        pass
                del self.image_loggers[source_id]
                logger.info(f"   Cleaned up ImageLogger for {source_id}")
            
            # 4. Clean up frame queue
            if source_id in self.frame_queues:
                # Clear the queue
                queue = self.frame_queues[source_id]
                while not queue.empty():
                    try:
                        queue.get_nowait()
                    except:
                        break
                del self.frame_queues[source_id]
                logger.info(f"   Cleared frame queue for {source_id}")
            
            # 5. Remove from other collections
            if source_id in self.active_sources:
                self.active_sources.remove(source_id)
                logger.info(f"   Removed from active sources")
            
            if source_id in self.source_configs:
                del self.source_configs[source_id]
                logger.info(f"   Removed source configuration")
            
            # 6. Clean up cache
            if hasattr(self, '_cctv_name_cache') and source_id in self._cctv_name_cache:
                del self._cctv_name_cache[source_id]
                logger.info(f"   Cleared cached CCTV name")
            
            logger.info(f"✅ Completely removed source: {source_id}")
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ Error removing source {source_id}: {e}")
            import traceback
            traceback.print_exc()
            return False
                                            
    def update_source(self, source_id: str, **kwargs):
        """Update configuration for an existing source"""
        if source_id not in self.stream_managers:
            logger.warning(f"❌ Source {source_id} not found")
            return False
        
        try:
            #   SIMPLIFIED: Update tracking manager configuration
            if source_id in self.tracking_managers:
                self.tracking_managers[source_id].update_config(kwargs)
            
            # Update ImageLogger if it exists
            if source_id in self.image_loggers:
                if 'cctv_name' in kwargs:
                    self.image_loggers[source_id].cctv_name = kwargs['cctv_name']
                if any(key.startswith('server_') for key in kwargs):
                    self.image_loggers[source_id].update_server_config(kwargs)
            
            logger.info(f"✅ Updated configuration for source: {source_id}")
            return True
        except Exception as e:
            logger.warning(f"❌ Failed to update source {source_id}: {e}")
            return False

    #     Add method to get verification statistics from TrackingManager
    def get_verification_stats(self) -> Dict[str, Any]:
        """Get verification statistics from all TrackingManagers"""
        all_stats = {}
        total_stats = {
            'total_detected': 0,
            'total_verified': 0,
            'total_rejected': 0,
            'false_positives_prevented': 0,
            'active_tracks': 0,
            'currently_verified': 0
        }
        
        for source_id, tracker in self.tracking_managers.items():
            try:
                if hasattr(tracker, 'get_violation_verification_stats'):
                    stats = tracker.get_violation_verification_stats()
                    all_stats[source_id] = stats
                    
                    # Aggregate totals
                    total_stats['total_detected'] += stats.get('total_detected', 0)
                    total_stats['total_verified'] += stats.get('total_verified', 0)
                    total_stats['total_rejected'] += stats.get('total_rejected', 0)
                    total_stats['false_positives_prevented'] += stats.get('false_positives_prevented', 0)
                    total_stats['active_tracks'] += stats.get('active_violation_tracks', 0)
                    total_stats['currently_verified'] += stats.get('currently_verified', 0)
            except Exception as e:
                logger.warning(f"⚠️ Error getting verification stats for {source_id}: {e}")
    
    def get_source_info(self, source_id: str) -> Optional[Dict]:
        """Get complete information about a source using source_configs - OPTIMIZED"""
        if source_id not in self.source_configs:
            return None
        
        source_config = self.source_configs[source_id]
        #   FIX: Use cached CCTV name
        dynamic_cctv_name = self._get_cached_cctv_name(source_id)
        
        info = {
            'source_id': source_id,
            'url': source_config.get('url', 'unknown'),
            'cctv_name': dynamic_cctv_name,
            'config': source_config.copy(),  #   Include full configuration
            'active': source_id in self.active_sources,
            'has_stream_manager': source_id in self.stream_managers,
            'has_tracking_manager': source_id in self.tracking_managers,
            'has_image_logger': source_id in self.image_loggers,
        }
        
        # Add stream health if available
        if source_id in self.stream_managers:
            info['stream_health'] = self.stream_managers[source_id].get_stream_info()
        
        # Add tracking info if available
        if source_id in self.tracking_managers:
            info['tracking_stats'] = self.tracking_managers[source_id].get_tracking_stats()
        
        # Add logging info if available
        if source_id in self.image_loggers:
            info['logging_status'] = self.image_loggers[source_id].get_logging_status()
            #   Ensure CCTV name is consistent
            info['cctv_name'] = info['logging_status'].get('cctv_name', dynamic_cctv_name)
        
        return info
    
    def print_all_sources_info(self):
        """logger.info information about all active sources using source_configs"""
        logger.info("\n" + "="*60)
        logger.info("📊 ALL ACTIVE SOURCES INFORMATION")
        logger.info("="*60)
        
        for source_id in self.active_sources:
            if source_id in self.source_configs:
                info = self.get_source_info(source_id)
                if info:
                    config = info['config']
                    logger.info(f"\n📹 {source_id}:")
                    logger.info(f"   🔗 URL: {info.get('url', 'Unknown')}")
                    logger.info(f"   🏷️  CCTV Name: {info.get('cctv_name', 'Unknown')}")
                    logger.info(f"   📝 Description: {config.get('description', 'No description')}")
                    logger.info(f"   ⚡ Active: {info['active']}")
                    logger.info(f"   🎯 Tracking: {info['has_tracking_manager']}")
                    logger.info(f"   🖼️  Logging: {info['has_image_logger']}")
                    logger.info(f"   ⚙️  Processing Scale: {config.get('processing_scale', 1.0)}")
                    
                    # Show stream health
                    health = info.get('stream_health', {})
                    if health.get('performance'):
                        fps = health['performance'].get('fps', 0)
                        logger.info(f"   📈 FPS: {fps:.1f}")
        
        logger.info("="*60)
        
    # ========== ENHANCED: Backward Compatibility Methods ==========
    
    def setup_logging(self, filename: str = None):
        """Backward compatibility: Setup logging for single source mode"""
        if len(self.active_sources) == 0:
            logger.warning("⚠️ No active sources for logging setup")
            return False
        
        # Use first source for backward compatibility
        primary_source = self.active_sources[0]
        return self.setup_multi_source_logging(filename)
    
    def setup_image_logging(self, csv_filename: str = None):
        """Backward compatibility: Setup image logging for single source mode"""
        return self.setup_multi_source_logging(csv_filename)
    
    def save_annotated_frame(self, frame: np.ndarray, results: List[Dict], original_frame: np.ndarray = None) -> Tuple[bool, Optional[str]]:
        """Backward compatibility: Save frame using primary source logger"""
        if len(self.active_sources) == 0:
            return False, None
        
        primary_source = self.active_sources[0]
        return self.log_source_violation(primary_source, frame, results, original_frame)
    
    def has_mask_violations(self, results: List[Dict]) -> bool:
        """Backward compatibility: Check violations using default logic"""
        if not results:
            return False
        
        for result in results:
            mask_status = result.get('mask_status')
            mask_conf = result.get('mask_confidence', 0)
            
            if mask_status == 'no_mask' and mask_conf > 0.3:
                return True
        
        return False
    
    def get_image_logging_status(self) -> Dict[str, Any]:
        """Backward compatibility: Get status of primary source logger"""
        if len(self.active_sources) == 0 or self.active_sources[0] not in self.image_loggers:
            return {'enabled': False, 'saved_image_count': 0}
        
        primary_source = self.active_sources[0]
        return self.image_loggers[primary_source].get_logging_status()
    
    # ========== ENHANCED: Dynamic CCTV Naming System ==========
       
    def _get_dynamic_cctv_name(self, source_config: Dict, source_id: str = None) -> str:
        """
        Get dynamic CCTV name from source configuration - OPTIMIZED VERSION
        """
        # First check if CCTV name is explicitly provided in config
        explicit_name = source_config.get('cctv_name')
        if explicit_name and explicit_name != "Unknown-Camera":
            return explicit_name
        
        # Extract from URL if available
        url = source_config.get('url', '')
        if url and url.startswith('rtsp://'):
            extracted_name = self._extract_cctv_name_from_url(url, source_id)
            return extracted_name
        
        # For local cameras
        if source_id and (source_id.isdigit() or (isinstance(url, str) and url.isdigit())):
            cam_num = url if url.isdigit() else source_id
            local_name = f"Local-Camera-{cam_num}"
            return local_name
        
        # Use source_id as fallback
        fallback_name = f"Camera-{source_id}" if source_id else "Unknown-Camera"
        return fallback_name
    
    def _extract_cctv_name_from_url(self, url: str, source_id: str = None) -> str:
        """
        Extract CCTV name from RTSP URL with enhanced pattern matching - OPTIMIZED
        """
        try:
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
            
            # Final fallbacks
            if source_id and source_id not in ['0', '1', '2']:
                return f"Camera-{source_id}"
            
            timestamp = datetime.datetime.now().strftime("%H%M%S")
            return f"Camera-{timestamp}"
            
        except Exception as e:
            #   FIX: Only log errors in debug mode
            if self.debug_mode:
                logger.warning(f"⚠️ Error extracting CCTV name from URL: {e}")
            return "Unknown-Camera"
                        
    def _create_source_safe_name(self, cctv_name: str) -> str:
        """
        Create filesystem-safe name from CCTV name.
        """
        # Replace problematic characters
        safe_name = re.sub(r'[^\w\-_.]', '_', cctv_name)
        # Remove multiple underscores
        safe_name = re.sub(r'_+', '_', safe_name)
        # Remove leading/trailing underscores
        safe_name = safe_name.strip('_')
        return safe_name

    def _get_cached_cctv_name(self, source_id: str) -> str:
        """Get CCTV name with caching to prevent repeated extraction"""
        if not hasattr(self, '_cctv_name_cache'):
            self._cctv_name_cache = {}
        
        if source_id in self._cctv_name_cache:
            return self._cctv_name_cache[source_id]
        
        # Get from source config
        if source_id in self.source_configs:
            source_config = self.source_configs[source_id]
            cctv_name = self._get_dynamic_cctv_name(source_config, source_id)
            self._cctv_name_cache[source_id] = cctv_name
            return cctv_name
        
        return "Unknown-Camera"    
    
    # ========== ADD MISSING DISPLAY METHODS ==========
    
    def set_display_size(self, width: int, height: int, method: str = " _size"):
        """Set   display size"""
        if hasattr(self, 'resizer'):
            self.resizer.target_width = width
            self.resizer.target_height = height
            self.resizer.resize_method = method
            logger.info(f"🖼️  Display size set to {width}x{height} using {method} method")
    
    def toggle_debug_mode(self):
        """Toggle comprehensive debug mode"""
        self.debug_mode = not self.debug_mode
        status = "ON" if self.debug_mode else "OFF"
        logger.info(f"🐛 Debug mode: {status}")
        
    def toggle_performance_stats(self):
        """Toggle performance statistics display"""
        self.show_performance_stats = not self.show_performance_stats
        status = "ON" if self.show_performance_stats else "OFF"
        logger.info(f"📈 Performance stats: {status}")
        
    def toggle_resize_info(self):
        """Toggle resize information display"""
        self.show_resize_info = not self.show_resize_info
        status = "ON" if self.show_resize_info else "OFF"
        logger.info(f"📊 Resize info display: {status}")
    
    # ========== ADD MISSING PROCESSING METHODS ==========
    
    def calculate_fps(self):
        """Calculate current FPS"""
        self.frame_count += 1
        self.fps_frame_count += 1
        
        current_time = time.time()
        elapsed = current_time - self.last_fps_time
        
        if elapsed >= 1.0:  # Update FPS every second
            self.fps = self.fps_frame_count / elapsed
            self.fps_frame_count = 0
            self.last_fps_time = current_time
    
    def enhanced_resize_for_processing(self, frame: np.ndarray) -> np.ndarray:
        """Resize frame for processing"""
        if hasattr(self, 'frame_utils') and hasattr(self, 'performance_manager'):
            return self.frame_utils.enhanced_resize_for_processing(
                frame, 
                self.performance_manager.current_processing_scale
            )
        else:
            # Fallback resize
            return cv2.resize(frame, (640, 480))
    
    def resize_frame_for_display(self, frame: np.ndarray) -> np.ndarray:
        """Apply resizing to frame for display"""
        if hasattr(self, 'resizer'):
            if self.original_frame_size is None:
                self.original_frame_size = frame.shape[:2]
            return self.resizer.resize_frame(frame)
        else:
            return frame
        
    # ========== ADD MISSING VISUALIZATION METHODS ==========            

    def draw_results(self, frame: np.ndarray, results: List[Dict], performance: Dict = None):
        """
        Draw bounding boxes and labels with enhanced identity transparency.
        Always shows known identities, shows "Verifying" for unknown during unverified phase.
        """
        for result in results:
            x1, y1, x2, y2 = result['bbox']
            
            identity = result.get('identity', 'Unknown')
            rec_conf = result.get('recognition_confidence', 0.0)
            
            # Get progressive mask data with fallback
            progressive_data = result.get('progressive_mask_data', {})
            
            if progressive_data:
                # Use progressive detection data
                mask_status = progressive_data.get('mask_status', result.get('mask_status', 'unknown'))
                mask_confidence = progressive_data.get('mask_confidence', result.get('mask_confidence', 0.0))
                verification_progress = progressive_data.get('verification_progress', 0.0)
                frames_processed = progressive_data.get('frames_processed', 0)
                is_stable = progressive_data.get('is_stable', False)
            else:
                # Fallback to raw data
                mask_status = result.get('mask_status', 'unknown')
                mask_confidence = result.get('mask_confidence', 0.0)
                verification_progress = 0.0
                frames_processed = 0
                is_stable = False
            
            violation_verified = result.get('violation_verified', False)
            
            # 🟡 VERIFYING STATE (Orange)
            if mask_status == 'verifying':
                color = (127, 0, 15)  # Orange
                verification_text = f" ⏳ {verification_progress:.0%}" if verification_progress > 0 else " ⏳"
                
                # Show identity during verification if known
                if identity and identity != "Unknown":
                    base_label = f"{identity}"
                    confidence_text = f" ({rec_conf:.2f})"
                else:
                    base_label = "Verifying"
                    confidence_text = ""
                
                full_label = f"{base_label}{confidence_text} | VERIFYING{verification_text}"
                
                # Draw bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                
                # Draw label background
                label_size = cv2.getTextSize(full_label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                            (x1 + label_size[0], y1), color, -1)
                
                # Draw label text
                cv2.putText(frame, full_label, (x1, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                # Draw progress bar
                if verification_progress > 0:
                    bar_width = x2 - x1
                    progress_width = int(bar_width * verification_progress)
                    cv2.rectangle(frame, (x1, y2 + 5), (x1 + progress_width, y2 + 10), (255, 255, 0), -1)
                    cv2.rectangle(frame, (x1, y2 + 5), (x2, y2 + 10), (255, 255, 255), 1)
                
                continue  # Skip the rest
            
            # 🟢 MASK STATE (Green)
            elif mask_status == "mask":
                color = (0, 255, 0)  # Green
                
                if identity and identity != "Unknown":
                    base_label = f"{identity}"
                    confidence_text = f" ({rec_conf:.2f})"
                else:
                    base_label = "Masked"
                    confidence_text = ""
                
                full_label = f"{base_label}{confidence_text} | MASK"
                
                # Draw bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                
                # Draw label background
                label_size = cv2.getTextSize(full_label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                            (x1 + label_size[0], y1), color, -1)
                
                # Draw label text
                cv2.putText(frame, full_label, (x1, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                continue
            
            # 🔴 NO_MASK STATE (Red/Orange) - IMPLEMENTED PROPOSED ALTERATION
            elif mask_status == 'no_mask':
                # Determine color and verification indicator
                color = (0, 0, 255)  # Red
                verification_text = ""
                box_thickness = 2
                
                if violation_verified:
                    color = (0, 0, 255)  # Red for verified violations
                    verification_text = " ✅"
                    box_thickness = 2
                
                # === PROPOSED ALTERATION: TRANSPARENT IDENTITY DISPLAY ===
                
                # 1. Check if the identity is known (No need to hide identity)
                if identity and identity != "Unknown":
                    base_label = f"{identity}"
                    confidence_text = f" ({rec_conf:.2f})"
                    
                # 2. Check if we are still verifying the *violation* and identity is unknown
                elif not violation_verified:
                    # Display "Verifying" if identity is unknown/none, removing prior suppression
                    base_label = "Verifying" 
                    confidence_text = ""
                    
                # 3. Final Fallback: Identity is unknown, but the violation is verified
                else:
                    base_label = "No Mask"
                    confidence_text = ""
                
                # =========================================================
                
                full_label = f"{base_label}{confidence_text} | NO_MASK{verification_text}"
                
                # Draw bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, box_thickness)
                
                # Draw label background
                label_size = cv2.getTextSize(full_label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                            (x1 + label_size[0], y1), color, -1)
                
                # Draw label text
                cv2.putText(frame, full_label, (x1, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                continue
            
            # ⚫ DEFAULT/UNKNOWN STATE (Gray)
            else:
                color = (135, 206, 235)  # Gray
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                default_label = f"Unknown: {mask_status}"
                
                label_size = cv2.getTextSize(default_label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                            (x1 + label_size[0], y1), color, -1)
                cv2.putText(frame, default_label, (x1, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                                                                                        
    def draw_enhanced_results(self, frame: np.ndarray, results: List[Dict], performance: Dict = None):
        """
        Enhanced drawing with tracking information - COMPATIBILITY WRAPPER
        This maintains compatibility with existing code that expects 3 parameters
        """
        # Simply delegate to the main draw_results method
        self.draw_results(frame, results, performance)
                                            
    def draw_resize_info(self, frame: np.ndarray):
        """Display resize information on frame"""
        if not self.show_resize_info:
            return
        
        original_h, original_w = self.original_frame_size or frame.shape[:2]
        display_h, display_w = frame.shape[:2]
        
        info_lines = [
            f"Original: {original_w}x{original_h}",
            f"Display: {display_w}x{display_h}",
            f"Sources: {len(self.active_sources)}",
            f"Layout: {self.display_layout}"
        ]
        
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 130), (350, 130 + len(info_lines) * 25 + 10), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        for i, line in enumerate(info_lines):
            y_position = 150 + (i * 25)
            cv2.putText(frame, line, (20, y_position),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    def draw_debug_info(self, frame: np.ndarray, results: List[Dict]):
        """Draw comprehensive debug information with identity control status"""
        if not self.debug_mode and not self.show_performance_stats:
            return
            
        lines = []
        if self.show_performance_stats:
            lines.extend([
                f"FPS: {self.fps:.1f}",
                f"Frame: {self.frame_count}",
                f"Sources: {len(self.active_sources)}",
                f"Active Tracks: {len(results)}"
            ])
        
        if self.debug_mode:
            lines.extend([
                f"Debug: ON",
                f"Sources: {list(self.active_sources)}"
            ])
        
        #   ENHANCED: Add identity control and verification stats
        if self.violation_verification_enabled:
            verified_count = sum(1 for r in results if r.get('violation_verified', False))
            unverified_count = sum(1 for r in results if r.get('mask_status') == 'no_mask' and not r.get('violation_verified', False))
            hidden_identities = sum(1 for r in results if r.get('identity_hidden', False))
            
            lines.extend([
                f"Verified: {verified_count}",
                f"Unverified: {unverified_count}",
                f"Hidden IDs: {hidden_identities}",
                f"Total Logged: {self.violation_stats['total_logged']}"
            ])
        
        if not lines:
            return
            
        # Draw background for all info
        overlay = frame.copy()
        start_y = 10
        end_y = start_y + len(lines) * 25 + 20
        cv2.rectangle(overlay, (10, start_y), (350, end_y), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # Draw info
        for i, line in enumerate(lines):
            y_position = 30 + (i * 25)
            color = (0, 255, 0) if "FPS" in line else (255, 255, 255)
            cv2.putText(frame, line, (20, y_position),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
    # ========== ENHANCED: Control Methods with CCTV Info ==========
    
    def print_verification_stats(self):
        """logger.info verification statistics"""
        logger.info("\n" + "="*60)
        logger.info("✅ VIOLATION VERIFICATION STATISTICS")
        logger.info("="*60)
        logger.info(f"Total Detected: {self.violation_stats.get('total_detected', 0)}")
        logger.info(f"Total Verified: {self.violation_stats.get('total_verified', 0)}")
        logger.info(f"Total Logged: {self.violation_stats.get('total_logged', 0)}")
        logger.info(f"Verified Logged: {self.violation_stats.get('verified_logged', 0)}")
        logger.info(f"False Positives Prevented: {self.violation_stats.get('false_positives_prevented', 0)}")
        
        if self.violation_stats.get('last_verified_time'):
            last_time = datetime.datetime.fromtimestamp(self.violation_stats['last_verified_time'])
            logger.info(f"Last Verified: {last_time.strftime('%H:%M:%S')}")
        
        # Calculate rates
        total_detected = max(1, self.violation_stats.get('total_detected', 1))
        verification_rate = (self.violation_stats.get('total_verified', 0) / total_detected) * 100
        prevention_rate = (self.violation_stats.get('false_positives_prevented', 0) / total_detected) * 100
        
        logger.info(f"Verification Rate: {verification_rate:.1f}%")
        logger.info(f"False Positive Prevention Rate: {prevention_rate:.1f}%")
        logger.info("="*60)    
    
    def print_control_reference(self):
        """logger.info multi-source control reference with CCTV info"""
        logger.info("\n🎮 MULTI-SOURCE CONTROLS:")
        logger.info("   [m] - Cycle display layouts (grid, horizontal, vertical)")
        logger.info("   [n] - Toggle source health display") 
        logger.info("   [0] - Show source health report")
        logger.info("   [l] - Toggle multi-source logging")
        logger.info("   [L] - Show multi-source logging status")
        logger.info("   [C] - Show CCTV name mapping")
        logger.info("   [v] - Toggle voice alerts")
        logger.info("   [V] - Toggle violation verification")
        logger.info("   [p] - Toggle performance stats")
        logger.info("   [d] - Toggle debug mode")
        logger.info("   [q] - Quit")
    
    def handle_key_controls(self, key: int, display_frame: np.ndarray = None):
        """Handle keyboard controls for multi-source with CCTV info"""
        if key == ord('m'):  # Cycle through display layouts
            layouts = ['grid', 'horizontal', 'vertical']
            current_idx = layouts.index(self.display_layout)
            self.display_layout = layouts[(current_idx + 1) % len(layouts)]
            logger.info(f"🔄 Display layout: {self.display_layout}")
        
        elif key == ord('n'):  # Toggle source health display
            self.show_source_health = not getattr(self, 'show_source_health', False)
            status = "ON" if self.show_source_health else "OFF"
            logger.info(f"📊 Source health display: {status}")
        
        elif key == ord('0'):  # Show source health report
            self.print_source_health_report()
        
        elif key == ord('l'):  # Toggle multi-source logging
            self.toggle_logging()
        
        elif key == ord('L'):  # Show multi-source logging status
            self.print_multi_source_logging_status()
        
        elif key == ord('V'):  #     Toggle violation verification
            self.toggle_violation_verification()
        
        elif key == ord('S'):  #     Show verification statistics
            self.print_verification_stats()
        
        elif key == ord('q'):  # Quit
            self.running = False
            logger.warning("🛑 Quitting...")
        
        # Delegate to control handler for common controls
        if hasattr(self, 'control_handler'):
            self.control_handler.handle_common_controls(key)
                        
    # ========== ENHANCED: Control Methods ==========
    
    def toggle_logging(self, filename: str = None, force_state: bool = None):
        """Toggle multi-source logging with optional forced state"""
        if force_state is not None:
            new_state = force_state
        else:
            new_state = not self.image_logging_enabled
        
        if new_state and not self.image_logging_enabled:
            # Enable multi-source logging
            success = self.setup_multi_source_logging(filename)
            if success:
                self.image_logging_enabled = True
                self.logging_enabled = True
                logger.info("🟢 Multi-source logging STARTED")
                self.print_multi_source_logging_status()
            else:
                logger.warning("❌ Failed to start multi-source logging")
        elif not new_state and self.image_logging_enabled:
            # Disable multi-source logging
            self.image_logging_enabled = False
            self.logging_enabled = False
            
            # logger.info summary
            total_images = 0
            total_server_pushes = 0
            
            for source_id, img_logger in self.image_loggers.items():
                status = img_logger.get_logging_status()
                total_images += status['saved_image_count']
                total_server_pushes += status['stats']['server_pushes']
                logger.info(f"📹 {source_id}: {status['saved_image_count']} images, {status['stats']['server_pushes']} server pushes")
            
            logger.warning(f"🔴 Multi-source logging STOPPED")
            logger.info(f"   - Total images: {total_images}")
            logger.info(f"   - Total server pushes: {total_server_pushes}")
    
    def toggle_violation_verification(self, enabled: bool = None):
        """Toggle violation verification for all sources"""
        if enabled is None:
            self.violation_verification_enabled = not self.violation_verification_enabled
        else:
            self.violation_verification_enabled = enabled
        
        # Update all tracking managers
        for source_id, tracking_manager in self.tracking_managers.items():
            tracking_manager.toggle_violation_verification(self.violation_verification_enabled)
        
        status = "ENABLED" if self.violation_verification_enabled else "DISABLED"
        logger.info(f"✅ Violation verification: {status}")
        
        if self.violation_verification_enabled:
            logger.info(f"   - Min Duration: {self.min_violation_duration}s")
            logger.info(f"   - Min Frames: {self.min_violation_frames}")
            logger.info(f"   - Confidence: {self.violation_confidence_threshold}")

        # ========== ENHANCED: Flexible Source Addition ==========
                    
    def add_source(self, source_id: str, url_or_config: Union[str, int, Dict] = None, **kwargs):
        """Thread-safe source addition"""
        with self._stream_lock:
            if source_id in self.stream_managers:
                logger.warning(f"⚠️ Source {source_id} already exists")
                return False
            
            try:
                # Create configuration
                final_config = self._create_source_config(url_or_config, **kwargs)
                
                # ========== STORE CONFIGURATION ==========
                self.source_configs[source_id] = final_config
                logger.info(f"📁 Stored configuration for {source_id}")
                
                # DEBUG: Show what's in the configuration
                logger.debug(f"🔍 Final config keys for {source_id}: {list(final_config.keys())}")
                if 'tracking' in final_config:
                    logger.debug(f"🔍 Tracking config structure: {list(final_config['tracking'].keys())}")
                    if 'progressive_mask' in final_config['tracking']:
                        logger.info(f"✅ Found progressive_mask in final_config['tracking']")
                
                # Initialize stream manager
                stream_manager = StreamManager(final_config)
                success = stream_manager.initialize_stream(final_config['url'])
                
                if not success:
                    logger.warning(f"❌ Failed to initialize stream for {source_id}")
                    return False
                
                # Store stream manager
                self.stream_managers[source_id] = stream_manager
                self.frame_queues[source_id] = Queue(maxsize=3)
                            
                # Get global tracking config (ensure it exists)
                global_tracking_config = {}
                if hasattr(self, 'config'):
                    global_tracking_config = self.config.get('tracking', {})
                    logger.info(f"🌐 Global tracking config available: {'tracking' in self.config}")
                
                # Get source-specific tracking config
                source_tracking_config = final_config.get('tracking', {})
                
                # Perform comprehensive deep merge
                tracking_config = self._deep_merge_tracking_config(
                    global_tracking_config, 
                    source_tracking_config
                )
                
                # Ensure progressive_mask exists in tracking_config
                if 'progressive_mask' not in tracking_config:
                    logger.warning(f"⚠️  No progressive_mask in merged config, adding defaults")
                    tracking_config['progressive_mask'] = self._deep_merge_progressive_mask({}, {})
                
                # DEBUG: logger.info final configuration
                logger.info(f"🎯 FINAL Tracking configuration for {source_id}:")
                logger.info(f"   Total keys in tracking_config: {len(tracking_config)}")
                if 'progressive_mask' in tracking_config:
                    prog_config = tracking_config['progressive_mask']
                    logger.info(f"   Progressive mask enabled: {prog_config.get('enabled', True)}")
                    logger.info(f"   Progressive mask parameters: {len(prog_config)}")
                    # logger.info a few key parameters
                    for key in ['mask_buffer_size', 'min_mask_frames', 'mask_confidence_threshold']:
                        if key in prog_config:
                            logger.info(f"     {key}: {prog_config[key]}")
                
                # Create tracking manager
                tracking_manager = TrackingManager(tracking_config)
                
                self.tracking_managers[source_id] = tracking_manager
                
                # Add to active sources
                self.active_sources.append(source_id)
                
                # Start capture
                stream_manager.start_capture()
                
                logger.info(f"✅ Added source: {source_id}")
                return True
                
            except Exception as e:
                logger.warning(f"❌ Failed to add source {source_id}: {e}")
                traceback.print_exc()
                return False
            
                
    # Add this method to MultiSourceRealTimeProcessor

    def _deep_merge_tracking_config(self, global_config: Dict, source_config: Dict) -> Dict:
        """
        Deep merge tracking configurations with special handling for progressive_mask.
        """
        result = global_config.copy()
        
        for key, value in source_config.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                if key == 'progressive_mask':
                    # Special merge for progressive_mask to ensure all parameters are included
                    result[key] = self._deep_merge_progressive_mask(result[key], value)
                else:
                    # Recursive merge for other nested dicts
                    result[key] = self._deep_merge_tracking_config(result[key], value)
            else:
                # Override or add new value
                result[key] = value
        
        return result

    def _deep_merge_progressive_mask(self, base: Dict, override: Dict) -> Dict:
        """
        Deep merge progressive_mask configurations with comprehensive defaults.
        """
        # Default progressive_mask configuration
        default_progressive = {
            'enabled': True,
            'mask_buffer_size': 1000,
            'min_mask_frames': 1,
            'occlusion_timeout': 3.0,
            'mask_confidence_threshold': 0.64,
            'mask_consistency_threshold': 0.64,
            'min_stability_to_commit': 0.2,
            'state_hold_duration': 30.0,
            'verification_grace_ratio': 0.6,
            'spatial_consistency_weight': 0.3,
            'max_bbox_variation': 0.45,
            'extreme_confidence_threshold': 0.95,
            'extreme_mask_penalty': 0.8,
            'extreme_no_mask_boost': 0.9,
            'initial_mask_weight': 0.01,
            'initial_no_mask_weight': 0.99,
            'weight_increase_high_conf': 0.99,
            'weight_decrease_low_conf': 0.7,
            'weight_increase_opposite': 1.5,
            'confidence_smoothing_factor': 0.3,
            'stability_smoothing_factor': 0.2
        }
        
        # Start with defaults
        result = default_progressive.copy()
        
        # Apply base configuration
        for key, value in base.items():
            if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                result[key] = {**result[key], **value}
            else:
                result[key] = value
        
        # Apply override configuration
        for key, value in override.items():
            if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                result[key] = {**result[key], **value}
            else:
                result[key] = value
        
        return result            
                                                            
    # ========== MODIFIED: Setup source logging to use run subdirs ==========
    
    def _setup_source_logging(self, source_id: str) -> bool:
        """Setup logging for a specific source using source_configs."""
        try:
            if source_id in self.image_loggers:
                existing_logger = self.image_loggers[source_id]
                status = existing_logger.get_logging_status()
                logger.info(f"📁 ImageLogger already exists for {source_id}: {status['image_log_folder']}")
                return True

            source_config = self.source_configs[source_id]
            cctv_name = self._get_cached_cctv_name(source_id)
            logger.debug(f"🔍 Creating ImageLogger for {source_id} with CCTV name: {cctv_name}")

            source_logger = ImageLogger(source_config)
            if source_logger.cctv_name != cctv_name:
                logger.warning(f"⚠️ CCTV name mismatch! Expected: {cctv_name}, Got: {source_logger.cctv_name}")
                source_logger.update_cctv_name(cctv_name)

            safe_cctv_name = self._create_source_safe_name(cctv_name)
            # Construct the base directory for this source's images
            source_image_dir = os.path.join(self.image_log_dir, f"{self.current_log_session}_{safe_cctv_name}")

            logger.debug(f"🔍 Setting up ImageLogger with base directory: {source_image_dir}")

            # Pass as base_dir, not base_filename
            success = source_logger.setup_image_logging(base_dir=source_image_dir)
            if success:
                self.image_loggers[source_id] = source_logger
                logger.info(f"✅ ImageLogger setup for source: {source_id} → {cctv_name}")
                status = source_logger.get_logging_status()
                logger.debug(f"🔍 Verification - ImageLogger CCTV name: {status['cctv_name']}")
                logger.debug(f"🔍 Verification - ImageLogger folder: {status['image_log_folder']}")
                return True
            else:
                logger.warning(f"❌ Failed to setup ImageLogger for source: {source_id}")
                return False
        except Exception as e:
            logger.warning(f"❌ Error setting up logging for source {source_id}: {e}")
            import traceback
            traceback.print_exc()
            return False
                                                                               
    def _create_source_config(self, url_or_config: Union[str, int, Dict] = None, **kwargs) -> Dict[str, Any]:
        """
        Create source configuration from URL, camera index, or existing config dictionary.
        """
        config = {}
        
        #   ENHANCED: Handle multiple input types
        if url_or_config is not None:
            if isinstance(url_or_config, dict):
                # If a dictionary is provided, use it as base config
                config.update(url_or_config)
            elif isinstance(url_or_config, (str, int)):
                # If string or int, treat as URL/camera index
                config['url'] = str(url_or_config)
        else:
            # Default to first camera if no URL provided
            config['url'] = "0"
        
        #   ENHANCED: Apply all keyword arguments (override existing)
        config.update(kwargs)
        
        # Set defaults for required fields
        config.setdefault('description', self._infer_description_from_config(config))
        config.setdefault('priority', 'medium')
        config.setdefault('processing_scale', 1.0)
        config.setdefault('buffer_size', 3)
        
        #   ENHANCED: Merge with base configuration for missing values
        for key, value in self.config.items():
            if key not in config and not isinstance(value, (dict, list)):
                config[key] = value
        
        return config

    def _infer_description_from_config(self, config: Dict) -> str:
        """Infer camera description from configuration"""
        url = config.get('url', '')
        
        # Handle dictionary config that might have url as key
        if isinstance(url, dict):
            url = url.get('url', '')
        
        if isinstance(url, str):
            if url.startswith('rtsp://'):
                return "RTSP Camera"
            elif url.startswith('http://') or url.startswith('https://'):
                return "HTTP Camera"
            elif url.endswith(('.mp4', '.avi', '.mov')):
                return "Video File"
            elif url.isdigit():
                return f"Camera {url}"
        
        # Check if description exists in config
        if config.get('description'):
            return config['description']
        
        return "Unknown Source"
    
    def _is_physical_camera(self, config: Dict) -> bool:
        """Check if source is a physical camera (not RTSP/HTTP)"""
        url = config.get('url', '')
        return url.isdigit() or url in ['0', '1', '2']
 
    def _print_source_details(self, source_id: str, config: Dict):
        """logger.info detailed information about the added source"""
        url = config.get('url', 'Unknown')
        description = config.get('description', 'No description')
        cctv_name = self._get_dynamic_cctv_name(config, source_id)
        
        logger.info(f"   📹 Source ID: {source_id}")
        logger.info(f"   🔗 URL: {url}")
        logger.info(f"   📝 Description: {description}")
        logger.info(f"   🏷️  CCTV Name: {cctv_name}")
        logger.info(f"   ⚙️  Processing Scale: {config.get('processing_scale', 1.0)}")
        logger.info(f"   📦 Buffer Size: {config.get('buffer_size', 3)}")
        
        # Detect source type
        if url.startswith('rtsp://'):
            logger.info(f"   🌐 Type: RTSP Stream")
        elif url.startswith(('http://', 'https://')):
            logger.info(f"   🌐 Type: HTTP Stream")
        elif url.endswith(('.mp4', '.avi', '.mov')):
            logger.info(f"   🎬 Type: Video File")
        elif url.isdigit():
            logger.info(f"   📷 Type: Physical Camera")
        else:
            logger.info(f"   ❓ Type: Unknown")
                                                                            
    def get_multi_source_frames(self, timeout: float = 0.1) -> Dict[str, Optional[np.ndarray]]:
        """Get latest frames from all active sources"""
        frames = {}
        
        for source_id in self.active_sources:
            try:
                frame = self.stream_managers[source_id].get_frame(timeout)
                frames[source_id] = frame
            except Exception as e:
                if self.config.get('debug', {}).get('verbose', False):
                    logger.warning(f"⚠️ Failed to get frame from {source_id}: {e}")
                frames[source_id] = None
        
        return frames

    # ========== ENHANCED: Batch Source Addition ==========        
    def add_sources(self, sources_config: Dict[str, Dict]) -> int:
        """Batch add multiple sources"""
        success_count = 0
        for source_id, config in sources_config.items():
            if self.add_source(source_id, config):
                success_count += 1
        return success_count    
   
    # ========== MODIFIED: run_multi_source_stable ==========
    def run_multi_source_stable(self, sources_config: Dict[str, Dict]):
        """Stabilized main processing loop with output directory and email."""
        exit_code = 0
        exit_message = "Normal shutdown"
        try:
            # Create run directory if not already created
            if self.run_dir is None:
                self._create_run_directory()

            # Initialize sources
            success_count = self.apply_multi_source_config(sources_config)
            if success_count == 0:
                logger.warning("❌ No valid sources could be initialized")
                return

            # Parse shutdown_at if provided
            if self.shutdown_at:
                try:
                    # Try to parse as HH:MM:SS (today's date)
                    shutdown_time = datetime.datetime.strptime(self.shutdown_at, "%H:%M:%S").time()
                    now = datetime.datetime.now()
                    self.shutdown_target_time = datetime.datetime.combine(now.date(), shutdown_time)
                    # If the time is already past today, schedule for tomorrow
                    if self.shutdown_target_time <= now:
                        self.shutdown_target_time += datetime.timedelta(days=1)
                        logger.info(f"⏰ Shutdown time {self.shutdown_at} is in the past, scheduling for tomorrow")
                    self.shutdown_remaining = (self.shutdown_target_time - now).total_seconds()
                    logger.info(f"⏰ Automatic shutdown scheduled at {self.shutdown_target_time.strftime('%Y-%m-%d %H:%M:%S')} "
                                f"(in {self.shutdown_remaining:.0f} seconds)")
                except Exception as e:
                    logger.warning(f"⚠️ Invalid shutdown_at format: {self.shutdown_at}. Should be HH:MM:SS. Disabling timer.")
                    self.shutdown_target_time = None
                    self.shutdown_remaining = None

            # Set running flag and start threads
            self.running = True
            logger.info(f"🎬 Starting stabilized multi-source processing with {success_count} sources")

            # Start background threads
            self.auto_health_monitoring()
            self.periodic_maintenance()

            # Set up signal handlers for headless mode
            if self.headless:
                import signal
                def signal_handler(sig, frame):
                    logger.info("Received signal %s, stopping...", sig)
                    self.running = False
                signal.signal(signal.SIGINT, signal_handler)
                signal.signal(signal.SIGTERM, signal_handler)
                # Custom signal for toggling logging – only on platforms that support it
                if hasattr(signal, 'SIGUSR1'):
                    signal.signal(signal.SIGUSR1, lambda s,f: self.toggle_logging())
                else:
                    logger.info("SIGUSR1 not available on this platform; use file‑based control for toggling logging.")

            # Main processing loop
            consecutive_errors = 0
            max_consecutive_errors = 10
            while self.running and consecutive_errors < max_consecutive_errors:
                try:
                    # Check shutdown event
                    if self._shutdown_event.is_set():
                        break

                    # Get frames from all sources
                    source_frames = self.get_multi_source_frames()
                    if not any(frame is not None for frame in source_frames.values()):
                        time.sleep(0.05)
                        consecutive_errors += 1
                        continue
                    consecutive_errors = 0

                    # Process each source and collect results
                    all_results = {}
                    for source_id, frame in source_frames.items():
                        if frame is not None:
                            try:
                                results = self.robust_process_multi_source_frame(source_id, frame)
                                all_results[source_id] = results
                            except Exception as e:
                                logger.warning(f"⚠️ Processing error for {source_id}: {e}")
                                all_results[source_id] = []
                                
                    # ---------- SHUTDOWN TIMER CHECK ----------
                    if self.shutdown_target_time is not None:
                        now = datetime.datetime.now()
                        if now >= self.shutdown_target_time:
                            logger.warning(f"⏰ Shutdown time reached ({self.shutdown_target_time.strftime('%H:%M:%S')}). Stopping...")
                            self.running = False
                            break
                        # Optionally log remaining time every ~100 frames
                        if self.processing_count % 100 == 0:
                            remaining = (self.shutdown_target_time - now).total_seconds()
                            logger.info(f"⏰ Shutdown in {remaining:.0f} seconds")                                

                    # ---------- GUI MODE ----------
                    if not self.headless:
                        # Create combined display
                        display_frame = self.create_multi_source_display(source_frames, all_results)

                        # Draw debug / performance info
                        if self.show_performance_stats or self.debug_mode:
                            total_results = []
                            for results in all_results.values():
                                total_results.extend(results)
                            self.draw_debug_info(display_frame, total_results)

                        if self.show_resize_info:
                            self.draw_resize_info(display_frame)

                        # Show the frame
                        if display_frame is not None and display_frame.size > 0:
                            cv2.imshow('Multi-Source Face Recognition', display_frame)
                        else:
                            logger.warning("⚠️ No display frame generated")

                        # Handle keyboard input
                        key = cv2.waitKey(1) & 0xFF
                        if key != 255:
                            self.handle_key_controls(key)

                    # ---------- HEADLESS MODE ----------
                    else:
                        # Simple pacing to avoid 100% CPU
                        time.sleep(0.033)  # ~30 fps

                        # Optional file‑based control
                        control_file = '/tmp/maskrecog_control'
                        if os.path.exists(control_file):
                            with open(control_file, 'r') as f:
                                command = f.read().strip()
                            os.remove(control_file)
                            self._handle_control_command(command)

                    # Calculate FPS (works in both modes)
                    self.calculate_fps()

                except Exception as e:
                    consecutive_errors += 1
                    logger.warning(f"❌ Main loop error: {e}")
                    traceback.print_exc()
                    time.sleep(1)

            logger.warning("🛑 Processing loop ended")

        except KeyboardInterrupt:
            exit_code = 130
            exit_message = "Interrupted by user"
            logger.info("\n🛑 Shutting down by user request...")
        except Exception as e:
            exit_code = 1
            exit_message = str(e)
            logger.warning(f"❌ Critical error in processing: {e}")
            traceback.print_exc()
        finally:
            # Write exit status
            self.write_exit_status(exit_code, exit_message)

            # Send email with results if configured
            if self.email_recipients and self.run_dir:
                zip_path = self._zip_run_directory()
                if zip_path:
                    self._send_email(zip_path)

            # Close all resources (OpenCV windows closed conditionally inside close())
            self.close()               
              
    # ========== ENHANCED: Logging Pipeline Integration ==========
                                   
    def create_multi_source_display(self, source_frames: Dict[str, np.ndarray], 
                                source_results: Dict[str, List[Dict]]) -> np.ndarray:
        """Combine multiple source frames into a single display"""
        if not source_frames:
            return np.zeros((480, 640, 3), dtype=np.uint8)
        
        valid_frames = {sid: frame for sid, frame in source_frames.items() 
                    if frame is not None}
        
        if not valid_frames:
            return np.zeros((480, 640, 3), dtype=np.uint8)
        
        if len(valid_frames) == 1:
            # Single source - return as is with overlay
            source_id = list(valid_frames.keys())[0]
            frame = valid_frames[source_id]
            results = source_results.get(source_id, [])
            self.draw_results(frame, results)
            return self.resize_frame_for_display(frame)
        
        # Multi-source layouts
        if self.display_layout == 'grid':
            return self._create_grid_layout(valid_frames, source_results)
        elif self.display_layout == 'horizontal':
            return self._create_horizontal_layout(valid_frames, source_results)
        elif self.display_layout == 'vertical':
            return self._create_vertical_layout(valid_frames, source_results)
        else:
            return self._create_grid_layout(valid_frames, source_results)

    def _create_grid_layout(self, frames: Dict[str, np.ndarray], 
                        results: Dict[str, List[Dict]]) -> np.ndarray:
        """Create grid layout for multiple sources"""
        source_ids = list(frames.keys())
        grid_size = int(np.ceil(np.sqrt(min(len(source_ids), self.max_display_sources))))
        
        # Get layout configuration
        target_h = self.config.get('grid_layout', {}).get('target_height', 360)
        target_w = self.config.get('grid_layout', {}).get('target_width', 480)
        
        resized_frames = []
        
        for source_id in source_ids:
            frame = frames[source_id]
            # Add source identifier and results
            frame_with_overlay = self._add_source_overlay(frame, source_id, 
                                                        results.get(source_id, []))
            resized = cv2.resize(frame_with_overlay, (target_w, target_h))
            resized_frames.append(resized)
        
        # Create grid
        rows = []
        for i in range(0, len(resized_frames), grid_size):
            row_frames = resized_frames[i:i + grid_size]
            # Pad row if necessary
            while len(row_frames) < grid_size:
                row_frames.append(np.zeros((target_h, target_w, 3), dtype=np.uint8))
            rows.append(np.hstack(row_frames))
        
        return np.vstack(rows)

    # ========== ENHANCED: Visualization with CCTV Names ==========
    
    def _add_source_overlay(self, frame: np.ndarray, source_id: str, results: List[Dict]) -> np.ndarray:
        """Add source identifier overlay to frame with CCTV name """
        
        #     Add violation verification status
        if self.violation_verification_enabled:
            verified_count = sum(1 for r in results if r.get('violation_verified', False))
            if verified_count > 0:
                cv2.putText(frame, f"Verified: {verified_count}", (10, 110), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # Draw results on this specific frame
        self.draw_results(frame, results)
        
        return frame
        
    def _create_horizontal_layout(self, frames: Dict[str, np.ndarray], 
                                results: Dict[str, List[Dict]]) -> np.ndarray:
        """Create horizontal strip layout"""
        source_ids = list(frames.keys())
        
        # Get layout configuration
        layout_config = self.config.get('horizontal_layout', {})
        target_h = layout_config.get('target_height', 360)
        
        resized_frames = []
        for source_id in source_ids:
            frame = frames[source_id]
            frame_with_overlay = self._add_source_overlay(frame, source_id, results.get(source_id, []))
            
            # Maintain aspect ratio
            h, w = frame_with_overlay.shape[:2]
            aspect_ratio = w / h
            target_w = int(target_h * aspect_ratio)
            
            resized = cv2.resize(frame_with_overlay, (target_w, target_h))
            resized_frames.append(resized)
        
        return np.hstack(resized_frames)

    def _create_vertical_layout(self, frames: Dict[str, np.ndarray], 
                            results: Dict[str, List[Dict]]) -> np.ndarray:
        """Create vertical stack layout"""
        source_ids = list(frames.keys())
        
        # Get layout configuration
        layout_config = self.config.get('vertical_layout', {})
        target_w = layout_config.get('target_width', 480)
        
        resized_frames = []
        for source_id in source_ids:
            frame = frames[source_id]
            frame_with_overlay = self._add_source_overlay(frame, source_id, results.get(source_id, []))
            
            # Maintain aspect ratio
            h, w = frame_with_overlay.shape[:2]
            aspect_ratio = h / w
            target_h = int(target_w * aspect_ratio)
            
            resized = cv2.resize(frame_with_overlay, (target_w, target_h))
            resized_frames.append(resized)
        
        return np.vstack(resized_frames)
    
    def _apply_identity_control_policy(self, results: List[Dict]) -> List[Dict]:
        """
        Apply identity control policy - UPDATED for transparent identity display
        """
        controlled_results = []
        
        for result in results:
            result_copy = result.copy()
            mask_status = result_copy.get('mask_status')
            violation_verified = result_copy.get('violation_verified', False)
            identity = result_copy.get('identity', 'Unknown')
            
            #   UPDATED: More transparent identity policy
            # 1. Always show identity if known, regardless of mask status
            # 2. Only mark as 'unverified' for logging/tracking purposes
            # 3. Never hide identity from display
            
            result_copy['identity_hidden'] = False  # Never hide identity from display
            
            if mask_status == 'no_mask' and not violation_verified:
                # Mark as unverified for logging purposes
                result_copy['identity_unverified'] = True
                # Keep original identity for display
            elif mask_status == 'no_mask' and violation_verified:
                # Verified violation
                result_copy['identity_unverified'] = False
                result_copy['identity_revealed'] = True
            else:
                # Mask wearers or other states
                result_copy['identity_unverified'] = False
            
            controlled_results.append(result_copy)
        
        return controlled_results
                
    def get_source_health_report(self) -> Dict[str, Dict]:
        """Get health status for all sources"""
        health_report = {}
        
        for source_id, stream_manager in self.stream_managers.items():
            health_report[source_id] = {
                'health': stream_manager.get_stream_info(),
                'success_rate': stream_manager.get_success_rate(),
                'is_healthy': stream_manager.is_healthy(),
                'frame_count': stream_manager.frame_count,
                'error_count': stream_manager.error_count
            }
        
        return health_report

    def print_source_health_report(self):
        """logger.info comprehensive health status for all sources"""
        health_report = self.get_source_health_report()
        
        logger.info("\n" + "="*60)
        logger.info("🏥 MULTI-SOURCE HEALTH REPORT")
        logger.info("="*60)
        
        for source_id, health in health_report.items():
            status = "✅ HEALTHY" if health['is_healthy'] else "❌ UNHEALTHY"
            stream_info = health['health']
            
            logger.info(f"\n📹 Source: {source_id} - {status}")
            logger.info(f"   Type: {stream_info.get('stream_type', 'Unknown')}")
            logger.info(f"   FPS: {health['health']['performance'].get('fps', 0):.1f}")
            logger.info(f"   Success Rate: {health['success_rate']:.1%}")
            logger.info(f"   Frames: {health['frame_count']}")
            logger.info(f"   Errors: {health['error_count']}")
        
        logger.info("="*60)
        
    def stop_all_sources(self):
        """Stop and release all stream managers with logging summary - ENHANCED"""
        logger.warning("🛑 Stopping all sources...")
        
        #   ADD: Safety check to prevent multiple stops
        if not self.running:
            logger.warning("⚠️ Already stopping or stopped")
            return
        
        # logger.info final logging summary
        if self.image_logging_enabled:
            total_images = 0
            total_server_pushes = 0
            
            logger.info(f"\n📊 MULTI-SOURCE LOGGING SUMMARY:")
            for source_id, img_logger in self.image_loggers.items():
                status = img_logger.get_logging_status()
                images = status['saved_image_count']
                pushes = status['stats']['server_pushes']
                total_images += images
                total_server_pushes += pushes
                logger.info(f"   {source_id}: {images} images, {pushes} server pushes")
            
            logger.info(f"   TOTAL: {total_images} images, {total_server_pushes} server pushes")
        
        #     logger.info violation verification summary - SAFE VERSION
        if self.violation_verification_enabled:
            logger.info(f"\n✅ VIOLATION VERIFICATION SUMMARY:")
            logger.info(f"   Total Detected: {self.violation_stats.get('total_detected', 0)}")
            logger.info(f"   Total Verified: {self.violation_stats.get('total_verified', 0)}")
            logger.info(f"   Total Logged: {self.violation_stats.get('total_logged', 0)}")
            
            # Safely get verified/unverified logged counts
            verified_logged = self.violation_stats.get('verified_logged', 0)
            unverified_logged = self.violation_stats.get('unverified_logged', 0)
            logger.info(f"   Verified Logged: {verified_logged}")
            logger.info(f"   Unverified Logged: {unverified_logged}")
            
            logger.info(f"   False Positives Prevented: {self.violation_stats.get('false_positives_prevented', 0)}")
            
            total_detected = self.violation_stats.get('total_detected', 1)
            prevention_rate = (self.violation_stats.get('false_positives_prevented', 0) / 
                            max(1, total_detected)) * 100
            logger.info(f"   False Positive Prevention Rate: {prevention_rate:.1f}%")
        
        #   ADD: Set running flag BEFORE cleanup
        self.running = False
        
        #   ADD: Brief pause to allow threads to notice
        time.sleep(0.5)
        
        # Call the enhanced cleanup
        self.close()
        
        logger.info("✅ All sources stopped")
                                    
    def _handle_violation_logging(self, source_id: str, frame: np.ndarray, results: List[Dict]):
        """
        Enhanced logging that uses ONLY TrackingManager's verified violations
        """
        # Extract only verified violations from TrackingManager
        verified_violations = []
        unverified_violations = []
        
        for result in results:
            if result.get('mask_status') == 'no_mask' and result.get('mask_confidence', 0) > 0.3:
                if result.get('violation_verified', False):
                    #   Use TrackingManager's verification metadata
                    verification_metadata = {
                        'violation_duration': result.get('violation_duration', 0),
                        'violation_frames': result.get('violation_frames', 0),
                        'verification_level': result.get('verification_level', 'unknown'),
                        'violation_stable': result.get('violation_stable', False),
                        'mask_stability_score': result.get('mask_stability_score', 0.0),
                        'temporal_consistency': result.get('temporal_consistency', 0.0)
                    }
                    
                    # Add verification metadata to result
                    result_copy = result.copy()
                    result_copy.update(verification_metadata)
                    result_copy['verification_status'] = 'verified'
                    verified_violations.append(result_copy)
                    
                    #   Update statistics
                    self.violation_stats['total_verified'] += 1
                    self.violation_stats['last_verified_time'] = time.time()
                else:
                    # Unverified violation - track but don't log
                    unverified_violations.append(result)
                    self.violation_stats['false_positives_prevented'] += 1
            
        # Log verified violations (images)
        if verified_violations:
            success, _ = self.log_source_violation(source_id, frame, verified_violations, frame)
            if success:
                self.violation_stats['total_logged'] += len(verified_violations)
                # Also log to data logger (CSV)
                if self.data_logger and self.logging_enabled:
                    log_entries = self.data_logger.collect_log_data(verified_violations)
                    if log_entries:
                        self.data_logger.write_log_entries(log_entries)
                
                    # Log verification details
                    for violation in verified_violations:
                        identity = violation.get('identity', 'Unknown')
                        duration = violation.get('violation_duration', 0)
                        frames = violation.get('violation_frames', 0)
                        level = violation.get('verification_level', 'unknown')
                        
                        verification_log = (
                            f"✅ VERIFIED VIOLATION | "
                            f"Source: {source_id} | "
                            f"Identity: {identity} | "
                            f"Level: {level} | "
                            f"Duration: {duration:.1f}s | "
                            f"Frames: {frames}"
                        )
                        logger.info(verification_log)
        
        # Log unverified violations for debugging only
        if unverified_violations and self.debug_mode:
            logger.warning(f"⚠️  {len(unverified_violations)} unverified violations detected (not logged)")
            for violation in unverified_violations:
                identity = violation.get('identity', 'Unknown')
                confidence = violation.get('mask_confidence', 0)
                if 'violation_progress' in violation:
                    progress = violation['violation_progress']
                    logger.info(f"   ⏳ Unverified: {identity} (conf: {confidence:.2f}) - "
                        f"Progress: {progress.get('overall', 0):.1%}")
                                                
        
                    