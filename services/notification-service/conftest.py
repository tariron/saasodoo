"""
Pytest configuration for notification-service tests
"""

import pytest

# Configure pytest-asyncio mode for version 1.x
pytest_plugins = ('pytest_asyncio',)

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as an asyncio test."
    )
