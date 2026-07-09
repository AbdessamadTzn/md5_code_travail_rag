from dotenv import load_dotenv
import os

load_dotenv()


GROQ_API_KEY=os.environ["GROQ_API_KEY"]

SUPABASE_URL=os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY=os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY=os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
EMBEDDING_MODEL="distiluse-base-multilingual-cased-v2"
LLM_MODEL="openai/gpt-oss-120b"
MODERATOR_MODEL="openai/gpt-oss-safeguard-20b"
QUESTION_FORMATTER_MODEL="openai/gpt-oss-120b"
QUESTION_DECOMPOSER_MODEL="openai/gpt-oss-120b"
VECTOR_DB_PATH="my_vector_db"
VECTOR_BACKEND=os.environ.get("VECTOR_BACKEND", "chroma")
