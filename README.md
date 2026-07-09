# md5_code_travail_rag

**RAG (Retrieval-Augmented Generation) sur le Code du travail français.**

Chatbot qui répond à des questions de droit du travail en s'appuyant uniquement
sur les articles du Code du travail, avec citation des sources. Le pipeline
couvre la préparation des données, le découpage (chunking), l'indexation
vectorielle (Supabase / pgvector), la génération augmentée via un LLM, et la
modération des questions.

---

## Architecture générale

```
Question utilisateur
        │
        ▼
┌──────────────────┐   hors-sujet / non sûr → refus
│  Moderator       │───────────────────────────────►
│  (LLM safeguard) │
└────────┬─────────┘
         │ question validée
         ▼
┌──────────────────┐   reformulation + découpage en sous-questions
│  Décomposeur /   │
│  Formatteur      │
└────────┬─────────┘
         ▼
┌──────────────────┐   embedding local (sentence-transformers)
│  Vector DB       │   recherche sémantique (pgvector) + fallback mots-clés
│  (Supabase)      │
└────────┬─────────┘
         │ chunks pertinents (contexte)
         ▼
┌──────────────────┐
│  RAG (LLM Groq)  │──► réponse + articles cités (num, section, similarité)
└──────────────────┘
```

L'ensemble est exposé par une **API FastAPI** et consommé par un **frontend
HTML/JS** statique.

---

## Source des données

Les articles du Code du travail sont extraits du dataset JSON maintenu par
[SocialGouv/legi-data](https://github.com/SocialGouv/legi-data), qui synchronise
quotidiennement le contenu officiel de Légifrance (base LEGI, DILA).

Fichier utilisé : `data/LEGITEXT000006072050.json` (identifiant Légifrance du
Code du travail), téléchargé dans `data/raw/code_du_travail.json`.

Ce dataset a été préféré à l'API officielle Légifrance (PISTE) car l'accès à
cette API nécessite une validation manuelle par la DILA, incompatible avec les
délais du projet. Il a aussi été préféré à un dump XML brut LEGI (data.gouv.fr)
car déjà structuré en JSON (arbre de sections/articles), ce qui évite un parsing
XML manuel.

---

## Jalon 1 — Préparation des données

Script : [`src/data_preparation.py`](src/data_preparation.py)
(télécharge/parse `data/raw/code_du_travail.json` → produit `data/articles.json`).

### Format de sortie

Chaque document produit dans `data/articles.json` contient :

| Champ          | Rôle             | Description |
|----------------|------------------|-------------|
| `id`           | Identifiant      | ID Légifrance de l'article (ex: `LEGIARTI000018764571`), stable dans le temps même si le texte change — sert de clé pour les mises à jour incrémentales (upsert) |
| `num`          | Métadonnée       | Numéro d'article (ex: `L1111-1`) |
| `texte`        | Texte à embedder | Contenu nettoyé de l'article |
| `embed_text`   | Texte à embedder | `texte` précédé du titre de la sous-section immédiate |
| `section_path` | Métadonnée       | Chemin hiérarchique complet (Partie > Livre > Titre > Chapitre...) |
| `source`       | Métadonnée       | `"Code du travail"` |
| `etat`         | Métadonnée       | État juridique (seuls les articles `VIGUEUR` sont conservés) |
| `hash`         | Contrôle         | SHA256 du `texte`, utilisé pour la mise à jour incrémentale |

### Choix : que mettre dans le texte embeddé ?

- **Dans le texte embeddé** : le `texte` de l'article, nettoyé, précédé du titre
  de la sous-section **immédiate** (le niveau le plus proche, pas tout le chemin).
  Objectif : donner un contexte thématique court sans diluer l'embedding — le
  `section_path` complet est répété sur des centaines d'articles et n'apporterait
  aucun signal discriminant.
- **Uniquement en métadonnées** : `id`, `num`, `section_path` complet, `source`,
  `etat`. Utiles pour le filtrage, l'affichage et la citation, mais pas pour la
  similarité sémantique.

### Nettoyage appliqué

Les articles bruts contiennent quelques scories issues de l'extraction (retrait
des liens hypertexte vers d'autres articles dans le HTML source) :

- Espaces doubles avant ponctuation (ex: `"l'article L. 3142-58 ,"` → `"l'article L. 3142-58,"`)
- Espaces multiples normalisés en un seul
- Espaces insécables (`\xa0`) normalisés
- `strip()` des espaces en début/fin de texte

### Contrôle qualité

10 documents sont tirés au hasard après extraction et affichés pour relecture
manuelle (fonction `quality_control` dans `src/data_preparation.py`).

---

## Jalon 2 — Chunking & indexation vectorielle

Les articles longs sont **découpés en chunks** avant l'embedding : un article
« fleuve » embeddé entier dilue son propre signal sémantique et dégrade la
recherche. Le découpage se fait par phrases regroupées jusqu'à une taille cible
(avec léger chevauchement), en conservant sur chaque chunk le contexte de
l'article parent (`article_id`, `num`, `section_path`).

Chaque chunk est embeddé **localement** avec `sentence-transformers`
(modèle `distiluse-base-multilingual-cased-v2`, 512 dimensions) — pas d'appel
API pour l'embedding.

### Backend vectoriel (Supabase / pgvector)

La base vectorielle de production est **Supabase (PostgreSQL + pgvector)**.
Table `rag_chunks` : contenu, embedding `vector(512)`, métadonnées, `article_hash`.
La recherche se fait via une fonction SQL `match_rag_chunks` (distance cosinus),
avec un fallback recherche par mots-clés.

- `src/vector_store.py` : sélectionne le backend selon `VECTOR_BACKEND` (`chroma` | `supabase`)
- `src/supabase_vector_db.py` / `src/vector_db_supabase.py` : accès Supabase
- `scripts/upload_to_supabase.py` : upload/upsert des chunks vers Supabase

---

## Le RAG (agents)

Tous les agents héritent de `src/agents/base_agent.py` (client Groq partagé).
Chaque agent a son prompt système dans un `.txt` dédié.

| Agent | Rôle | Modèle (Groq) |
|-------|------|---------------|
| `Moderator` (`moderator_agent.py`) | Filtre les questions non sûres / hors-sujet, renvoie `{safe, in_scope, reason}` | `openai/gpt-oss-safeguard-20b` |
| Décomposeur / Formatteur (`question_decomposer_agent.py`, `question_formatter_agent.py`) | Reformule et découpe la question en sous-questions de recherche | `openai/gpt-oss-120b` |
| `Rag` (`rag_agent_supabase.py`) | Récupère les chunks pertinents et génère la réponse ancrée sur les sources | `openai/gpt-oss-120b` |

L'embedding est local ; **seuls le LLM et le modérateur passent par l'API Groq**
(d'où une seule clé `GROQ_API_KEY` nécessaire).

---

## API (FastAPI)

Fichier : [`src/main.py`](src/main.py)

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/ask` | POST | Corps `{"question": "..."}`. Modère → (refuse si non sûr/hors-sujet) → décompose → recherche → génère. Renvoie `response`, `documents`, `metadatas`, `moderation`, `sub_questions`, `formatted_question` |
| `/health` | GET | `{"status": "ok"}` |
| `/` | GET | Sert le frontend statique (`frontend/`) |

---

## Frontend

`frontend/` — HTML/CSS/JS pur (Tailwind via CDN), **sans build Node.js**.
Servable directement (`python -m http.server`) ou monté par FastAPI sur `/`.
Affiche la réponse, le statut de modération, et les articles sources
(numéro, section, score de similarité).

---

## Mise à jour incrémentale (cron)

Le dataset source est resynchronisé quotidiennement en amont. La sync
incrémentale évite de tout ré-embedder à chaque fois.

Script : [`scripts/sync_from_github.py`](scripts/sync_from_github.py)

1. Interroge l'API GitHub (`/commits?path=data/LEGITEXT000006072050.json`) pour
   le SHA du dernier commit. Si identique au dernier sync → **arrêt immédiat**
   (pas de téléchargement).
2. Sinon : retélécharge le JSON, ré-extrait les articles (avec hash).
3. Compare aux `article_hash` déjà indexés dans Supabase :
   - **added** : nouvel `id` → embed + insert
   - **modified** : `id` existant, hash différent → ré-embed + remplace
   - **removed** : `id` disparu (abrogé) → suppression
4. Ne (ré)embedde **que** les articles ajoutés/modifiés (upsert par chunk).

Le cron est un **GitHub Actions schedulé** :
[`.github/workflows/sync-supabase.yml`](.github/workflows/sync-supabase.yml)
(quotidien à 03:00 UTC + déclenchement manuel). Aucun serveur allumé en
permanence. Secrets requis côté Actions : `GROQ_API_KEY`, `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`.

---

## Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copier `.env.example` en `.env` et renseigner :

| Variable | Rôle |
|----------|------|
| `GROQ_API_KEY` | Clé API Groq (LLM + modérateur) — **requis** |
| `VECTOR_BACKEND` | `supabase` (prod) ou `chroma` (local) |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | Accès Supabase (écriture, ex. upload/sync) |
| `SUPABASE_ANON_KEY` | Accès Supabase en lecture |
| `DATABASE_URL` | Connexion Postgres directe (alternative à la clé Supabase) |

## Lancement en local

**Backend (API + frontend servi sur `/`)** :
```bash
uvicorn src.main:app --reload
# http://localhost:8000
```

**Frontend seul (statique)** :
```bash
cd frontend && python -m http.server 3000
```

## Déploiement

Voir [`DEPLOYMENT.md`](DEPLOYMENT.md) — backend sur **Render**
(`uvicorn src.main:app --host 0.0.0.0 --port $PORT`), frontend sur **Vercel**
(root directory `frontend/`, preset « Other »).

---

## Structure du projet

```
src/
  main.py                    # API FastAPI (/ask, /health, sert le frontend)
  config.py                  # variables d'env + modèles
  data_preparation.py        # Jalon 1 : extraction + nettoyage + hash
  vector_store.py            # sélection du backend vectoriel
  supabase_vector_db.py      # recherche vectorielle Supabase (+ fallback mots-clés)
  vector_db_supabase.py      # accès Supabase
  agents/
    base_agent.py            # client Groq partagé
    moderator_agent.py       # modération des questions
    question_decomposer_agent.py / question_formatter_agent.py
    rag_agent_supabase.py    # retrieval + génération
    *_prompt_system.txt      # prompts système
scripts/
  upload_to_supabase.py      # upload des chunks vers Supabase
  sync_from_github.py        # sync incrémentale (cron)
frontend/                    # UI statique HTML/CSS/JS
.github/workflows/
  sync-supabase.yml          # cron GitHub Actions
data/                        # (gitignoré) JSON bruts, articles, base locale
```
