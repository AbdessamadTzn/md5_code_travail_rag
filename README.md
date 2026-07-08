# md5_code_travail_rag

RAG (Retrieval-Augmented Generation) sur le Code du travail français.

## Source des données

Les articles du Code du travail sont extraits du dataset JSON maintenu par
[SocialGouv/legi-data](https://github.com/SocialGouv/legi-data), qui synchronise
quotidiennement le contenu officiel de Légifrance (base LEGI, DILA).

Fichier utilisé : `data/LEGITEXT000006072050.json` (identifiant Légifrance du Code
du travail), téléchargé dans `data/raw/code_du_travail.json`.

Ce dataset a été préféré à l'API officielle Légifrance (PISTE) car l'accès à
cette API nécessite une validation manuelle par la DILA, incompatible avec les
délais du projet. Il a aussi été préféré à un dump XML brut LEGI (data.gouv.fr)
car déjà structuré en JSON (arbre de sections/articles), ce qui évite un parsing
XML manuel.

## Jalon 1 — Préparation des données

### Format de sortie

Chaque document produit dans `data/articles.json` contient :

| Champ          | Rôle                        | Description |
|----------------|------------------------------|-------------|
| `id`           | Identifiant                  | ID Légifrance de l'article (ex: `LEGIARTI000018764571`), stable dans le temps même si le texte change — sert de clé pour les mises à jour incrémentales (upsert) dans la vector DB |
| `num`          | Métadonnée                   | Numéro d'article (ex: `L1111-1`) |
| `texte`        | Texte à embedder             | Contenu nettoyé de l'article |
| `section_path` | Métadonnée                   | Chemin hiérarchique complet (Partie > Livre > Titre > Chapitre...) |
| `source`       | Métadonnée                   | `"Code du travail"` |
| `etat`         | Métadonnée                   | État juridique (seuls les articles `VIGUEUR` sont conservés) |

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

- Espaces doubles avant ponctuation (ex: `"l'article L. 3142-58 ,"` →
  `"l'article L. 3142-58,"`)
- Espaces multiples normalisés en un seul
- Espaces insécables (`\xa0`) normalisés
- `strip()` des espaces en début/fin de texte

### Contrôle qualité

10 documents sont tirés au hasard après extraction et affichés pour relecture
manuelle (voir `scripts/extract_articles.py`, section QC).

### Mise à jour incrémentale

Le dataset source est resynchronisé quotidiennement en amont. Stratégie de
mise à jour prévue :

1. Interroger l'API GitHub (`/commits?path=data/LEGITEXT000006072050.json`)
   pour connaître le dernier commit touchant le fichier
2. Si le SHA diffère du dernier sync connu → retélécharger le JSON
3. Recalculer un hash SHA256 du `texte` de chaque article et comparer aux hash
   déjà indexés dans la vector DB
4. `upsert` (par `id`) uniquement les articles dont le hash a changé, ajout des
   nouveaux, suppression de ceux disparus (abrogés)

## Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copier `.env.example` en `.env` et renseigner `GROQ_API_KEY`.
