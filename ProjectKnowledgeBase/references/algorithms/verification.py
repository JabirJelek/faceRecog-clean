

# ==============================================
# REFERENCED
# REASON: Simple verification if library is installed
# LEARNING: For checking specific utilization can be utilized
# REFERENCE: If such library existed or not.
# ==============================================


print("Below is the checking for CuDNN availability:")
import torch
print(torch.backends.cudnn.is_available())
print(torch.backends.cudnn.version())
print("="*60)

print("Below is checking for torch with CUDA availability: ")
import torch
print(torch.__version__)
print(torch.cuda.is_available()) # Check for CUDA availability if installed
print("="*60)

print("Below is checking for OpenCV availability:")
import cv2
#print(cv2.getBuildInformation())
print("="*60)

print("Below is checking CUDA availability")
print(torch.version.cuda)