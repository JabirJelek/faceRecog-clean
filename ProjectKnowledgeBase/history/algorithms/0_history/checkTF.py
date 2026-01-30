import sys
print(f"Python {sys.version}")
print(f"Python architecture: {sys.maxsize > 2**32 and '64-bit' or '32-bit'}")

# Check TensorFlow if it can load
try:
    import tensorflow as tf
    print(f"TensorFlow {tf.__version__}")
    print("SUCCESS: TensorFlow loaded!")
except Exception as e:
    print(f"FAILED: {e}")
    