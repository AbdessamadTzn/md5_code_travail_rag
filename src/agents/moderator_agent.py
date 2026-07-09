import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from .base_agent import Agent
from config import MODERATOR_MODEL

PROMPT_SYSTEM_PATH = Path(__file__).parent / "moderator_prompt_system.txt"


class Moderator(Agent):
	def __init__(self):
		super().__init__()


	def moderate(self, question):
		prompt_system = Moderator.read_file(PROMPT_SYSTEM_PATH)

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
			model=MODERATOR_MODEL
		)

		moderation_response = chat_completion.choices[0].message.content
		return json.loads(moderation_response)


if __name__ == "__main__":
	moderator_object = Moderator()

	result = moderator_object.moderate(question="Quelle est la durée légale du travail ?")

	print(result)