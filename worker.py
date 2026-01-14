import google.generativeai as genai
import os
import re
import json
import httpx
import asyncio
from typing import Dict, Any, List
from datetime import datetime
from dotenv import load_dotenv
import json
from utils import get_pending_requests, update_request_status, update_request_posts

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set in .env")
genai.configure(api_key=GEMINI_API_KEY)

EXTERNAL_API_URL = os.getenv("EXTERNAL_API_URL")
EXTERNAL_API_AUTH_TOKEN = os.getenv("EXTERNAL_API_AUTH_TOKEN")

worker_lock = asyncio.Lock()

SYSTEM_PROMPT = """
You are an expert content writer and blogger. Your primary task is to generate well-structured, engaging articles in HTML format based on the user's request.

**Your Instructions:**

1.  **Role**: Act as a professional writer. Your tone should be informative and engaging.
2.  **Output Format**: The entire response must be formatted using HTML tags.
3.  **HTML Tags**:
    * Use `<h1>` for the main title of the article.
    * Use `<h2>` for major sections or subheadings.
    * Use `<p>` for all paragraphs.
    * Use `<ul>` with `<li>` for bullet points and `<strong>` for important keywords.
    * **Crucially, do NOT include `<html>`, `<head>`, or `<body>` tags.** Only generate the HTML content that would go inside the `<body>` of a webpage.
    * Each complete article MUST be wrapped in its own `<article>` tag.
4.  **Multiple Articles**: If the user asks for more than one article, wrap each complete article in its own `<article>` tag. Separate each `<article>` tag with an `<hr>` (horizontal rule) for clear visual division. Ensure you generate the requested number of distinct articles, each with its own heading and content.

Analyze the user's query below and generate the content according to these rules.
"""

async def get_auth_token() -> str:
    login_url = "https://srvaau.com/aayu_api_prod/api/login"
    credentials = {
        "email": os.getenv("AAYUEMAIL"),
        "password": os.getenv("AAYUPASSWORD")
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(login_url, json=credentials, timeout=15.0)
            response.raise_for_status()
            data = response.json()
            if data.get("succeeded") and data.get("data", {}).get("token"):
                return data["data"]["token"]
            else:
                raise Exception(f"Login failed: {data.get('error', {}).get('message', 'Unknown error')}")
    except Exception as e:
        return ""

async def _process_single_request(request_data: Dict[str, Any]) -> Dict[str, Any]:
    request_id = request_data["request_id"]
    user_query = request_data["user_query"]
    model_name = request_data.get("model", "gemini-2.5-flash")
    name = request_data["name"]
    
    processing_result = {
        "status": 3,
        "message": "Processing started, but no definitive outcome yet.",
        "articles": [],
        "error_details": None
    }

    posts_collected = []  # <-- new, holds {"id": ..., "title": ...}

    try:
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=SYSTEM_PROMPT
        )
        auth_token = await get_auth_token()
        
        llm_response = await model.generate_content_async(user_query)
        raw_html_content = llm_response.text

        article_blocks = re.findall(r'<article>(.*?)</article>', raw_html_content, re.DOTALL)
        if not article_blocks and raw_html_content.strip():
            article_blocks = [raw_html_content]

        generated_articles = []
        for i, article_html_raw in enumerate(article_blocks):
            article_html = article_html_raw.strip()
            article_html = re.sub(r'<hr\s*/>|<hr>', '', article_html, flags=re.IGNORECASE).strip()

            title_match = re.search(r'<h1>(.*?)</h1>', article_html, re.DOTALL)
            title = title_match.group(1).strip() if title_match else f"No Title Found (Article {i+1})"
            
            content_without_h1 = re.sub(r'<h1>.*?</h1>', '', article_html, 1, flags=re.DOTALL).strip()
            slug = re.sub(r'[^\w\s-]', '', title).replace(' ', '-').lower()
            
            payload = {
                "title": title,
                "metaTitle": title,
                "slug": slug,
                "name": name,
                "summary": title,
                "content": content_without_h1,
                "suggestions": title,
                "enablePostMetaDetail": False,
                "enablePostTagDetails": False,
                "enableApiSetting": False,
                "enableCategorieDetails": False,
                "enableAdsTemplate": False,
                "LeftRightAdsBanner": False,
                "TopBottomAdsBanner": False,
                "feedbackId": 0,
                "post_metas": [{ "key": "", "content": "" }],
                "post_categories": [{ "key": "", "content": "" }],
                "post_tags": [{ "title": "", "metaTitle": "", "slug": "", "content": "" }],
                "api_settings": { "method": "GET", "apiUrl": "", "queryParams": [{ "key": "", "value": "" }], "headers": [{ "key": "", "value": "" }], "jsonData": "{}" },
                "AdsBanner": {}
            }
            
            post_api_response = {}
            async with httpx.AsyncClient() as client:
                try:
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {auth_token}"
                    }
                    
                    res = await client.put(EXTERNAL_API_URL, json=payload, headers=headers, timeout=30.0)
                    res.raise_for_status()
                    
                    if res.status_code != 204 and res.text:
                        try:
                            post_api_response = res.json()
                        except json.JSONDecodeError:
                            post_api_response = {"error": "Failed to parse API response as JSON", "raw_response": res.text}
                    else:
                        post_api_response = {"message": f"API call successful, but no content or 204 No Content. Status: {res.status_code}"}

                except httpx.RequestError as e:
                    post_api_response = {"error": f"Request failed: {str(e)}"}
                except httpx.HTTPStatusError as e:
                    post_api_response = {"error": f"API error {e.response.status_code}: {e.response.text}"}
                except Exception as e:
                    post_api_response = {"error": f"Unexpected API call error: {str(e)}"}
            
            # 🔹 Collect post_id + title if present
            if post_api_response.get("data") and post_api_response["data"].get("id"):
                posts_collected.append({
                    "id": post_api_response["data"]["id"],
                    "title": post_api_response["data"]["title"]
                })
            
            generated_articles.append({
                "article_title": title,
                "article_content_snippet": content_without_h1[:200] + "...",
                "post_api_response": post_api_response
            })
        
        if not generated_articles:
            processing_result["status"] = 3
            processing_result["message"] = "No articles could be generated or extracted from the model response."
            processing_result["error_details"] = "LLM did not return valid article structure."
        else:
            processing_result["status"] = 2
            processing_result["message"] = "Article(s) generated and posted successfully."
            processing_result["articles"] = llm_response.text

        # 🔹 Save posts to DB if any collected
        if posts_collected:
            await update_request_posts(request_id, posts_collected)

    except Exception as e:
        processing_result["status"] = 3
        processing_result["message"] = f"An unexpected error occurred during processing: {e}"
        processing_result["error_details"] = str(e)
    
    return processing_result

async def run_worker():
    if worker_lock.locked():
        return

    async with worker_lock:
        pending_requests = await get_pending_requests()

        if not pending_requests:
            return

        for req_to_process in pending_requests:
            request_id = req_to_process["request_id"]
            
            await update_request_status(request_id, 1, "Processing started...")

            processing_outcome = await _process_single_request(req_to_process)
            
            result = {
                "message": processing_outcome["message"],
                "articles": processing_outcome["articles"],
                "error_details": processing_outcome["error_details"]
            }
            
            await update_request_status(request_id, processing_outcome["status"],json.dumps(result))