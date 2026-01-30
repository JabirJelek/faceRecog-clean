import cv2
import numpy as np
import time
import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import pipeline components
from pipeline.core.orchestrator import PipelineOrchestrator
from pipeline.processors.input_adapter import InputAdapter
from pipeline.processors.detector import YOLODetector
from pipeline.processors.visualizer import DetectionVisualizer
from pipeline.processors.output_adapter import OutputAdapter

def create_yolo_pipeline(model_name="yolov8n.pt"):
    """Create a YOLO-based object detection pipeline"""
    print(f"Creating YOLO object detection pipeline with model: {model_name}")
    
    # Create orchestrator
    pipeline = PipelineOrchestrator("YOLOPipeline")
    
    # Create processors with configurations
    input_adapter = InputAdapter("input_adapter")
    
    # Configure YOLO detector
    yolo_config = {
        "model_name": model_name,
        "confidence_threshold": 0.25,
        "iou_threshold": 0.45
    }
    detector = YOLODetector("yolo_detector", yolo_config)
    
    # Configure visualizer
    visualizer_config = {
        "colors": {
            "person": (0, 255, 0),       # Green
            "car": (255, 0, 0),          # Blue
            "truck": (0, 255, 255),      # Yellow
            "bus": (0, 165, 255),        # Orange
            "motorcycle": (255, 0, 255), # Purple
            "bicycle": (0, 128, 255),    # Cyan
            "default": (0, 0, 255)       # Red
        },
        "font_scale": 0.6,
        "font_thickness": 2,
        "box_thickness": 2
    }
    visualizer = DetectionVisualizer("visualizer", visualizer_config)
    
    output_adapter = OutputAdapter("output_adapter")
    
    # Add processors to pipeline
    pipeline.add_processor("input", input_adapter)
    pipeline.add_processor("detect", detector)
    pipeline.add_processor("visualize", visualizer)
    pipeline.add_processor("output", output_adapter)
    
    # Set execution order
    pipeline.set_execution_order(["input", "detect", "visualize", "output"])
    
    print("✓ YOLO pipeline created successfully!")
    return pipeline

def test_yolo_with_webcam(model_name="yolov8n.pt"):
    """Test YOLO pipeline with webcam"""
    print(f"\n--- YOLO Webcam Test (Model: {model_name}) ---")
    
    pipeline = create_yolo_pipeline(model_name)
    
    # Open webcam
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("✗ Webcam not available")
        return
    
    # Set webcam resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    print("Webcam opened. Press 'q' to quit, 's' to save frame.")
    
    try:
        frame_count = 0
        fps_history = []
        save_count = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            
            # Skip frames for performance (process every 2nd frame)
            if frame_count % 2 != 0:
                continue
            
            # Process frame
            input_data = {
                "image": frame,
                "source": f"webcam_frame_{frame_count}",
                "timestamp": time.time()
            }
            
            parameters = {
                "confidence_threshold": 0.25,
                "frame_number": frame_count
            }
            
            result = pipeline.execute(input_data, parameters)
            
            # Get visualized image
            if "visualized_image" in result.data:
                display_frame = result.data["visualized_image"]
            else:
                display_frame = frame.copy()
            
            # Get output results
            output = result.output
            detection_count = output.get("detection_count", 0)
            
            # Display performance info
            processing_time_ms = result.metadata.get('total_processing_time_ms', 0)
            
            if processing_time_ms > 0:
                current_fps = 1000.0 / processing_time_ms
                fps_history.append(current_fps)
                
                # Keep only last 30 FPS readings
                if len(fps_history) > 30:
                    fps_history.pop(0)
                
                # Calculate average FPS
                avg_fps = sum(fps_history) / len(fps_history)
                
                # Display FPS
                cv2.putText(display_frame, f"FPS: {avg_fps:.1f}", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Display detection count
            cv2.putText(display_frame, f"Detections: {detection_count}", (10, 60), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Display processing time
            cv2.putText(display_frame, f"Time: {processing_time_ms:.1f}ms", (10, 90), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Display model info
            cv2.putText(display_frame, f"Model: {model_name}", (10, display_frame.shape[0] - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Show frame
            cv2.imshow('YOLO Object Detection', display_frame)
            
            # Handle key presses
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                # Save current frame
                save_count += 1
                filename = f"detection_{save_count}_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
                cv2.imwrite(filename, display_frame)
                print(f"✓ Saved frame to {filename}")
    
    finally:
        cap.release()
        cv2.destroyAllWindows()

def test_yolo_with_image(image_path, model_name="yolov8n.pt"):
    """Test YOLO pipeline with an image file"""
    print(f"\n--- YOLO Image Test (Model: {model_name}) ---")
    
    if not os.path.exists(image_path):
        print(f"✗ Image not found: {image_path}")
        return
    
    pipeline = create_yolo_pipeline(model_name)
    
    input_data = {
        "image": image_path,
        "source": "image_file",
        "timestamp": time.time()
    }
    
    result = pipeline.execute(input_data, {"confidence_threshold": 0.25})
    
    # Display results
    output = result.output
    detections = output.get("detections", [])
    
    print(f"\n=== YOLO Detection Results ===")
    print(f"Image: {image_path}")
    print(f"Model: {model_name}")
    print(f"Detections found: {len(detections)}")
    print(f"Processing time: {result.metadata.get('total_processing_time_ms', 0):.2f} ms")
    
    # Print detection details
    if detections:
        print("\nDetected Objects:")
        for i, det in enumerate(detections, 1):
            print(f"  {i}. {det['class_name']}: {det['confidence']:.2f} at {det['bbox']}")
    
    # Show visualized image
    if "visualized_image" in result.data:
        display_image = result.data["visualized_image"]
        
        # Resize for display if too large
        h, w = display_image.shape[:2]
        if w > 1280 or h > 720:
            scale = min(1280 / w, 720 / h)
            new_w, new_h = int(w * scale), int(h * scale)
            display_image = cv2.resize(display_image, (new_w, new_h))
        
        cv2.imshow(f'YOLO Detection - {os.path.basename(image_path)}', display_image)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
        
        # Ask to save
        save = input("\nSave result image? (y/n): ").strip().lower()
        if save == 'y':
            base_name = os.path.splitext(os.path.basename(image_path))[0]
            save_name = f"{base_name}_yolo_detection.jpg"
            cv2.imwrite(save_name, result.data["visualized_image"])
            print(f"✓ Saved to {save_name}")
    
    return result

def benchmark_yolo_models(image_path=None):
    """Benchmark different YOLO models"""
    print("\n=== YOLO Model Benchmark ===")
    
    # Different YOLO models (from smallest/fastest to largest/most accurate)
    models = [
        ("yolov8n.pt", "YOLOv8 Nano (fastest)"),
        ("yolov8s.pt", "YOLOv8 Small"),
        ("yolov8m.pt", "YOLOv8 Medium"),
        ("yolov8l.pt", "YOLOv8 Large"),
        ("yolov8x.pt", "YOLOv8 XLarge (most accurate)")
    ]
    
    if image_path and os.path.exists(image_path):
        test_image = cv2.imread(image_path)
    else:
        # Create test image
        test_image = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(test_image, "Test Image", (200, 240), 
                   cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
        image_path = "test_benchmark.jpg"
    
    print(f"Testing with image: {image_path}")
    print("\nModel | Detections | Time (ms) | FPS")
    print("-" * 40)
    
    results = []
    
    for model_file, model_desc in models:
        try:
            # Create pipeline with this model
            pipeline = create_yolo_pipeline(model_file)
            
            # Test
            input_data = {"image": test_image, "timestamp": time.time()}
            result = pipeline.execute(input_data, {"confidence_threshold": 0.25})
            
            # Record results
            detections = result.output.get("detections", [])
            proc_time = result.metadata.get('total_processing_time_ms', 0)
            fps = 1000 / proc_time if proc_time > 0 else 0
            
            print(f"{model_desc:20} | {len(detections):10} | {proc_time:8.1f} | {fps:5.1f}")
            results.append((model_desc, len(detections), proc_time, fps))
            
        except Exception as e:
            print(f"{model_desc:20} | ERROR: {str(e)[:30]}")
    
    return results

def main():
    """Main function with YOLO pipeline options"""
    print("=" * 60)
    print("YOLO Object Detection Pipeline")
    print("=" * 60)
    
    # Check if ultralytics is installed
    try:
        import ultralytics
        print(f"✓ Ultralytics YOLO version: {ultralytics.__version__}")
    except ImportError:
        print("\n✗ Ultralytics package not found!")
        print("Please install it with: pip install ultralytics")
        return
    
    while True:
        print("\nChoose an option:")
        print("1. Test with webcam (YOLOv8n)")
        print("2. Test with webcam (choose model)")
        print("3. Test with image file")
        print("4. Benchmark different YOLO models")
        print("5. Exit")
        
        choice = input("\nEnter choice (1-5): ").strip()
        
        if choice == "1":
            test_yolo_with_webcam("yolov8n.pt")
        
        elif choice == "2":
            print("\nAvailable YOLO models:")
            print("1. yolov8n.pt - Nano (fastest)")
            print("2. yolov8s.pt - Small")
            print("3. yolov8m.pt - Medium")
            print("4. yolov8l.pt - Large")
            print("5. yolov8x.pt - XLarge (most accurate)")
            
            model_choice = input("Choose model (1-5, default: 1): ").strip()
            models = ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt"]
            
            if model_choice.isdigit() and 1 <= int(model_choice) <= 5:
                model = models[int(model_choice) - 1]
            else:
                model = "yolov8n.pt"
            
            test_yolo_with_webcam(model)
        
        elif choice == "3":
            image_path = input("Enter image path (or press Enter for sample): ").strip()
            if not image_path:
                # Create sample image
                sample_image = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.rectangle(sample_image, (100, 100), (300, 300), (0, 255, 0), 2)
                cv2.putText(sample_image, "Test Object", (120, 200), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                image_path = "sample_yolo_test.jpg"
                cv2.imwrite(image_path, sample_image)
                print(f"Created sample image: {image_path}")
            
            test_yolo_with_image(image_path)
        
        elif choice == "4":
            image_path = input("Enter image path for benchmarking (or press Enter for default): ").strip()
            if not image_path:
                image_path = None
            benchmark_yolo_models(image_path)
        
        elif choice == "5":
            print("\nExiting YOLO Pipeline...")
            break
        
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()