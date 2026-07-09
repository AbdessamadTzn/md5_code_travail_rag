from pathlib import Path
from src.agents.base_agent import Agent
from src.config import LLM_MODEL, VECTOR_DB_PATH
from src.vector_db import VectorDB

PROMPT_SYSTEM_PATH = Path(__file__).parent / "rag_prompt_system.txt"

class Rag(Agent):
	def __init__(self, vector_db_path):
		super().__init__()
		self.vector_db_object = VectorDB(vector_db_path=vector_db_path)



	def build_context(self, question, n_chunks=5):
		documents, metadatas = self.vector_db_object.retrieve(question, n=n_chunks)
		prompt_system = Rag.read_file(PROMPT_SYSTEM_PATH)

		prompt_system = prompt_system.replace("{{CHUNKS}}", "\n\t".join(documents))

		return prompt_system, documents, metadatas


	def ask_rag(self, question):

		prompt_system, documents, metadatas = self.build_context(question)
		
		chat_completion = self.client.chat.completions.create(
			messages=[
				{
					"role": "system",
					"content": prompt_system
				},
				{
					"role": "user",
					"content": question,
				}
			],
			temperature=0,
			model=LLM_MODEL
		)

		rag_response = chat_completion.choices[0].message.content
		return rag_response, documents, metadatas


if __name__ == "__main__":
	vector_db_path = VECTOR_DB_PATH
	rag_object = Rag(vector_db_path=vector_db_path)
	#question = "Quelle est la durée légale du travail par semaine?"
	#question = "c'est quoi le smic en france?"
	#question = "c'est quoi le smic en france? pourquoi il est important?"
	question = "droit au congé payé en france?"
	print(f"Question: {question}")
	rag_response, documents, metadatas = rag_object.ask_rag(question)
	print("\nChunks utilisés:")
	for i, meta in enumerate(metadatas, 1):
		print(f"  {i}. {meta.get('num')} (chunk {meta.get('chunk_index')})")
	print("\nRéponse:")
	try:
		print(rag_response)
	except UnicodeEncodeError:
		print(rag_response.encode("cp1252", errors="replace").decode("cp1252"))