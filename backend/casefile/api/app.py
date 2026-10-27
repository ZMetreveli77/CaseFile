"""HTTP API for CaseFile. Run locally (from backend/):  ../.venv/bin/uvicorn casefile.api.app:app --reload
Interactive docs: http://127.0.0.1:8000/docs
"""
import logging
import queue
import threading
from pathlib import Path
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from dataclasses import asdict
from casefile.api.streaming import KEEP_ALIVE_COMMENT, format_sse

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field, field_validator

from casefile.api.services import AppServices, build_services
from casefile.api.streaming import format_sse
from casefile.config import get_settings
from casefile.ingestion.loaders import SUPPORTED_EXTENSIONS, UnsupportedFormat, load_documents
from casefile.rag.llm import LLMError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB per file
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
MAX_QUESTION_CHARACTERS = 1000
# Without these, proxies (Render's included) may buffer the stream and deliver every event at the very end.
STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
END_OF_STREAM = None  # sentinel the worker thread always puts on the queue last
HEARTBEAT_SECONDS = 15  # silence after which a keep-alive comment is sent (slow LLM, retries), so proxies don't hang up
# The React UI after `npm run build` (repo root/frontend/dist). parents[3]: api -> casefile -> backend -> repo root.
FRONTEND_BUILD_DIRECTORY = Path(__file__).resolve().parents[3] / "frontend" / "dist"

logger = logging.getLogger(__name__)


class AskRequest(BaseModel):
    question: str = Field(max_length=MAX_QUESTION_CHARACTERS)

    @field_validator("question")
    @classmethod
    def require_non_blank_question(cls, question: str) -> str:
        question = question.strip()
        if not question:
            raise ValueError("question must not be empty")
        return question


def describe_llm_error(error: LLMError) -> str:
    """Same message for /ask (HTTP 503) and /ask/stream (an error event)."""
    return f"The language model is unavailable: {error}"


def read_upload(file: UploadFile) -> bytes:
    """Read at most MAX_UPLOAD_BYTES + 1 bytes: getting the extra byte means the file is too large."""
    file_bytes = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    return file_bytes


def create_app(services: AppServices | None = None,
               frontend_directory: Path = FRONTEND_BUILD_DIRECTORY) -> FastAPI:
    """Pass `services` in tests; otherwise they are built from settings when the server starts.
    The UI is served from `frontend_directory` when it has been built; otherwise "/" opens the API docs."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.services is None:
            app.state.services = build_services(get_settings())
        yield

    app = FastAPI(title="CaseFile", description="AI investigation engine that cites its evidence", lifespan=lifespan)
    app.state.services = services
    write_lock = threading.Lock()  # uploads/deletes change the shared duplicate index, which is not thread-safe

    def get_services(request: Request) -> AppServices:
        return request.app.state.services

    @app.exception_handler(LLMError)
    def handle_llm_error(request: Request, error: LLMError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": describe_llm_error(error)})

    @app.exception_handler(UnsupportedFormat)
    def handle_unsupported_format(request: Request, error: UnsupportedFormat) -> JSONResponse:
        return JSONResponse(status_code=415, content={"detail": str(error)})

    has_built_frontend = (frontend_directory / "index.html").is_file()
    if not has_built_frontend:
        @app.get("/", include_in_schema=False)
        def open_docs() -> RedirectResponse:
            return RedirectResponse("/docs")  # no UI build yet (backend-only development)

    @app.get("/health")
    def health(request: Request) -> JSONResponse:
        services = get_services(request)
        try:
            counts = {"documents": services.store.count_documents(), "chunks": services.store.count_chunks()}
        except Exception as error:  # the database is unreachable: report it instead of crashing
            return JSONResponse(status_code=503, content={"status": "degraded", "detail": f"Qdrant: {error}"})
        return JSONResponse({"status": "ok", "model": services.model_name, **counts})

    @app.post("/documents", status_code=201)
    def upload_document(request: Request, file: UploadFile = File(...)) -> dict:
        """Add a file. A file with the same name as an existing one updates it; identical content is skipped."""
        file_bytes = read_upload(file)
        try:
            with write_lock:
                results = get_services(request).pipeline.ingest_file(file.filename or "upload", file_bytes)
        except UnsupportedFormat:
            raise  # handled by handle_unsupported_format -> 415 (it is a ValueError, so catch it first)
        except ValueError as error:  # e.g. no text could be extracted
            raise HTTPException(422, str(error))
        return {"results": [asdict(result) for result in results]}

    @app.get("/documents")
    def list_documents(request: Request, limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
                       cursor: str | None = None) -> dict:
        """One page of documents. Pass `next_cursor` back as `cursor` to get the next page."""
        store = get_services(request).store
        documents, next_cursor = store.list_documents_page(limit, cursor)
        return {"documents": documents, "next_cursor": next_cursor, "total": store.count_documents()}

    @app.get("/documents/{doc_id}")
    def get_document(request: Request, doc_id: str) -> dict:
        document = get_services(request).store.get_document(doc_id)
        if document is None:
            raise HTTPException(404, f"No document with id '{doc_id}'")
        return {**asdict(document), "characters": len(document.text)}

    @app.put("/documents/{doc_id}")
    def replace_document(request: Request, doc_id: str, file: UploadFile = File(...)) -> dict:
        """Replace an existing document's content with an uploaded file (which must hold exactly one document)."""
        services = get_services(request)
        if services.store.get_document(doc_id) is None:
            raise HTTPException(404, f"No document with id '{doc_id}'")
        file_bytes = read_upload(file)
        try:
            documents = load_documents(file.filename or "upload", file_bytes)
        except UnsupportedFormat:
            raise  # -> 415, see upload_document
        except ValueError as error:
            raise HTTPException(422, str(error))
        if len(documents) != 1:
            raise HTTPException(422, f"PUT replaces one document, but this file contains {len(documents)}")
        [document] = documents
        document.doc_id = doc_id  # keep the id: the new content replaces the old document
        with write_lock:
            result = services.pipeline.ingest_document(document)
        return asdict(result)

    @app.delete("/documents/{doc_id}", status_code=204)
    def delete_document(request: Request, doc_id: str) -> None:
        with write_lock:
            was_deleted = get_services(request).pipeline.delete(doc_id)
        if not was_deleted:
            raise HTTPException(404, f"No document with id '{doc_id}'")

    @app.get("/sources/{chunk_id}")
    def get_source(request: Request, chunk_id: str) -> dict:
        """The full passage behind a citation."""
        chunk = get_services(request).store.get_chunk(chunk_id)
        if chunk is None:
            raise HTTPException(404, f"No passage with id '{chunk_id}'")
        return asdict(chunk)

    @app.post("/ask")
    def ask(request: Request, body: AskRequest) -> dict:
        """Investigate a question: multi-step search, then a cited answer (or an abstention)."""
        return asdict(get_services(request).agent.answer(body.question))

    @app.post("/ask/stream")
    def ask_stream(request: Request, body: AskRequest) -> StreamingResponse:
        """Same investigation as /ask, streamed as Server-Sent Events: progress events, then "answer" or "error"."""
        agent = get_services(request).agent
        events: queue.Queue[dict | None] = queue.Queue()  # thread-safe hand-over from the worker to the response

        def run_investigation() -> None:
            # Runs in its own thread, because agent.answer() blocks until it is done. Errors are caught HERE:
            # the 200 status and headers are already sent, so the LLMError -> 503 handler can no longer help.
            try:
                final_answer = agent.answer(body.question, on_event=events.put)
                events.put({"type": "answer", **asdict(final_answer)})
            except LLMError as error:
                events.put({"type": "error", "detail": describe_llm_error(error)})
            except Exception:
                logger.exception("streamed investigation failed")
                events.put({"type": "error", "detail": "Internal error while investigating the question."})
            finally:
                events.put(END_OF_STREAM)  # always, so the generator below can never wait forever

        def stream_events():
            threading.Thread(target=run_investigation, daemon=True).start()
            while True:
                try:
                    event = events.get(timeout=HEARTBEAT_SECONDS)  # waits until the worker has something
                except queue.Empty:
                    yield KEEP_ALIVE_COMMENT  # nothing new yet: show the connection is still alive
                    continue
                if event is END_OF_STREAM:
                    return
                yield format_sse(event)

        return StreamingResponse(stream_events(), media_type="text/event-stream", headers=STREAM_HEADERS)

    @app.get("/formats")
    def supported_formats() -> dict:
        return {"extensions": SUPPORTED_EXTENSIONS, "max_upload_bytes": MAX_UPLOAD_BYTES}

    if has_built_frontend:
        # Mounted last, so every API route above is matched first. html=True serves index.html for "/".
        app.mount("/", StaticFiles(directory=frontend_directory, html=True), name="frontend")

    return app


app = create_app()
