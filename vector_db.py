import json
import chromadb
from chromadb.utils import embedding_functions
from typing import List, Dict, Any
import openai
from pathlib import Path
from sentence_transformers import SentenceTransformer
import uuid

class DentalKnowledgeBase:
    def __init__(self):
        # Initialize sentence transformer model
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Initialize ChromaDB with sentence transformer embeddings
        self.client = chromadb.Client()
        self.collection = self.client.create_collection(
            name="dental_knowledge",
            embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name='all-MiniLM-L6-v2'
            )
        )
    
    def load_knowledge_base(self, processed_file: str = "processed_knowledge_base.json"):
        """Load and process knowledge base from processed JSON file."""
        try:
            with open(processed_file, 'r') as f:
                data = json.load(f)
            
            if 'chunks' not in data:
                raise ValueError("Processed file must contain 'chunks' key")
            
            # Add chunks to vector database
            for chunk in data['chunks']:
                self.collection.add(
                    documents=[chunk['text']],
                    ids=[chunk.get('id', str(uuid.uuid4()))],
                    metadatas=[chunk['metadata']]
                )
            
            print(f"Successfully loaded {len(data['chunks'])} chunks into vector database")
        
        except Exception as e:
            print(f"Error loading knowledge base: {str(e)}")
            raise
    
    def get_context_for_query(self, query: str, n_results: int = 3) -> str:
        """Retrieve relevant context for a query."""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            # Combine retrieved chunks into context
            context_parts = []
            for doc, metadata in zip(results['documents'][0], results['metadatas'][0]):
                # Use type and subtype from metadata instead of section
                section_info = f"{metadata.get('type', '')}"
                if 'subtype' in metadata:
                    section_info += f" - {metadata['subtype']}"
                if 'practice_name' in metadata:
                    section_info += f" ({metadata['practice_name']})"
                
                context_parts.append(f"Section: {section_info}\n{doc}")
            
            context = "\n\n".join(context_parts)
            return context
        
        except Exception as e:
            print(f"Error retrieving context: {str(e)}")
            return ""

# Example usage:
if __name__ == "__main__":
    # Initialize the knowledge base
    kb = DentalKnowledgeBase()
    
    # Load the processed knowledge base
    kb.load_knowledge_base()
    
    # Test some queries
    test_queries = [
        "What services do you offer for emergency dental care?",
        "What insurance plans do you accept?",
        "What should I bring for my first visit?",
        "What are your payment options?"
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        context = kb.get_context_for_query(query)
        print("Context:", context) 