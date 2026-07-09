import argparse
import chromadb
from pathlib import Path

from supabase import create_client

from src.config import EMBEDDING_MODEL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL, VECTOR_DB_PATH


def to_embedding_list(embedding):
	if hasattr(embedding, "tolist"):
		return embedding.tolist()
	return list(embedding)


def export_chroma_rows(collection, offset, limit):
	result = collection.get(
		limit=limit,
		offset=offset,
		include=["documents", "metadatas", "embeddings"],
	)
	rows = []
	for chunk_id, document, metadata, embedding in zip(
		result["ids"],
		result["documents"],
		result["metadatas"],
		result["embeddings"],
	):
		rows.append(
			{
				"id": chunk_id,
				"article_id": metadata.get("article_id"),
				"num": metadata.get("num"),
				"section_path": metadata.get("section_path"),
				"source": metadata.get("source"),
				"etat": metadata.get("etat"),
				"chunk_index": metadata.get("chunk_index", 0),
				"chunk_count": metadata.get("chunk_count", 1),
				"article_hash": metadata.get("article_hash"),
				"content": document,
				"embedding": to_embedding_list(embedding),
				"embedding_model": EMBEDDING_MODEL,
			}
		)
	return rows


def upload_rows(supabase_client, rows):
	if not rows:
		return 0
	supabase_client.table("rag_chunks").upsert(rows, on_conflict="id").execute()
	return len(rows)


def main():
	parser = argparse.ArgumentParser(description="Upload local Chroma vectors to Supabase")
	parser.add_argument("--db-path", default=VECTOR_DB_PATH)
	parser.add_argument("--batch-size", type=int, default=200)
	parser.add_argument("--truncate", action="store_true", help="Delete all rows before upload")
	args = parser.parse_args()

	if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
		raise ValueError("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env")

	supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
	if args.truncate:
		supabase.table("rag_chunks").delete().neq("id", "").execute()
		print("Cleared rag_chunks table")

	chroma = chromadb.PersistentClient(path=args.db_path)
	collection = chroma.get_collection("rag_knowledge")
	total = collection.count()
	print(f"Exporting {total} chunks from {args.db_path}")

	uploaded = 0
	for offset in range(0, total, args.batch_size):
		rows = export_chroma_rows(collection, offset=offset, limit=args.batch_size)
		uploaded += upload_rows(supabase, rows)
		print(f"Uploaded {uploaded}/{total}")

	print("Done.")


if __name__ == "__main__":
	main()
