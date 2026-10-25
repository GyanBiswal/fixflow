"""Loads settings from the .env file and builds the database URL."""
import os

from dotenv import load_dotenv
from sqlalchemy.engine import URL

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "fixflow_user")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "fixflow")

if not DB_PASSWORD or DB_PASSWORD == "your_db_password_here":
    raise RuntimeError("DB_PASSWORD is missing. Put the fixflow_user password in your .env file.")

# URL.create handles special characters in the password safely.
DATABASE_URL = URL.create(
    drivername="mysql+pymysql",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
    query={"charset": "utf8mb4"},
)
