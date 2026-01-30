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
from typing import Tuple, Optional, Union, Dict, Any
from scipy import signal
from scipy.ndimage import convolve

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

# Enhanced interpolation kernel for 16x16 neighborhood
def interpolation_kernel_16x16(s: float, a: float = -0.5, mode: str = 'bicubic', L: int = 8) -> float:
    """
    Interpolation kernels for 16x16 neighborhood
    Modes: 'bicubic', 'lanczos', 'mitchell', 'catmull_rom', 'gaussian', 'sinc'
    L: Support size (for kernels that need it)
    """
    s_abs = abs(s)
    
    if mode == 'bicubic':
        # Extended bicubic kernel for 16x16 (support up to 8)
        if s_abs < 1:
            return (a + 2) * (s_abs ** 3) - (a + 3) * (s_abs ** 2) + 1
        elif s_abs < 2:
            return a * (s_abs ** 3) - 5 * a * (s_abs ** 2) + 8 * a * s_abs - 4 * a
        elif s_abs < 3:
            # Extended cubic (experimental)
            return 0.5 * a * (s_abs ** 3) - 2.5 * a * (s_abs ** 2) + 4 * a * s_abs - 2 * a
        elif s_abs < 4:
            return 0.25 * a * (s_abs ** 3) - 1.25 * a * (s_abs ** 2) + 2 * a * s_abs - a
        return 0
    
    elif mode == 'catmull_rom':
        # Extended Catmull-Rom for 16x16
        if s_abs < 1:
            return 1.5 * (s_abs ** 3) - 2.5 * (s_abs ** 2) + 1
        elif s_abs < 2:
            return -0.5 * (s_abs ** 3) + 2.5 * (s_abs ** 2) - 4 * s_abs + 2
        elif s_abs < 3:
            return 0.1667 * (s_abs ** 3) - 1.5 * (s_abs ** 2) + 4.3333 * s_abs - 3
        elif s_abs < 4:
            return -0.0417 * (s_abs ** 3) + 0.5 * (s_abs ** 2) - 2.0 * s_abs + 2.6667
        return 0
    
    elif mode == 'lanczos':
        # Lanczos kernel with configurable L (support size)
        if s_abs == 0:
            return 1
        elif s_abs < L:
            return (L * math.sin(math.pi * s_abs) * math.sin(math.pi * s_abs / L)) / \
                   (math.pi ** 2 * s_abs ** 2)
        return 0
    
    elif mode == 'lanczos2':
        # Two-lobe Lanczos (standard)
        return interpolation_kernel_16x16(s_abs, a, 'lanczos', L=2)
    
    elif mode == 'lanczos3':
        # Three-lobe Lanczos
        return interpolation_kernel_16x16(s_abs, a, 'lanczos', L=3)
    
    elif mode == 'lanczos4':
        # Four-lobe Lanczos
        return interpolation_kernel_16x16(s_abs, a, 'lanczos', L=4)
    
    elif mode == 'mitchell':
        # Extended Mitchell-Netravali
        if s_abs < 1:
            return (7 * (s_abs ** 3) - 12 * (s_abs ** 2) + 5.3333) / 6
        elif s_abs < 2:
            return (-2.3333 * (s_abs ** 3) + 12 * (s_abs ** 2) - 20 * s_abs + 10.6667) / 6
        elif s_abs < 3:
            return (0.3889 * (s_abs ** 3) - 3.5 * (s_abs ** 2) + 10.5 * s_abs - 10.5) / 6
        elif s_abs < 4:
            return (-0.0556 * (s_abs ** 3) + 0.6667 * (s_abs ** 2) - 2.6667 * s_abs + 3.5556) / 6
        return 0
    
    elif mode == 'gaussian':
        # Gaussian kernel
        sigma = 1.5
        return math.exp(-(s_abs ** 2) / (2 * sigma ** 2))
    
    elif mode == 'sinc':
        # Sinc function kernel
        if s_abs == 0:
            return 1
        else:
            return math.sin(math.pi * s_abs) / (math.pi * s_abs)
    
    elif mode == 'blackman':
        # Blackman windowed sinc
        if s_abs == 0:
            return 1
        elif s_abs < L:
            window = 0.42 + 0.5 * math.cos(math.pi * s_abs / L) + \
                     0.08 * math.cos(2 * math.pi * s_abs / L)
            return window * math.sin(math.pi * s_abs) / (math.pi * s_abs)
        return 0
    
    else:
        raise ValueError(f"Unknown kernel mode: {mode}")

# Optimized padding for 16x16 neighborhood
def optimized_padding_16x16(img: np.ndarray, border_size: int = 8, mode: str = 'reflect') -> np.ndarray:
    """
    Enhanced padding for 16x16 neighborhood with multiple border types
    Modes: 'reflect', 'replicate', 'constant', 'wrap', 'mirror'
    """
    if len(img.shape) == 2:
        H, W = img.shape
        C = 1
        img = img.reshape(H, W, 1)
    else:
        H, W, C = img.shape
    
    border_types = {
        'reflect': cv2.BORDER_REFLECT_101,
        'replicate': cv2.BORDER_REPLICATE,
        'constant': cv2.BORDER_CONSTANT,
        'wrap': cv2.BORDER_WRAP,
        'mirror': cv2.BORDER_REFLECT
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

# Modern progress indicator with time estimation
class ProgressBar:
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
        """Update progress bar with time estimation"""
        current_time = time.time()
        if current_time - self.last_update < 0.1 and iteration < self.total:  # Update max 10Hz
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
        
        sys.stderr.write(f'\r{self.prefix} |{bar}| {progress*100:6.2f}% ({iteration}/{self.total}) '
                        f'[{rate:.1f} pix/s] {eta_str}')
        sys.stderr.flush()
        self.last_update = current_time
        
    def finish(self):
        """Finish progress bar"""
        elapsed = time.time() - self.start_time
        sys.stderr.write(f'\r{self.prefix} |{"█" * self.length}| 100.00% ({self.total}/{self.total}) '
                        f'[{self.total/elapsed:.1f} pix/s] Completed in {elapsed:.2f}s\n')
        sys.stderr.flush()

class ImageInterpolator16x16:
    """Main class for 16x16 neighborhood interpolation operations"""
    
    def __init__(self, a: float = -0.5, kernel_mode: str = 'lanczos4', 
                 neighborhood_size: int = 16):
        """
        Initialize interpolator with configurable parameters
        
        Parameters:
        -----------
        a : float
            Bicubic parameter (default -0.5 for Keys' cubic)
        kernel_mode : str
            Interpolation kernel mode
        neighborhood_size : int
            Size of neighborhood (should be 16 for 16x16)
        """
        self.a = a
        self.kernel_mode = kernel_mode
        self.neighborhood_size = neighborhood_size
        self.half_size = neighborhood_size // 2
        
    def get_kernel_weight(self, s: float) -> float:
        """
        Get interpolation kernel weight for current mode
        
        Parameters:
        -----------
        s : float
            Distance from reference point
            
        Returns:
        --------
        float: Weight value
        """
        return interpolation_kernel_16x16(s, self.a, self.kernel_mode)
    
    def generate_kernel_matrix(self, x_frac: float, y_frac: float) -> np.ndarray:
        """
        Generate 16x16 kernel matrix for given fractional positions
        
        Parameters:
        -----------
        x_frac : float
            Fractional part in x direction
        y_frac : float
            Fractional part in y direction
            
        Returns:
        --------
        np.ndarray: 16x16 kernel matrix
        """
        kernel = np.zeros((self.neighborhood_size, self.neighborhood_size))
        
        for j in range(self.neighborhood_size):
            dy = (j - self.half_size + 0.5) - y_frac
            y_weight = self.get_kernel_weight(dy)
            
            for i in range(self.neighborhood_size):
                dx = (i - self.half_size + 0.5) - x_frac
                x_weight = self.get_kernel_weight(dx)
                
                kernel[j, i] = x_weight * y_weight
        
        # Normalize kernel to sum to 1
        kernel_sum = np.sum(kernel)
        if kernel_sum != 0:
            kernel /= kernel_sum
        
        return kernel
    
    def optimized_padding(self, img: np.ndarray, mode: str = 'reflect') -> np.ndarray:
        """
        Enhanced padding for 16x16 neighborhood
        
        Parameters:
        -----------
        img : numpy array
            Input image
        mode : str
            Border type
            
        Returns:
        --------
        numpy array: Padded image
        """
        return optimized_padding_16x16(img, border_size=self.half_size, mode=mode)
    
    def interpolate_pixel(self, padded_img: np.ndarray, x: float, y: float, 
                         channel: int = 0) -> float:
        """
        Interpolate single pixel using 16x16 neighborhood
        
        Parameters:
        -----------
        padded_img : numpy array
            Padded input image
        x : float
            X coordinate (including fractional part)
        y : float
            Y coordinate (including fractional part)
        channel : int
            Color channel index
            
        Returns:
        --------
        float: Interpolated pixel value
        """
        # Integer and fractional parts
        x_int = int(math.floor(x))
        y_int = int(math.floor(y))
        x_frac = x - x_int
        y_frac = y - y_int
        
        # Generate kernel for this fractional position
        kernel = self.generate_kernel_matrix(x_frac, y_frac)
        
        # Extract 16x16 neighborhood
        y_start = y_int - self.half_size + 1
        x_start = x_int - self.half_size + 1
        
        if len(padded_img.shape) == 3:
            neighborhood = padded_img[y_start:y_start + self.neighborhood_size,
                                      x_start:x_start + self.neighborhood_size,
                                      channel]
        else:
            neighborhood = padded_img[y_start:y_start + self.neighborhood_size,
                                      x_start:x_start + self.neighborhood_size]
        
        # Apply convolution
        result = np.sum(neighborhood * kernel)
        
        return result
    
    def vectorized_interpolation_16x16(self, img: np.ndarray, ratio: float, 
                                      use_fast_method: bool = False) -> np.ndarray:
        """
        Enhanced interpolation using 16x16 neighborhood
        
        Parameters:
        -----------
        img : numpy array
            Input image
        ratio : float
            Scale ratio
        use_fast_method : bool
            Whether to use optimized method when available
            
        Returns:
        --------
        numpy array: Interpolated image
        """
        # For certain modes, use OpenCV's optimized implementation
        if use_fast_method and self.kernel_mode in ['bicubic', 'lanczos2']:
            print("Using OpenCV's optimized resize...")
            height, width = img.shape[:2]
            new_height = int(height * ratio)
            new_width = int(width * ratio)
            
            if self.kernel_mode == 'bicubic':
                return cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
            else:
                # For lanczos2, we can use INTER_LANCZOS4 which is similar
                return cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)
        
        # Custom 16x16 implementation
        if len(img.shape) == 2:
            H, W = img.shape
            C = 1
            img_reshaped = img.reshape(H, W, 1)
        else:
            H, W, C = img.shape
            img_reshaped = img.copy()
        
        # Pad image
        print(f"Padding image for {self.neighborhood_size}x{self.neighborhood_size} neighborhood...")
        padded_img = self.optimized_padding(img_reshaped, mode='reflect')
        
        # Calculate new dimensions
        dH = int(H * ratio)
        dW = int(W * ratio)
        
        if C == 1:
            dst = np.zeros((dH, dW), dtype=np.float32)
        else:
            dst = np.zeros((dH, dW, C), dtype=np.float32)
        
        # Step size
        h = 1.0 / ratio
        
        total_pixels = dH * dW * C
        progress = ProgressBar(total_pixels, 
                              prefix=f'{self.kernel_mode.title()} 16x16 Interpolation:')
        
        print(f'\nStarting {self.kernel_mode} interpolation with 16x16 neighborhood')
        print(f'Input: {H}x{W} -> Output: {dH}x{dW} (Scale: {ratio:.2f}x)')
        print(f'Kernel: {self.kernel_mode}, Neighborhood: {self.neighborhood_size}x{self.neighborhood_size}')
        print(f'Half size: {self.half_size}')
        print('-' * 60)
        
        pixel_count = 0
        start_time = time.time()
        
        # Pre-compute kernels for different fractional positions (cache)
        kernel_cache = {}
        frac_steps = 8  # Cache for 8x8 fractional positions
        for fy in range(frac_steps):
            y_frac = fy / frac_steps
            for fx in range(frac_steps):
                x_frac = fx / frac_steps
                key = (fx, fy)
                kernel_cache[key] = self.generate_kernel_matrix(x_frac, y_frac)
        
        for c in range(C):
            for j in range(dH):
                y = j * h + self.half_size  # Account for padding
                
                y_int = int(math.floor(y))
                y_frac = y - y_int
                fy_idx = int(y_frac * frac_steps) % frac_steps
                
                for i in range(dW):
                    x = i * h + self.half_size  # Account for padding
                    
                    x_int = int(math.floor(x))
                    x_frac = x - x_int
                    fx_idx = int(x_frac * frac_steps) % frac_steps
                    
                    # Get cached kernel or compute new one
                    key = (fx_idx, fy_idx)
                    if key in kernel_cache:
                        kernel = kernel_cache[key]
                    else:
                        kernel = self.generate_kernel_matrix(x_frac, y_frac)
                        kernel_cache[key] = kernel
                    
                    # Extract 16x16 neighborhood
                    y_start = y_int - self.half_size + 1
                    x_start = x_int - self.half_size + 1
                    
                    if C == 1:
                        neighborhood = padded_img[y_start:y_start + self.neighborhood_size,
                                                  x_start:x_start + self.neighborhood_size]
                    else:
                        neighborhood = padded_img[y_start:y_start + self.neighborhood_size,
                                                  x_start:x_start + self.neighborhood_size, c]
                    
                    # Apply convolution
                    result = np.sum(neighborhood * kernel)
                    
                    if C == 1:
                        dst[j, i] = result
                    else:
                        dst[j, i, c] = result
                    
                    pixel_count += 1
                    if pixel_count % 100 == 0:
                        progress.update(pixel_count)
        
        progress.finish()
        elapsed_time = time.time() - start_time
        print(f"Total processing time: {elapsed_time:.2f} seconds")
        print(f"Pixels per second: {total_pixels / elapsed_time:.0f}")
        
        # Clip and convert
        dst = np.clip(dst, 0, 255).astype(np.uint8)
        
        return dst
    
    def resize_to_target(self, img: np.ndarray, target_size: Tuple[int, int], 
                        mode: str = 'fit', use_fast_method: bool = False) -> np.ndarray:
        """
        Resize image to target size using 16x16 interpolation
        
        Parameters:
        -----------
        img : numpy array
            Input image
        target_size : tuple
            (target_height, target_width) desired output size
        mode : str
            Scaling mode: 'fit', 'fill', 'stretch'
        use_fast_method : bool
            Whether to use fast method when available
            
        Returns:
        --------
        numpy array: Resized image
        """
        try:
            input_size = img.shape[:2]
            scale = ScaleCalculator.calculate_scale_factor(input_size, target_size, mode=mode)
            
            print(f"Target size: {target_size[0]}x{target_size[1]}")
            print(f"Calculated scale: {scale}")
            print(f"Using kernel: {self.kernel_mode} with {self.neighborhood_size}x{self.neighborhood_size} neighborhood")
            
            if isinstance(scale, tuple):
                # For different scales in height and width
                print("Note: Different scales for height and width - using average scale")
                scale_avg = (scale[0] + scale[1]) / 2
                return self.vectorized_interpolation_16x16(img, scale_avg, use_fast_method)
            else:
                return self.vectorized_interpolation_16x16(img, scale, use_fast_method)
            
        except Exception as e:
            raise ImageProcessingError(f"Error resizing to target: {str(e)}") from e

class ImageQualityMetrics:
    """Enhanced image quality metrics calculation"""
    
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
        
        # Enhanced SSIM calculation using scipy
        C1 = (0.01 * 255) ** 2
        C2 = (0.03 * 255) ** 2
        
        img1 = original_gray.astype(np.float32)
        img2 = processed_gray.astype(np.float32)
        
        kernel = cv2.getGaussianKernel(11, 1.5)
        window = np.outer(kernel, kernel.transpose())
        
        mu1 = signal.convolve2d(img1, window, mode='valid')
        mu2 = signal.convolve2d(img2, window, mode='valid')
        
        mu1_sq = mu1 ** 2
        mu2_sq = mu2 ** 2
        mu1_mu2 = mu1 * mu2
        
        sigma1_sq = signal.convolve2d(img1 * img1, window, mode='valid') - mu1_sq
        sigma2_sq = signal.convolve2d(img2 * img2, window, mode='valid') - mu2_sq
        sigma12 = signal.convolve2d(img1 * img2, window, mode='valid') - mu1_mu2
        
        ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / \
                   ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))
        
        return float(np.mean(ssim_map))
    
    @staticmethod
    def calculate_mse(original: np.ndarray, processed: np.ndarray) -> float:
        """
        Calculate Mean Squared Error
        
        Parameters:
        -----------
        original : numpy array
            Original image
        processed : numpy array
            Processed image
            
        Returns:
        --------
        float: MSE value
        """
        if original.shape != processed.shape:
            processed = cv2.resize(processed, (original.shape[1], original.shape[0]))
        
        return np.mean((original.astype(float) - processed.astype(float)) ** 2)
    
    @staticmethod
    def calculate_metrics(original: np.ndarray, interpolated: np.ndarray) -> Dict[str, float]:
        """
        Calculate multiple image quality metrics
        
        Parameters:
        -----------
        original : numpy array
            Original image
        interpolated : numpy array
            Interpolated image
            
        Returns:
        --------
        dict: Dictionary containing PSNR, SSIM, and MSE
        """
        return {
            'psnr': ImageQualityMetrics.calculate_psnr(original, interpolated),
            'ssim': ImageQualityMetrics.calculate_ssim(original, interpolated),
            'mse': ImageQualityMetrics.calculate_mse(original, interpolated)
        }

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

def create_comparison_montage(original: np.ndarray, results: Dict[str, np.ndarray], 
                             scale: float = 1.0) -> np.ndarray:
    """
    Create visual comparison montage with multiple interpolation methods
    
    Parameters:
    -----------
    original : numpy array
        Original image
    results : dict
        Dictionary of interpolation results
    scale : float
        Scale factor for display
        
    Returns:
    --------
    numpy array: Montage image
    """
    # Resize original for comparison
    H, W = original.shape[:2]
    display_H = int(H * scale)
    display_W = int(W * scale)
    
    original_resized = cv2.resize(original, (display_W, display_H))
    
    # Create montage grid
    n_methods = len(results)
    cols = min(3, n_methods + 1)  # Include original
    rows = (n_methods + 1 + cols - 1) // cols
    
    cell_height = display_H
    cell_width = display_W
    
    montage = np.zeros((rows * cell_height, cols * cell_width, 3), dtype=np.uint8)
    
    # Place original
    montage[0:cell_height, 0:cell_width] = original_resized
    
    # Add label for original
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(montage, 'Original', (10, 30), 
               font, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    
    # Place results
    for idx, (method, result_img) in enumerate(results.items()):
        row = (idx + 1) // cols
        col = (idx + 1) % cols
        
        y_start = row * cell_height
        x_start = col * cell_width
        
        # Resize result for display
        result_display = cv2.resize(result_img, (display_W, display_H))
        montage[y_start:y_start + cell_height, x_start:x_start + cell_width] = result_display
        
        # Add label
        label_y = y_start + 30
        cv2.putText(montage, method, (x_start + 10, label_y), 
                   font, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    
    return montage

def benchmark_interpolation_methods(img: np.ndarray, ratio: float = 2.0) -> Dict[str, Dict]:
    """
    Benchmark different interpolation methods
    
    Parameters:
    -----------
    img : numpy array
        Input image
    ratio : float
        Scale ratio
        
    Returns:
    --------
    dict: Benchmark results
    """
    print("\n" + "=" * 60)
    print("BENCHMARKING INTERPOLATION METHODS")
    print("=" * 60)
    
    methods = [
        ('bicubic', 'bicubic'),
        ('lanczos2', 'lanczos2'),
        ('lanczos3', 'lanczos3'),
        ('lanczos4', 'lanczos4'),
        ('catmull_rom', 'catmull_rom'),
        ('mitchell', 'mitchell'),
        ('gaussian', 'gaussian')
    ]
    
    results = {}
    
    for method_name, kernel_mode in methods:
        print(f"\nTesting {method_name}...")
        
        try:
            # Create interpolator
            interpolator = ImageInterpolator16x16(kernel_mode=kernel_mode, neighborhood_size=16)
            
            # Time the interpolation
            start_time = time.time()
            result = interpolator.vectorized_interpolation_16x16(img, ratio, use_fast_method=False)
            elapsed_time = time.time() - start_time
            
            # Calculate quality metrics
            original_resized = cv2.resize(img, (result.shape[1], result.shape[0]))
            metrics = ImageQualityMetrics.calculate_metrics(original_resized, result)
            
            # Store results
            results[method_name] = {
                'image': result,
                'time': elapsed_time,
                'metrics': metrics,
                'kernel': kernel_mode
            }
            
            print(f"  Time: {elapsed_time:.3f} seconds")
            print(f"  PSNR: {metrics['psnr']:.2f} dB")
            print(f"  SSIM: {metrics['ssim']:.4f}")
            print(f"  MSE: {metrics['mse']:.2f}")
            
            # Save image
            save_image(result, f'interpolation_{method_name}_16x16.png')
            
        except Exception as e:
            print(f"  Error: {str(e)}")
    
    return results

def main():
    """Main function with comprehensive error handling and 16x16 interpolation"""
    try:
        print("=" * 80)
        print("16x16 NEIGHBORHOOD INTERPOLATION TOOL")
        print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        # Load image
        image_path = r'C:\raihan\dokumen\project\data-embed\current_database-Copy\Alvin\face_1768901825563_pos9207_d1_c0.745.jpg'
        
        img = load_image(image_path)
        if img is None:
            print("Using test pattern instead...")
            # Create a test pattern if image loading fails
            img = np.zeros((256, 256, 3), dtype=np.uint8)
            for i in range(256):
                for j in range(256):
                    img[i, j] = [i % 256, j % 256, (i + j) % 256]
        
        print(f"Image size: {img.shape[1]}x{img.shape[0]}")
        
        # Benchmark different methods
        benchmark_results = benchmark_interpolation_methods(img, ratio=2.0)
        
        # Create comparison montage
        if benchmark_results:
            result_images = {k: v['image'] for k, v in benchmark_results.items()}
            montage = create_comparison_montage(img, result_images, scale=0.5)
            save_image(montage, 'interpolation_comparison_16x16.png')
            print("\nComparison montage saved as 'interpolation_comparison_16x16.png'")
        
        # Test target resizing with different modes
        print("\n" + "=" * 60)
        print("TESTING TARGET RESIZING WITH 16x16 LANCZOS4")
        print("=" * 60)
        
        interpolator = ImageInterpolator16x16(kernel_mode='lanczos4', neighborhood_size=16)
        
        targets = [(224, 224)#, 
                    #(480, 640),
                     #(1080, 1920)
                     ]
        
        for target_size in targets:
            print(f"\nTarget: {target_size[0]}x{target_size[1]}")
            
            for mode in ['fit', 'fill']:
                print(f"\n  Mode: {mode}")
                try:
                    result = interpolator.resize_to_target(img, target_size, mode=mode, use_fast_method=False)
                    output_size = result.shape[:2]
                    print(f"  Output: {output_size[0]}x{output_size[1]}")
                    
                    filename = f'16x16_lanczos4_{target_size[0]}x{target_size[1]}_{mode}.png'
                    save_image(result, filename)
                    
                    # For comparison, resize original to same size using OpenCV
                    original_resized = cv2.resize(img, (output_size[1], output_size[0]))
                    metrics = ImageQualityMetrics.calculate_metrics(original_resized, result)
                    print(f"  Quality: PSNR={metrics['psnr']:.2f}dB, SSIM={metrics['ssim']:.4f}")
                    
                except Exception as e:
                    print(f"  Error: {str(e)}")
        
        # Display summary
        print("\n" + "=" * 80)
        print("BENCHMARK SUMMARY")
        print("=" * 80)
        
        if benchmark_results:
            print("\nRanking by PSNR (higher is better):")
            sorted_by_psnr = sorted(benchmark_results.items(), 
                                   key=lambda x: x[1]['metrics']['psnr'], 
                                   reverse=True)
            for i, (method, data) in enumerate(sorted_by_psnr):
                print(f"{i+1}. {method}: PSNR={data['metrics']['psnr']:.2f} dB, "
                      f"Time={data['time']:.2f}s")
            
            print("\nRanking by SSIM (higher is better):")
            sorted_by_ssim = sorted(benchmark_results.items(), 
                                   key=lambda x: x[1]['metrics']['ssim'], 
                                   reverse=True)
            for i, (method, data) in enumerate(sorted_by_ssim):
                print(f"{i+1}. {method}: SSIM={data['metrics']['ssim']:.4f}, "
                      f"Time={data['time']:.2f}s")
        
        print("\n" + "=" * 80)
        print("ALL TESTS COMPLETED")
        print("=" * 80)
        
        # Display final result if possible
        try:
            if benchmark_results:
                # Show the best method by PSNR
                best_method = sorted_by_psnr[0][0]
                best_image = benchmark_results[best_method]['image']
                
                # Create comparison with original
                original_resized = cv2.resize(img, (best_image.shape[1], best_image.shape[0]))
                comparison = np.hstack([original_resized, best_image])
                
                # Add labels
                font = cv2.FONT_HERSHEY_SIMPLEX
                cv2.putText(comparison, 'Original (OpenCV resize)', (10, 30), 
                           font, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.putText(comparison, f'Best: {best_method} 16x16', 
                           (original_resized.shape[1] + 10, 30), 
                           font, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
                
                cv2.imshow(f'Best Result: {best_method} 16x16', comparison)
                cv2.waitKey(5000)  # Display for 5 seconds
                cv2.destroyAllWindows()
                
        except Exception as e:
            print(f"Display not available: {e}")
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()