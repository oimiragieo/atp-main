#!/usr/bin/env python3
"""
Tests for ATP vLLM Adapter
"""

import asyncio
import json
import pytest
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone

# Mock the GPU monitoring before importing the adapter
with patch('GPUtil.getGPUs', return_value=[]):
    from server import (
        VLLMAdapter, VLLMClient, GPUMonitor, BatchProcessor, 
        BatchRequest, BatchResponse, GPUStats
    )

import adapter_pb2


class TestGPUMonitor:
    """Test GPU monitoring functionality."""
    
    @patch('GPUtil.getGPUs')
    def test_gpu_stats_collection(self, mock_get_gpus):
        """Test GPU statistics collection."""
        # Mock GPU data
        mock_gpu = Mock()
        mock_gpu.id = 0
        mock_gpu.name = "NVIDIA A100"
        mock_gpu.memoryTotal = 40960
        mock_gpu.memoryUsed = 15360
        mock_gpu.memoryFree = 25600
        mock_gpu.load = 0.85
        mock_gpu.temperature = 65
        mock_get_gpus.return_value = [mock_gpu]
        
        monitor = GPUMonitor()
        monitor._update_gpu_stats()
        
        stats = monitor.get_gpu_stats()
        assert len(stats) == 1
        assert stats[0].gpu_id == 0
        assert stats[0].name == "NVIDIA A100"
        assert stats[0].memory_total == 40960
        assert stats[0].utilization == 85.0
    
    @patch('GPUtil.getGPUs')
    def test_optimal_gpu_selection(self, mock_get_gpus):
        """Test optimal GPU selection."""
        # Mock multiple GPUs with different memory availability
        gpu1 = Mock()
        gpu1.id = 0
        gpu1.memoryFree = 5000
        
        gpu2 = Mock()
        gpu2.id = 1
        gpu2.memoryFree = 15000
        
        mock_get_gpus.return_value = [gpu1, gpu2]
        
        monitor = GPUMonitor()
        monitor._update_gpu_stats()
        
        optimal_gpu = monitor.get_optimal_gpu()
        assert optimal_gpu == 1  # GPU with more free memory
    
    def test_monitoring_lifecycle(self):
        """Test monitoring start/stop lifecycle."""
        monitor = GPUMonitor()
        
        assert not monitor.monitoring
        
        monitor.start_monitoring(interval=0.1)
        assert monitor.monitoring
        assert monitor.monitor_thread is not None
        
        time.sleep(0.2)  # Let it run briefly
        
        monitor.stop_monitoring()
        assert not monitor.monitoring


class TestVLLMClient:
    """Test vLLM client functionality."""
    
    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful health check."""
        client = VLLMClient()
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_get.return_value.__aenter__.return_value = mock_response
            
            result = await client.health_check()
            assert result is True
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test failed health check."""
        client = VLLMClient()
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_get.return_value.__aenter__.return_value = mock_response
            
            result = await client.health_check()
            assert result is False
    
    @pytest.mark.asyncio
    async def test_get_models(self):
        """Test getting available models."""
        client = VLLMClient()
        
        mock_models_response = {
            "data": [
                {"id": "llama-2-7b"},
                {"id": "llama-2-13b"}
            ]
        }
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = mock_models_response
            mock_get.return_value.__aenter__.return_value = mock_response
            
            models = await client.get_models()
            assert models == ["llama-2-7b", "llama-2-13b"]
    
    @pytest.mark.asyncio
    async def test_generate_text(self):
        """Test text generation."""
        client = VLLMClient()
        
        mock_response_data = {
            "choices": [{"text": "Generated text response"}]
        }
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = mock_response_data
            mock_post.return_value.__aenter__.return_value = mock_response
            
            result = await client.generate(
                prompt="Test prompt",
                model="llama-2-7b",
                max_tokens=100
            )
            assert result == "Generated text response"
    
    @pytest.mark.asyncio
    async def test_generate_stream(self):
        """Test streaming text generation."""
        client = VLLMClient()
        
        # Mock streaming response
        stream_data = [
            b'data: {"choices": [{"text": "Hello"}]}\n',
            b'data: {"choices": [{"text": " world"}]}\n',
            b'data: [DONE]\n'
        ]
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.content = AsyncMock()
            mock_response.content.__aiter__.return_value = iter(stream_data)
            mock_post.return_value.__aenter__.return_value = mock_response
            
            chunks = []
            async for chunk in client.generate_stream(
                prompt="Test prompt",
                model="llama-2-7b"
            ):
                chunks.append(chunk)
            
            assert chunks == ["Hello", " world"]


class TestBatchProcessor:
    """Test batch processing functionality."""
    
    @pytest.mark.asyncio
    async def test_batch_request_processing(self):
        """Test batch request processing."""
        mock_client = AsyncMock()
        mock_client.generate_batch.return_value = ["Response 1", "Response 2"]
        
        processor = BatchProcessor(mock_client, max_batch_size=2)
        processor.start_processing()
        
        try:
            # Submit batch requests
            request1 = BatchRequest(
                request_id="req1",
                prompt="Prompt 1",
                model="llama-2-7b",
                max_tokens=100,
                temperature=0.7,
                top_p=0.9,
                stop_sequences=[],
                timestamp=datetime.now(timezone.utc)
            )
            
            request2 = BatchRequest(
                request_id="req2",
                prompt="Prompt 2",
                model="llama-2-7b",
                max_tokens=100,
                temperature=0.7,
                top_p=0.9,
                stop_sequences=[],
                timestamp=datetime.now(timezone.utc)
            )
            
            # Submit requests concurrently
            task1 = asyncio.create_task(processor.submit_request(request1))
            task2 = asyncio.create_task(processor.submit_request(request2))
            
            # Wait for responses
            response1, response2 = await asyncio.gather(task1, task2)
            
            assert response1.request_id == "req1"
            assert response2.request_id == "req2"
            assert response1.text == "Response 1"
            assert response2.text == "Response 2"
            
        finally:
            processor.stop_processing()
    
    def test_batch_collection(self):
        """Test batch collection logic."""
        mock_client = Mock()
        processor = BatchProcessor(mock_client, max_batch_size=3)
        
        # Add requests to queue
        requests = [
            BatchRequest(f"req{i}", f"prompt{i}", "llama-2-7b", 100, 0.7, 0.9, [], datetime.now(timezone.utc))
            for i in range(5)
        ]
        
        for req in requests:
            processor.request_queue.put(req)
        
        # Collect batch
        batch = processor._collect_batch()
        
        # Should collect up to max_batch_size
        assert len(batch) == 3
        assert batch[0].request_id == "req0"
        assert batch[1].request_id == "req1"
        assert batch[2].request_id == "req2"


class TestVLLMAdapter:
    """Test vLLM adapter functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        with patch('server.GPUMonitor'), \
             patch('server.BatchProcessor'), \
             patch('server.VLLMClient'):
            self.adapter = VLLMAdapter()
    
    def test_prompt_json_parsing(self):
        """Test prompt JSON parsing."""
        # Valid JSON
        valid_json = '{"prompt": "Hello", "model": "llama-2-7b", "max_tokens": 100}'
        result = self.adapter._parse_prompt_json(valid_json)
        assert result["prompt"] == "Hello"
        assert result["model"] == "llama-2-7b"
        assert result["max_tokens"] == 100
        
        # Invalid JSON - should fallback
        invalid_json = "Just a string"
        result = self.adapter._parse_prompt_json(invalid_json)
        assert result["prompt"] == "Just a string"
        assert "model" in result
    
    def test_token_estimation(self):
        """Test token count estimation."""
        text = "This is a test sentence with multiple words."
        tokens = self.adapter._estimate_tokens(text)
        
        # Should be roughly 1/4 of character count
        expected = max(1, len(text) // 4)
        assert tokens == expected
    
    def test_cost_calculation(self):
        """Test cost calculation."""
        input_tokens = 100
        output_tokens = 200
        model = "llama-2-7b"
        
        cost = self.adapter._calculate_cost(input_tokens, output_tokens, model)
        
        # Should calculate based on pricing table
        expected_input_cost = (input_tokens * 200) // 1000  # 200 micros per 1K tokens
        expected_output_cost = (output_tokens * 400) // 1000  # 400 micros per 1K tokens
        expected_total = expected_input_cost + expected_output_cost
        
        assert cost == expected_total
    
    @pytest.mark.asyncio
    async def test_estimate_request(self):
        """Test estimate request handling."""
        prompt_json = json.dumps({
            "prompt": "Test prompt for estimation",
            "model": "llama-2-7b",
            "max_tokens": 100
        })
        
        request = adapter_pb2.EstimateRequest(prompt_json=prompt_json)
        response = await self.adapter.Estimate(request, None)
        
        assert response.input_tokens > 0
        assert response.output_tokens > 0
        assert response.cost_usd_micros > 0
        assert response.latency_ms > 0
    
    @pytest.mark.asyncio
    async def test_health_request(self):
        """Test health request handling."""
        with patch.object(self.adapter.vllm_client, '__aenter__', return_value=self.adapter.vllm_client), \
             patch.object(self.adapter.vllm_client, 'health_check', return_value=True), \
             patch('psutil.cpu_percent', return_value=50.0), \
             patch('psutil.virtual_memory') as mock_memory:
            
            mock_memory.return_value.percent = 60.0
            
            request = adapter_pb2.HealthRequest()
            response = await self.adapter.Health(request, None)
            
            assert response.healthy is True
            assert "vllm_server" in response.details
            
            details = json.loads(response.details)
            assert details["vllm_server"] == "healthy"
            assert "cpu_usage" in details
            assert "memory_usage" in details


class TestIntegration:
    """Integration tests."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_flow(self):
        """Test complete end-to-end flow."""
        # Mock all external dependencies
        with patch('server.GPUMonitor') as mock_gpu_monitor, \
             patch('server.BatchProcessor') as mock_batch_processor, \
             patch('server.VLLMClient') as mock_vllm_client:
            
            # Set up mocks
            mock_gpu_instance = Mock()
            mock_gpu_instance.get_gpu_stats.return_value = []
            mock_gpu_monitor.return_value = mock_gpu_instance
            
            mock_batch_instance = Mock()
            mock_batch_processor.return_value = mock_batch_instance
            
            mock_client_instance = AsyncMock()
            mock_client_instance.health_check.return_value = True
            mock_vllm_client.return_value = mock_client_instance
            
            # Create adapter
            adapter = VLLMAdapter()
            
            # Test estimate
            prompt_json = json.dumps({
                "prompt": "Hello, world!",
                "model": "llama-2-7b",
                "max_tokens": 50
            })
            
            estimate_req = adapter_pb2.EstimateRequest(prompt_json=prompt_json)
            estimate_resp = await adapter.Estimate(estimate_req, None)
            
            assert estimate_resp.input_tokens > 0
            assert estimate_resp.cost_usd_micros > 0
            
            # Test health
            with patch('psutil.cpu_percent', return_value=30.0), \
                 patch('psutil.virtual_memory') as mock_memory:
                
                mock_memory.return_value.percent = 40.0
                
                health_req = adapter_pb2.HealthRequest()
                health_resp = await adapter.Health(health_req, None)
                
                assert health_resp.healthy is True


class TestErrorHandling:
    """Test error handling scenarios."""
    
    def setup_method(self):
        """Set up test fixtures."""
        with patch('server.GPUMonitor'), \
             patch('server.BatchProcessor'), \
             patch('server.VLLMClient'):
            self.adapter = VLLMAdapter()
    
    @pytest.mark.asyncio
    async def test_invalid_prompt_json(self):
        """Test handling of invalid prompt JSON."""
        invalid_json = "{ invalid json"
        
        request = adapter_pb2.EstimateRequest(prompt_json=invalid_json)
        response = await self.adapter.Estimate(request, None)
        
        # Should still return a response with defaults
        assert response.input_tokens > 0
        assert response.cost_usd_micros > 0
    
    @pytest.mark.asyncio
    async def test_vllm_server_unavailable(self):
        """Test handling when vLLM server is unavailable."""
        with patch.object(self.adapter.vllm_client, '__aenter__', return_value=self.adapter.vllm_client), \
             patch.object(self.adapter.vllm_client, 'health_check', return_value=False), \
             patch('psutil.cpu_percent', return_value=50.0), \
             patch('psutil.virtual_memory') as mock_memory:
            
            mock_memory.return_value.percent = 60.0
            
            request = adapter_pb2.HealthRequest()
            response = await self.adapter.Health(request, None)
            
            # Should report unhealthy
            details = json.loads(response.details)
            assert details["vllm_server"] == "unhealthy"
    
    @pytest.mark.asyncio
    async def test_high_resource_usage(self):
        """Test handling of high resource usage."""
        with patch.object(self.adapter.vllm_client, '__aenter__', return_value=self.adapter.vllm_client), \
             patch.object(self.adapter.vllm_client, 'health_check', return_value=True), \
             patch('psutil.cpu_percent', return_value=95.0), \
             patch('psutil.virtual_memory') as mock_memory:
            
            mock_memory.return_value.percent = 95.0
            
            request = adapter_pb2.HealthRequest()
            response = await self.adapter.Health(request, None)
            
            # Should report unhealthy due to high resource usage
            assert response.healthy is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])