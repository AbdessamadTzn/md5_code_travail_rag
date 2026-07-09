import os
import psycopg2
from psycopg2.extras import RealDictCursor
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from config import EMBEDDING_MODEL

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")


class VectorDB:
	def __init__(self):
		if not DATABASE_URL:
			raise ValueError("DATABASE_URL not set in environment")
		self.sentence_transformers_object = SentenceTransformer(EMBEDDING_MODEL)
		self.conn = psycopg2.connect(DATABASE_URL)


	def get_embeddings(self, texts):
		if isinstance(texts, str):
			texts = [texts]
		embeddings = self.sentence_transformers_object.encode(
			texts,
			batch_size=64,
			normalize_embeddings=True,
			show_progress_bar=False
		).tolist()
		return embeddings[0] if len(texts) == 1 else embeddings


	def retrieve(self, question, n=3):
		query_embedding = self.get_embeddings(question)

		with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
			cur.execute(
				"SELECT * FROM public.match_rag_chunks(%s, %s);",
				(query_embedding, n)
			)
			results = cur.fetchall()

		if not results:
			return [], []

		documents = [r["content"] for r in results]
		metadatas = [
			{
				"id": r["id"],
				"article_id": r["article_id"],
				"num": r["num"],
				"section_path": r["section_path"],
				"source": r["source"],
				"etat": r["etat"],
				"chunk_index": r["chunk_index"],
				"chunk_count": r["chunk_count"],
				"similarity": float(r["similarity"]) if r.get("similarity") else None,
			}
			for r in results
		]

		return documents, metadatas


	def close(self):
		if self.conn:
			self.conn.close()


if __name__ == "__main__":
	vector_db = VectorDB()

	docs, meta = vector_db.retrieve("Quelle est la durée légale du travail ?")

	print(f"Found {len(docs)} documents:")
	for i, (doc, m) in enumerate(zip(docs, meta)):
		print(f"\n--- Document {i+1} ---")
		print(f"Num: {m['num']}")
		print(f"Similarity: {m['similarity']}")
		print(f"Content: {doc[:200]}...")

	vector_db.close()
