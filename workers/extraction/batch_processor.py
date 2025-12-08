"""
Async Batch Processor for Concurrent Image Processing.

Features:
- Processes multiple images concurrently using asyncio
- Uses model.generate_content_async() for non-blocking API calls
- Implements batch size of 15 images (respecting Gemini rate limits)
- Adds delays between batches for rate limiting
- Handles exceptions gracefully without stopping entire batch
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from PIL import Image
import io

import google.generativeai as genai

from workers.extraction.rate_limiter import get_rate_limiter, AdaptiveRateLimiter
from workers.extraction.cache_manager import get_cache_manager, CacheManager
from workers.extraction.preprocessing import preprocess_image
from workers.extraction.prompts import VISION_PROMPTS, get_refinement_prompt
from workers.extraction.standardizer import standardize_lab_results
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class BatchResult:
    """Result of batch processing."""
    total: int = 0
    successful: int = 0
    failed: int = 0
    cached: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    processing_time: float = 0.0
    
    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.successful / self.total


@dataclass
class ImageResult:
    """Result for a single image."""
    image_path: str
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    from_cache: bool = False
    processing_time: float = 0.0


class BatchProcessor:
    """
    Async batch processor for lab report images.
    
    Processes images concurrently while respecting rate limits
    and utilizing caching for efficiency.
    
    Usage:
        processor = BatchProcessor(api_key="...", max_workers=15)
        results = await processor.process_images_async(image_paths)
    """
    
    def __init__(
        self,
        api_key: str,
        max_workers: int = 15,
        batch_delay_seconds: float = 5.0,
        rate_limiter: Optional[AdaptiveRateLimiter] = None,
        cache_manager: Optional[CacheManager] = None
    ):
        """
        Initialize batch processor.
        
        Args:
            api_key: Gemini API key
            max_workers: Max concurrent workers per batch
            batch_delay_seconds: Delay between batches
            rate_limiter: Rate limiter instance (uses global if None)
            cache_manager: Cache manager instance (uses global if None)
        """
        self.api_key = api_key
        self.max_workers = max_workers
        self.batch_delay = batch_delay_seconds
        
        # Initialize Gemini
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(settings.gemini.model)
        
        # Use provided or global instances
        self.rate_limiter = rate_limiter or get_rate_limiter()
        self.cache_manager = cache_manager or get_cache_manager()
        
        logger.info(
            f"BatchProcessor initialized: max_workers={max_workers}, "
            f"batch_delay={batch_delay_seconds}s"
        )
    
    async def process_images_async(
        self,
        image_paths: List[str],
        use_cache: bool = True
    ) -> BatchResult:
        """
        Process multiple images concurrently.
        
        Args:
            image_paths: List of image file paths
            use_cache: Whether to use caching
            
        Returns:
            BatchResult with all processing results
        """
        start_time = time.time()
        batch_result = BatchResult(total=len(image_paths))
        
        logger.info(f"Starting batch processing of {len(image_paths)} images")
        
        # Split into batches
        batches = [
            image_paths[i:i + self.max_workers]
            for i in range(0, len(image_paths), self.max_workers)
        ]
        
        for batch_idx, batch in enumerate(batches):
            logger.info(f"Processing batch {batch_idx + 1}/{len(batches)} ({len(batch)} images)")
            
            # Process batch concurrently
            tasks = [
                self._process_single_image(path, use_cache)
                for path in batch
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Collect results
            for result in results:
                if isinstance(result, Exception):
                    batch_result.failed += 1
                    batch_result.errors.append({
                        "error": str(result),
                        "type": type(result).__name__
                    })
                elif isinstance(result, ImageResult):
                    if result.success:
                        batch_result.successful += 1
                        if result.from_cache:
                            batch_result.cached += 1
                        batch_result.results.append({
                            "image_path": result.image_path,
                            "data": result.data,
                            "from_cache": result.from_cache,
                            "processing_time": result.processing_time
                        })
                    else:
                        batch_result.failed += 1
                        batch_result.errors.append({
                            "image_path": result.image_path,
                            "error": result.error
                        })
            
            # Delay between batches (except last)
            if batch_idx < len(batches) - 1:
                logger.debug(f"Batch delay: {self.batch_delay}s")
                await asyncio.sleep(self.batch_delay)
        
        batch_result.processing_time = time.time() - start_time
        
        logger.info(
            f"Batch processing complete: {batch_result.successful}/{batch_result.total} successful, "
            f"{batch_result.cached} from cache, {batch_result.failed} failed, "
            f"time={batch_result.processing_time:.1f}s"
        )
        
        return batch_result
    
    async def _process_single_image(
        self,
        image_path: str,
        use_cache: bool = True
    ) -> ImageResult:
        """
        Process a single image through the 3-pass pipeline.
        
        Args:
            image_path: Path to image file
            use_cache: Whether to check/use cache
            
        Returns:
            ImageResult with extraction data or error
        """
        start_time = time.time()
        
        try:
            # Check cache first
            if use_cache:
                image_hash = self.cache_manager.get_image_hash(image_path)
                cached = self.cache_manager.get_cached_result(image_hash)
                
                if cached:
                    return ImageResult(
                        image_path=image_path,
                        success=True,
                        data=cached.get("result"),
                        from_cache=True,
                        processing_time=time.time() - start_time
                    )
            else:
                image_hash = None
            
            # Acquire rate limit
            await self.rate_limiter.acquire_async()
            
            # Pass 1: Vision extraction
            raw_text = await self._extract_raw_vision_async(image_path)
            
            if not raw_text:
                return ImageResult(
                    image_path=image_path,
                    success=False,
                    error="Vision extraction returned empty result"
                )
            
            # Acquire rate limit for pass 2
            await self.rate_limiter.acquire_async()
            
            # Pass 2: Structure and validate
            structured = await self._structure_and_validate_async(raw_text)
            
            # Pass 3: Standardize (sync, no API call needed)
            final_result = await asyncio.to_thread(
                self._standardize_results, structured
            )
            
            # Report success to rate limiter
            self.rate_limiter.report_success()
            
            # Cache result
            if use_cache and image_hash:
                self.cache_manager.cache_result(image_hash, final_result)
            
            return ImageResult(
                image_path=image_path,
                success=True,
                data=final_result,
                from_cache=False,
                processing_time=time.time() - start_time
            )
            
        except Exception as e:
            logger.error(f"Error processing {image_path}: {e}")
            
            # Check if rate limit error
            if "429" in str(e) or "rate" in str(e).lower():
                self.rate_limiter.report_rate_limit_error()
            
            return ImageResult(
                image_path=image_path,
                success=False,
                error=str(e),
                processing_time=time.time() - start_time
            )
    
    async def _extract_raw_vision_async(self, image_path: str) -> Optional[str]:
        """
        Pass 1: Extract raw text from image using vision model.
        
        Uses multi-prompt retry strategy.
        """
        # Preprocess image
        try:
            img = await asyncio.to_thread(preprocess_image, image_path)
        except Exception as e:
            logger.warning(f"Preprocessing failed, using original: {e}")
            img = Image.open(image_path)
        
        # Try each prompt until success
        for prompt_idx, prompt in enumerate(VISION_PROMPTS):
            try:
                response = await self.model.generate_content_async(
                    [prompt, img],
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=4096
                    )
                )
                
                if response.text and len(response.text.strip()) > 50:
                    logger.debug(f"Vision extraction succeeded with prompt {prompt_idx + 1}")
                    return response.text
                    
            except Exception as e:
                logger.warning(f"Vision prompt {prompt_idx + 1} failed: {e}")
                continue
        
        return None
    
    async def _structure_and_validate_async(self, raw_text: str) -> Dict[str, Any]:
        """
        Pass 2: Convert raw text to structured JSON.
        """
        prompt = get_refinement_prompt(raw_text, attempt=0)
        
        try:
            response = await self.model.generate_content_async(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=4096
                )
            )
            
            result_text = response.text.strip()
            
            # Clean markdown if present
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]
            
            import json
            return json.loads(result_text)
            
        except Exception as e:
            logger.error(f"Structuring failed: {e}")
            return {
                "lab_results": [],
                "patient_info": {},
                "metadata": {
                    "confidence_score": 0.0,
                    "needs_review": True,
                    "error": str(e)
                }
            }
    
    def _standardize_results(self, structured: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pass 3: Standardize test names with LOINC codes.
        """
        lab_results = structured.get("lab_results", [])
        
        if lab_results:
            standardized = standardize_lab_results(lab_results)
            structured["lab_results"] = standardized
            
            # Add standardization metrics
            total = len(standardized)
            standardized_count = sum(
                1 for r in standardized
                if r.get("standardization", {}).get("is_standardized", False)
            )
            
            if "metadata" not in structured:
                structured["metadata"] = {}
            
            structured["metadata"]["standardization"] = {
                "total_tests": total,
                "standardized_count": standardized_count,
                "standardization_rate": standardized_count / total if total > 0 else 0
            }
        
        return structured


# Convenience function for sync usage
def process_images_batch(
    image_paths: List[str],
    api_key: Optional[str] = None,
    max_workers: int = 15
) -> BatchResult:
    """
    Sync wrapper for batch processing.
    
    Args:
        image_paths: List of image file paths
        api_key: Gemini API key (uses settings if None)
        max_workers: Max concurrent workers
        
    Returns:
        BatchResult with all processing results
    """
    key = api_key or settings.gemini.api_key
    if not key:
        raise ValueError("Gemini API key not provided")
    
    processor = BatchProcessor(api_key=key, max_workers=max_workers)
    return asyncio.run(processor.process_images_async(image_paths))
