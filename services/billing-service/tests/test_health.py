"""
Tests for billing service health endpoints
"""

from fastapi.testclient import TestClient
import pytest
from unittest.mock import AsyncMock, patch

# Import the app after the mocks are set up
def test_root_endpoint():
    """Test the root endpoint"""
    with patch('services.billing-service.app.main.init_db', new_callable=AsyncMock):
        with patch('services.billing-service.app.main.close_db', new_callable=AsyncMock):
            from app.main import app
            client = TestClient(app)
            
            response = client.get("/")
            assert response.status_code == 200
            data = response.json()
            assert data["service"] == "billing-service"
            assert data["status"] == "running"
            assert data["version"] == "1.0.0"

if __name__ == "__main__":
    test_root_endpoint()
    print("All tests passed!")
