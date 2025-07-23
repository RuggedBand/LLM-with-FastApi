import re
import html
import json
import asyncio
import google.generativeai as genai
import os
from dotenv import load_dotenv
from llama_index.core import Document, VectorStoreIndex, Settings, StorageContext, load_index_from_storage
from llama_index.embeddings.gemini import GeminiEmbedding
from llama_index.llms.gemini import Gemini
from typing import Dict, Any, List ,AsyncGenerator
from utils import get_posts_from_db_async
load_dotenv()

class RAGSystem:
    def __init__(self, system_prompt: str = None, vector_store_path: str = "./vector_store"):
        self.index = None
        self.query_engine = None
        self.vector_store_path = vector_store_path
        self.system_prompt = system_prompt
        self.initialized = False
        
    async def _ensure_initialized(self):
        """Ensure the system is initialized before processing queries"""
        if not self.initialized:
            await self.initialize()
        
    async def initialize(self):
        """Initialize the RAG system"""
        if self.initialized:
            return
            
        print("Setting up LLM and embeddings...")
        Settings.llm = Gemini(model="models/gemini-1.5-flash")
        Settings.embed_model = GeminiEmbedding(model_name="models/embedding-001")
        
        # Check if vector store already exists
        if os.path.exists(self.vector_store_path) and os.path.exists(os.path.join(self.vector_store_path, "index_store.json")):
            print("Loading existing vector store...")
            self._load_existing_index()
        else:
            print("Creating new vector store...")
            await self._create_new_index()
        
        # Setup query engine
        self.query_engine = self.index.as_query_engine(
            similarity_top_k=3,
            response_mode="compact"
        )
        
        self.initialized = True
        print("RAG system ready!")
        
    def _load_existing_index(self):
        """Load existing vector store from disk"""
        try:
            storage_context = StorageContext.from_defaults(persist_dir=self.vector_store_path)
            self.index = load_index_from_storage(storage_context)
            print("Successfully loaded existing vector store!")
        except Exception as e:
            print(f"Error loading existing vector store: {e}")
            print("Creating new vector store...")
            import asyncio
            asyncio.create_task(self._create_new_index())
    
    async def _create_new_index(self):
        """Create new vector store and save to disk"""
        print("Loading and preprocessing documents...")
        documents = await self._load_documents()
        
        print(f"Creating index from {len(documents)} documents...")
        self.index = VectorStoreIndex.from_documents(documents)
        
        # Save the index to disk
        os.makedirs(self.vector_store_path, exist_ok=True)
        self.index.storage_context.persist(persist_dir=self.vector_store_path)
        print(f"Vector store saved to {self.vector_store_path}")
        
    async def _load_documents(self) -> List[Document]:
        posts_data = await get_posts_from_db_async() 
        documents = []
        for row in posts_data:
            doc = Document(
                text=self._preprocess_text(row['Content']),
                metadata={
                    'title': row['Title'],
                    'url': f"https://srvaau.com/dashboard/post/{row['Id']}"
                }
            )
            documents.append(doc)
        
        return documents
    
    def _preprocess_text(self, text: str) -> str:
        clean = re.compile('<.*?>')
        text = re.sub(clean, '', text)
        text = html.unescape(text)
        text = ''.join(c for c in text if 32 <= ord(c) <= 126)
        return text.strip()
    
    # async def _get_general_response(self, query: str) -> str:
    async def _get_general_response(self, query: str) -> AsyncGenerator[str, None]:
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            full_prompt = f"{self.system_prompt}\n\nUser Query: {query}"
            response_stream = await model.generate_content_async(full_prompt, stream=True) 
            async for chunk in response_stream:
                if chunk.text: # Ensure chunk has text content
                    yield chunk.text
        except Exception as e:
            print(f"Error streaming general response: {e}")
            yield "I'm here to help! Please ask me a question."
    
    async def process_query(self, query: str, similarity_threshold: float = 0.7) -> AsyncGenerator[str, None]:
        await self._ensure_initialized()
        
        print(f"Processing query: {query}")
        
        try:
            response = self.query_engine.query(query)
            response_type = "rag_with_sources"
            sources = []
            max_score = 0.0

            if response.source_nodes:
                max_score = max([node.score for node in response.source_nodes if hasattr(node, 'score')])
                print(f"Max similarity score: {max_score}")

                if max_score >= similarity_threshold:
                    for i, node in enumerate(response.source_nodes):
                        source_score = getattr(node, 'score', 0.0)
                        if source_score >= similarity_threshold:
                            sources.append({
                                "title": node.metadata.get('title', 'N/A'),
                                "url": node.metadata.get('url', 'N/A'),
                                "relevance_score": round(source_score, 3),
                                "text_snippet": node.text[:200] + "..." if len(node.text) > 200 else node.text
                            })
                else:
                    response_type = "general_fallback"
            else:
                response_type = "general_fallback"

            # Yield an initial JSON object with metadata (response_type, sources)
            # This is sent first to the client
            yield json.dumps({
                "response_type": response_type,
                "sources": sources if response_type == "rag_with_sources" else None,
                "initial_message": "Streaming response...",
            }) + "\n" # Add newline for JSON streaming (common for SSE or custom protocols)

            # Now stream the actual answer content
            if response_type == "rag_with_sources":
                # If using RAG, the 'response.response' is already the full text from LlamaIndex.
                # To stream it, we manually chunk it. For very long responses, you might
                # integrate a streaming LLM call *within* LlamaIndex's response synthesis.
                # For simplicity here, we'll just chunk the already generated text.
                # A more advanced LlamaIndex setup would involve a streaming LLM in its response builder.

                # Fallback to streaming general response if LlamaIndex's synthesis isn't streaming directly
                # For the purposes of a simple demo, we'll simulate chunking or directly stream from _get_general_response
                # if RAG response itself isn't streamable from LlamaIndex directly for complex queries.
                # For this example, if RAG is triggered, we'll assume response.response is the final answer.
                # If you want true streaming for LlamaIndex responses, you might need a custom response synthesizer
                # or ensure the underlying LLM in Settings is set to stream.

                # Since `query_engine.query` returns a full response, we'll stream it character by character
                # or in small chunks. This is a simulation if LlamaIndex itself isn't streaming the answer.
                for char in str(response.response):
                    yield json.dumps({"text_chunk": char}) + "\n" # Yield each character as a chunk
                    await asyncio.sleep(0.005) # Simulate delay for streaming effect
            else:
                # If falling back, use the dedicated general response streamer
                async for chunk in self._get_general_response(query):
                    yield json.dumps({"text_chunk": chunk}) + "\n" # Yield each chunk

        except Exception as e:
            print(f"Error in RAG processing: {e}")
            # Yield an error message if something goes wrong
            yield json.dumps({
                "error": True,
                "message": f"An error occurred: {e}",
                "response_type": "error_fallback"
            }) + "\n"
            # As a fallback, still try to give a general response if the error was not fatal
            async for chunk in self._get_general_response(query):
                 yield json.dumps({"text_chunk": chunk}) + "\n"