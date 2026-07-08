from dotenv import load_dotenv
import os

load_dotenv()


GROQ_API_KEY=os.environ["GROQ_API_KEY"]


EMBEDDING_MODEL="distiluse-base-multilingual-cased-v2"
LLM_MODEL="openai/gpt-oss-120b"
MODERATOR_MODEL="openai/gpt-oss-safeguard-20b"