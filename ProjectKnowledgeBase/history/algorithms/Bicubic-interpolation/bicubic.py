# ==============================================
# DEPRECATED 
# REASON: This is only utilized for scaling up the low res image with bicubic calculation
# LEARNINGS: Matemathical calculation can be utilized in upscaling the low res images
# REFERENCE: -
# ==============================================

import cv2
import numpy as np
import math
import sys
import time
from datetime import datetime
from typing import Tuple, Optional, Union

class ImageProcessingError(Exception):
    """Custom exception for image processing errors"""
    pass

class ScaleCalculator:
    """Handles scale factor calculations for image resizing"""
    
    @staticmethod
    def calculate_scale_factor(input_size: Tuple[int, int], 
                              target_size: Tuple[int, int], 
                              mode: str = 'fit', 
                              maintain_aspect: bool = True) -> Union[float, Tuple[float, float]]:
        """
        Calculate scale factor to achieve desired output size.
        
        Parameters:
        -----------
        input_size : tuple
            (height, width) of input image
        target_size : tuple
            (desired_height, desired_width) of output image
        mode : str
            'fit' : scale to fit within target (maintain aspect ratio)
            'fill' : scale to fill target (maintain aspect ratio)
            'stretch' : stretch to exactly match target (ignore aspect ratio)
            'height' : scale based on height only
            'width' : scale based on width only
        maintain_aspect : bool
            Whether to maintain aspect ratio
            
        Returns:
        --------
        float or tuple : Single scale factor or (scale_height, scale_width)
        """
        try:
            input_h, input_w = input_size
            target_h, target_w = target_size
            
            # Validate inputs
            if input_h <= 0 or input_w <= 0:
                raise ValueError(f"Invalid input dimensions: {input_size}")
            if target_h <= 0 or target_w <= 0:
                raise ValueError(f"Invalid target dimensions: {target_size}")
            
            if mode == 'stretch' or not maintain_aspect:
                # Calculate separate scales for height and width
                scale_h = target_h / input_h
                scale_w = target_w / input_w
                return (scale_h, scale_w)
            
            elif mode == 'fit':
                # Scale to fit within target (preserving aspect ratio)
                scale_h = target_h / input_h
                scale_w = target_w / input_w
                scale = min(scale_h, scale_w)  # Use smaller scale to fit within bounds
                return scale
            
            elif mode == 'fill':
                # Scale to fill entire target (preserving aspect ratio)
                scale_h = target_h / input_h
                scale_w = target_w / input_w
                scale = max(scale_h, scale_w)  # Use larger scale to fill bounds
                return scale
            
            elif mode == 'height':
                # Scale based on height only
                scale = target_h / input_h
                return scale
            
            elif mode == 'width':
                # Scale based on width only
                scale = target_w / input_w
                return scale
            
            else:
                raise ValueError(f"Unknown mode: {mode}. Use 'fit', 'fill', 'stretch', 'height', or 'width'.")
                
        except ZeroDivisionError as e:
            raise ValueError("Cannot calculate scale factor: division by zero") from e
        except Exception as e:
            raise ImageProcessingError(f"Error calculating scale factor: {str(e)}") from e

class ImageInterpolator:
    """Main class for bicubic interpolation operations"""
    
    def __init__(self, a: float = -0.5):
        """
        Initialize interpolator with bicubic parameter
        
        Parameters:
        -----------
        a : float
            Bicubic parameter (default -0.5 for Keys' cubic)
        """
        self.a = a
        
    @staticmethod
    def u(s: float, a: float) -> float:
        """
        Bicubic interpolation kernel function
        
        Parameters:
        -----------
        s : float
            Distance from reference point
        a : float
            Bicubic parameter
            
        Returns:
        --------
        float: Weight value
        """
        s_abs = abs(s)
        if 0 <= s_abs <= 1:
            return (a + 2) * (s_abs ** 3) - (a + 3) * (s_abs ** 2) + 1
        elif 1 < s_abs <= 2:
            return a * (s_abs ** 3) - 5 * a * (s_abs ** 2) + 8 * a * s_abs - 4 * a
        return 0.0
    
    @staticmethod
    def padding(img: np.ndarray) -> np.ndarray:
        """
        Pad image with border pixels for interpolation
        
        Parameters:
        -----------
        img : numpy array
            Input image (H, W, C)
            
        Returns:
        --------
        numpy array: Padded image
        """
        if img.ndim != 3:
            raise ValueError(f"Expected 3D image, got {img.ndim}D")
        
        H, W, C = img.shape
        zimg = np.zeros((H + 4, W + 4, C), dtype=img.dtype)
        
        # Copy original image to center
        zimg[2:H + 2, 2:W + 2, :C] = img
        
        # Pad borders
        zimg[2:H + 2, 0:2, :C] = img[:, 0:1, :C]  # Left border
        zimg[H + 2:H + 4, 2:W + 2, :] = img[H - 1:H, :, :]  # Bottom border
        zimg[2:H + 2, W + 2:W + 4, :] = img[:, W - 1:W, :]  # Right border
        zimg[0:2, 2:W + 2, :C] = img[0:1, :, :C]  # Top border
        
        # Pad corners
        zimg[0:2, 0:2, :C] = img[0, 0, :C]  # Top-left
        zimg[H + 2:H + 4, 0:2, :C] = img[H - 1, 0, :C]  # Bottom-left
        zimg[H + 2:H + 4, W + 2:W + 4, :C] = img[H - 1, W - 1, :C]  # Bottom-right
        zimg[0:2, W + 2:W + 4, :C] = img[0, W - 1, :C]  # Top-right
        
        return zimg
    
    @staticmethod
    def optimized_padding(img: np.ndarray, border_size: int = 2, mode: str = 'reflect') -> np.ndarray:
        """
        Enhanced padding using OpenCV's border functions
        
        Parameters:
        -----------
        img : numpy array
            Input image
        border_size : int
            Size of border to add
        mode : str
            Border type: 'reflect', 'replicate', 'constant', 'wrap'
            
        Returns:
        --------
        numpy array: Padded image
        """
        if img.ndim not in [2, 3]:
            raise ValueError(f"Expected 2D or 3D image, got {img.ndim}D")
        
        border_types = {
            'reflect': cv2.BORDER_REFLECT_101,
            'replicate': cv2.BORDER_REPLICATE,
            'constant': cv2.BORDER_CONSTANT,
            'wrap': cv2.BORDER_WRAP
        }
        
        if mode not in border_types:
            raise ValueError(f"Unknown border mode: {mode}")
        
        border_type = border_types[mode]
        
        if mode == 'constant':
            return cv2.copyMakeBorder(img, 
                                     border_size, border_size, 
                                     border_size, border_size, 
                                     border_type, 
                                     value=[0, 0, 0])
        else:
            return cv2.copyMakeBorder(img, 
                                     border_size, border_size, 
                                     border_size, border_size, 
                                     border_type)
    
    def bicubic(self, img: np.ndarray, scale: Union[float, Tuple[float, float]]) -> np.ndarray:
        """
        Bicubic interpolation with flexible scaling
        
        Parameters:
        -----------
        img : numpy array
            Input image (H, W, C)
        scale : float or tuple
            Scale factor(s). If tuple: (scale_height, scale_width)
            
        Returns:
        --------
        numpy array: Interpolated image
        """
        try:
            # Validate input
            if img is None or img.size == 0:
                raise ValueError("Input image is empty")
            
            if img.dtype != np.uint8:
                print(f"Warning: Converting image from {img.dtype} to uint8")
                img = img.astype(np.uint8)
            
            # Get image size
            H, W, C = img.shape
            
            # Determine scale factors
            if isinstance(scale, tuple):
                scale_h, scale_w = scale
                if scale_h <= 0 or scale_w <= 0:
                    raise ValueError(f"Invalid scale factors: {scale}")
            else:
                if scale <= 0:
                    raise ValueError(f"Invalid scale factor: {scale}")
                scale_h = scale_w = scale
            
            # Pad image
            padded_img = self.padding(img)
            
            # Calculate output dimensions
            dH = int(math.floor(H * scale_h))
            dW = int(math.floor(W * scale_w))
            
            if dH <= 0 or dW <= 0:
                raise ValueError(f"Invalid output dimensions: {dH}x{dW}")
            
            # Initialize output
            dst = np.zeros((dH, dW, C), dtype=np.float32)
            
            # Step sizes
            h_h = 1.0 / scale_h
            h_w = 1.0 / scale_w
            
            print(f'Starting bicubic interpolation...')
            print(f'Input: {H}x{W}x{C} -> Output: {dH}x{dW}x{C}')
            print(f'Scale: Height={scale_h:.2f}x, Width={scale_w:.2f}x')
            
            total_pixels = C * dH * dW
            progress = ProgressBar(total_pixels, prefix='Processing:')
            
            pixel_count = 0
            for c in range(C):
                for j in range(dH):
                    y = j * h_h + 2  # Account for padding
                    
                    # Calculate y-related values
                    y_floor = math.floor(y)
                    y1 = 1 + y - y_floor
                    y2 = y - y_floor
                    y3 = y_floor + 1 - y
                    y4 = y_floor + 2 - y
                    
                    for i in range(dW):
                        x = i * h_w + 2  # Account for padding
                        
                        # Calculate x-related values
                        x_floor = math.floor(x)
                        x1 = 1 + x - x_floor
                        x2 = x - x_floor
                        x3 = x_floor + 1 - x
                        x4 = x_floor + 2 - x
                        
                        # Calculate kernel weights
                        u_x1 = self.u(x1, self.a)
                        u_x2 = self.u(x2, self.a)
                        u_x3 = self.u(x3, self.a)
                        u_x4 = self.u(x4, self.a)
                        
                        u_y1 = self.u(y1, self.a)
                        u_y2 = self.u(y2, self.a)
                        u_y3 = self.u(y3, self.a)
                        u_y4 = self.u(y4, self.a)
                        
                        # Get 4x4 neighborhood
                        neighborhood = np.array([
                            [padded_img[int(y - y1), int(x - x1), c], padded_img[int(y - y2), int(x - x1), c],
                             padded_img[int(y + y3), int(x - x1), c], padded_img[int(y + y4), int(x - x1), c]],
                            [padded_img[int(y - y1), int(x - x2), c], padded_img[int(y - y2), int(x - x2), c],
                             padded_img[int(y + y3), int(x - x2), c], padded_img[int(y + y4), int(x - x2), c]],
                            [padded_img[int(y - y1), int(x + x3), c], padded_img[int(y - y2), int(x + x3), c],
                             padded_img[int(y + y3), int(x + x3), c], padded_img[int(y + y4), int(x + x3), c]],
                            [padded_img[int(y - y1), int(x + x4), c], padded_img[int(y - y2), int(x + x4), c],
                             padded_img[int(y + y3), int(x + x4), c], padded_img[int(y + y4), int(x + x4), c]]
                        ])
                        
                        # Calculate interpolation
                        mat_l = np.array([[u_x1, u_x2, u_x3, u_x4]])
                        mat_r = np.array([[u_y1], [u_y2], [u_y3], [u_y4]])
                        
                        result = np.dot(np.dot(mat_l, neighborhood), mat_r)
                        dst[j, i, c] = result.item()
                        
                        pixel_count += 1
                        progress.update(pixel_count)
            
            progress.finish()
            
            # Clip and convert to uint8
            dst = np.clip(dst, 0, 255).astype(np.uint8)
            
            return dst
            
        except Exception as e:
            raise ImageProcessingError(f"Error during bicubic interpolation: {str(e)}") from e
    
    def resize_to_target(self, img: np.ndarray, target_size: Tuple[int, int], 
                        mode: str = 'fit') -> np.ndarray:
        """
        Resize image to target size using bicubic interpolation
        
        Parameters:
        -----------
        img : numpy array
            Input image
        target_size : tuple
            (target_height, target_width) desired output size
        mode : str
            Scaling mode: 'fit', 'fill', 'stretch'
            
        Returns:
        --------
        numpy array: Resized image
        """
        try:
            input_size = img.shape[:2]
            scale = ScaleCalculator.calculate_scale_factor(input_size, target_size, mode=mode)
            
            print(f"Target size: {target_size[0]}x{target_size[1]}")
            print(f"Calculated scale: {scale}")
            
            return self.bicubic(img, scale)
            
        except Exception as e:
            raise ImageProcessingError(f"Error resizing to target: {str(e)}") from e

class ProgressBar:
    """Progress bar with time estimation"""
    
    def __init__(self, total: int, prefix: str = 'Progress:', length: int = 50):
        """
        Initialize progress bar
        
        Parameters:
        -----------
        total : int
            Total number of iterations
        prefix : str
            Prefix string
        length : int
            Length of progress bar in characters
        """
        self.total = total
        self.prefix = prefix
        self.length = length
        self.start_time = time.time()
        self.last_update = 0
        
    def update(self, iteration: int):
        """Update progress bar"""
        current_time = time.time()
        if current_time - self.last_update < 0.1 and iteration < self.total:
            return
            
        progress = iteration / self.total
        filled_length = int(self.length * progress)
        bar = '█' * filled_length + '░' * (self.length - filled_length)
        
        # Calculate ETA
        elapsed = current_time - self.start_time
        if progress > 0:
            eta = elapsed * (1 - progress) / progress
            eta_str = f"ETA: {eta:.1f}s"
        else:
            eta_str = "ETA: --"
            
        # Calculate processing rate
        rate = iteration / elapsed if elapsed > 0 else 0
        
        sys.stderr.write(f'\r{self.prefix} |{bar}| {progress*100:6.2f}% '
                        f'[{rate:.1f} iter/s] {eta_str}')
        sys.stderr.flush()
        self.last_update = current_time
        
    def finish(self):
        """Finish progress bar"""
        elapsed = time.time() - self.start_time
        sys.stderr.write(f'\r{self.prefix} |{"█" * self.length}| 100.00% '
                        f'[{self.total/elapsed:.1f} iter/s] Completed in {elapsed:.2f}s\n')
        sys.stderr.flush()

class ImageQualityMetrics:
    """Calculate image quality metrics"""
    
    @staticmethod
    def calculate_psnr(original: np.ndarray, processed: np.ndarray) -> float:
        """
        Calculate Peak Signal-to-Noise Ratio
        
        Parameters:
        -----------
        original : numpy array
            Original image
        processed : numpy array
            Processed image
            
        Returns:
        --------
        float: PSNR value in dB
        """
        if original.shape != processed.shape:
            # Resize processed to match original
            processed = cv2.resize(processed, (original.shape[1], original.shape[0]))
        
        mse = np.mean((original.astype(float) - processed.astype(float)) ** 2)
        if mse == 0:
            return float('inf')
        
        psnr = 20 * math.log10(255.0 / math.sqrt(mse))
        return psnr
    
    @staticmethod
    def calculate_ssim(original: np.ndarray, processed: np.ndarray) -> float:
        """
        Calculate Structural Similarity Index
        
        Parameters:
        -----------
        original : numpy array
            Original image
        processed : numpy array
            Processed image
            
        Returns:
        --------
        float: SSIM value (0 to 1)
        """
        if original.shape != processed.shape:
            processed = cv2.resize(processed, (original.shape[1], original.shape[0]))
        
        # Convert to grayscale for SSIM
        if len(original.shape) == 3:
            original_gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
            processed_gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
        else:
            original_gray = original
            processed_gray = processed
        
        # Simple SSIM calculation
        C1 = (0.01 * 255) ** 2
        C2 = (0.03 * 255) ** 2
        
        mu1 = cv2.GaussianBlur(original_gray.astype(np.float32), (11, 11), 1.5)
        mu2 = cv2.GaussianBlur(processed_gray.astype(np.float32), (11, 11), 1.5)
        
        mu1_sq = mu1 ** 2
        mu2_sq = mu2 ** 2
        mu1_mu2 = mu1 * mu2
        
        sigma1_sq = cv2.GaussianBlur(original_gray.astype(np.float32) ** 2, (11, 11), 1.5) - mu1_sq
        sigma2_sq = cv2.GaussianBlur(processed_gray.astype(np.float32) ** 2, (11, 11), 1.5) - mu2_sq
        sigma12 = cv2.GaussianBlur(original_gray.astype(np.float32) * processed_gray.astype(np.float32), (11, 11), 1.5) - mu1_mu2
        
        ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / \
                   ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))
        
        return float(np.mean(ssim_map))

def load_image(image_path: str) -> Optional[np.ndarray]:
    """
    Load image with error handling
    
    Parameters:
    -----------
    image_path : str
        Path to image file
        
    Returns:
    --------
    numpy array or None: Loaded image
    """
    try:
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Cannot load image from {image_path}")
        
        print(f"Successfully loaded image: {img.shape[1]}x{img.shape[0]} pixels")
        return img
        
    except Exception as e:
        print(f"Error loading image: {str(e)}")
        return None

def save_image(image: np.ndarray, filename: str) -> bool:
    """
    Save image with error handling
    
    Parameters:
    -----------
    image : numpy array
        Image to save
    filename : str
        Output filename
        
    Returns:
    --------
    bool: True if successful
    """
    try:
        success = cv2.imwrite(filename, image)
        if success:
            print(f"Image saved successfully: {filename}")
        else:
            print(f"Failed to save image: {filename}")
        return success
    except Exception as e:
        print(f"Error saving image: {str(e)}")
        return False

def main():
    """Main function with comprehensive error handling"""
    try:
        print("=" * 60)
        print("BICUBIC INTERPOLATION TOOL")
        print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        # Load image
        image_path = r'C:\raihan\dokumen\project\data-embed\current_database-Copy\Alvin\face_1768901825563_pos9207_d1_c0.745.jpg'
        # image_path = 'butterfly.png'  # Using a simpler test image
        
        img = load_image(image_path)
        if img is None:
            return
        
        # Create interpolator
        interpolator = ImageInterpolator(a=-0.5)
        
        # print("\n" + "=" * 60)
        # print("TEST 1: Fixed scale factor (2x)")
        # print("=" * 60)
        
        # # Test 1: Fixed scale factor
        # try:
        #     result1 = interpolator.bicubic(img, scale=2.0)
        #     save_image(result1, 'bicubic_2x.png')
        #     print(f"Output size: {result1.shape[0]}x{result1.shape[1]}")
        # except Exception as e:
        #     print(f"Error in fixed scale test: {str(e)}")
        
        print("\n" + "=" * 60)
        print("TEST 2: Resize to target dimensions")
        print("=" * 60)
        
        # Test 2: Target dimensions
        targets = [(224, 224)#, 
                    #(480, 640), 
                    #(1080, 1920)
                    ]
        
        for target_size in targets:
            print(f"\nTarget: {target_size[0]}x{target_size[1]}")
            
            for mode in ['fit', 'fill', 'stretch']:
                print(f"\n  Mode: {mode}")
                try:
                    result = interpolator.resize_to_target(img, target_size, mode=mode)
                    output_size = result.shape[:2]
                    print(f"  Output: {output_size[0]}x{output_size[1]}")
                    
                    filename = f'bicubic_{target_size[0]}x{target_size[1]}_{mode}.png'
                    save_image(result, filename)
                    
                    # Calculate quality metrics if original is available
                    if mode == 'stretch':
                        # For comparison, resize original to same size using OpenCV
                        original_resized = cv2.resize(img, (output_size[1], output_size[0]))
                        psnr = ImageQualityMetrics.calculate_psnr(original_resized, result)
                        ssim = ImageQualityMetrics.calculate_ssim(original_resized, result)
                        print(f"  Quality: PSNR={psnr:.2f}dB, SSIM={ssim:.4f}")
                        
                except Exception as e:
                    print(f"  Error: {str(e)}")
        
        print("\n" + "=" * 60)
        print("ALL TESTS COMPLETED")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()