# Article Generation Queue API

This FastAPI application provides endpoints to queue article generation requests, check their status, interact with a RAG (Retrieval-Augmented Generation) system, and manage requests.

---

**Base URL (when running locally):**  
```
http://localhost:8000
```

---


## 📄 **Queue Article Generation**

**Purpose:**  
Queue a new article generation request for background processing.

**Route:**  
```
POST /queue-article-generation
```

**Request Body (JSON):**
```
{
  "user_query": "string",
  "model": "string (optional, default: gemini-1.5-flash)",
  "name": "string",
  "userid": "string"
}
```

**Sample Response:**
```
{
  "request_id": "<request_id>",
  "status": "QUEUED",
  "estimated_completion_time_minutes": <number>,
  "message": "Your article generation request has been queued. Please note the request_id to check status later."
}
```

---

## 📄 **Get All Requests for a User**

**Purpose:**  
Retrieve all article generation requests submitted by a specific user.

**Route:**  
```
POST /get-requests
```

**Request Body (JSON):**
```
{
  "user_id": "string"
}
```

**Sample Response:**
```
[
  {
    "request_id": "<request_id>",
    "user_query": "string",
    "model": "string",
    "name": "string",
    "userid": "string",
    "status": <number>,
    "timestamp": "<timestamp>",
    "result": <result or null>
  },
  ...
]
```

---

## 📄 **Get Status of a Request**

**Purpose:**  
Check the status and result of a specific article generation request.

**Route:**  
```
GET /get-request-status/{request_id}
```

**Path Parameter:**  
- `request_id` (string): The request's unique ID.

**Sample Response:**
```
{
  "request_id": "<request_id>",
  "status": "<status>",
  "result": <result or null>,
  "message": "<status message>"
}
```

---

## 📄 **Ask LLM (RAG Query)**

**Purpose:**  
Query the RAG system for an answer, optionally using similarity threshold.

**Route:**  
```
POST /askllm
```

**Request Body (JSON):**
```
{
  "query": "string",
  "similarity_threshold": 0.7  // optional, default: 0.7
}
```

**Sample Response:**
```
<data streamed in NDJSON format>
```

---

## 📄 **Update Request Status (If Pending)**

**Purpose:**  
Update the model or user query of a pending (not processed) request.

**Route:**  
```
PUT /update-request-status/{request_id}
```

**Path Parameter:**  
- `request_id` (string): The request's unique ID.

**Request Body (JSON):**
```
{
  "model": "string (optional)",
  "user_query": "string (optional)"
}
```

**Sample Response:**
```
{
  "message": "<update status message>"
}
```

---

## 📄 **Delete a Pending Request**

**Purpose:**  
Delete a request if it is still pending (not processed).

**Route:**  
```
DELETE /delete-request/{request_id}
```

**Path Parameter:**  
- `request_id` (string): The request's unique ID.

**Sample Response:**
```
{
  "message": "<delete status message>"
}
```

---

## 🛠️ **Background Worker**

- The background worker runs every `WORKER_RUN_INTERVAL_MINUTES` (default: 10 minutes) to process queued article generation requests.

---

## 📝 **Environment Variables**

See [`sample.env`](sample.env) for required environment variables.

---

## 📦 **Install Requirements**

```
pip install -r requirements.txt
```

---

## 🚀 **Run the API**

```
uvicorn