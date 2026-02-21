"""
Tests for provider metadata capture.
"""
import sys
from pathlib import Path
import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ai_factory.config import Config
from ai_factory.result import ProviderResponse, Metrics
from ai_factory.metrics import build_metrics


class TestProviderMetadata:
    """Test that provider metadata is captured and serialized."""
    
    def test_build_metrics_with_provider_metadata(self):
        """Test that build_metrics accepts and stores provider_metadata."""
        metadata = {
            "id": "msg_123",
            "model": "claude-3-opus",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
            }
        }
        
        metrics = build_metrics(
            input_chars=500,
            output_chars=250,
            latency_ms=1000,
            success=True,
            provider_metadata=metadata,
        )
        
        assert metrics.provider_metadata is not None
        assert metrics.provider_metadata == metadata
        assert metrics.provider_metadata["id"] == "msg_123"
        assert metrics.provider_metadata["model"] == "claude-3-opus"
    
    def test_build_metrics_without_provider_metadata(self):
        """Test that build_metrics works without provider_metadata."""
        metrics = build_metrics(
            input_chars=500,
            output_chars=250,
            latency_ms=1000,
            success=True,
        )
        
        assert metrics.provider_metadata is None
    
    def test_provider_response_has_metadata_field(self):
        """Test that ProviderResponse has metadata field."""
        response = ProviderResponse(
            text="Test response",
            metadata={"key": "value"},
            attempts=1,
        )
        
        assert hasattr(response, "metadata")
        assert response.metadata == {"key": "value"}
    
    def test_metrics_has_provider_metadata_field(self):
        """Test that Metrics dataclass has provider_metadata field."""
        metrics = Metrics(
            input_chars=100,
            output_chars=50,
            latency_ms=500,
            success=True,
            provider_metadata={"test": "data"},
        )
        
        assert hasattr(metrics, "provider_metadata")
        assert metrics.provider_metadata == {"test": "data"}
    
    def test_provider_metadata_can_be_complex(self):
        """Test that provider_metadata can store complex nested structures."""
        complex_metadata = {
            "id": "msg_abc123",
            "model": "gpt-4",
            "usage": {
                "prompt_tokens": 150,
                "completion_tokens": 75,
                "total_tokens": 225,
            },
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                }
            ],
            "system_fingerprint": "fp_xyz",
        }
        
        metrics = build_metrics(
            input_chars=600,
            output_chars=300,
            latency_ms=2000,
            success=True,
            provider_metadata=complex_metadata,
        )
        
        assert metrics.provider_metadata == complex_metadata
        assert metrics.provider_metadata["usage"]["total_tokens"] == 225


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
