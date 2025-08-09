#!/usr/bin/env python3
"""
Test script to check if Docker Python client can receive destroy events
"""
import docker
import json

def test_destroy_events():
    client = docker.from_env()
    
    # Listen specifically for destroy events
    event_filters = {
        'type': 'container',
        'event': ['destroy']
    }
    
    print(f"Testing destroy event reception with filters: {event_filters}")
    print("Waiting for destroy events... (Ctrl+C to stop)")
    
    try:
        for event in client.events(decode=True, filters=event_filters):
            print(f"DESTROY EVENT RECEIVED: {json.dumps(event, indent=2)}")
            
    except KeyboardInterrupt:
        print("\nTest stopped by user")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_destroy_events()