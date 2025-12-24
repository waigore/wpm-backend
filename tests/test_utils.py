"""Tests for utility modules."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from wpm_backend.utils.openapi_generator import generate_openapi_spec
from wpm_backend.utils.logging_config import setup_logging


def test_generate_openapi_spec_success():
    """Test generate_openapi_spec() successfully generates OpenAPI spec."""
    app = MagicMock()
    app.openapi.return_value = {"openapi": "3.0.0", "info": {"title": "Test API"}}
    
    output_path = "SPEC/test_openapi.json"
    
    try:
        generate_openapi_spec(app, output_path)
        
        # Verify file was created
        assert os.path.exists(output_path)
        
        # Verify content
        with open(output_path, "r") as f:
            content = json.load(f)
            assert content["openapi"] == "3.0.0"
            assert content["info"]["title"] == "Test API"
    finally:
        # Cleanup
        if os.path.exists(output_path):
            os.remove(output_path)
        # Remove SPEC directory if empty
        if os.path.exists("SPEC") and not os.listdir("SPEC"):
            os.rmdir("SPEC")


def test_generate_openapi_spec_creates_directory():
    """Test generate_openapi_spec() creates directory if it doesn't exist."""
    app = MagicMock()
    app.openapi.return_value = {"openapi": "3.0.0", "info": {"title": "Test API"}}
    
    output_path = "SPEC/test/test_openapi.json"
    
    try:
        generate_openapi_spec(app, output_path)
        
        # Verify directory and file were created
        assert os.path.exists(output_path)
    finally:
        # Cleanup
        if os.path.exists(output_path):
            os.remove(output_path)
        if os.path.exists("SPEC/test"):
            os.rmdir("SPEC/test")
        if os.path.exists("SPEC") and not os.listdir("SPEC"):
            os.rmdir("SPEC")


def test_generate_openapi_spec_exception_handling():
    """Test generate_openapi_spec() handles exceptions properly."""
    app = MagicMock()
    app.openapi.side_effect = Exception("OpenAPI generation failed")
    
    output_path = "SPEC/test_openapi.json"
    
    # Should raise the exception
    with pytest.raises(Exception, match="OpenAPI generation failed"):
        generate_openapi_spec(app, output_path)


def test_setup_logging_creates_directory(tmp_path):
    """Test setup_logging() creates log directory if it doesn't exist."""
    log_dir = tmp_path / "test_logs"
    
    setup_logging(log_dir=str(log_dir), log_level="INFO")
    
    # Verify directory was created
    assert log_dir.exists()
    assert (log_dir / "app.log").exists()


def test_setup_logging_exception_handling():
    """Test setup_logging() handles exceptions when configuring wpm logger."""
    import logging
    
    # Patch getLogger to return a mock that raises an exception when accessed
    original_get_logger = logging.getLogger
    
    def mock_get_logger(name=None):
        if name == "wpm":
            # Return a mock logger that raises exception when setLevel is called
            mock_logger = Mock()
            mock_logger.setLevel.side_effect = Exception("WPM logger error")
            mock_logger.handlers = []
            mock_logger.propagate = False
            return mock_logger
        return original_get_logger(name)
    
    with patch("logging.getLogger", side_effect=mock_get_logger):
        # Should not raise exception, should continue
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            setup_logging(log_dir=tmp_dir, log_level="INFO")
        
        # Should not raise exception
        assert True

