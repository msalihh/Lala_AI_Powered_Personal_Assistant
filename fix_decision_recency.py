import sys
import os

filepath = r"c:\Users\msg\bitirme\backend\app\rag\decision.py"
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Add recency sorting logic
insertion_point = 'retrieval_stats["retrieved_chunks_count"] = len(retrieved_chunks)'
reorder_logic = """                # CRITICAL: If intent implies recency (e.g. "son mail"), re-sort by date
                latest_keywords = ["son", "en yeni", "güncel", "latest", "recent"]
                is_latest_query = any(kw in query.lower() for kw in latest_keywords)
                
                if is_latest_query and retrieved_chunks:
                    try:
                        # Re-sort chunks by date metadata (most recent first)
                        # We keep chunks with missing dates at the end
                        retrieved_chunks.sort(key=lambda x: x.get('date', ''), reverse=True)
                        logger.info(f"[{request_id}] RAG_DECISION: Re-sorted {len(retrieved_chunks)} chunks by date for 'latest' query")
                    except Exception as sort_err:
                        logger.warning(f"Failed to re-sort chunks by date: {sort_err}")
                
                """

if insertion_point in content:
    content = content.replace(insertion_point, reorder_logic + insertion_point)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Replacement successful")
else:
    print("Insertion point not found")
