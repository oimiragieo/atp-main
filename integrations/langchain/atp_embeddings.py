# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
ATP LangChain Embeddings Integration
This module provides LangChain embeddings interface for ATP platform.
"""
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from pydantic import Field, validator
import aiohttp
import json

try:
    from langchain.embeddings.base import Embeddings
except ImportError:
    raise ImportError(
        "LangChain is required for ATP LangChain integration. "
        "Install it with: pip install langchain"
    )

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ATPEmbeddings(Embeddings):
    """ATP LangChain Embeddings implementation."""
    
    # Configuration
    atp_base_url: str = Field(default="http://localhost:8000")
    atp_api_key: Optional[str] = Field(default=None)
    model: str = Field(default="text-embedding-ada-002")
    
    # ATP-specific settings
    request_timeout: int = Field(default=60)
    max_retries: int = Field(default=3)
    retry_delay: float = Field(default=1.0)
    batch_size: int = Field(default=100)
    
    # Internal state
    _session: Optional[aiohttp.ClientSession] = None
    
    class Config:
        """Pydantic configuration."""
        arbitrary_types_allowed = True
        
    @validator('atp_base_url')
    def validate_base_url(cls, v):
        """Validate base URL format."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError('Base URL must start with http:// or https://')
        return v.rstrip('/')
    
    def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def _close_session(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _prepare_headers(self) -> Dict[str, str]:
        """Prepare request headers."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ATP-LangChain-Embeddings/1.0.0"
        }
        
        if self.atp_api_key:
            headers["Authorization"] = f"Bearer {self.atp_api_key}"
            
        return headers
    
    async def _make_request(self, texts: List[str]) -> List[List[float]]:
        """Make request to ATP embeddings API with retries."""
        session = self._get_session()
        headers = self._prepare_headers()
        url = f"{self.atp_base_url}/api/v1/embeddings"
        
        data = {
            "input": texts,
            "model": self.model
        }
        
        for attempt in range(self.max_retries):
            try:
                async with session.post(url, json=data, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        # Extract embeddings from response
                        embeddings = []
                        for item in result.get("data", []):
                            embeddings.append(item.get("embedding", []))
                        return embeddings
                    elif response.status == 429:  # Rate limited
                        if attempt < self.max_retries - 1:
                            retry_after = int(response.headers.get('Retry-After', self.retry_delay))
                            logger.warning(f"Rate limited, retrying after {retry_after}s")
                            await asyncio.sleep(retry_after)
                            continue
                    
                    # Handle other errors
                    error_text = await response.text()
                    raise Exception(f"ATP Embeddings API error {response.status}: {error_text}")
                    
            except asyncio.TimeoutError:
                if attempt < self.max_retries - 1:
                    logger.warning(f"Request timeout, retrying (attempt {attempt + 1})")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise Exception("Request timeout after all retries")
            except Exception as e:
                if attempt < self.max_retries - 1:
                    logger.warning(f"Request failed: {e}, retrying (attempt {attempt + 1})")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise
        
        raise Exception("All retry attempts failed")
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed search docs."""
        # Run async method in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.aembed_documents(texts))
        finally:
            loop.close()
    
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """Async embed search docs."""
        try:
            # Process in batches to avoid overwhelming the API
            all_embeddings = []
            
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i:i + self.batch_size]
                batch_embeddings = await self._make_request(batch)
                all_embeddings.extend(batch_embeddings)
            
            return all_embeddings
            
        except Exception as e:
            logger.error(f"Failed to embed documents: {e}")
            # Return zero embeddings on error
            return [[0.0] * 1536 for _ in texts]  # Assuming 1536-dim embeddings
        finally:
            await self._close_session()
    
    def embed_query(self, text: str) -> List[float]:
        """Embed query text."""
        # Run async method in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.aembed_query(text))
        finally:
            loop.close()
    
    async def aembed_query(self, text: str) -> List[float]:
        """Async embed query text."""
        try:
            embeddings = await self._make_request([text])
            return embeddings[0] if embeddings else [0.0] * 1536
            
        except Exception as e:
            logger.error(f"Failed to embed query: {e}")
            # Return zero embedding on error
            return [0.0] * 1536
        finally:
            await self._close_session()
    
    def __del__(self):
        """Cleanup on deletion."""
        if self._session and not self._session.closed:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._close_session())
                else:
                    loop.run_until_complete(self._close_session())
            except Exception:
                pass

# Factory function for easy instantiation
def create_atp_embeddings(
    base_url: str = "http://localhost:8000",
    api_key: Optional[str] = None,
    model: str = "text-embedding-ada-002",
    **kwargs
) -> ATPEmbeddings:
    """Create ATP Embeddings instance."""
    return ATPEmbeddings(
        atp_base_url=base_url,
        atp_api_key=api_key,
        model=model,
        **kwargs
    )