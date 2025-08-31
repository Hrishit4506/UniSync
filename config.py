import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base configuration class"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'dataset'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///instance/User.db'
    
    # ESP32-CAM Configuration
    ESP32_IP = os.environ.get('ESP32_IP') or '192.168.1.100'  # Default IP
    STREAM_URL = f"http://{ESP32_IP}/stream"
    ESP32_STREAM_URL = f"http://{ESP32_IP}:81/stream"
    
    # Arduino Configuration
    SERIAL_PORT = os.environ.get('SERIAL_PORT') or 'COM3'  # Default port
    SERIAL_BAUD = int(os.environ.get('SERIAL_BAUD') or '9600')
    
    # Face Recognition Configuration
    DATASET_DIR = "dataset"
    FACE_SIZE = (160, 160)
    BUFFER_DURATION_SEC = 1.0
    CONFIDENCE_THRESHOLD = 150

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///instance/User.db'

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    # Use environment variables for production
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable must be set in production")

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
