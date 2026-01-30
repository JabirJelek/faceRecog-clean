import cv2
import numpy as np
import time
from ..core.processor import Processor

class InputAdapter(Processor):
    """Converts input data to a standardized format"""
    def process(self, packet):
        image_data = packet.input.get("image")
        
        # Handle different input types
        if isinstance(image_data, str):
            # Load from file
            image = cv2.imread(image_data)
            if image is None:
                print(f"[InputAdapter] Could not load image from path: {image_data}")
                image = self._create_dummy_image()
        elif isinstance(image_data, np.ndarray):
            # Already an image array
            image = image_data
        elif image_data is None:
            # Create dummy image
            image = self._create_dummy_image()
        else:
            raise ValueError(f"Unsupported image type: {type(image_data)}")
        
        # Store in packet
        packet.data["image"] = image
        packet.data["image_shape"] = image.shape
        packet.data["timestamp"] = packet.input.get("timestamp", time.time())
        
        print(f"[InputAdapter] Loaded image with shape: {image.shape}")
        return packet
    
    def _create_dummy_image(self):
        """Create a dummy test image"""
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(image, "Test Image", (200, 240), 
                   cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
        return image