import re
from pathlib import Path

from src.agents.base_agent import Agent
from src.config import QUESTION_FORMATTER_MODEL

PROMPT_SYSTEM_PATH = Path(__file__).parent / "question_formatter_prompt_system.txt"


class QuestionFormatter(Agent):
	def format_question(self, raw_question):
		pre_cleaned = self._pre_clean(raw_question)
		if not pre_cleaned:
			return raw_question

		prompt_system = QuestionFormatter.read_file(PROMPT_SYSTEM_PATH)
		chat_completion = self.client.chat.completions.create(
			messages=[
				{"role": "system", "content": prompt_system},
				{"role": "user", "content": pre_cleaned},
			],
			temperature=0,
			model=QUESTION_FORMATTER_MODEL,
		)

		formatted = chat_completion.choices[0].message.content.strip()
		return formatted or pre_cleaned

	@staticmethod
	def _pre_clean(text):
		text = str(text).strip()
		text = re.sub(r"\s+", " ", text)
		text = re.sub(r"^(euh|bah|ben|du coup|en gros|genre)\s+", "", text, flags=re.IGNORECASE)
		text = re.sub(r"\s+(svp|stp|please)\s*$", "", text, flags=re.IGNORECASE)
		return text.strip()
