import json
from typing import List, Dict, Any
import re
from pathlib import Path

class KnowledgeBaseProcessor:
    def __init__(self):
        self.chunks = []
        self.current_chunk_id = 0

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove special characters but keep basic punctuation
        text = re.sub(r'[^\w\s.,!?-]', '', text)
        return text.strip()

    def _create_chunk(self, content: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Create a chunk with metadata."""
        self.current_chunk_id += 1
        return {
            "id": f"chunk_{self.current_chunk_id}",
            "content": self._clean_text(content),
            "metadata": metadata
        }

    def _process_list(self, items: List, prefix: str, metadata: Dict[str, Any]) -> None:
        """Process a list of items into chunks."""
        if not items:
            return

        # If items are strings, combine them into a meaningful chunk
        if all(isinstance(item, str) for item in items):
            content = f"{prefix}:\n" + "\n".join(f"- {item}" for item in items)
            self.chunks.append(self._create_chunk(content, metadata))
        # If items are dictionaries, process each one
        elif all(isinstance(item, dict) for item in items):
            for item in items:
                self._process_dict(item, prefix, metadata)

    def _process_dict(self, data: Dict[str, Any], prefix: str = "", metadata: Dict[str, Any] = None) -> None:
        """Process a dictionary into chunks."""
        if metadata is None:
            metadata = {}

        for key, value in data.items():
            # Skip certain keys that don't add value to the content
            if key in ['id', 'created_at', 'modified_at', 'created_by_id', 'modified_by_id']:
                continue

            current_prefix = f"{prefix} {key}".strip() if prefix else key
            current_metadata = metadata.copy()
            current_metadata['section'] = current_prefix

            if isinstance(value, dict):
                # For nested dictionaries, create a chunk if it has meaningful content
                if any(isinstance(v, (str, list)) for v in value.values()):
                    content_parts = []
                    for k, v in value.items():
                        if isinstance(v, str):
                            content_parts.append(f"{k}: {v}")
                        elif isinstance(v, list) and all(isinstance(item, str) for item in v):
                            content_parts.append(f"{k}: {', '.join(v)}")
                    
                    if content_parts:
                        content = f"{current_prefix}:\n" + "\n".join(content_parts)
                        self.chunks.append(self._create_chunk(content, current_metadata))
                
                # Continue processing nested dictionary
                self._process_dict(value, current_prefix, current_metadata)

            elif isinstance(value, list):
                self._process_list(value, current_prefix, current_metadata)

            elif isinstance(value, str) and value.strip():
                # For string values, create a chunk if it's meaningful
                content = f"{current_prefix}: {value}"
                self.chunks.append(self._create_chunk(content, current_metadata))

    def process_knowledge_base(self, json_file: str) -> List[Dict[str, Any]]:
        """Process the knowledge base JSON file into chunks."""
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)

            # Process the knowledge base section specifically
            if 'knowledge_base' in data:
                self._process_dict(data['knowledge_base'], "Practice Information")
            
            # Process services offered
            if 'services_offered' in data:
                self._process_dict(data['services_offered'], "Services")

            # Process practice information
            if 'practices' in data:
                for practice in data['practices']:
                    practice_name = practice.get('display_name', 'Practice')
                    self._process_dict(practice, f"{practice_name} Information")

            print(f"Processed {len(self.chunks)} chunks from knowledge base")
            return self.chunks

        except Exception as e:
            print(f"Error processing knowledge base: {str(e)}")
            raise

    def save_chunks(self, output_file: str) -> None:
        """Save processed chunks to a JSON file."""
        try:
            with open(output_file, 'w') as f:
                json.dump({"chunks": self.chunks}, f, indent=2)
            print(f"Saved {len(self.chunks)} chunks to {output_file}")
        except Exception as e:
            print(f"Error saving chunks: {str(e)}")
            raise

def main():
    # Initialize processor
    processor = KnowledgeBaseProcessor()
    
    # Process knowledge base
    input_file = "knowledge_base.json"
    output_file = "processed_knowledge_base.json"
    
    # Create output directory if it doesn't exist
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Process and save chunks
    chunks = processor.process_knowledge_base(input_file)
    processor.save_chunks(output_file)
    
    # Print some example chunks
    print("\nExample chunks:")
    for chunk in chunks[:3]:
        print(f"\nChunk ID: {chunk['id']}")
        print(f"Section: {chunk['metadata']['section']}")
        print(f"Content: {chunk['content'][:200]}...")

if __name__ == "__main__":
    main() 