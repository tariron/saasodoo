"""
Tests for health check endpoints
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    """Test basic health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["service"] == "tenant-service"
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "version" in data


def test_root_endpoint():
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    
    data = response.json()
    assert data["service"] == "tenant-service"
    assert data["status"] == "running"
    assert data["version"] == "1.0.0"
    assert data["docs"] == "/docs"


def test_docs_accessible():
    """Test that API docs are accessible"""
    response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_spec():
    """Test that OpenAPI spec is accessible"""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    
    spec = response.json()
    assert spec["info"]["title"] == "SaaS Odoo - Tenant Service"
    assert spec["info"]["version"] == "1.0.0" 