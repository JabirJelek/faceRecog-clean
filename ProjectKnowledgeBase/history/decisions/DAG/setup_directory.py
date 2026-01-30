import os
import shutil

def setup_project():
    """Setup the complete project structure"""
    
    # Define directory structure
    dirs = [
        "pipeline",
        "pipeline/core",
        "pipeline/processors"
    ]
    
    # Create directories
    for dir_path in dirs:
        os.makedirs(dir_path, exist_ok=True)
        print(f"Created: {dir_path}")
    
    # Create __init__.py files
    init_files = [
        "pipeline/__init__.py",
        "pipeline/core/__init__.py",
        "pipeline/processors/__init__.py"
    ]
    
    for file_path in init_files:
        if not os.path.exists(file_path):
            with open(file_path, "w") as f:
                f.write("# Package initializer\n")
            print(f"Created: {file_path}")
    
    # List of files to create
    files_content = {
        # Core files
        "pipeline/core/context.py": """
class DataPacket:
    def __init__(self):
        self.input = {}
        self.data = {}
        self.parameters = {}
        self.metadata = {}
        self.output = None
""",
        
        "pipeline/core/processor.py": """
class Processor:
    def __init__(self, name, config=None):
        self.name = name
        self.config = config or {}
        self.parameters = {}
    
    def configure(self, params):
        self.parameters.update(params)
    
    def process(self, packet):
        return packet
""",
        
        "pipeline/core/orchestrator.py": """
import time

class PipelineOrchestrator:
    def __init__(self, config=None):
        self.config = config or {}
        self.processors = {}
        self.execution_order = []
        
    def add_processor(self, name, processor):
        self.processors[name] = processor
        
    def set_execution_order(self, order):
        self.execution_order = order
    
    def execute(self, input_data, parameters=None):
        from .context import DataPacket
        
        packet = DataPacket()
        packet.input = input_data
        packet.parameters = parameters or {}
        
        start_time = time.time()
        
        for processor_name in self.execution_order:
            if processor_name not in self.processors:
                continue
                
            processor = self.processors[processor_name]
            
            # Configure with parameters
            processor.configure(packet.parameters)
            
            # Process
            try:
                processor.process(packet)
            except Exception as e:
                print(f"Error in processor {processor_name}: {e}")
                continue
        
        packet.metadata['processing_time'] = (time.time() - start_time) * 1000
        return packet.output
""",
        
        # Processor files
        "pipeline/processors/input_adapter.py": """
import cv2
import numpy as np
import time
from ..core.processor import Processor

class SimpleInputAdapter(Processor):
    def process(self, packet):
        # Get image from input
        image_data = packet.input.get("image")
        
        if isinstance(image_data, str):
            # File path
            image = cv2.imread(image_data)
        elif isinstance(image_data, np.ndarray):
            # Numpy array
            image = image_data
        elif image_data is None:
            # Create dummy image
            image = np.zeros((480, 640, 3), dtype=np.uint8)
        else:
            raise ValueError(f"Unsupported image type: {type(image_data)}")
        
        packet.data["image"] = image
        packet.data["timestamp"] = packet.input.get("timestamp", time.time())
        
        return packet
""",
        
        "pipeline/processors/detector.py": """
import numpy as np
from ..core.processor import Processor

class SimpleDetector(Processor):
    def process(self, packet):
        # Simulate detection
        confidence = self.parameters.get("confidence_threshold", 0.5)
        
        # Create dummy detections
        packet.data["detections"] = [
            {
                "bbox": [100, 100, 200, 200],
                "confidence": 0.8,
                "class": 0,
                "class_name": "person"
            }
        ]
        
        # Check if we have detections
        packet.data["has_detections"] = len(packet.data["detections"]) > 0
        
        return packet
""",
        
        "pipeline/processors/output_adapter.py": """
import time
from ..core.processor import Processor

class SimpleOutputAdapter(Processor):
    def process(self, packet):
        # Create output based on detections
        if packet.data.get("has_detections", False):
            packet.output = {
                "status": "detection",
                "timestamp": packet.data.get("timestamp", time.time()),
                "detections": packet.data.get("detections", []),
                "detection_count": len(packet.data.get("detections", [])),
                "message": "Object detected"
            }
        else:
            packet.output = {
                "status": "no_detection",
                "timestamp": packet.data.get("timestamp", time.time()),
                "detections": [],
                "detection_count": 0,
                "message": "No objects detected"
            }
        
        return packet
""",
        
        # Main application
        "run_pipeline.py": """
import cv2
import numpy as np
import time
import sys
import os

# Add pipeline to path
sys.path.append(os.path.dirname(__file__))

# Import our simple pipeline components
from pipeline.core.orchestrator import PipelineOrchestrator
from pipeline.processors.input_adapter import SimpleInputAdapter
from pipeline.processors.detector import SimpleDetector
from pipeline.processors.output_adapter import SimpleOutputAdapter

def create_simple_pipeline():
    \"\"\"Create and return a simple pipeline\"\"\"
    # Create orchestrator
    pipeline = PipelineOrchestrator()
    
    # Create processors
    input_processor = SimpleInputAdapter("input")
    detector = SimpleDetector("detector")
    output_processor = SimpleOutputAdapter("output")
    
    # Add to pipeline
    pipeline.add_processor("input", input_processor)
    pipeline.add_processor("detector", detector)
    pipeline.add_processor("output", output_processor)
    
    # Set execution order
    pipeline.set_execution_order(["input", "detector", "output"])
    
    return pipeline

def main():
    print("=== Simple Pipeline Demo ===\\n")
    
    # Create pipeline
    pipeline = create_simple_pipeline()
    
    # Test 1: Dummy image
    print("Test 1: Processing dummy image...")
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(dummy_frame, "Test Image", (200, 240), 
               cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
    
    result = pipeline.execute(
        {"image": dummy_frame, "timestamp": time.time()},
        {"confidence_threshold": 0.5}
    )
    
    print(f"Result: {result}\\n")
    
    # Test 2: Webcam (if available)
    print("Test 2: Trying webcam...")
    cap = cv2.VideoCapture(0)
    
    if cap.isOpened():
        print("Webcam opened. Press 'q' to quit.\\n")
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Process frame
                result = pipeline.execute(
                    {"image": frame, "timestamp": time.time()},
                    {"confidence_threshold": 0.5}
                )
                
                # Display result on frame
                cv2.putText(frame, f"Status: {result.get('status', 'N/A')}", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(frame, f"Detections: {result.get('detection_count', 0)}", (10, 60),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                cv2.imshow('Simple Pipeline', frame)
                
                # Check for quit
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        
        finally:
            cap.release()
            cv2.destroyAllWindows()
    else:
        print("Webcam not available. Skipping webcam test.\\n")
    
    print("=== Demo Complete ===")

if __name__ == "__main__":
    main()
"""
    }
    
    # Create files
    for file_path, content in files_content.items():
        with open(file_path, "w") as f:
            f.write(content)
        print(f"Created: {file_path}")
    
    print("\n=== Setup Complete ===")
    print("\nTo run the pipeline:")
    print("1. Install dependencies: pip install numpy opencv-python")
    print("2. Run: python run_pipeline.py")
    print("3. Or run: python simple_pipeline.py")


if __name__ == "__main__":
    setup_project()