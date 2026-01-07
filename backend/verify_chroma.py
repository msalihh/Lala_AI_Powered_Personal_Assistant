from app.rag.vector_store import get_collection
import json

def verify_metadata():
    col = get_collection()
    # Get last 10 entries for emails
    results = col.get(
        where={"source_type": "email"},
        limit=20,
        include=["metadatas"]
    )
    
    print(f"Found {len(results['ids'])} email chunks.")
    for i in range(len(results['ids'])):
        meta = results['metadatas'][i]
        print(f"ID: {results['ids'][i]} | Date: {meta.get('date')} | Subject: {meta.get('original_filename')[:40]}...")

if __name__ == "__main__":
    verify_metadata()
