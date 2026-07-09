import os
import re

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from supabase import create_client

from src.config import EMBEDDING_MODEL

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


class VectorDB:
	def __init__(self):
		if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
			raise ValueError(
				"SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env"
			)
		self.supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
		self.sentence_transformers_object = SentenceTransformer(EMBEDDING_MODEL)

	def get_embeddings(self, texts):
		if isinstance(texts, str):
			texts = [texts]
		embeddings = self.sentence_transformers_object.encode(
			texts,
			batch_size=64,
			normalize_embeddings=True,
			show_progress_bar=False,
		).tolist()
		return embeddings[0] if len(texts) == 1 else embeddings

	def retrieve(self, question, n=5, sub_questions=None):
		queries = self._normalize_queries(question, sub_questions)
		merged_documents = []
		merged_metadatas = []
		seen_keys = set()
		per_query_limit = max(2, (n * 2) // len(queries))

		def add_candidates(documents, metadatas, source=None):
			for doc, meta in zip(documents, metadatas):
				if source:
					meta = {**meta, "retrieval_source": source}
				key = (meta.get("article_id"), meta.get("chunk_index"), doc[:120])
				if key in seen_keys:
					continue
				seen_keys.add(key)
				merged_documents.append(doc)
				merged_metadatas.append(meta)

		for query in queries:
			add_candidates(
				*self._search_by_keywords(self._domain_keywords(query), per_query_limit),
				source="keyword",
			)
			add_candidates(
				*self._search_by_keywords(self._general_keywords(query), per_query_limit),
				source="keyword",
			)
			add_candidates(*self._search_by_semantic(query, per_query_limit), source="semantic")

		documents, metadatas = merged_documents[: n * 2], merged_metadatas[: n * 2]
		return self._rerank_for_question(question, documents, metadatas)[:n]

	def retrieve_hybrid(self, question, sub_questions=None, n=5):
		return self.retrieve(question, n=n, sub_questions=sub_questions)

	def _normalize_queries(self, question, sub_questions):
		queries = []
		for item in [question, *(sub_questions or [])]:
			cleaned = " ".join(str(item).split()).strip()
			if cleaned and cleaned not in queries:
				queries.append(cleaned)
		return queries or [question]

	def _search_by_semantic(self, question, limit):
		query_embedding = self.get_embeddings(question)
		response = self.supabase.rpc(
			"match_rag_chunks",
			{"query_embedding": query_embedding, "match_count": max(limit * 2, 6)},
		).execute()

		documents = []
		metadatas = []
		for row in response.data or []:
			similarity = row.get("similarity")
			if similarity is not None and similarity < 0.25:
				continue
			documents.append(row["content"])
			metadatas.append(self._row_to_metadata(row))
			if len(documents) >= limit:
				break

		return documents, metadatas

	def _search_by_keywords(self, keywords, limit):
		documents = []
		metadatas = []
		seen = set()
		per_keyword_limit = 2

		for keyword in keywords:
			try:
				response = self.supabase.rpc(
					"search_rag_chunks_by_keyword",
					{"keyword": keyword, "match_count": per_keyword_limit},
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
			"id": row.get("id"),
			"article_id": row.get("article_id"),
			"num": row.get("num"),
			"section_path": row.get("section_path"),
			"source": row.get("source"),
			"etat": row.get("etat"),
			"chunk_index": row.get("chunk_index"),
			"chunk_count": row.get("chunk_count"),
			"article_hash": row.get("article_hash"),
			"similarity": float(row["similarity"]) if row.get("similarity") is not None else None,
		}

	def _domain_keywords(self, question):
		normalized_question = question.lower()
		keywords = []

		if "smic" in normalized_question or "salaire minimum" in normalized_question:
			keywords.extend(
				[
					"Article: L3231-2",
					"salaire minimum de croissance assure",
					"Chapitre Ier : Salaire minimum interprofessionnel de croissance",
				]
			)

		if (
			("heure" in normalized_question or "heures" in normalized_question)
			and "travail" in normalized_question
		) or "durée légale" in normalized_question:
			keywords.extend(
				[
					"trente-cinq heures par semaine",
					"durée légale de travail effectif",
					"Article: L3121-27",
				]
			)

		return keywords

	def _general_keywords(self, question):
		normalized_question = question.lower()
		raw_tokens = re.findall(r"[a-zA-ZÀ-ÿ0-9]{4,}", normalized_question)
		stopwords = {"quoi", "comment", "combien", "avec", "pour", "dans", "cest", "estil", "france", "peut"}
		keywords = [token for token in raw_tokens if token not in stopwords]

		if "smic" in normalized_question:
			keywords.extend(["salaire minimum de croissance"])
		if "heure" in normalized_question and "travail" in normalized_question:
			keywords.append("durée légale du travail")

		return keywords[:8]

	def _rerank_for_question(self, question, documents, metadatas):
		normalized_question = question.lower()

		def priority(meta):
			num = meta.get("num") or ""
			section = (meta.get("section_path") or "").lower()

			if "smic" in normalized_question or "salaire minimum" in normalized_question:
				if num.startswith("L3231"):
					return 0
				if "salaire minimum interprofessionnel de croissance" in section:
					return 1

			if (
				("heure" in normalized_question or "heures" in normalized_question)
				and "travail" in normalized_question
			) or "durée légale" in normalized_question:
				if num == "L3121-27":
					return 0
				if "durée légale" in section:
					return 1

			similarity = meta.get("similarity")
			source = meta.get("retrieval_source")
			if source == "keyword":
				return 1
			if similarity is not None:
				return 2 - similarity
			return 3

		ranked = sorted(zip(documents, metadatas), key=lambda item: priority(item[1]))
		if not ranked:
			return documents, metadatas
		documents, metadatas = zip(*ranked)
		return list(documents), list(metadatas)

	def close(self):
		pass


if __name__ == "__main__":
	vector_db = VectorDB()
	docs, meta = vector_db.retrieve("Quelle est la durée légale du travail ?")
	print(f"Found {len(docs)} documents:")
	for i, (doc, m) in enumerate(zip(docs, meta)):
		print(f"\n--- Document {i+1} ---")
		print(f"Num: {m['num']}")
		print(f"Similarity: {m.get('similarity')}")
		print(f"Content: {doc[:200]}...")
