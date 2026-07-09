# Supabase (vecteurs RAG)

## 1. Créer le projet Supabase

1. Va sur [supabase.com](https://supabase.com) et crée un projet.
2. Copie dans ton `.env` :
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY` (pour l'UI frontend)
   - `SUPABASE_SERVICE_ROLE_KEY` (backend / upload uniquement, jamais dans le navigateur)
3. Mets `VECTOR_BACKEND=supabase`.

## 2. Appliquer le schéma SQL

Dans **Supabase Dashboard → SQL Editor**, exécute le fichier :

`supabase/migrations/20260709120000_rag_chunks.sql`

Ça crée :
- la table `rag_chunks` (14 854 chunks, embeddings 512D)
- les fonctions RPC `match_rag_chunks` et `search_rag_chunks_by_keyword`
- une policy lecture publique (anon/authenticated) pour l'UI

## 3. Uploader la DB locale vers Supabase

```powershell
.\.venv\Scripts\pip install supabase
.\.venv\Scripts\python -m scripts.upload_to_supabase --truncate
```

Le script lit `my_vector_db` (Chroma) et envoie les chunks + embeddings vers Supabase.

## 4. Tester le RAG avec Supabase

```powershell
.\.venv\Scripts\python -m src.agents.rag_agent
```

## 5. Utiliser depuis une UI (frontend)

Avec `@supabase/supabase-js` et la clé **anon** :

```ts
const { data } = await supabase.rpc('match_rag_chunks', {
  query_embedding: embedding, // float[512] calculé côté backend
  match_count: 5,
})
```

```ts
const { data } = await supabase.rpc('search_rag_chunks_by_keyword', {
  keyword: 'salaire minimum de croissance',
  match_count: 5,
})
```

Pour l'UI, le plus simple est souvent :
- **frontend** : chat + affichage
- **backend** (Python/FastAPI) : embedding question + appel Groq + RPC Supabase

## Revenir en local (Chroma)

Dans `.env` :

```
VECTOR_BACKEND=chroma
```
