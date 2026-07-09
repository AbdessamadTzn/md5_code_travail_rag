from src.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL, VECTOR_BACKEND, VECTOR_DB_PATH
from src.supabase_vector_db import SupabaseVectorDB
from src.vector_db import VectorDB


def get_vector_db():
	if VECTOR_BACKEND == "supabase":
		return SupabaseVectorDB()
	return VectorDB(vector_db_path=VECTOR_DB_PATH)
