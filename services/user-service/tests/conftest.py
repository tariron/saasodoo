"""
Pytest configuration for user-service tests
"""

import pytest

# Configure pytest-asyncio mode for version 1.x
pytest_plugins = ('pytest_asyncio',)

# Set asyncio mode to auto - automatically detect async tests
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as an asyncio test."
    )
