# Image Processing & Quality Checks

This document provides detailed explanations of all image preprocessing techniques and quality checks used in the Lab Extraction System.

---

## Overview

The system uses a two-stage approach:

1. **Quality Gate** - Evaluate image quality BEFORE processing (reject unreadable images early)
2. **Preprocessing** - Apply corrections to improve extraction accuracy

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Upload Image  │────▶│  Quality Gate   │────▶│  Preprocessing  │
└─────────────────┘     └────────┬────────┘     └────────┬────────┘
                                 │                       │
                        ┌────────▼────────┐     ┌────────▼────────┐
                        │ REJECT if poor  │     │ Vision Extract  │
                        └─────────────────┘     └─────────────────┘
```

---

## Part 1: Quality Checks (OCR Quality Gate)

**File:** `workers/extraction/ocr_quality.py`

The quality gate prevents wasted API calls on unreadable images by checking multiple metrics.

### 1.1 Resolution Check

**Purpose:** Ensure image has sufficient pixels for text recognition.

| Metric | Threshold | Description |
|--------|-----------|-------------|
| Minimum dimension | 400px | Smallest side must be at least 400 pixels |

**Why it matters:** Low-resolution images lose fine details like decimal points and small characters that are critical in lab values.

---

### 1.2 Blur Detection (Laplacian Variance)

**Purpose:** Detect out-of-focus or motion-blurred images.

**Algorithm:**
```
1. Apply Laplacian kernel (edge detector):
   [0,  1, 0]
   [1, -4, 1]
   [0,  1, 0]

2. Calculate variance of the result
3. Higher variance = sharper edges = less blur
```

| Score | Quality |
|-------|---------|
| < 25 | Critically blurry - REJECT |
| < 50 | Very blurry - REJECT |
| 50-100 | Slightly blurry - may proceed with warning |
| > 100 | Acceptable sharpness |
| > 300 | Excellent sharpness |

**Multi-scale Analysis:**
The system also downsamples the image by 2x and recalculates blur. Sharp images lose detail when downsampled, while blurry images stay similarly blurry at all scales. This helps catch consistently blurred images.

---

### 1.3 Text Clarity (Gradient Coherence)

**Purpose:** Detect noisy/degraded scans where text is unreadable.

**How it works:**
1. Calculate image gradients (direction of edges)
2. For clean text, edges align with text strokes (horizontal/vertical)
3. For noisy scans, edges point in random directions

**Coherence Score:**
- Clean text: Gradients align with 0°, 90°, 180°, 270° axes
- Noisy image: Random gradient directions

| Score | Quality |
|-------|---------|
| < 0.25 | CRITICAL - Text completely unreadable |
| < 0.40 | Very low - May be unreadable |
| < 0.55 | Low - OCR accuracy affected |
| > 0.70 | Good clarity |

**Critical Pattern - Noisy Scan Detection:**
```
IF contrast > 85 AND text_clarity < 0.45:
    → REJECT (This is a noisy scan)
```
High contrast + low clarity = grainy/noisy scan that appears sharp but is actually unreadable.

---

### 1.4 Contrast Check

**Purpose:** Ensure sufficient difference between text and background.

| Range | Status | Issue |
|-------|--------|-------|
| < 35 | REJECT | Too low - faded print |
| 35-90 | OK | Acceptable range |
| > 90 | WARNING | Over-processed, may indicate noise |

**Why high contrast is suspicious:** Very high contrast often indicates a scan with noise or artifacts that create false edges.

---

### 1.5 Brightness Check

**Purpose:** Detect images that are too dark or washed out.

| Range | Status | Issue |
|-------|--------|-------|
| < 50 | REJECT | Too dark to read |
| 50-220 | OK | Acceptable range |
| > 220 | REJECT | Washed out / overexposed |

---

### 1.6 Skew Detection (Projection Profile)

**Purpose:** Detect rotated/tilted documents.

**Algorithm:**
1. Convert image to binary (black/white)
2. Try rotating by -15° to +15° in 0.5° steps
3. For each angle, project pixels horizontally
4. Best angle = highest variance in projection (text lines align)

| Skew | Status |
|------|--------|
| < 1° | Excellent |
| 1-5° | OK |
| > 5° | Needs preprocessing correction |

---

### 1.7 Noise Level Estimation

**Purpose:** Detect grainy or speckled images.

**Algorithm:**
1. Calculate local variance in 3x3 windows
2. Noise shows in "blank" areas (low text variance regions)
3. Sample the bottom 10% of variance values
4. Normalize to 0-1 scale

| Level | Status |
|-------|--------|
| < 0.05 | Clean |
| 0.05-0.15 | Acceptable |
| > 0.15 | High noise - needs preprocessing |

---

### 1.8 Text Density Check

**Purpose:** Detect partial documents or mostly blank pages.

**Algorithm:**
1. Calculate edge magnitude (proxy for text presence)
2. Count pixels with strong edges
3. Compute ratio of text-like pixels

| Density | Status |
|---------|--------|
| < 0.03 | Warning - may be partial document |
| > 0.03 | OK |

---

### 1.9 Uniform Region Detection

**Purpose:** Detect scanning issues like shadows or obstructions.

**Algorithm:**
1. Calculate local gradient magnitude
2. Regions with very low variance are "uniform"
3. Compute ratio of uniform pixels

| Ratio | Status |
|-------|--------|
| < 0.8 | OK |
| > 0.8 | Warning - possible scanning issue |

---

### Quality Score Calculation

The final quality score (0.0 to 1.0) is calculated by:

1. Starting at 1.0
2. Subtracting penalties for each issue:
   - Critical (unreadable text): -0.35
   - Severe (dark/washed out): -0.25
   - Medium (blur/skew/noise): -0.20
   - Minor (low density): -0.15
3. Adding bonuses for excellent metrics:
   - High resolution (>1200px): +0.10
   - Ideal contrast (50-80): +0.10
   - Clear text (clarity > 0.7): +0.10

**Acceptance Criteria:**
```
ACCEPT if:
  score >= 0.3
  AND text_clarity >= 0.20
  AND blur_score >= 25
  AND NOT (contrast > 85 AND clarity < 0.45)  // Not a noisy scan
```

---

## Part 2: Image Preprocessing

**File:** `workers/extraction/preprocessing.py`

Preprocessing is applied AFTER the quality gate passes, to further improve extraction accuracy.

### 2.1 Deskew (Rotation Correction)

**Purpose:** Correct tilted scans for better text line detection.

**Algorithm: Hough Line Transform**
1. Convert to grayscale
2. Apply Canny edge detection
3. Detect lines using Hough Transform
4. Calculate median angle of detected lines
5. Rotate image by the inverse of that angle

**Parameters:**
- `minLineLength`: 100px (ignore short edges)
- `maxLineGap`: 10px (connect broken lines)
- Only lines within ±45° of horizontal considered

**Result:** Image rotated so text lines are horizontal.

---

### 2.2 Denoise (Non-Local Means Denoising)

**Purpose:** Remove grain/speckle while preserving edges.

**Algorithm:** `cv2.fastNlMeansDenoisingColored`

Unlike simple blur, Non-Local Means:
1. For each pixel, find similar patches elsewhere in the image
2. Average those similar patches
3. Preserves edges while smoothing uniform areas

**Parameters:**
| Parameter | Value | Purpose |
|-----------|-------|---------|
| h | 6 | Luminance filter strength |
| hColor | 6 | Color filter strength |
| templateWindowSize | 7 | Patch size for comparison |
| searchWindowSize | 21 | Search area for similar patches |

---

### 2.3 Contrast Enhancement (CLAHE)

**Purpose:** Improve text/background separation, especially for uneven lighting.

**Algorithm: Contrast Limited Adaptive Histogram Equalization**

Unlike global contrast adjustment, CLAHE:
1. Divides image into tiles (8x8 grid)
2. Applies histogram equalization to each tile
3. Limits amplification to prevent noise boost
4. Blends tiles to avoid block artifacts

**Why CLAHE for documents:**
- Lab reports often have uneven lighting from folding/scanning
- Global contrast boost would over-saturate bright areas
- CLAHE adapts to local conditions

**Parameters:**
| Parameter | Value | Purpose |
|-----------|-------|---------|
| clipLimit | 2.0 | Limits contrast amplification |
| tileGridSize | 8x8 | Size of local regions |

**Color Space:** Applied only to L channel in LAB color space to avoid color distortion.

---

### 2.4 Binarization (Optional)

**Purpose:** Convert to pure black/white for very poor quality documents.

**Algorithm:** Adaptive Gaussian Thresholding

1. For each pixel, calculates threshold from weighted mean of neighborhood
2. Gaussian weighting gives more importance to nearby pixels
3. Better than global thresholding for uneven lighting

**Parameters:**
| Parameter | Value | Purpose |
|-----------|-------|---------|
| blockSize | 11 | Neighborhood size |
| C | 2 | Constant subtracted from mean |

**Note:** Binarization is disabled by default because the Vision API handles color images well. Only enable for severely degraded documents.

---

### 2.5 Sharpness Enhancement

**Purpose:** Make text edges more defined.

**Algorithm:** PIL ImageEnhance.Sharpness

**Factor:** 1.5 (50% increase in sharpness)

**Applied:** After all other preprocessing as a final polish.

---

### 2.6 Basic Preprocessing Fallback

If advanced preprocessing fails, the system falls back to PIL-only operations:

1. **Auto Contrast:** `ImageOps.autocontrast(cutoff=2%)` - stretches histogram
2. **Sharpness:** 1.5x enhancement
3. **Contrast Boost:** 1.2x enhancement

---

## Preprocessing Pipeline Order

The default pipeline runs in this order:

```
1. Load image (OpenCV)
2. Convert BGR → RGB
3. Deskew (Hough Transform)
4. Denoise (Non-Local Means)
5. Enhance Contrast (CLAHE)
6. [Optional] Binarize
7. Convert to PIL Image
8. Enhance Sharpness
9. Return preprocessed image
```

---

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `target_dpi` | 300 | Target resolution (higher = better but slower) |
| `deskew_enabled` | True | Auto-correct rotation |
| `denoise_enabled` | True | Apply noise reduction |
| `contrast_enhance_enabled` | True | Enhance contrast with CLAHE |
| `binarize_enabled` | False | Convert to black/white |

---

## Usage Examples

### Quality Check Only
```python
from workers.extraction.ocr_quality import evaluate_ocr_quality
from PIL import Image

image = Image.open("lab_report.jpg")
result = evaluate_ocr_quality(image)

if result.is_acceptable:
    print("Image quality OK")
else:
    print(f"Rejected: {result.issues}")
```

### Full Preprocessing
```python
from workers.extraction.preprocessing import preprocess_image

processed = preprocess_image(
    "lab_report.jpg",
    deskew=True,
    denoise=True,
    enhance_contrast=True,
    binarize=False
)
processed.save("processed.jpg")
```

---

## Quality Thresholds Reference

| Metric | Threshold | Action if Failed |
|--------|-----------|------------------|
| Min Resolution | 400px | Reject |
| Blur Score | < 50 | Reject |
| Blur Score Critical | < 25 | Reject immediately |
| Contrast Min | 35 | Needs preprocessing |
| Contrast Max | 90 | Warning (possible noise) |
| Brightness Min | 50 | Needs preprocessing |
| Brightness Max | 220 | Needs preprocessing |
| Text Density Min | 0.03 | Warning |
| Skew Angle Max | 5° | Needs deskew |
| Noise Threshold | 0.15 | Needs denoise |
| Text Clarity Min | 0.25 | Reject |
| Noisy Scan Pattern | contrast>85 & clarity<0.45 | Reject |

---

## Part 3: Backend Image Optimization (On Upload)

**File:** `backend/utils/image_optimizer.py`

When a file is uploaded, the backend performs additional optimizations BEFORE the quality gate. This reduces storage and improves processing speed.

### 3.1 Image Compression

**Purpose:** Reduce file size without significant quality loss.

**Algorithm:** JPEG compression with optimization

| Setting | Value | Purpose |
|---------|-------|---------|
| JPEG Quality | 85 | Balance between quality and size |
| WebP Quality | 85 | Alternative format (disabled by default) |
| Optimize Flag | True | Additional lossless compression |

**Savings:** Typically 40-60% reduction in file size.

---

### 3.2 Smart Resizing (LANCZOS)

**Purpose:** Reduce image dimensions for faster processing.

**Algorithm:** LANCZOS resampling (high-quality downscaling)

| Setting | Value | Purpose |
|---------|-------|---------|
| Max Dimension | 2048px | Gemini doesn't need larger |
| Min Dimension | 500px | Don't resize below this |

**How it works:**
1. Check if max(width, height) > 2048
2. If yes, calculate scale ratio: `2048 / max_dimension`
3. Apply LANCZOS resampling (better than bilinear for text)

**Why LANCZOS:** It uses a sinc-based kernel that preserves sharp edges, ideal for text documents.

---

### 3.3 Color Mode Conversion

**Purpose:** Ensure compatibility with JPEG format.

**Conversions:**
| From | To | Method |
|------|-----|--------|
| RGBA | RGB | Composite on white background |
| P (Palette) | RGB | Direct convert |
| LA (Grayscale+Alpha) | RGB | Composite on white |
| Other | RGB | Direct convert |

**Why white background:** Lab reports typically have white backgrounds, so transparency is replaced with white.

---

### 3.4 Hash-Based Deduplication

**Purpose:** Avoid storing and re-processing duplicate uploads.

**Two Hash Methods:**

**1. SHA-256 (Exact Duplicate Detection)**
```python
# File hash - detects exact byte-for-byte duplicates
hash = hashlib.sha256(file_bytes).hexdigest()
```

**2. Perceptual Hash (pHash) - Similar Image Detection**
```python
# Perceptual hash - detects visually similar images
phash = imagehash.phash(image)
```

**How pHash Works:**
1. Resize image to 32x32
2. Convert to grayscale
3. Apply DCT (Discrete Cosine Transform)
4. Take top-left 8x8 (low frequencies)
5. Generate 64-bit hash from mean comparison

**pHash Properties:**
- Same image at different sizes → Same hash
- Same image with compression → Same hash
- Minor edits → Similar hash (low Hamming distance)

---

### 3.5 Automatic Cleanup Policy

**Purpose:** Manage storage by deleting old files.

| Setting | Value |
|---------|-------|
| Delete originals after | 10 days |
| Delete all after | 90 days |

---

### 3.6 Hash Index

**Purpose:** Fast duplicate lookup without scanning all files.

**Storage:** `.hash_index.json` in the storage directory

```json
{
  "a1b2c3d4...": "report_a1b2c3d4.jpg",
  "e5f6g7h8...": "another_e5f6g7h8.jpg"
}
```

---

## Complete Processing Pipeline

Here's the full flow from upload to extraction:

```
┌─────────────────────────────────────────────────────────────────┐
│                        UPLOAD PHASE                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Receive uploaded file                                       │
│         ↓                                                       │
│  2. Compute SHA-256 hash                                        │
│         ↓                                                       │
│  3. Check for duplicate (hash index)                            │
│         ↓ (if not duplicate)                                    │
│  4. Convert to RGB (handle transparency)                        │
│         ↓                                                       │
│  5. Resize if > 2048px (LANCZOS)                                │
│         ↓                                                       │
│  6. Compress to JPEG (quality 85)                               │
│         ↓                                                       │
│  7. Compute pHash (for similar detection)                       │
│         ↓                                                       │
│  8. Store optimized file + update hash index                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      EXTRACTION PHASE                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  9. Quality Gate (blur, clarity, contrast, etc.)                │
│         ↓ (if acceptable)                                       │
│  10. Preprocessing (deskew, denoise, CLAHE)                     │
│         ↓                                                       │
│  11. Gemini Vision API extraction                               │
│         ↓                                                       │
│  12. Normalization + Validation                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Configuration Reference

### Backend Optimization Config

```python
OptimizationConfig(
    jpeg_quality=85,           # 0-100
    webp_quality=85,           # 0-100
    use_webp=False,            # WebP vs JPEG
    max_dimension=2048,        # Resize limit
    min_dimension=500,         # Don't resize below
    delete_originals_after_days=10,
    delete_processed_after_days=90,
    enable_deduplication=True
)
```

### Preprocessing Config

```python
ImagePreprocessor(
    target_dpi=300,
    deskew_enabled=True,
    denoise_enabled=True,
    contrast_enhance_enabled=True,
    binarize_enabled=False
)
```

### Quality Thresholds Config

```python
QUALITY_THRESHOLDS = {
    'min_resolution': 400,
    'blur_score': 50,
    'blur_score_critical': 25,
    'contrast_min': 35,
    'contrast_max': 90,
    'brightness_min': 50,
    'brightness_max': 220,
    'text_density_min': 0.03,
    'skew_angle_max': 5.0,
    'noise_threshold': 0.15
}
```
