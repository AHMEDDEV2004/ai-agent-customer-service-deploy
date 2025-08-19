import os
from typing import Optional

# MongoDB Configuration
# Option 1: Local MongoDB (recommended for development)
DEFAULT_MONGODB_URI = "mongodb://localhost:27017"

# Option 2: MongoDB Atlas (if you have a working connection)
# DEFAULT_MONGODB_URI = "mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority"

# Database name
DEFAULT_MONGODB_DB = "sobrus_customer_service"

def get_mongodb_uri() -> str:
    """Get MongoDB URI from environment or use default local URI"""
    return os.getenv("MONGODB_URI", DEFAULT_MONGODB_URI)

def get_mongodb_db() -> str:
    """Get MongoDB database name from environment or use default"""
    return os.getenv("MONGODB_DB", DEFAULT_MONGODB_DB)

def get_openai_api_key() -> Optional[str]:
    """Get OpenAI API key from environment"""
    return os.getenv("OPENAI_API_KEY")

def get_google_api_key() -> Optional[str]:
    """Get Google API key from environment"""
    return os.getenv("GOOGLE_API_KEY")
