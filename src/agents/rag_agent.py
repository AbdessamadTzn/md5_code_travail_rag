from pathlib import Path
from src.agents.base_agent import Agent
from src.agents.question_formatter_agent import QuestionFormatter
from src.config import LLM_MODEL
from src.vector_store import get_vector_db

PROMPT_SYSTEM_PATH = Path(__file__).parent / "rag_prompt_system.txt"

class Rag(Agent):
	def __init__(self):
		super().__init__()
		self.vector_db_object = get_vector_db()
		self.question_formatter = QuestionFormatter()



	def build_context(self, question, n_chunks=5):
		documents, metadatas = self.vector_db_object.retrieve(question, n=n_chunks)
		prompt_system = Rag.read_file(PROMPT_SYSTEM_PATH)

		prompt_system = prompt_system.replace("{{CHUNKS}}", "\n\t".join(documents))

		return prompt_system, documents, metadatas


	def ask_rag(self, question):
		formatted_question = self.question_formatter.format_question(question)
		prompt_system, documents, metadatas = self.build_context(formatted_question)
		
		chat_completion = self.client.chat.completions.create(
			messages=[
				{
					"role": "system",
					"content": prompt_system
				},
				{
					"role": "user",
					"content": formatted_question,
				}
			],
			temperature=0,
			model=LLM_MODEL
		)

		rag_response = chat_completion.choices[0].message.content
		return rag_response, documents, metadatas, formatted_question


if __name__ == "__main__":
	rag_object = Rag()
	#question = "Quelle est la durée légale du travail par semaine?"
	#question = "c'est quoi le smic en france?"
	#question = "c'est quoi le smic en france? pourquoi il est important?"
	question = "euh du coup c'est quoi le smic en france stp"
	print(f"Question brute: {question}")
	rag_response, documents, metadatas, formatted_question = rag_object.ask_rag(question)
	print(f"Question formatée: {formatted_question}")
	print("\nChunks utilisés:")
	for i, meta in enumerate(metadatas, 1):
		print(f"  {i}. {meta.get('num')} (chunk {meta.get('chunk_index')})")
	print("\nRéponse:")
	try:
		print(rag_response)
	except UnicodeEncodeError:
		print(rag_response.encode("cp1252", errors="replace").decode("cp1252"))
