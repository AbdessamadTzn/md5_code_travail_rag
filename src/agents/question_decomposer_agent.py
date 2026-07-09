import json
import re
from pathlib import Path

from src.agents.base_agent import Agent
from src.config import QUESTION_DECOMPOSER_MODEL

PROMPT_SYSTEM_PATH = Path(__file__).parent / "question_decomposer_prompt_system.txt"


class QuestionDecomposer(Agent):
	def decompose(self, raw_question):
		pre_cleaned = self._pre_clean(raw_question)
		if not pre_cleaned:
			return [raw_question]

		prompt_system = QuestionDecomposer.read_file(PROMPT_SYSTEM_PATH)
		chat_completion = self.client.chat.completions.create(
			messages=[
				{"role": "system", "content": prompt_system},
				{"role": "user", "content": pre_cleaned},
			],
			temperature=0,
			model=QUESTION_DECOMPOSER_MODEL,
		)

		content = chat_completion.choices[0].message.content.strip()
		sub_questions = self._parse_sub_questions(content)
		return sub_questions or [pre_cleaned]

	@staticmethod
	def _pre_clean(text):
		text = str(text).strip()
		text = re.sub(r"\s+", " ", text)
		text = re.sub(r"^(euh|bah|ben|du coup|en gros|genre)\s+", "", text, flags=re.IGNORECASE)
		text = re.sub(r"\s+(svp|stp|please)\s*$", "", text, flags=re.IGNORECASE)
		return text.strip()

	@staticmethod
	def _parse_sub_questions(content):
		try:
			payload = json.loads(content)
			sub_questions = payload.get("sub_questions", [])
			if isinstance(sub_questions, list):
				return [q.strip() for q in sub_questions if str(q).strip()]
		except json.JSONDecodeError:
			pass

		match = re.search(r"\[.*\]", content, re.DOTALL)
		if match:
			try:
				sub_questions = json.loads(match.group(0))
				if isinstance(sub_questions, list):
					return [q.strip() for q in sub_questions if str(q).strip()]
			except json.JSONDecodeError:
				pass

		return []
