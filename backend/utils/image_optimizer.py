"""
Image Storage Optimization Module.

Features:
- Image compression on upload (JPEG/WebP optimization)
- Smart resizing for large images
- Hash-based deduplication (avoid storing duplicates)
- Automatic cleanup policy for old files
"""

import os
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass

from PIL import Image
import io

# Optional: perceptual hashing for similar image detection
try:
    import imagehash
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class OptimizationConfig:
    """Configuration for image optimization."""
    # Compression settings
    jpeg_quality: int = 85  # 0-100, higher = better quality
    webp_quality: int = 85
    use_webp: bool = False  # WebP offers better compression but less compatibility
    
    # Resize settings
    max_dimension: int = 2048  # Max width/height (Gemini doesn't need larger)
    min_dimension: int = 500   # Don't resize below this
    
    # Cleanup settings
    delete_originals_after_days: int = 30  # Delete originals after processing
    delete_processed_after_days: int = 90  # Delete everything after 90 days
    
    # Deduplication
    enable_deduplication: bool = True


class ImageOptimizer:
    """
    Optimizes images for storage efficiency.
    
    Usage:
        optimizer = ImageOptimizer()
        
        # On upload
        optimized_path, is_duplicate = optimizer.optimize_and_store(
            input_path="/tmp/upload.jpg",
            output_dir="storage/lab-reports",
            original_filename="report.jpg"
        )
        
        # Periodic cleanup
        deleted_count = optimizer.cleanup_old_files("storage/lab-reports")
    """
    
    def __init__(self, config: Optional[OptimizationConfig] = None):
        self.config = config or OptimizationConfig()
        self._hash_cache: Dict[str, str] = {}  # path -> hash
    
    def get_file_hash(self, file_path: str) -> str:
        """
        Generate SHA-256 hash of file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Hex digest of file hash
        """
        if file_path in self._hash_cache:
            return self._hash_cache[file_path]
        
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        
        hash_value = hasher.hexdigest()
        self._hash_cache[file_path] = hash_value
        return hash_value
    
    def get_perceptual_hash(self, file_path: str) -> Optional[str]:
        """
        Generate perceptual hash (pHash) for similar image detection.
        
        pHash is robust to minor changes like resizing, compression, etc.
        Two visually similar images will have similar pHash values.
        
        Args:
            file_path: Path to image file
            
        Returns:
            16-character hex string of pHash, or None if unavailable
        """
        if not IMAGEHASH_AVAILABLE:
            logger.debug("imagehash not available, skipping pHash")
            return None
        
        try:
            img = Image.open(file_path)
            phash = imagehash.phash(img)
            return str(phash)
        except Exception as e:
            logger.warning(f"Failed to compute pHash: {e}")
            return None
    
    def optimize_image(
        self,
        input_path: str,
        output_path: Optional[str] = None
    ) -> Tuple[str, int, int]:
        """
        Optimize image for storage (compress and resize).
        
        Args:
            input_path: Path to original image
            output_path: Path for optimized image (optional, creates temp if None)
            
        Returns:
            Tuple of (output_path, original_size, optimized_size)
        """
        original_size = os.path.getsize(input_path)
        
        # Open image
        img = Image.open(input_path)
        
        # Convert to RGB if needed (for JPEG compatibility)
        if img.mode in ('RGBA', 'P', 'LA'):
            # Create white background for transparency
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'RGBA':
                background.paste(img, mask=img.split()[3])
            else:
                background.paste(img)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Resize if too large
        img = self._resize_if_needed(img)
        
        # Determine output format and path
        if output_path is None:
            ext = '.webp' if self.config.use_webp else '.jpg'
            output_path = input_path.rsplit('.', 1)[0] + '_optimized' + ext
        
        # Save optimized
        if self.config.use_webp:
            img.save(output_path, 'WEBP', quality=self.config.webp_quality, optimize=True)
        else:
            img.save(output_path, 'JPEG', quality=self.config.jpeg_quality, optimize=True)
        
        optimized_size = os.path.getsize(output_path)
        
        reduction_pct = (1 - optimized_size / original_size) * 100
        logger.info(
            f"Optimized image: {original_size:,} → {optimized_size:,} bytes "
            f"({reduction_pct:.1f}% reduction)"
        )
        
        return output_path, original_size, optimized_size
    
    def _resize_if_needed(self, img: Image.Image) -> Image.Image:
        """Resize image if larger than max dimension."""
        max_dim = max(img.size)
        
        if max_dim > self.config.max_dimension:
            ratio = self.config.max_dimension / max_dim
            new_size = (int(img.width * ratio), int(img.height * ratio))
            
            logger.debug(f"Resizing from {img.size} to {new_size}")
            return img.resize(new_size, Image.Resampling.LANCZOS)
        
        return img
    
    def find_duplicate(self, file_hash: str, storage_dir: str) -> Optional[str]:
        """
        Find existing file with same hash (duplicate detection).
        
        Args:
            file_hash: SHA-256 hash of file
            storage_dir: Directory to search
            
        Returns:
            Path to existing duplicate, or None
        """
        if not self.config.enable_deduplication:
            return None
        
        storage_path = Path(storage_dir)
        if not storage_path.exists():
            return None
        
        # Check hash index file
        index_path = storage_path / '.hash_index.json'
        if index_path.exists():
            import json
            try:
                with open(index_path) as f:
                    index = json.load(f)
                if file_hash in index:
                    existing_path = storage_path / index[file_hash]
                    if existing_path.exists():
                        logger.info(f"Found duplicate: {existing_path}")
                        return str(existing_path)
            except Exception as e:
                logger.warning(f"Failed to read hash index: {e}")
        
        return None
    
    def update_hash_index(self, file_hash: str, filename: str, storage_dir: str) -> None:
        """Update the hash index with new file."""
        import json
        
        storage_path = Path(storage_dir)
        index_path = storage_path / '.hash_index.json'
        
        # Load existing index
        index = {}
        if index_path.exists():
            try:
                with open(index_path) as f:
                    index = json.load(f)
            except Exception:
                pass
        
        # Update and save
        index[file_hash] = filename
        with open(index_path, 'w') as f:
            json.dump(index, f, indent=2)
    
    def optimize_and_store(
        self,
        input_path: str,
        output_dir: str,
        original_filename: str
    ) -> Tuple[str, bool, Dict[str, Any]]:
        """
        Optimize image and store with deduplication.
        
        Args:
            input_path: Path to uploaded file
            output_dir: Directory to store optimized file
            original_filename: Original filename from upload
            
        Returns:
            Tuple of (stored_path, is_duplicate, stats)
        """
        # Compute hash of original
        file_hash = self.get_file_hash(input_path)
        
        # Check for duplicate
        duplicate_path = self.find_duplicate(file_hash, output_dir)
        if duplicate_path:
            return duplicate_path, True, {
                'is_duplicate': True,
                'original_path': duplicate_path,
                'saved_bytes': os.path.getsize(input_path)
            }
        
        # Ensure output directory exists
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        ext = '.webp' if self.config.use_webp else '.jpg'
        base_name = Path(original_filename).stem
        output_filename = f"{base_name}_{file_hash[:8]}{ext}"
        output_path = str(Path(output_dir) / output_filename)
        
        # Optimize and save
        _, original_size, optimized_size = self.optimize_image(input_path, output_path)
        
        # Compute perceptual hash BEFORE deleting the original
        phash = self.get_perceptual_hash(input_path)
        
        # Update hash index
        self.update_hash_index(file_hash, output_filename, output_dir)
        
        return output_path, False, {
            'is_duplicate': False,
            'original_size': original_size,
            'optimized_size': optimized_size,
            'reduction_pct': (1 - optimized_size / original_size) * 100,
            'file_hash': file_hash,
            'phash': phash  # Actual perceptual hash for similar image detection
        }
    
    def cleanup_old_files(
        self,
        storage_dir: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Clean up old files based on retention policy.
        
        Args:
            storage_dir: Directory to clean
            dry_run: If True, don't actually delete, just report
            
        Returns:
            Cleanup statistics
        """
        storage_path = Path(storage_dir)
        if not storage_path.exists():
            return {'deleted': 0, 'freed_bytes': 0}
        
        now = datetime.now()
        deleted_count = 0
        freed_bytes = 0
        files_to_delete = []
        
        for file_path in storage_path.glob('*'):
            if file_path.is_file() and not file_path.name.startswith('.'):
                # Get file age
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                age_days = (now - mtime).days
                
                # Check retention policy
                if age_days > self.config.delete_processed_after_days:
                    files_to_delete.append(file_path)
                    freed_bytes += file_path.stat().st_size
        
        # Delete files
        if not dry_run:
            for file_path in files_to_delete:
                try:
                    file_path.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted old file: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to delete {file_path}: {e}")
        else:
            deleted_count = len(files_to_delete)
        
        result = {
            'deleted': deleted_count,
            'freed_bytes': freed_bytes,
            'freed_mb': freed_bytes / (1024 * 1024),
            'dry_run': dry_run
        }
        
        logger.info(
            f"Cleanup complete: {deleted_count} files, "
            f"{result['freed_mb']:.2f} MB freed"
        )
        
        return result


# Global instance
_optimizer: Optional[ImageOptimizer] = None


def get_optimizer(config: Optional[OptimizationConfig] = None) -> ImageOptimizer:
    """Get or create the global optimizer instance."""
    global _optimizer
    if _optimizer is None:
        _optimizer = ImageOptimizer(config)
    return _optimizer


def optimize_uploaded_image(
    input_path: str,
    output_dir: str,
    original_filename: str
) -> Tuple[str, bool, Dict[str, Any]]:
    """
    Convenience function to optimize an uploaded image.
    
    Returns:
        Tuple of (stored_path, is_duplicate, stats)
    """
    return get_optimizer().optimize_and_store(input_path, output_dir, original_filename)


def cleanup_storage(storage_dir: str, dry_run: bool = False) -> Dict[str, Any]:
    """Convenience function to run storage cleanup."""
    return get_optimizer().cleanup_old_files(storage_dir, dry_run)
