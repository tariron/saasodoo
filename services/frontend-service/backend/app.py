import os
import logging
from flask import Flask, render_template, jsonify, send_from_directory
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='./frontend/build/static', 
           template_folder='./frontend/build')

# Configuration
app.config['ENV'] = os.getenv('FLASK_ENV', 'development')
app.config['DEBUG'] = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'

# =====================
# CONFIGURATION ENDPOINT (OPTIONAL)
# =====================

@app.route('/api/config')
def get_config():
    """Runtime configuration for frontend"""
    config = {
        'BASE_DOMAIN': os.getenv('BASE_DOMAIN', 'saasodoo.local'),
        'ENVIRONMENT': os.getenv('ENVIRONMENT', 'development'),
        'API_BASE_URL': f"http://api.{os.getenv('BASE_DOMAIN', 'saasodoo.local')}",
        'VERSION': '1.0.0',
        'FEATURES': {
            'billing': True,
            'analytics': False,
            'monitoring': True
        }
    }
    return jsonify(config)

@app.route('/health')
def health():
    """Health check endpoint"""
    return {
        'status': 'healthy',
        'service': 'frontend-service',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0'
    }

# =====================
# STATIC FILE SERVING
# =====================

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files explicitly"""
    return send_from_directory('./frontend/build/static', filename)

# =====================
# SPA ROUTING (CATCH ALL)
# =====================

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_react(path):
    """Serve React SPA with proper fallback"""
    # Block API paths from SPA routing
    if path.startswith('api/') or path.startswith('static/') or path.startswith('health'):
        return jsonify({'error': 'Not found'}), 404
    
    # Serve React app for all other paths
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error serving React app: {str(e)}")
        return jsonify({'error': 'Frontend not available'}), 503

if __name__ == '__main__':
    port = int(os.getenv('PORT', 3000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)