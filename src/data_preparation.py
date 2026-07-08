import hashlib
import json
import random
import re
from pathlib import Path

RAW_PATH = Path(__file__).parent.parent / "data" / "raw" / "code_du_travail.json"
OUT_PATH = Path(__file__).parent.parent / "data" / "articles.json"


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def walk(node, section_path, articles):
    node_type = node.get("type")
    data = node.get("data", {})

    if node_type == "article":
        if data.get("etat") != "VIGUEUR" or not data.get("texte"):
            return
        texte = clean_text(data["texte"])
        immediate_section = section_path[-1] if section_path else ""
        embed_text = f"[{immediate_section}] {texte}" if immediate_section else texte
        articles.append(
            {
                "id": data.get("id"),
                "num": data.get("num", "").strip() if data.get("num") else data.get("num"),
                "texte": texte,
                "embed_text": embed_text,
                "section_path": " > ".join(section_path),
                "source": "Code du travail",
                "etat": data.get("etat"),
                "hash": hashlib.sha256(texte.encode("utf-8")).hexdigest(), #Pour le maj des artcilces apres
            }
        )
        return

    title = data.get("title", "").strip() if data.get("title") else None
    next_path = section_path + [title] if title else section_path
    for child in node.get("children", []):
        walk(child, next_path, articles)


def quality_control(articles, n=10):
    sample = random.sample(articles, min(n, len(articles)))
    for a in sample:
        print(f"ID: {a['id']}")
        print(f"Num: {a['num']}")
        print(f"Section: {a['section_path']}")
        print(f"Embed text: {a['embed_text'][:300]}")
        print("-" * 10)



if __name__ == "__main__":
    with open(RAW_PATH) as f:
        root = json.load(f)

    articles = []
    walk(root, [], articles)

    with open(OUT_PATH, "w") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"{len(articles)} articles en vigueur extraits -> {OUT_PATH}")

    quality_control(articles)