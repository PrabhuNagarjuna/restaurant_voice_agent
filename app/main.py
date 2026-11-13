"""
FastAPI backend for the voice restaurant assistant.

  POST /voice     audio in  -> STT -> LLM+tools -> TTS -> JSON (transcript, reply, mp3 base64)
  POST /chat      text in   -> LLM+tools -> text reply  (use this to debug without audio)
  GET  /restaurants, /restaurants/{id}, POST/GET/DELETE /reservations...   plain REST over the same tools
Run:  uvicorn app.main:app --reload
"""
import base64
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, tools

app = FastAPI(title="Voice Restaurant Assistant", version="1.0.0")
STATIC = Path(__file__).resolve().parent.parent / "static"


# ---------------------------------------------------------------- models
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: Optional[str] = None


class ReservationIn(BaseModel):
    restaurant_id: str
    customer_name: str
    phone: str
    party_size: int = Field(ge=1, le=20)
    date: str = Field(description="YYYY-MM-DD")
    time: str = Field(description="HH:MM, 24h")
    special_requests: Optional[str] = None


def _raise_if_error(result: dict, ok_status: int = 200) -> dict:
    if result.get("success") is False:
        code = {"not_found": 404, "no_availability": 409, "internal": 500}.get(result.get("error_code"), 400)
        raise HTTPException(status_code=code, detail=result)
    return result


# ---------------------------------------------------------------- AI endpoints
@app.post("/chat")
def chat(body: ChatIn):
    sid = body.session_id or uuid.uuid4().hex
    out = agent.chat(sid, body.message)
    return {"session_id": sid, **out}


@app.post("/voice")
def voice(audio: UploadFile = File(...), session_id: Optional[str] = Form(None)):
    from . import voice as speech  # lazy: heavy imports

    sid = session_id or uuid.uuid4().hex
    data = audio.file.read()
    if not data:
        raise HTTPException(400, "Empty audio upload.")
    transcript = speech.speech_to_text(data)
    if not transcript:
        reply, tool_calls = "Sorry, I didn't catch that. Could you say it again?", []
    else:
        out = agent.chat(sid, transcript)
        reply, tool_calls = out["reply"], out["tool_calls"]
    mp3 = speech.text_to_speech(reply)
    return {
        "session_id": sid,
        "transcript": transcript,
        "reply": reply,
        "tool_calls": tool_calls,
        "audio_mp3_base64": base64.b64encode(mp3).decode(),
    }


@app.delete("/sessions/{session_id}", status_code=204)
def end_session(session_id: str):
    agent.reset_session(session_id)


# ---------------------------------------------------------------- REST over the same tools
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/restaurants")
def list_restaurants(city: Optional[str] = None, area: Optional[str] = None, cuisine: Optional[str] = None,
                     price_range: Optional[str] = None, delivery_only: Optional[bool] = None,
                     min_rating: Optional[float] = None, max_avg_price: Optional[int] = None, limit: int = 10):
    return tools.search_restaurants(city, area, cuisine, price_range, delivery_only, min_rating, max_avg_price, limit)


@app.get("/restaurants/{restaurant_id}")
def restaurant(restaurant_id: str):
    return _raise_if_error(tools.get_restaurant_details(restaurant_id=restaurant_id))


@app.get("/restaurants/{restaurant_id}/availability")
def availability(restaurant_id: str, date: str, time: str, party_size: int):
    return _raise_if_error(tools.check_availability(restaurant_id, date, time, party_size))


@app.post("/reservations", status_code=201)
def book(body: ReservationIn):
    return _raise_if_error(tools.create_reservation(**body.model_dump()))


@app.get("/reservations/{code}")
def get_booking(code: str, phone_last4: str):
    return _raise_if_error(tools.get_reservation(code, phone_last4))


@app.delete("/reservations/{code}")
def cancel_booking(code: str, phone_last4: str):
    return _raise_if_error(tools.cancel_reservation(code, phone_last4))


# ---------------------------------------------------------------- tiny test UI
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
