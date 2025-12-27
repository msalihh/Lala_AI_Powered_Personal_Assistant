"""
Kritik akış testi: Document upload → list → get detail → delete

Bu test şunları doğrular:
1. Document upload çalışıyor mu?
2. Document list'te görünüyor mu?
3. Document detail'de text_content var mı?
4. Document silme çalışıyor mu?
"""
import io
import httpx


def test_document_upload_list_get_delete(base_url: str, auth_headers: dict):
    """
    Ne işe yarar?
    - Document upload, list, get detail ve delete akışını test eder.
    - RAG indexing'in çalıştığını doğrular (text extraction).
    
    Olmazsa ne olur?
    - Dosyalar yüklenir ama text extract edilmez (RAG çalışmaz)
    - Document list'te görünmez (DB kayıt sorunu)
    - Document detail'de content yok (text extraction kırık)
    """
    # 1) In-memory TXT dosyası
    # io.BytesIO: disk'e dosya yazmadan upload test eder
    # Olmazsa CI'da path vs bozulur
    file_content = b"Bu bir test dokumanidir. RAG icin icerik. Matematik: 2+2=4."
    files = {
        "file": ("test.txt", io.BytesIO(file_content), "text/plain")
    }

    # 2) Upload
    up = httpx.post(
        f"{base_url}/documents/upload",
        headers=auth_headers,
        files=files,
        timeout=60,  # Upload + indexing sürebilir
    )
    assert up.status_code in (200, 201), \
        f"Upload failed: {up.status_code} - {up.text[:500]}"
    
    doc = up.json()
    # documentId extraction: backend'iniz camelCase kullanıyor
    doc_id = doc.get("documentId") or doc.get("id") or doc.get("_id")
    assert doc_id is not None, \
        f"Document ID missing in response: {doc}"
    assert len(doc_id) > 0, "Document ID is empty"
    
    # Upload response kontrolü
    assert doc.get("filename") == "test.txt", \
        f"Filename mismatch: {doc.get('filename')}"
    assert doc.get("text_has_content") is True, \
        f"Text extraction failed: text_has_content={doc.get('text_has_content')}"

    # 3) List
    lst = httpx.get(
        f"{base_url}/documents",
        headers=auth_headers,
        timeout=30,
    )
    assert lst.status_code == 200, \
        f"List documents failed: {lst.status_code} - {lst.text[:200]}"
    
    items = lst.json()
    assert isinstance(items, list), \
        f"Expected list, got {type(items)}: {items}"
    
    # Document listede var mı?
    found = any(
        (d.get("id") == doc_id or d.get("_id") == doc_id or d.get("documentId") == doc_id)
        for d in items
    )
    assert found, \
        f"Document {doc_id} not found in list. Items: {[d.get('id') or d.get('_id') or d.get('documentId') for d in items[:3]]}"

    # 4) Detail (text_content dahil)
    det = httpx.get(
        f"{base_url}/documents/{doc_id}",
        headers=auth_headers,
        timeout=30,
    )
    assert det.status_code == 200, \
        f"Get document detail failed: {det.status_code} - {det.text[:200]}"
    
    det_data = det.json()
    # text_content alanı farklı isimde olabilir (content). Bu yüzden fallback koyduk
    text = det_data.get("text_content") or det_data.get("content") or det_data.get("text") or ""
    assert len(text) > 0, \
        f"Text content is empty: {det_data}"
    assert "test dokumanidir" in text.lower(), \
        f"Expected text not found in content: {text[:200]}"

    # 5) Delete
    dele = httpx.delete(
        f"{base_url}/documents/{doc_id}",
        headers=auth_headers,
        timeout=30,
    )
    assert dele.status_code in (200, 204), \
        f"Delete failed: {dele.status_code} - {dele.text[:200]}"
    
    # 6) Verify delete (document artık listede olmamalı)
    lst_after = httpx.get(
        f"{base_url}/documents",
        headers=auth_headers,
        timeout=30,
    )
    assert lst_after.status_code == 200
    items_after = lst_after.json()
    
    found_after = any(
        (d.get("id") == doc_id or d.get("_id") == doc_id or d.get("documentId") == doc_id)
        for d in items_after
    )
    assert not found_after, \
        f"Document {doc_id} still exists after delete!"

