

# ==============================================
# DEPRECATED 
# REASON: This only provide the pipeline for creation of mask detector
# LEARNINGS: A pipeline with argument parser is approachable
# REFERENCE: Other pipeline for model creation is saved in google colab
# ==============================================

# import the necessary packages
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.layers import AveragePooling2D, Dropout, Flatten, Dense, Input, RandomFlip, RandomRotation, RandomZoom, Rescaling
from tensorflow.keras.models import Model, Sequential
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
from sklearn.metrics import classification_report
import matplotlib.pyplot as plt
import numpy as np
import argparse
import os

# --- 1. CORRECTED ARGUMENT PARSING ---
ap = argparse.ArgumentParser()
ap.add_argument("-d", "--dataset", required=True, help="path to input dataset")
ap.add_argument("-p", "--plot", type=str, default="plot.png", help="path to output loss/accuracy plot")
ap.add_argument("-m", "--model", type=str, default="mask_detector.keras", help="path to output model")
args = vars(ap.parse_args())
# -------------------------------------

print("[INFO] loading images...")
IMG_SIZE = (224, 224)
BATCH_SIZE = 32  # Slightly increased for efficiency
INIT_LR = 1e-4
EPOCHS = 50  # Set a high maximum, will stop early based on validation

# --- 2. STABLE DATA LOADING ---
# Use the path from the parsed arguments
train_ds, val_ds = tf.keras.utils.image_dataset_from_directory(
    args["dataset"],  # Correctly uses the parsed argument
    validation_split=0.20,
    subset="both",
    seed=42,
    image_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    label_mode='categorical'
)
class_names = train_ds.class_names
print(f"[INFO] Class names: {class_names}")

AUTOTUNE = tf.data.AUTOTUNE
train_ds = train_ds.cache().shuffle(1000).prefetch(buffer_size=AUTOTUNE)
val_ds = val_ds.cache().prefetch(buffer_size=AUTOTUNE)
# -------------------------------------

# --- 3. DATA AUGMENTATION & PREPROCESSING ---
data_augmentation = Sequential([
    RandomFlip("horizontal"),  # No input_shape defined here
    RandomRotation(0.1),
    RandomZoom(0.1),
])
preprocess_rescale = Rescaling(scale=1./127.5, offset=-1)  # For MobileNetV2
# -------------------------------------

# --- 4. MODEL CONSTRUCTION WITH STABLE INITIALIZATION ---
# Define the input tensor separately
inputs = Input(shape=(224, 224, 3))
# Then build MobileNetV2 on top of it
baseModel = MobileNetV2(
    weights="imagenet",
    include_top=False,
    input_tensor=inputs  # Use the predefined input
)

headModel = baseModel.output
headModel = AveragePooling2D(pool_size=(7, 7))(headModel)
headModel = Flatten(name="flatten")(headModel)
# Use He Normal initializer for stability with ReLU[citation:9]
headModel = Dense(128, activation="relu", kernel_initializer='he_normal')(headModel)
headModel = Dropout(0.5)(headModel)
headModel = Dense(len(class_names), activation="softmax")(headModel)

model = Model(inputs=baseModel.input, outputs=headModel)

# Freeze base model
for layer in baseModel.layers:
    layer.trainable = False

# Build the training model with augmentation
inputs = Input(shape=(224, 224, 3))
x = data_augmentation(inputs)
x = preprocess_rescale(x)
x = model(x)
training_model = Model(inputs, x)
# -------------------------------------

# --- 5. COMPILATION WITH OPTIMIZER ---
print("[INFO] compiling model...")
opt = Adam(learning_rate=INIT_LR)
training_model.compile(
    loss="categorical_crossentropy",
    optimizer=opt,
    metrics=["accuracy"]
)
# -------------------------------------

# --- 6. STABILIZING CALLBACKS ---
# Stop training when validation loss doesn't improve, restore best weights[citation:5]
early_stopping = EarlyStopping(
    monitor='val_loss',
    patience=10,
    restore_best_weights=True,
    verbose=1
)
# Save the best model found during training
model_checkpoint = ModelCheckpoint(
    filepath='best_model.keras',
    monitor='val_accuracy',
    save_best_only=True,
    verbose=1
)
# Reduce learning rate when validation loss plateaus[citation:3]
reduce_lr = ReduceLROnPlateau(
    monitor='val_loss',
    factor=0.5,
    patience=5,
    min_lr=1e-7,
    verbose=1
)

callbacks_list = [early_stopping, model_checkpoint, reduce_lr]
# -------------------------------------

# --- 7. STABLE TRAINING ---
print("[INFO] training head...")
H = training_model.fit(
    train_ds,
    validation_data=val_ds,
    epochs=EPOCHS,  # Will stop early due to callback
    callbacks=callbacks_list  # Critical for stability
)
# -------------------------------------

# --- 8. EVALUATION & SAVING ---
print("[INFO] evaluating network...")
# Load the best saved model for final evaluation
best_model = keras.models.load_model('best_model.keras')
predIdxs = best_model.predict(val_ds)
predIdxs = np.argmax(predIdxs, axis=1)

true_labels = np.concatenate([y for x, y in val_ds], axis=0)
true_labels = np.argmax(true_labels, axis=1)

print(classification_report(true_labels, predIdxs, target_names=class_names))

print("[INFO] saving final mask detector model...")
# Save the core model for inference (without augmentation layers)
model.save(args["model"])
# -------------------------------------

# --- 9. PLOTTING (Optional) ---
if args["plot"]:
    N = len(H.history["loss"])
    plt.style.use("ggplot")
    plt.figure()
    plt.plot(np.arange(0, N), H.history["loss"], label="train_loss")
    plt.plot(np.arange(0, N), H.history["val_loss"], label="val_loss")
    plt.plot(np.arange(0, N), H.history["accuracy"], label="train_acc")
    plt.plot(np.arange(0, N), H.history["val_accuracy"], label="val_acc")
    plt.title("Training Loss and Accuracy")
    plt.xlabel("Epoch #")
    plt.ylabel("Loss/Accuracy")
    plt.legend(loc="lower left")
    plt.savefig(args["plot"])
# -------------------------------------