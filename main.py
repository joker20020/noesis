import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    host = os.getenv("NOESIS_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("NOESIS_WEB_PORT", "8000"))
    uvicorn.run("server.app:app", host=host, port=port, reload=False)
