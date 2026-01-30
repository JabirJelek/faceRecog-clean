import time
from pipeline.core.processor import Processor

class OutputAdapter(Processor):
    """Formats the output for consumption"""
    def process(self, packet):
        detections = packet.data.get("detections", [])
        
        # Create structured output
        packet.output = {
            "status": "success",
            "timestamp": packet.data.get("timestamp", time.time()),
            "detections": detections,
            "detection_count": len(detections),
            "has_detections": len(detections) > 0,
            "summary": self._create_summary(detections)
        }
        
        print(f"[OutputAdapter] Created output with {len(detections)} detections")
        return packet
    
    def _create_summary(self, detections):
        """Create a human-readable summary"""
        if not detections:
            return "No objects detected"
        
        # Count by class
        class_counts = {}
        for det in detections:
            class_name = det.get("class_name", "unknown")
            class_counts[class_name] = class_counts.get(class_name, 0) + 1
        
        summary_parts = []
        for class_name, count in class_counts.items():
            summary_parts.append(f"{count} {class_name}{'s' if count > 1 else ''}")
        
        return f"Detected: {', '.join(summary_parts)}"