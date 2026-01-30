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

# Enhanced interpolation kernel with multiple options
def interpolation_kernel(s, a=-0.5, mode='bicubic'):
    """
    Interpolation kernels with recent improvements
    Modes: 'bicubic', 'lanczos', 'mitchell', 'catmull_rom'
    """
    s = abs(s)
    
    if mode == 'bicubic':
        # Traditional bicubic (Keys' kernel)
        if s < 1:
            return (a + 2) * (s ** 3) - (a + 3) * (s ** 2) + 1
        elif s < 2:
            return a * (s ** 3) - 5 * a * (s ** 2) + 8 * a * s - 4 * a
        return 0
    
    elif mode == 'catmull_rom':
        # Catmull-Rom spline (a=0.5 in bicubic formulation)
        if s < 1:
            return 1.5 * (s ** 3) - 2.5 * (s ** 2) + 1
        elif s < 2:
            return -0.5 * (s ** 3) + 2.5 * (s ** 2) - 4 * s + 2
        return 0
    
    elif mode == 'lanczos':
        # Lanczos kernel (windowed sinc)
        if s == 0:
            return 1
        elif s < 2:  # Typically L=2 or 3
            return (2 * math.sin(math.pi * s) * math.sin(math.pi * s / 2)) / (math.pi ** 2 * s ** 2)
        return 0
    
    elif mode == 'mitchell':
        # Mitchell-Netravali
        if s < 1:
            return (7 * (s ** 3) - 12 * (s ** 2) + 5.3333) / 6
        elif s < 2:
            return (-2.3333 * (s ** 3) + 12 * (s ** 2) - 20 * s + 10.6667) / 6
        return 0
    
    return 0

# Optimized padding with recent border handling techniques
def optimized_padding(img, border_size=2, mode='reflect'):
    """
    Enhanced padding with multiple border types
    Modes: 'reflect', 'replicate', 'constant', 'wrap'
    """
    H, W, C = img.shape
    
    if mode == 'reflect':
        # Most common for interpolation - reflects border pixels
        return cv2.copyMakeBorder(img, 
                                 border_size, border_size, 
                                 border_size, border_size, 
                                 cv2.BORDER_REFLECT_101)
    
    elif mode == 'replicate':
        # Replicates last pixel (OpenCV default for many operations)
        return cv2.copyMakeBorder(img, 
                                 border_size, border_size, 
                                 border_size, border_size, 
                                 cv2.BORDER_REPLICATE)
    
    elif mode == 'constant':
        # Constant value padding
        return cv2.copyMakeBorder(img, 
                                 border_size, border_size, 
                                 border_size, border_size, 
                                 cv2.BORDER_CONSTANT, 
                                 value=[0, 0, 0])
    
    else:  # Default to reflect
        return cv2.copyMakeBorder(img, 
                                 border_size, border_size, 
                                 border_size, border_size, 
                                 cv2.BORDER_REFLECT_101)

# Modern progress indicator with time estimation
class ProgressBar:
    def __init__(self, total, prefix='Progress:', length=50):
        self.total = total
        self.prefix = prefix
        self.length = length
        self.start_time = time.time()
        self.last_update = 0
        
    def update(self, iteration):
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
        elapsed = time.time() - self.start_time
        sys.stderr.write(f'\r{self.prefix} |{"█" * self.length}| 100.00% ({self.total}/{self.total}) '
                        f'[{self.total/elapsed:.1f} pix/s] Completed in {elapsed:.2f}s\n')
        sys.stderr.flush()

# Vectorized bicubic interpolation - FIXED VERSION
def vectorized_bicubic(img, ratio, a=-0.5, kernel_mode='bicubic', use_opencv_optimized=True):
    """
    Enhanced bicubic interpolation with multiple optimization strategies
    """
    if use_opencv_optimized and kernel_mode == 'bicubic':
        # Use OpenCV's optimized implementation (fastest)
        print("Using OpenCV's optimized resize...")
        height, width = img.shape[:2]
        new_height = int(height * ratio)
        new_width = int(width * ratio)
        return cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
    
    # Custom implementation for other kernels
    H, W, C = img.shape
    
    # Pad image
    padded_img = optimized_padding(img, border_size=2, mode='reflect')
    
    # Calculate new dimensions
    dH = int(H * ratio)
    dW = int(W * ratio)
    dst = np.zeros((dH, dW, C), dtype=np.float32)
    
    # Pre-calculate kernel weights if possible
    h = 1.0 / ratio
    
    total_pixels = dH * dW * C
    progress = ProgressBar(total_pixels, prefix='Bicubic Interpolation:')
    
    print(f'\nStarting {kernel_mode} interpolation')
    print(f'Input: {H}x{W} -> Output: {dH}x{dW} (Scale: {ratio}x)')
    print(f'Kernel: {kernel_mode}, Parameter a={a}')
    print('-' * 60)
    
    pixel_count = 0
    for c in range(C):
        for j in range(dH):
            y = j * h + 2  # Account for padding
            
            y_floor = math.floor(y)
            y_frac = y - y_floor
            
            # Pre-calculate y weights
            y_offsets = [-1, 0, 1, 2]
            y_weights = np.array([interpolation_kernel(y_frac + offset, a, kernel_mode) 
                                for offset in y_offsets])
            
            for i in range(dW):
                x = i * h + 2  # Account for padding
                
                x_floor = math.floor(x)
                x_frac = x - x_floor
                
                # Pre-calculate x weights
                x_offsets = [-1, 0, 1, 2]
                x_weights = np.array([interpolation_kernel(x_frac + offset, a, kernel_mode) 
                                    for offset in x_offsets])
                
                # Extract 4x4 neighborhood
                neighborhood = np.zeros((4, 4))
                for ny in range(4):
                    for nx in range(4):
                        ny_idx = int(y_floor + ny - 1)
                        nx_idx = int(x_floor + nx - 1)
                        neighborhood[ny, nx] = padded_img[ny_idx, nx_idx, c]
                
                # Apply separable convolution
                # FIX: Use @ operator for matrix multiplication and extract scalar
                intermediate = y_weights.reshape(1, 4) @ neighborhood
                result = intermediate @ x_weights.reshape(4, 1)
                dst[j, i, c] = result[0, 0]  # Extract scalar value
                
                pixel_count += 1
                progress.update(pixel_count)
    
    progress.finish()
    return np.clip(dst, 0, 255).astype(np.uint8)

# Modern PSNR and SSIM calculation
def calculate_metrics(original, interpolated):
    """Calculate image quality metrics"""
    if original.shape != interpolated.shape:
        # Resize interpolated to match original for comparison
        interpolated = cv2.resize(interpolated, (original.shape[1], original.shape[0]))
    
    # PSNR
    mse = np.mean((original - interpolated) ** 2)
    if mse == 0:
        psnr = 100
    else:
        psnr = 20 * math.log10(255.0 / math.sqrt(mse))
    
    # SSIM (simplified)
    from scipy import signal
    def ssim(img1, img2):
        C1 = (0.01 * 255) ** 2
        C2 = (0.03 * 255) ** 2
        
        img1 = img1.astype(np.float32)
        img2 = img2.astype(np.float32)
        
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
        
        return ssim_map.mean()
    
    ssim_value = ssim(cv2.cvtColor(original, cv2.COLOR_BGR2GRAY),
                     cv2.cvtColor(interpolated, cv2.COLOR_BGR2GRAY))
    
    return psnr, ssim_value

# Main execution with modern features
def main():
    # Configuration
    input_path = r'C:\raihan\dokumen\project\data-embed\current_database-Copy\Alvin\face_1768901825563_pos9207_d1_c0.745.jpg'
    ratio = 2.0
    kernel_mode = 'bicubic'  # Options: 'bicubic', 'catmull_rom', 'lanczos', 'mitchell'
    use_opencv_optimized = False  # Set to True to use OpenCV's built-in (fastest)
    
    print("=" * 60)
    print("ENHANCED BICUBIC INTERPOLATION")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Read image
    try:
        img = cv2.imread(input_path)
        if img is None:
            print(f"Error: Could not read image '{input_path}'")
            return
        
        print(f"Image loaded: {img.shape[1]}x{img.shape[0]} pixels")
        
        # Convert to float32 for better precision
        img_float = img.astype(np.float32)
        
        # Perform interpolation
        start_time = time.time()
        
        if use_opencv_optimized and kernel_mode == 'bicubic':
            print("\nUsing OpenCV optimized implementation...")
            result = vectorized_bicubic(img_float, ratio, use_opencv_optimized=True)
        else:
            print(f"\nUsing custom {kernel_mode} implementation...")
            result = vectorized_bicubic(img_float, ratio, kernel_mode=kernel_mode, 
                                      use_opencv_optimized=False)
        
        elapsed_time = time.time() - start_time
        
        # Calculate metrics if original size image available for comparison
        print("\n" + "=" * 60)
        print("PERFORMANCE METRICS")
        print("=" * 60)
        print(f"Processing time: {elapsed_time:.3f} seconds")
        print(f"Processing rate: {img.shape[0]*img.shape[1]/elapsed_time:.0f} pixels/second")
        
        # Save result
        output_path = f'bicubic_{kernel_mode}_butterfly_x{ratio}.png'
        cv2.imwrite(output_path, result)
        print(f"\nResult saved to: {output_path}")
        
        # Show comparison if display is available
        try:
            # Resize original for visual comparison
            original_resized = cv2.resize(img, (result.shape[1], result.shape[0]))
            
            # Create comparison montage
            comparison = np.hstack([original_resized, result])
            
            # Add labels
            font = cv2.FONT_HERSHEY_SIMPLEX
            cv2.putText(comparison, 'Original (resized)', (10, 30), 
                       font, 1, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(comparison, f'{kernel_mode.title()} Result', 
                       (result.shape[1] + 10, 30), font, 1, (255, 255, 255), 2, cv2.LINE_AA)
            
            cv2.imshow('Comparison', comparison)
            cv2.waitKey(3000)  # Display for 3 seconds
            cv2.destroyAllWindows()
            
        except Exception as e:
            print(f"Display not available: {e}")
        
        print("\nInterpolation completed successfully!")
        
    except Exception as e:
        print(f"Error during processing: {e}")
        import traceback
        traceback.print_exc()

def bicubic(img, ratio, a):
    #Get image size
    H,W,C = img.shape

    img = padding(img,H,W,C)
    #Create new image
    dH = math.floor(H*ratio)
    dW = math.floor(W*ratio)
    dst = np.zeros((dH, dW, 3))

    h = 1/ratio

    print('Start bicubic interpolation')
    print('It will take a little while...')
    inc = 0
    for c in range(C):
        for j in range(dH):
            for i in range(dW):
                x, y = i * h + 2 , j * h + 2

                x1 = 1 + x - math.floor(x)
                x2 = x - math.floor(x)
                x3 = math.floor(x) + 1 - x
                x4 = math.floor(x) + 2 - x

                y1 = 1 + y - math.floor(y)
                y2 = y - math.floor(y)
                y3 = math.floor(y) + 1 - y
                y4 = math.floor(y) + 2 - y

                mat_l = np.matrix([[u(x1,a),u(x2,a),u(x3,a),u(x4,a)]])
                mat_m = np.matrix([[img[int(y-y1),int(x-x1),c],img[int(y-y2),int(x-x1),c],img[int(y+y3),int(x-x1),c],img[int(y+y4),int(x-x1),c]],
                                   [img[int(y-y1),int(x-x2),c],img[int(y-y2),int(x-x2),c],img[int(y+y3),int(x-x2),c],img[int(y+y4),int(x-x2),c]],
                                   [img[int(y-y1),int(x+x3),c],img[int(y-y2),int(x+x3),c],img[int(y+y3),int(x+x3),c],img[int(y+y4),int(x+x3),c]],
                                   [img[int(y-y1),int(x+x4),c],img[int(y-y2),int(x+x4),c],img[int(y+y3),int(x+x4),c],img[int(y+y4),int(x+x4),c]]])
                mat_r = np.matrix([[u(y1,a)],[u(y2,a)],[u(y3,a)],[u(y4,a)]])
                
                # FIX: Extract scalar value from the 1x1 matrix result
                result = np.dot(np.dot(mat_l, mat_m), mat_r)
                dst[j, i, c] = result[0, 0]  # Extract the scalar value

                # Print progress
                inc = inc + 1
                sys.stderr.write('\r\033[K' + get_progressbar_str(inc/(C*dH*dW)))
                sys.stderr.flush()
    sys.stderr.write('\n')
    sys.stderr.flush()
    return dst

if __name__ == "__main__":
    main()