# base64_viewer.py

"""
Standalone Base64 Image Viewer for ImageLogger generated files.
"""

import json
import base64
import cv2
import numpy as np
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

class Base64ImageViewer:
    """Viewer for base64 encoded images from ImageLogger JSON files."""
    
    def __init__(self):
        self.current_file = None
        self.current_image = None
        self.json_data = None
        self.window_name = "Base64 Image Viewer"
        
    def load_json_file(self, file_path: str) -> bool:
        """
        Load and parse a base64 JSON file.
        
        Args:
            file_path: Path to the JSON file
            
        Returns:
            bool: True if successful
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.json_data = json.load(f)
            
            self.current_file = file_path
            
            # Extract base64 image data
            base64_string = self.json_data.get('image_data', '')
            if not base64_string:
                print("❌ No image data found in JSON file")
                return False
            
            # Decode base64 to image
            image_bytes = base64.b64decode(base64_string)
            np_array = np.frombuffer(image_bytes, np.uint8)
            self.current_image = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
            
            if self.current_image is None:
                print("❌ Failed to decode image from base64")
                return False
            
            print(f"✅ Successfully loaded: {Path(file_path).name}")
            print(f"   Resolution: {self.current_image.shape[1]}x{self.current_image.shape[0]}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error loading JSON file: {e}")
            return False
    
    def display_metadata(self) -> str:
        """Extract and format metadata for display."""
        if not self.json_data:
            return "No metadata available"
        
        metadata_text = []
        
        # Basic file info
        metadata_text.append(f"File: {self.json_data.get('filename', 'N/A')}")
        metadata_text.append(f"Timestamp: {self.json_data.get('timestamp', 'N/A')}")
        metadata_text.append(f"Format: {self.json_data.get('image_format', 'N/A')}")
        
        # Resolution
        resolution = self.json_data.get('resolution', {})
        metadata_text.append(f"Resolution: {resolution.get('width', 'N/A')}x{resolution.get('height', 'N/A')}")
        
        # Additional metadata
        metadata = self.json_data.get('metadata', {})
        if metadata:
            metadata_text.append("\n--- VIOLATION METADATA ---")
            metadata_text.append(f"Total Faces: {metadata.get('total_faces', 'N/A')}")
            metadata_text.append(f"Violations: {metadata.get('violation_count', 'N/A')}")
            
            violations = metadata.get('violations', [])
            if violations:
                metadata_text.append("\nViolators:")
                for i, violator in enumerate(violations, 1):
                    metadata_text.append(f"  {i}. {violator.get('identity', 'Unknown')}")
                    metadata_text.append(f"     Mask Confidence: {violator.get('mask_confidence', 0):.3f}")
                    metadata_text.append(f"     Recognition Confidence: {violator.get('recognition_confidence', 0):.3f}")
        
        return "\n".join(metadata_text)
    
    def draw_metadata_overlay(self, image: np.ndarray) -> np.ndarray:
        """Draw metadata overlay on the image."""
        if self.current_image is None:
            return image
        
        overlay = image.copy()
        h, w = overlay.shape[:2]
        
        # Create semi-transparent background for text
        text_bg = np.zeros((h, 400, 3), dtype=np.uint8)
        overlay[10:10 + text_bg.shape[0], 10:10 + text_bg.shape[1]] = text_bg
        
        metadata_lines = self.display_metadata().split('\n')
        
        # Draw each line of metadata
        y_offset = 40
        for line in metadata_lines:
            if line.strip():
                cv2.putText(overlay, line, (20, y_offset), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                y_offset += 20
        
        return overlay
    
    def show_image(self):
        """Display the loaded image with metadata."""
        if self.current_image is None:
            print("❌ No image loaded")
            return
        
        # Create image with metadata overlay
        display_image = self.draw_metadata_overlay(self.current_image)
        
        # Resize for display if too large
        h, w = display_image.shape[:2]
        max_display_size = 1200
        if w > max_display_size or h > max_display_size:
            scale = min(max_display_size / w, max_display_size / h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            display_image = cv2.resize(display_image, (new_w, new_h))
        
        # Display image
        cv2.imshow(self.window_name, display_image)
        
        # Print metadata to console
        print("\n" + "="*60)
        print("IMAGE METADATA")
        print("="*60)
        print(self.display_metadata())
        print("="*60)
        print("\nControls:")
        print("  's' - Save image as JPEG")
        print("  'm' - Toggle metadata overlay")
        print("  'q' or ESC - Quit")
        print("  Any other key - Load next file in directory")
    
    def save_current_image(self, output_path: str = None):
        """Save the current image as JPEG."""
        if self.current_image is None:
            print("❌ No image to save")
            return False
        
        try:
            if output_path is None:
                if self.current_file:
                    base_name = Path(self.current_file).stem
                    output_path = f"{base_name}_decoded.jpg"
                else:
                    output_path = "decoded_base64_image.jpg"
            
            success = cv2.imwrite(output_path, self.current_image)
            if success:
                print(f"💾 Image saved: {output_path}")
                return True
            else:
                print(f"❌ Failed to save image: {output_path}")
                return False
                
        except Exception as e:
            print(f"❌ Error saving image: {e}")
            return False
    
    def find_json_files(self, directory: str) -> List[str]:
        """Find all JSON files in directory and subdirectories."""
        json_files = []
        directory_path = Path(directory)
        
        # Search in base64 subdirectories
        search_patterns = [
            "**/base64/**/*.json",
            "**/*.json"  # Fallback to any JSON file
        ]
        
        for pattern in search_patterns:
            found_files = list(directory_path.glob(pattern))
            if found_files:
                json_files.extend([str(f) for f in found_files])
                break
        
        # Remove duplicates and sort
        json_files = sorted(list(set(json_files)))
        return json_files
    
    def browse_and_load(self):
        """Open file dialog to browse and load JSON files."""
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        
        file_path = filedialog.askopenfilename(
            title="Select Base64 JSON File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if file_path:
            success = self.load_json_file(file_path)
            if success:
                self.show_image()
                return file_path
        
        return None

def main():
    """Main function for standalone base64 viewer."""
    viewer = Base64ImageViewer()
    
    print("🔍 Base64 Image Viewer")
    print("=" * 50)
    
    # Check if file path provided as command line argument
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if os.path.isfile(file_path):
            success = viewer.load_json_file(file_path)
            if success:
                viewer.show_image()
            else:
                print(f"❌ Failed to load: {file_path}")
                return
        else:
            print(f"❌ File not found: {file_path}")
            return
    else:
        # Interactive file selection
        print("Select a Base64 JSON file to view...")
        file_path = viewer.browse_and_load()
        if not file_path:
            print("❌ No file selected. Exiting.")
            return
    
    # Get directory for navigation
    current_dir = Path(file_path).parent
    all_json_files = viewer.find_json_files(str(current_dir))
    current_index = all_json_files.index(file_path) if file_path in all_json_files else -1
    
    show_overlay = True
    
    # Main interaction loop
    while True:
        key = cv2.waitKey(0) & 0xFF
        
        if key == 27 or key == ord('q'):  # ESC or 'q'
            break
            
        elif key == ord('s'):  # Save image
            viewer.save_current_image()
            
        elif key == ord('m'):  # Toggle metadata overlay
            show_overlay = not show_overlay
            if show_overlay:
                display_image = viewer.draw_metadata_overlay(viewer.current_image)
            else:
                display_image = viewer.current_image.copy()
            cv2.imshow(viewer.window_name, display_image)
            print(f"📊 Metadata overlay: {'ON' if show_overlay else 'OFF'}")
        
        else:  # Load next file
            if current_index >= 0 and all_json_files:
                current_index = (current_index + 1) % len(all_json_files)
                next_file = all_json_files[current_index]
                success = viewer.load_json_file(next_file)
                if success:
                    viewer.show_image()
                else:
                    print(f"❌ Failed to load next file: {next_file}")
    
    cv2.destroyAllWindows()
    print("👋 Viewer closed.")

def batch_convert_directory():
    """Batch convert all base64 JSON files in a directory to images."""
    viewer = Base64ImageViewer()
    
    root = tk.Tk()
    root.withdraw()
    
    directory = filedialog.askdirectory(title="Select Directory with Base64 JSON Files")
    if not directory:
        return
    
    json_files = viewer.find_json_files(directory)
    if not json_files:
        print("❌ No JSON files found in directory")
        return
    
    print(f"🔍 Found {len(json_files)} JSON files")
    
    output_dir = Path(directory) / "decoded_images"
    output_dir.mkdir(exist_ok=True)
    
    success_count = 0
    for json_file in json_files:
        try:
            if viewer.load_json_file(json_file):
                output_path = output_dir / f"{Path(json_file).stem}.jpg"
                if viewer.save_current_image(str(output_path)):
                    success_count += 1
        except Exception as e:
            print(f"❌ Error processing {Path(json_file).name}: {e}")
    
    print(f"✅ Successfully converted {success_count}/{len(json_files)} files")
    print(f"📁 Output directory: {output_dir}")

if __name__ == "__main__":
    print("Base64 Image Viewer")
    print("1. Single file viewer")
    print("2. Batch convert directory")
    
    choice = input("Choose option (1 or 2): ").strip()
    
    if choice == "2":
        batch_convert_directory()
    else:
        main()