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
import shutil
from utils import (
    insert_request,
    get_requests_by_user_id,
    get_pending_requests_count,
    get_request_status_only,
    update_request_if_pending,
    delete_request_by_id,
    requeue_request_by_id
)
from worker import run_worker
from rag_system import RAGSystem
from models import (ArticleRequest,QueuedArticleResponse,RAGQuery,RequestStatusResponse)

load_dotenv()

REQUEST_PROCESSING_TIME_MINUTES = float(os.getenv("REQUEST_PROCESSING_TIME_MINUTES", 2))
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
async def root():
    return {
        "message": "Welcome to the Article Generation Queue API. Use this service to queue, track, and manage article generation requests powered by LLM and RAG."
    }

@app.post("/queue-article-generation", response_model=QueuedArticleResponse)
async def queue_article_generation(request: ArticleRequest):
    request_id = str(uuid.uuid4())
    timestamp = datetime.now()
    if not request.user_query or request.user_query.strip() == "":
        raise HTTPException(status_code=400, detail="user_query cannot be empty.")
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
    
    # Get next run time of the worker
    next_run = None
    for job in scheduler.get_jobs():
        if job.id == "article_generation_worker":
            next_run = job.next_run_time.replace(tzinfo=None)  # Remove timezone info for comparison
            break

    # Calculate time until next run
    current_time = datetime.now()
    time_until_next_run = (next_run - current_time).total_seconds() / 60 if next_run else WORKER_RUN_INTERVAL_MINUTES
    estimated_time = time_until_next_run + pending_count * REQUEST_PROCESSING_TIME_MINUTES

    return QueuedArticleResponse(
        request_id=request_id,
        status="QUEUED",
        estimated_completion_time_minutes=int(estimated_time),
        message="Your article generation request has been queued. Please note the request_id to check status later."
    )

@app.post("/get-requests")
async def get_requests(payload: Dict[str, Any] = Body(...)) -> List[Dict[str, Any]]:
    try:
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="Missing 'user_id' in request body")
        return await get_requests_by_user_id(user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get requests for user_id: {e}")

@app.get("/get-request-status/{request_id}", response_model=RequestStatusResponse)
async def get_request_status(request_id: str) ->RequestStatusResponse:
    response = await get_request_status_only(request_id)
    if response.status == "QUEUED":
        pending_count = await get_pending_requests_count()
        
        next_run = None
        for job in scheduler.get_jobs():
            if job.id == "article_generation_worker":
                next_run = job.next_run_time.replace(tzinfo=None)
                break
        
        current_time = datetime.now()
        time_until_next_run = (next_run - current_time).total_seconds() / 60 if next_run else WORKER_RUN_INTERVAL_MINUTES
        estimated_time = time_until_next_run + pending_count * REQUEST_PROCESSING_TIME_MINUTES
        response.estimated_completion_time_minutes = int(estimated_time)
        
    return response

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

@app.post("/requeue-request/{request_id}")
async def requeue_request(request_id: str):
    message = await requeue_request_by_id(request_id)
    return {"message": message}

@app.post("/reset-vector")
async def reset_vector(data : Dict[str, Any]= Body(...)):
    try:
        password = data.get("password")
        if password != os.getenv("RESET_VECTOR_PASSWORD"):
            raise HTTPException(status_code=401, detail="Invalid password for vector reset.")
        vector_store_path = rag_system.vector_store_path

        # Delete old vector store if it exists
        if os.path.exists(vector_store_path):
            shutil.rmtree(vector_store_path)
            deleted = True
        else:
            deleted = False

        try:
            rag_system.initialized = False
            await rag_system.initialize()
            await rag_system._create_new_index()
            documents = await rag_system._load_documents()
            indexed_count = len(documents)

            return {
                "message": f"Vector store {'reset and rebuilt' if deleted else 'created'} successfully.",
                "documents_indexed": indexed_count,
                "status": "success"
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to rebuild vector store: {e}")

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unhandled error during reset: {e}")
            


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