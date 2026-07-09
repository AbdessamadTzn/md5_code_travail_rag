"""Synchronisation incrémentale du Code du travail depuis SocialGouv/legi-data vers Supabase.

Logique :
1. Vérifie via l'API GitHub si le fichier source a changé depuis le dernier sync (SHA du dernier commit).
   - Si un fichier d'état local existe et le SHA est identique -> rien à faire (évite de télécharger 54 Mo).
2. Télécharge le JSON brut, ré-extrait les articles en vigueur (avec hash par article).
3. Compare aux hash déjà indexés dans Supabase (source de vérité, donc sans état local requis) :
   - added    : nouvel `id` -> à embedder + insérer
   - modified : `id` existant mais hash différent -> à ré-embedder + remplacer
   - removed  : `id` disparu -> à supprimer de Supabase
4. Ne (ré)embedde QUE les articles ajoutés/modifiés, puis upsert par chunk ; supprime les articles retirés.
"""

import argparse
import json
from pathlib import Path

import requests
from sentence_transformers import SentenceTransformer
from supabase import create_client

from src.config import EMBEDDING_MODEL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from src.data_preparation import walk
from src.vector_db import VectorDB

REPO = "SocialGouv/legi-data"
FILE_PATH = "data/LEGITEXT000006072050.json"
BRANCH = "master"
RAW_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{FILE_PATH}"
COMMITS_API = f"https://api.github.com/repos/{REPO}/commits"

ROOT = Path(__file__).parent.parent
RAW_PATH = ROOT / "data" / "raw" / "code_du_travail.json"
ARTICLES_PATH = ROOT / "data" / "articles.json"
STATE_PATH = ROOT / "data" / ".last_sync.json"


# --- Détection de changement côté source (GitHub) ---

def get_latest_sha():
	resp = requests.get(COMMITS_API, params={"path": FILE_PATH, "sha": BRANCH, "per_page": 1}, timeout=30)
	resp.raise_for_status()
	commits = resp.json()
	return commits[0]["sha"] if commits else None


def load_last_sha():
	if STATE_PATH.exists():
		return json.loads(STATE_PATH.read_text()).get("sha")
	return None


def save_last_sha(sha):
	STATE_PATH.write_text(json.dumps({"sha": sha}, indent=2))


# --- Extraction des articles (réutilise data_preparation) ---

def download_raw():
	RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
	resp = requests.get(RAW_URL, timeout=120)
	resp.raise_for_status()
	RAW_PATH.write_bytes(resp.content)


def extract_articles():
	root = json.loads(RAW_PATH.read_text())
	articles = []
	walk(root, [], articles)
	return {a["id"]: a for a in articles}


# --- État déjà indexé dans Supabase (hash par article_id) ---

def fetch_indexed_hashes(supabase):
	hashes = {}
	page_size = 1000
	offset = 0
	while True:
		rows = (
			supabase.table("rag_chunks")
			.select("article_id, article_hash")
			.range(offset, offset + page_size - 1)
			.execute()
			.data
		)
		if not rows:
			break
		for r in rows:
			hashes[r["article_id"]] = r.get("article_hash")
		if len(rows) < page_size:
			break
		offset += page_size
	return hashes


# --- Chunking + embedding (réutilise les helpers de VectorDB pour un découpage identique) ---

def build_rows(articles, model):
	rows = []
	for article in articles:
		article_id = str(article["id"])
		chunks = VectorDB._chunk_text(article["texte"])
		total = len(chunks)
		texts = [
			VectorDB._format_chunk_for_embedding(
				source=article.get("source", ""),
				section_path=article.get("section_path", ""),
				article_num=article.get("num", ""),
				chunk_text=chunk,
			)
			for chunk in chunks
		]
		embeddings = model.encode(texts, normalize_embeddings=True).tolist()
		for i, (text, embedding) in enumerate(zip(texts, embeddings)):
			rows.append(
				{
					"id": f"{article_id}__chunk_{i}",
					"article_id": article_id,
					"num": article.get("num"),
					"section_path": article.get("section_path"),
					"source": article.get("source"),
					"etat": article.get("etat"),
					"chunk_index": i,
					"chunk_count": total,
					"article_hash": article.get("hash"),
					"content": text,
					"embedding": embedding,
					"embedding_model": EMBEDDING_MODEL,
				}
			)
	return rows


def upsert_rows(supabase, rows, batch_size=200):
	for i in range(0, len(rows), batch_size):
		supabase.table("rag_chunks").upsert(rows[i : i + batch_size], on_conflict="id").execute()


def delete_articles(supabase, article_ids, batch_size=100):
	ids = list(article_ids)
	for i in range(0, len(ids), batch_size):
		supabase.table("rag_chunks").delete().in_("article_id", ids[i : i + batch_size]).execute()


def main():
	parser = argparse.ArgumentParser(description="Sync incrémentale Code du travail -> Supabase")
	parser.add_argument("--force", action="store_true", help="Ignore le SHA et resynchronise")
	args = parser.parse_args()

	if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
		raise ValueError("SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY requis dans .env")

	latest_sha = get_latest_sha()
	last_sha = load_last_sha()

	if not args.force and latest_sha and latest_sha == last_sha:
		print(f"Aucun changement (SHA {latest_sha[:7]}). Rien à faire.")
		return

	print("Téléchargement du JSON source...")
	download_raw()
	new_articles = extract_articles()
	print(f"{len(new_articles)} articles en vigueur extraits.")

	supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
	indexed = fetch_indexed_hashes(supabase)
	print(f"{len(indexed)} articles déjà indexés dans Supabase.")

	new_ids = set(new_articles)
	old_ids = set(indexed)

	added = new_ids - old_ids
	removed = old_ids - new_ids
	modified = {aid for aid in (new_ids & old_ids) if new_articles[aid]["hash"] != indexed[aid]}

	print(f"Ajoutés: {len(added)} | Modifiés: {len(modified)} | Supprimés: {len(removed)}")

	changed = added | modified
	if changed:
		model = SentenceTransformer(EMBEDDING_MODEL)
		# On supprime d'abord les anciens chunks des articles modifiés (leur nombre de chunks peut changer)
		delete_articles(supabase, modified)
		rows = build_rows([new_articles[aid] for aid in changed], model)
		upsert_rows(supabase, rows)
		print(f"{len(rows)} chunks upsertés pour {len(changed)} articles.")

	if removed:
		delete_articles(supabase, removed)
		print(f"{len(removed)} articles supprimés de Supabase.")

	# Sauvegarde de l'état pour le prochain run (optimisation early-exit)
	ARTICLES_PATH.write_text(json.dumps(list(new_articles.values()), ensure_ascii=False, indent=2))
	if latest_sha:
		save_last_sha(latest_sha)

	print("Sync terminé.")


if __name__ == "__main__":
	main()
