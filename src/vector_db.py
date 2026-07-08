import chromadb
from sentence_transformers import SentenceTransformer
from config import EMBEDDING_MODEL

import os
import pandas

class VectorDB:
	def __init__(self, vector_db_path="", corpus_df=None):
		if os.path.exists(vector_db_path):
			self.load_vector_db(vector_db_path)


		elif not corpus_df.empty:
			self.create_vector_db(vector_db_path, corpus_df)


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

		chuncks = list(corpus_df["embed_text"].values)

		embeddings = self.get_embeddings(chuncks)

		collection.add(
			ids = list(corpus_df["id"].values),
			documents=chuncks,
			embeddings=embeddings,
			metadatas=[{"source": row["source"], "num": row["num"], "section_path": row["section_path"], "etat": row["etat"]} for _, row in corpus_df.iterrows()]
			)



	def get_embeddings(self, chuncks):
		embeddings = self.sentence_transformers_object.encode(
			chuncks,
			batch_size=64,
			normalize_embeddings=True,
			show_progress_bar=True
		).tolist()
		return embeddings



	def retrieve(self, question, n=3):
		embedded_question = self.get_embeddings([question])

		collection = self.chroma_vector_db.get_collection("rag_knowledge")

		results = collection.query(query_embeddings=embedded_question, n_results=n)

		return results["documents"][0], results["metadatas"][0]



if __name__ == "__main__":
	vector_db_path="my_vector_db"
	
	corpus_df=pandas.read_json("../data/articles.json")

	vector_db_object = VectorDB(vector_db_path, corpus_df)


	print(vector_db_object.retrieve(question="Quelle est la durée légale du travail ?"))