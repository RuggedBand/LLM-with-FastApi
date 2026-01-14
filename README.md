# Article Generation Queue API

Welcome! This API lets you generate articles using AI, track their status, interact with a Retrieval-Augmented Generation (RAG) system, and manage requests. It’s built with FastAPI and runs in the background, so you can queue requests and check back later for results.

---

## 📁 Project Structure & File Roles

- **main.py**: Main FastAPI application. Defines all API endpoints and background scheduling.
- **worker.py**: Handles background processing of queued article generation requests.
- **rag_system.py**: Implements the Retrieval-Augmented Generation (RAG) logic and vector store management.
- **models.py**: Contains all Pydantic models for request and response validation.
- **utils.py**: Includes all utility functions for database operations and request management.
- **app.py**: Sample Streamlit frontend for testing purpose.
- **requirements.txt**: Python dependencies.
- **sample.env**: Example environment variable file (copy to `.env` and fill in your values).
- **vector_store/**: Directory for vector store files used by the RAG system.

---

## 🚀 Quick Start

1. **Clone the Repository**
   ```sh
   git clone <your-repo-url>
   cd <repo-folder>
   ```

2. **Set Up Virtual Environment with UV package**
   ```sh
   pip install uv 
   uv venv
   ```
3. **Install Requirements**
   ```sh
   uv pip install -r requirements.txt
   ```

4. **Set Up Environment Variables**
   - Copy `sample.env` to `.env` and fill in the required values.

5. **Run the API**
   ```sh
   uvicorn main:app --reload
   ```
   The API will be available at [http://localhost:8000](http://localhost:8000).

6. **(Optional) Run the Sample Frontend**
   ```sh
   streamlit run app.py
   ```
   This launches a simple web UI for testing purposes.

---

## 📝 API Endpoints

### 1. **Queue Article Generation**
- **POST** `/queue-article-generation`
- Queue a new article generation request for background processing.
- **Request Body:**
  ```json
  {
    "user_query": "What is AI?",
    "model": "gemini-1.5-flash",   // optional
    "name": "John Doe",
    "userid": "user123"
  }
  ```
- **Response:** Returns a request ID and estimated completion time.

---

### 2. **Get All Requests for a User**
- **POST** `/get-requests`
- Retrieve all article generation requests submitted by a specific user.
- **Request Body:**
  ```json
  {
    "user_id": "user123"
  }
  ```
- **Response:** List of all requests for the user.

---

### 3. **Get Status of a Request**
- **GET** `/get-request-status/{request_id}`
- Check the status and result of a specific article generation request.
- **Response:** Status, result, and estimated completion time.

---

### 4. **Ask LLM (RAG Query)**
- **POST** `/askllm`
- Query the RAG system for an answer, optionally using a similarity threshold.
- **Request Body:**
  ```json
  {
    "query": "What is SRVAAU.com about?",
    "similarity_threshold": 0.75
  }
  ```
- **Response:** Data streamed in NDJSON format.

---

### 5. **Update Request Status (If Pending)**
- **PUT** `/update-request-status/{request_id}`
- Update the model or user query of a pending (not processed) request.
- **Request Body:**
  ```json
  {
    "model": "string",
    "user_query": "string"
  }
  ```
- **Response:** Update status message.

---

### 6. **Delete a Pending Request**
- **DELETE** `/delete-request/{request_id}`
- Delete a request if it is still pending (not processed).
- **Response:** Delete status message.

---

### 7. **Requeue a Failed Request**
- **POST** `/requeue-request/{request_id}`
- Re-queue a request that previously failed.
- **Response:** Requeue status message.

---

### 8. **Reset Vector Store**
- **POST** `/reset-vector`
- Reset and rebuild the RAG vector store (admin only, requires password).
- **Request Body:**
  ```json
  {
    "password": "your_admin_password"
  }
  ```
- **Response:** Status and number of documents indexed.

---

## ⚙️ Background Worker

- The background worker runs every `WORKER_RUN_INTERVAL_MINUTES` (default: 10 minutes) to process queued article generation requests.

---

## 🔑 Environment Variables

See [sample.env](sample.env) for all required settings (API keys, database URL, etc.).

---

## 🆘 Need Help?

- Make sure your database is set up and accessible.
- Check your `.env` file for missing or incorrect values.
- For more details, see the comments in each Python file.

---


test branch change
some more testing 
new branch visual testing 