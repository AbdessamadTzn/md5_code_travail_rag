from src.vector_db import VectorDB
from src.config import VECTOR_DB_PATH

db = VectorDB(vector_db_path=VECTOR_DB_PATH)
questions = [
    "c'est quoi le smic en france?",
    "Quelle est la durée légale du travail par semaine?",
]

for q in questions:
    print("Q:", q)
    docs, metas = db.retrieve(q, n=5)
    print("returned", len(docs))
    for i, (doc, meta) in enumerate(zip(docs, metas), 1):
        print(f"--- {i} num={meta.get('num')} chunk={meta.get('chunk_index')}")
        print(doc[:600])
        print()
