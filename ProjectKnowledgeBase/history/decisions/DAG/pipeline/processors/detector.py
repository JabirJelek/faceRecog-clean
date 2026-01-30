import numpy as np
import cv2
from ultralytics import YOLO
from pipeline.core.processor import Processor

class YOLODetector(Processor):
    """Real YOLO-based object detector"""
    
    def __init__(self, name, config=None):
        super().__init__(name, config)
        
        # YOLO model configuration
        self.model_name = config.get("model_name", r"D:\RaihanFarid\Dokumen\Object Detection\3.1_FaceRecog\run_py\DAG\pipeline-1\models\yolov11n-face.pt")
        self.confidence_threshold = config.get("confidence_threshold", 0.5)
        self.iou_threshold = config.get("iou_threshold", 0.5)
        
        # Load YOLO model
        print(f"[{self.name}] Loading YOLO model: {self.model_name}")
        try:
            self.model = YOLO(self.model_name)
            print(f"[{self.name}] YOLO model loaded successfully")
        except Exception as e:
            print(f"[{self.name}] Error loading YOLO model: {e}")
            print("[{self.name}] Attempting to download model...")
            self.model = YOLO(self.model_name)  # This will download if not available
            print(f"[{self.name}] YOLO model downloaded and loaded")
    
    def configure(self, params):
        super().configure(params)
        # Update thresholds from parameters
        self.confidence_threshold = self.parameters.get("confidence_threshold", self.confidence_threshold)
        self.iou_threshold = self.parameters.get("iou_threshold", self.iou_threshold)
        return self
    
    def process(self, packet):
        image = packet.data.get("image")
        
        if image is None:
            print(f"[{self.name}] No image in packet")
            packet.data["detections"] = []
            packet.data["has_detections"] = False
            return packet
        
        # Run YOLO inference
        results = self.model(
            image, 
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            verbose=False
        )
        
        # Process results
        detections = []
        for result in results:
            if result.boxes is not None:
                boxes = result.boxes.xyxy.cpu().numpy()  # Bounding boxes
                confidences = result.boxes.conf.cpu().numpy()  # Confidence scores
                class_ids = result.boxes.cls.cpu().numpy()  # Class IDs
                
                # YOLO class names
                class_names = self.model.names
                
                for i, (box, conf, cls_id) in enumerate(zip(boxes, confidences, class_ids)):
                    detection = {
                        "bbox": box.tolist(),  # [x1, y1, x2, y2]
                        "confidence": float(conf),
                        "class_id": int(cls_id),
                        "class_name": class_names.get(int(cls_id), f"class_{int(cls_id)}"),
                        "tracking_id": None  # For future tracking support
                    }
                    detections.append(detection)
        
        # Store in packet
        packet.data["detections"] = detections
        packet.data["detection_count"] = len(detections)
        packet.data["has_detections"] = len(detections) > 0
        packet.data["raw_results"] = results
        
        print(f"[{self.name}] Found {len(detections)} detections")
        
        return packet