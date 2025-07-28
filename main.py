from fastapi import FastAPI, HTTPException,Body
from fastapi.responses import StreamingResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
import asyncio
import os
from typing import Dict, Any, List
import uuid

from datetime import datetime
from utils import (
    insert_request,
    get_requests_by_user_id,
    get_pending_requests_count,
    get_request_status_only,
    update_request_if_pending,
    delete_request_by_id
)
from worker import run_worker
from rag_system import RAGSystem
from models import (ArticleRequest,QueuedArticleResponse,RAGQuery,RAGResponse,RequestStatusResponse)
load_dotenv()

REQUEST_PROCESSING_TIME_MINUTES = int(os.getenv("REQUEST_PROCESSING_TIME_MINUTES", 2))
WORKER_RUN_INTERVAL_MINUTES = int(os.getenv("WORKER_RUN_INTERVAL_MINUTES", 10))

app = FastAPI(
    title="Article Generation Queue API",
    description="An API to queue article generation requests for background processing and provide ETA."
)

scheduler = AsyncIOScheduler()
worker_lock = asyncio.Lock()
rag_system = RAGSystem(
    system_prompt=os.getenv("SYSTEMPROMPT_RAG")
)
@app.get("/")
async def start():
    return {"Welcome to the Article Generation Queue API. Use the endpoints to queue article requests and manage them."}

@app.post("/queue-article-generation", response_model=QueuedArticleResponse)
async def queue_article_generation(request: ArticleRequest):
    request_id = str(uuid.uuid4())
    timestamp = datetime.now()

    queued_data = {
        "request_id": request_id,
        "user_query": request.user_query,
        "model": request.model,
        "name": request.name,
        "userid":request.userid,
        "status": 0,
        "timestamp": timestamp,
        "result": None 
    }

    await insert_request(queued_data)

    pending_count = await get_pending_requests_count()
    estimated_time = (pending_count + 1)*0.5 + REQUEST_PROCESSING_TIME_MINUTES

    return QueuedArticleResponse(
        request_id=request_id,
        status="QUEUED",
        estimated_completion_time_minutes=estimated_time,
        message="Your article generation request has been queued. Please note the request_id to check status later."
    )

@app.get("/get-requests/{user_id}")
async def get_requests(user_id: str) -> List[Dict[str, Any]]:
    try:
        return await get_requests_by_user_id(user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get requests for user_id {user_id}: {e}")

@app.get("/get-request-status/{request_id}", response_model=RequestStatusResponse)
async def get_request_status(request_id: str) ->RequestStatusResponse:
    return await get_request_status_only(request_id)

@app.post("/askllm")
async def ask_llm(query: RAGQuery):
    async def generate_chunks():
        async for chunk_data in rag_system.process_query(query.query, query.similarity_threshold):
            yield chunk_data.encode("utf-8") 
    return StreamingResponse(generate_chunks(), media_type="application/x-ndjson")

@app.put("/update-request-status/{request_id}")
async def update_request_status(request_id: str,  model: str = Body(default=None),user_query: str = Body(default=None)):
    message = await update_request_if_pending(request_id, model, user_query)
    return {"message": message}

@app.delete("/delete-request/{request_id}")
async def delete_request(request_id: str):
    message = await delete_request_by_id(request_id)
    return {"message": message}

@app.on_event("startup")
async def startup_event():
    scheduler.add_job(
        run_worker,
        IntervalTrigger(minutes=WORKER_RUN_INTERVAL_MINUTES),
        coalesce=True,
        id="article_generation_worker",
        replace_existing=True
    )
    scheduler.start()

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()