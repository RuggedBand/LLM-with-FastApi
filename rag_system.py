import pandas as pd
import re
import html
import google.generativeai as genai
import os
from dotenv import load_dotenv
from llama_index.core import Document, VectorStoreIndex, Settings, StorageContext, load_index_from_storage
from llama_index.embeddings.gemini import GeminiEmbedding
from llama_index.llms.gemini import Gemini
from typing import Dict, Any, Optional, List
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
    
    async def _get_general_response(self, query: str) -> str:
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            
            # Use system prompt with the query
            full_prompt = f"{self.system_prompt}\n\nUser Query: {query}"
            
            response = await model.generate_content_async(full_prompt)
            return response.text
        except Exception as e:
            print(f"Error getting general response: {e}")
            return "I'm here to help! Please ask me a question."
    
    async def process_query(self, query: str, similarity_threshold: float = 0.7) -> Dict[str, Any]:
        await self._ensure_initialized()
        
        print(f"Processing query: {query}")
        
        try:
            response = self.query_engine.query(query)
            
            if not response.source_nodes:
                print("No sources found - falling back to general LLM")
                answer = await self._get_general_response(query)
                return {
                    "answer": answer,
                    "response_type": "general_fallback",
                    "sources": None
                }
            
            max_score = max([node.score for node in response.source_nodes if hasattr(node, 'score')])
            print(f"Max similarity score: {max_score}")
            
            if max_score < similarity_threshold:
                print("Similarity below threshold - using general LLM")
                answer = await self._get_general_response(query)
                return {
                    "answer": answer,
                    "response_type": "general_fallback",
                    "sources": None
                }
            
            sources = []
            for i, node in enumerate(response.source_nodes):
                source_score = getattr(node, 'score', 0.0)
                if source_score >= similarity_threshold:
                    sources.append({
                        "title": node.metadata.get('title', 'N/A'),
                        "url": node.metadata.get('url', 'N/A'),
                        "relevance_score": round(source_score, 3),
                        "text_snippet": node.text[:200] + "..." if len(node.text) > 200 else node.text
                    })
            
            print(f"Found {len(sources)} relevant sources")
            return {
                "answer": str(response.response),
                "response_type": "rag_with_sources",
                "sources": sources
            }
            
        except Exception as e:
            print(f"Error in RAG processing: {e}")
            answer = await self._get_general_response(query)
            return {
                "answer": answer,
                "response_type": "error_fallback",
                "sources": None
            }