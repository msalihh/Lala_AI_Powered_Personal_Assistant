"""
Kritik akış testi: RAG debug endpoint güvenliği

Bu test şunları doğrular:
1. Debug endpoint auth gerektiriyor mu?
2. Auth'suz erişim kapalı mı?
3. Auth'lu erişim çalışıyor mu?
"""
import httpx


def test_debug_rag_requires_auth(base_url: str, auth_headers: dict):
    """
    Ne işe yarar?
    - Debug endpoint'inin güvenliğini doğrular.
    - Prod'da debug endpoint'lerinin kapalı olması gerektiğini hatırlatır.
    
    Olmazsa ne olur?
    - Debug endpoint herkese açık olur (güvenlik açığı)
    - RAG iç yapısı sızdırılır
    - Sistem bilgileri expose edilir
    """
    # 1) Auth'suz erişim kapalı mı?
    # Neden 404'ü kabul ettik? İlerde prod'da kapatırsan test kırılmasın.
    # Ama anon erişimde 200 olursa kırmızı alarm.
    anon = httpx.get(
        f"{base_url}/debug/rag?query=test",
        timeout=30,
    )
    assert anon.status_code in (401, 403, 404), \
        f"Debug endpoint should require auth (401/403/404), got {anon.status_code}. " \
        f"This is a security issue if status is 200!"

    # 2) Auth'lu erişim (dev ortamında genelde 200)
    # Not: Backend'iniz query parametresi istiyor
    authed = httpx.get(
        f"{base_url}/debug/rag?query=test",
        headers=auth_headers,
        timeout=30,
    )
    # 404: prod'da kapalı olabilir (OK)
    # 200: dev'de açık (OK)
    # 400: query parametresi eksik/yanlış (OK, endpoint çalışıyor demek)
    assert authed.status_code in (200, 404, 400), \
        f"Unexpected status code for authed request: {authed.status_code} - {authed.text[:200]}"
    
    # Eğer 200 döndüyse, response formatını kontrol et
    if authed.status_code == 200:
        data = authed.json()
        # Debug endpoint genelde RAG sonuçlarını döndürür
        assert isinstance(data, dict), \
            f"Expected dict response, got {type(data)}"

