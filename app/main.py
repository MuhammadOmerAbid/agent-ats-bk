from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from app.api.match import router as match_router
from app.api.resume import router as resume_router
from app.agent import chat_with_agent
from app.interview_agent import evaluate_answer, generate_interview_questions, run_mock_interview_turn
from app.services.extractors import extract_text_from_upload
from app.voice_agent import DEFAULT_VOICE_ID, text_to_speech


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    resume_text: str = ""
    jd_text: str = ""


class InterviewRequest(BaseModel):
    resume_text: str
    jd_text: Optional[str] = ""


class EvaluateRequest(BaseModel):
    question: str
    user_answer: str
    role: str
    what_interviewer_wants: str


class MockInterviewRequest(BaseModel):
    conversation: list[Message]
    resume_text: str
    role: str


class TTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = DEFAULT_VOICE_ID

app = FastAPI(
    title="AI Career Optimization Engine API",
    description="JD-to-resume matching, ATS scoring, and resume optimization API.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(match_router)
app.include_router(resume_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict[str, str]:
    messages = [{"role": message.role, "content": message.content} for message in req.messages]
    reply = chat_with_agent(messages=messages, resume_text=req.resume_text, jd_text=req.jd_text)
    return {"reply": reply}


@app.post("/api/context/extract")
async def extract_context(
    resume_text: str = Form(default=""),
    jd_text: str = Form(default=""),
    resume_file: UploadFile | None = File(default=None),
    jd_file: UploadFile | None = File(default=None),
) -> dict[str, str]:
    extracted_resume_text = resume_text
    extracted_jd_text = jd_text

    if resume_file:
        try:
            content = await resume_file.read()
            extracted_resume_text = await extract_text_from_upload(resume_file.filename or "resume.txt", content)
        except Exception as error:
            raise HTTPException(status_code=400, detail=f"Could not extract text from resume file: {error}") from error

    if jd_file:
        try:
            content = await jd_file.read()
            extracted_jd_text = await extract_text_from_upload(jd_file.filename or "job-description.txt", content)
        except Exception as error:
            raise HTTPException(status_code=400, detail=f"Could not extract text from JD file: {error}") from error

    return {"resume_text": extracted_resume_text, "jd_text": extracted_jd_text}


@app.post("/api/interview/questions")
async def get_interview_questions(req: InterviewRequest) -> dict[str, object]:
    return generate_interview_questions(req.resume_text, req.jd_text or "")


@app.post("/api/interview/evaluate")
async def evaluate_interview_answer(req: EvaluateRequest) -> dict[str, object]:
    return evaluate_answer(
        req.question,
        req.user_answer,
        req.role,
        req.what_interviewer_wants,
    )


@app.post("/api/interview/mock")
async def mock_interview(req: MockInterviewRequest) -> dict[str, str]:
    conversation = [{"role": message.role, "content": message.content} for message in req.conversation]
    reply = run_mock_interview_turn(conversation, req.resume_text, req.role)
    return {"reply": reply}


@app.post("/api/interview/speak")
async def speak(req: TTSRequest) -> Response:
    try:
        audio = text_to_speech(req.text, req.voice_id or DEFAULT_VOICE_ID)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline; filename=interviewer.mp3"},
    )
