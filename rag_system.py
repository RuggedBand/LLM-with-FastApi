import re
import html
import json
import asyncio
import google.generativeai as genai
import os
from dotenv import load_dotenv
from llama_index.core import Document, VectorStoreIndex, Settings, StorageContext, load_index_from_storage
# New import for node parsing (chunking)
from llama_index.core.node_parser import SentenceSplitter
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
            
        # print("Setting up LLM and embeddings...")
        Settings.llm = Gemini(model="models/gemini-1.5-flash")
        Settings.embed_model = GeminiEmbedding(model_name="models/embedding-001")
        
        # Check if vector store already exists
        if os.path.exists(self.vector_store_path) and os.path.exists(os.path.join(self.vector_store_path, "index_store.json")):
            # print("Loading existing vector store...")
            self._load_existing_index()
        else:
            # print("Creating new vector store...")
            await self._create_new_index()
        
        # Setup query engine
        self.query_engine = self.index.as_query_engine(
            similarity_top_k=10,
            response_mode="compact",
            streaming=True
        )
        
        self.initialized = True
        # print("RAG system ready!")
        
    def _load_existing_index(self):
        """Load existing vector store from disk"""
        try:
            storage_context = StorageContext.from_defaults(persist_dir=self.vector_store_path)
            self.index = load_index_from_storage(storage_context)
            # print("Successfully loaded existing vector store!")
        except Exception as e:
            # print(f"Error loading existing vector store: {e}")
            # print("Creating new vector store...")
            asyncio.create_task(self._create_new_index())
    
    async def _create_new_index(self):
        """Create new vector store by chunking documents into nodes and save to disk"""
        # print("Loading and preprocessing documents...")
        documents = await self._load_documents()
        
        # print("Parsing documents into smaller nodes (chunking)...")
        parser = SentenceSplitter(chunk_size=256, chunk_overlap=60)
        nodes = parser.get_nodes_from_documents(documents, show_progress=True)
        
        # print(f"Creating index from {len(nodes)} nodes...")
        self.index = VectorStoreIndex(nodes)

        os.makedirs(self.vector_store_path, exist_ok=True)
        self.index.storage_context.persist(persist_dir=self.vector_store_path)
        # print(f"Vector store saved to {self.vector_store_path}")
        
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
    
    async def _get_general_response(self, query: str) -> AsyncGenerator[str, None]:
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            full_prompt = f"{self.system_prompt}\n\nUser Query: {query}"
            response_stream = await model.generate_content_async(full_prompt, stream=True) 
            async for chunk in response_stream:
                if chunk.text: 
                    yield chunk.text
        except Exception as e:
            # print(f"Error streaming general response: {e}")
            yield "I'm here to help! Please ask me a question."
    
    async def process_query(self, query: str, similarity_threshold: float = 0.7) -> AsyncGenerator[str, None]:
        await self._ensure_initialized()
        
        # print(f"Processing query: {query}")
        
        try:
            response = self.query_engine.query(query)
            response_type = "rag_with_sources"
            sources = []
            max_score = 0.0

            if response.source_nodes:
                max_score = max([node.score for node in response.source_nodes if hasattr(node, 'score')])
                # print(f"Max similarity score: {max_score}")
                unique_sources =[]
                if max_score >= similarity_threshold:

                    for i, node in enumerate(response.source_nodes):
                        source_score = getattr(node, 'score', 0.0)
                        if source_score >= similarity_threshold:
                            if node.metadata.get('url') not in unique_sources:
                                unique_sources.append(node.metadata.get('url'))
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

            
            yield json.dumps({
                "response_type": response_type,
                "sources": sources if response_type == "rag_with_sources" else None,
                "unique_sources": unique_sources if response_type == "rag_with_sources" else None,
                "initial_message": "Streaming response...",
            }) + "\n" # Add newline for JSON streaming (common for SSE or custom protocols)

            # Now stream the actual answer content
            if response_type == "rag_with_sources":
                for word in response.response_gen:
                    yield json.dumps({"text_chunk": word + ' '}) + "\n"
                    await asyncio.sleep(0.005) # Increased sleep time for better effect
            else:
                # If falling back, use the dedicated general response streamer
                async for chunk in self._get_general_response(query):
                    yield json.dumps({"text_chunk": chunk}) + "\n" # Yield each chunk

        except Exception as e:
            # print(f"Error in RAG processing: {e}")
            # Yield an error message if something goes wrong
            yield json.dumps({
                "error": True,
                "message": f"An error occurred: {e}",
                "response_type": "error_fallback"
            }) + "\n"
            # As a fallback, still try to give a general response if the error was not fatal
            async for chunk in self._get_general_response(query):
                 yield json.dumps({"text_chunk": chunk}) + "\n"