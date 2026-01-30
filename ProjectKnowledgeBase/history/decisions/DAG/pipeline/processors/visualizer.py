import cv2
import numpy as np
from pipeline.core.processor import Processor

class DetectionVisualizer(Processor):
    """Visualizes detections on images"""
    
    def __init__(self, name, config=None):
        super().__init__(name, config)
        
        # Visualization configuration
        self.colors = config.get("colors", {
            "person": (0, 255, 0),      # Green
            "car": (255, 0, 0),         # Blue
            "bicycle": (0, 255, 255),   # Yellow
            "motorcycle": (0, 165, 255), # Orange
            "default": (0, 0, 255)       # Red
        })
        
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.font_scale = config.get("font_scale", 0.5)
        self.font_thickness = config.get("font_thickness", 2)
        self.box_thickness = config.get("box_thickness", 2)
    
    def process(self, packet):
        image = packet.data.get("image")
        detections = packet.data.get("detections", [])
        
        if image is None:
            print(f"[{self.name}] No image to visualize")
            return packet
        
        # Create a copy for visualization
        visual_image = image.copy()
        
        # Draw each detection
        for detection in detections:
            bbox = detection["bbox"]
            class_name = detection["class_name"]
            confidence = detection["confidence"]
            
            # Get color for this class
            color = self.colors.get(class_name, self.colors["default"])
            
            # Convert bbox coordinates to integers
            x1, y1, x2, y2 = map(int, bbox)
            
            # Draw bounding box
            cv2.rectangle(visual_image, (x1, y1), (x2, y2), color, self.box_thickness)
            
            # Create label
            label = f"{class_name}: {confidence:.2f}"
            
            # Get text size for background
            (text_width, text_height), baseline = cv2.getTextSize(
                label, self.font, self.font_scale, self.font_thickness
            )
            
            # Draw label background
            cv2.rectangle(visual_image, 
                         (x1, y1 - text_height - 10), 
                         (x1 + text_width, y1), 
                         color, 
                         -1)  # Filled rectangle
            
            # Draw label text
            cv2.putText(visual_image, label, 
                       (x1, y1 - 5), 
                       self.font, 
                       self.font_scale, 
                       (255, 255, 255),  # White text
                       self.font_thickness)
        
        # Add frame information
        h, w = visual_image.shape[:2]
        cv2.putText(visual_image, f"Detections: {len(detections)}", 
                   (10, 30), self.font, 1, (0, 255, 0), 2)
        
        # Store visualized image
        packet.data["visualized_image"] = visual_image
        packet.data["original_image"] = image
        
        print(f"[{self.name}] Visualized {len(detections)} detections")
        
        return packet