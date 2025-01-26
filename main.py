from app import app
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

if __name__ == "__main__":
    # Use Flask's built-in server only for development; not for production
    app.run(host="0.0.0.0", port=8080)

