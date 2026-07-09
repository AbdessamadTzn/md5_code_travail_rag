from src.config import EMBEDDING_MODEL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from src.vector_db import VectorDB
from supabase import Client, create_client


class SupabaseVectorDB(VectorDB):
	def __init__(self):
		if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
			raise ValueError(
				"SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for Supabase vector backend."
			)
		self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
		self.sentence_transformers_object = None
		self._load_embedding_model()

	def _load_embedding_model(self):
		response = (
			self.supabase.table("rag_chunks")
			.select("embedding_model")
			.limit(1)
			.execute()
		)
		if not response.data:
			raise ValueError("rag_chunks table is empty. Run scripts/upload_to_supabase.py first.")
		model_name = response.data[0].get("embedding_model") or EMBEDDING_MODEL
		from sentence_transformers import SentenceTransformer

		self.sentence_transformers_object = SentenceTransformer(model_name)

	def retrieve(self, question, n=5):
		merged_documents = []
		merged_metadatas = []
		seen_keys = set()

		def add_candidates(documents, metadatas):
			for doc, meta in zip(documents, metadatas):
				key = (meta.get("article_id"), meta.get("chunk_index"), doc[:120])
				if key in seen_keys:
					continue
				seen_keys.add(key)
				merged_documents.append(doc)
				merged_metadatas.append(meta)

		domain_keywords = self._domain_keywords(question)
		add_candidates(*self._search_by_keywords(domain_keywords, limit=n))

		general_keywords = self._general_keywords(question)
		add_candidates(*self._search_by_keywords(general_keywords, limit=n))

		embedded_question = self.get_embeddings([question])[0]
		semantic_response = self.supabase.rpc(
			"match_rag_chunks",
			{"query_embedding": embedded_question, "match_count": max(n * 3, 10)},
		).execute()

		max_semantic_distance = 1.6
		semantic_documents = []
		semantic_metadatas = []
		for row in semantic_response.data or []:
			similarity = row.get("similarity")
			distance = None if similarity is None else 1 - similarity
			if distance is not None and distance > max_semantic_distance:
				continue
			semantic_documents.append(row["content"])
			semantic_metadatas.append(self._row_to_metadata(row))

		add_candidates(semantic_documents, semantic_metadatas)
		return merged_documents[:n], merged_metadatas[:n]

	def _search_by_keywords(self, keywords, limit):
		documents = []
		metadatas = []
		seen = set()

		for keyword in keywords:
			try:
				response = self.supabase.rpc(
					"search_rag_chunks_by_keyword",
					{"keyword": keyword, "match_count": limit},
				).execute()
			except Exception:
				continue

			for row in response.data or []:
				doc = row["content"]
				meta = self._row_to_metadata(row)
				key = (meta.get("article_id"), meta.get("chunk_index"), doc[:120])
				if key in seen:
					continue
				seen.add(key)
				documents.append(doc)
				metadatas.append(meta)
				if len(documents) >= limit:
					return documents, metadatas

		return documents, metadatas

	@staticmethod
	def _row_to_metadata(row):
		return {
			"article_id": row.get("article_id"),
			"chunk_index": row.get("chunk_index"),
			"chunk_count": row.get("chunk_count"),
			"source": row.get("source"),
			"num": row.get("num"),
			"section_path": row.get("section_path"),
			"etat": row.get("etat"),
			"article_hash": row.get("article_hash"),
		}
