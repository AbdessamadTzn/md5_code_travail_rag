from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from src.agents.moderator_agent import Moderator
from src.agents.rag_agent_supabase import Rag
import json

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="RAG Code du Travail", version="1.0")

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

moderator = Moderator()
rag = Rag()


class QuestionRequest(BaseModel):
	question: str


class RagResponse(BaseModel):
	response: str
	documents: list
	metadatas: list
	moderation: dict
	sub_questions: list = []
	formatted_question: str = ""


@app.post("/ask")
async def ask(request: QuestionRequest):
	try:
		moderation_result = moderator.moderate(request.question)

		if not moderation_result.get("safe"):
			raise HTTPException(status_code=400, detail=f"Question not safe: {moderation_result.get('reason')}")

		if not moderation_result.get("in_scope"):
			raise HTTPException(status_code=400, detail=f"Question out of scope: {moderation_result.get('reason')}")

		rag_response, documents, metadatas, sub_questions, formatted_question = rag.ask_rag(request.question)

		return RagResponse(
			response=rag_response,
			documents=documents,
			metadatas=metadatas,
			moderation=moderation_result,
			sub_questions=sub_questions,
			formatted_question=formatted_question,
		)

	except HTTPException:
		raise
	except json.JSONDecodeError:
		raise HTTPException(status_code=500, detail="Moderation response format error")
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
	return {"status": "ok"}


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
	import uvicorn
	uvicorn.run(app, host="0.0.0.0", port=8000)
