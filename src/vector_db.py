import chromadb
from sentence_transformers import SentenceTransformer
from src.config import EMBEDDING_MODEL, VECTOR_DB_PATH

import os
import pandas
import re
import argparse
import shutil
from pathlib import Path

class VectorDB:
	def __init__(self, vector_db_path="", corpus_df=None):
		if os.path.exists(vector_db_path):
			self.load_vector_db(vector_db_path)


		elif corpus_df is not None and not corpus_df.empty:
			self.create_vector_db(vector_db_path, corpus_df)
		else:
			raise ValueError(
				"VectorDB initialization failed: provide an existing vector_db_path or a non-empty corpus_df."
			)


	def load_vector_db(self, vector_db_path):
		print("Loading Vector DB")
		self.chroma_vector_db = chromadb.PersistentClient(path=vector_db_path)
		collection = self.chroma_vector_db.get_collection(name="rag_knowledge")

		if "embedding_model" in collection.metadata.keys():
			self.sentence_transformers_object = SentenceTransformer(collection.metadata["embedding_model"])
		else:
			raise(Exception("Error : we miss the embeddings model's name information"))

	
	def create_vector_db(self, vector_db_path, corpus_df):
		print("Creating Vector DB")
		self.sentence_transformers_object = SentenceTransformer(EMBEDDING_MODEL)

		self.chroma_vector_db = chromadb.PersistentClient(path=vector_db_path)

		collection = self.chroma_vector_db.get_or_create_collection(
			name="rag_knowledge",
			metadata={
				"embedding_model": EMBEDDING_MODEL
			}
		)

		chuncks, ids, metadatas = self._build_chunks(corpus_df)
		embeddings = self.get_embeddings(chuncks)

		BATCH_SIZE = 5000

		for i in range(0, len(chuncks), BATCH_SIZE):
			collection.add(
				ids=ids[i : i + BATCH_SIZE],
				documents=chuncks[i : i + BATCH_SIZE],
				embeddings=embeddings[i : i + BATCH_SIZE],
				metadatas=metadatas[i : i + BATCH_SIZE],
			)





	def get_embeddings(self, chuncks):
		embeddings = self.sentence_transformers_object.encode(
			chuncks,
			batch_size=64,
			normalize_embeddings=True,
			show_progress_bar=True
		).tolist()
		return embeddings


	def _build_chunks(self, corpus_df):
		chunks = []
		ids = []
		metadatas = []

		for _, row in corpus_df.iterrows():
			article_id = str(row["id"])
			article_num = row.get("num", "")
			section_path = row.get("section_path", "")
			source = row.get("source", "")
			etat = row.get("etat", "")
			article_hash = row.get("hash", "")
			article_text = str(row.get("texte", row.get("embed_text", "")))

			article_chunks = self._chunk_text(article_text)
			total_chunks = len(article_chunks)

			for chunk_index, chunk in enumerate(article_chunks):
				chunk_with_context = self._format_chunk_for_embedding(
					source=source,
					section_path=section_path,
					article_num=article_num,
					chunk_text=chunk,
				)
				chunks.append(chunk_with_context)
				ids.append(f"{article_id}__chunk_{chunk_index}")
				metadatas.append(
					{
						"article_id": article_id,
						"chunk_index": chunk_index,
						"chunk_count": total_chunks,
						"source": source,
						"num": article_num,
						"section_path": section_path,
						"etat": etat,
						"article_hash": article_hash,
					}
				)

		return chunks, ids, metadatas


	@staticmethod
	def _chunk_text(text, max_chars=900, overlap_chars=160):
		text = " ".join(str(text).split())
		if len(text) <= max_chars:
			return [text]

		sentences = re.split(r"(?<=[\.\!\?;:])\s+", text)
		if len(sentences) <= 1:
			return VectorDB._fallback_char_chunking(text, max_chars=max_chars, overlap_chars=overlap_chars)

		chunks = []
		current = ""
		for sentence in sentences:
			if not sentence:
				continue
			candidate = f"{current} {sentence}".strip() if current else sentence
			if len(candidate) <= max_chars:
				current = candidate
				continue

			if current:
				chunks.append(current)
				overlap = current[-overlap_chars:].strip() if overlap_chars > 0 else ""
				current = f"{overlap} {sentence}".strip() if overlap else sentence
				if len(current) > max_chars:
					chunks.extend(VectorDB._fallback_char_chunking(current, max_chars=max_chars, overlap_chars=overlap_chars))
					current = ""
			else:
				chunks.extend(VectorDB._fallback_char_chunking(sentence, max_chars=max_chars, overlap_chars=overlap_chars))

		if current:
			chunks.append(current)

		return chunks or [text]


	@staticmethod
	def _fallback_char_chunking(text, max_chars=900, overlap_chars=160):
		chunks = []
		start = 0
		text_len = len(text)
		while start < text_len:
			end = min(start + max_chars, text_len)
			if end < text_len:
				last_space = text.rfind(" ", start, end)
				if last_space > start + int(max_chars * 0.6):
					end = last_space
			chunk = text[start:end].strip()
			if chunk:
				chunks.append(chunk)
			if end >= text_len:
				break
			start = max(0, end - overlap_chars)
		return chunks or [text]


	@staticmethod
	def _format_chunk_for_embedding(source, section_path, article_num, chunk_text):
		header_parts = []
		if source:
			header_parts.append(f"Source: {source}")
		if section_path:
			header_parts.append(f"Section: {section_path}")
		if article_num:
			header_parts.append(f"Article: {article_num}")
		header = " | ".join(header_parts)
		if header:
			return f"{header}\n{chunk_text}"
		return chunk_text


	@staticmethod
	def delete_vector_db(vector_db_path):
		path_obj = Path(vector_db_path)
		if path_obj.exists():
			shutil.rmtree(path_obj)
			print(f"Deleted vector DB at: {vector_db_path}")



	def retrieve(self, question, n=5):
		collection = self.chroma_vector_db.get_collection("rag_knowledge")
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
		add_candidates(*self._search_by_keywords(collection, domain_keywords, limit=n))

		general_keywords = self._general_keywords(question)
		add_candidates(*self._search_by_keywords(collection, general_keywords, limit=n))

		embedded_question = self.get_embeddings([question])
		results = collection.query(
			query_embeddings=embedded_question,
			n_results=max(n * 3, 10),
			include=["documents", "metadatas", "distances"],
		)
		raw_documents = results["documents"][0] if results.get("documents") else []
		raw_metadatas = results["metadatas"][0] if results.get("metadatas") else []
		raw_distances = results["distances"][0] if results.get("distances") else []

		max_semantic_distance = 1.6
		semantic_documents = []
		semantic_metadatas = []
		for doc, md, dist in zip(raw_documents, raw_metadatas, raw_distances):
			if dist is None or dist <= max_semantic_distance:
				semantic_documents.append(doc)
				semantic_metadatas.append(md)

		add_candidates(semantic_documents, semantic_metadatas)
		return merged_documents[:n], merged_metadatas[:n]


	def _domain_keywords(self, question):
		normalized_question = question.lower()
		keywords = []

		if "smic" in normalized_question or "salaire minimum" in normalized_question:
			keywords.extend(
				[
					"Salaire minimum interprofessionnel de croissance",
					"salaire minimum de croissance assure",
					"Article: L3231-2",
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


	def _search_by_keywords(self, collection, keywords, limit):
		documents = []
		metadatas = []
		seen = set()

		for keyword in keywords:
			try:
				result = collection.get(
					where_document={"$contains": keyword},
					limit=limit,
					include=["documents", "metadatas"],
				)
			except Exception:
				continue

			for doc, meta in zip(result.get("documents", []), result.get("metadatas", [])):
				key = (meta.get("article_id"), meta.get("chunk_index"), doc[:120])
				if key in seen:
					continue
				seen.add(key)
				documents.append(doc)
				metadatas.append(meta)
				if len(documents) >= limit:
					return documents, metadatas

		return documents, metadatas



if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Create or rebuild Chroma vector DB")
	parser.add_argument("--rebuild", action="store_true", help="Delete and rebuild the vector DB")
	parser.add_argument("--db-path", default=VECTOR_DB_PATH, help="Path to vector DB directory")
	args = parser.parse_args()

	data_path = Path(__file__).resolve().parent.parent / "data" / "articles.json"
	corpus_df = pandas.read_json(data_path)

	if args.rebuild:
		VectorDB.delete_vector_db(args.db_path)

	vector_db_object = VectorDB(args.db_path, corpus_df)
	print(vector_db_object.retrieve(question="Quelle est la durée légale du travail ?"))