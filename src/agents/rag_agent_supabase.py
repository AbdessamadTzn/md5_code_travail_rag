from pathlib import Path

from src.agents.base_agent import Agent
from src.agents.question_decomposer_agent import QuestionDecomposer
from src.agents.question_formatter_agent import QuestionFormatter
from src.config import LLM_MODEL
from src.vector_db_supabase import VectorDB

PROMPT_SYSTEM_PATH = Path(__file__).parent / "rag_prompt_system.txt"


class Rag(Agent):
	def __init__(self):
		super().__init__()
		self.vector_db_object = VectorDB()
		self.question_formatter = QuestionFormatter()
		self.question_decomposer = QuestionDecomposer()

	def build_context(self, question, n_chunks=5):
		formatted_question = self.question_formatter.format_question(question)
		sub_questions = self.question_decomposer.decompose(formatted_question)
		documents, metadatas = self.vector_db_object.retrieve_hybrid(
			question=formatted_question,
			sub_questions=sub_questions,
			n=n_chunks,
		)
		prompt_system = Rag.read_file(PROMPT_SYSTEM_PATH)
		prompt_system = prompt_system.replace("{{CHUNKS}}", "\n\t".join(documents))
		return prompt_system, documents, metadatas, sub_questions, formatted_question

	def ask_rag(self, question):
		prompt_system, documents, metadatas, sub_questions, formatted_question = self.build_context(question)

		chat_completion = self.client.chat.completions.create(
			messages=[
				{"role": "system", "content": prompt_system},
				{"role": "user", "content": formatted_question},
			],
			temperature=0,
			model=LLM_MODEL,
		)

		rag_response = chat_completion.choices[0].message.content
		return rag_response, documents, metadatas, sub_questions, formatted_question
