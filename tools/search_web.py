import logging
import httpx
from config import settings

logger = logging.getLogger(__name__)

_TAVILY_URL = "https://api.tavily.com/search"


async def search_web(query: str, max_results: int = 4) -> str:
    if not settings.tavily_api_key:
        return "Ricerca web non disponibile (TAVILY_API_KEY non configurata)."

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _TAVILY_URL,
                json={
                    "api_key": settings.tavily_api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": max_results,
                    "include_answer": True,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        parts = []

        answer = data.get("answer", "").strip()
        if answer:
            parts.append(f"**Risposta sintetica:** {answer}")

        results = data.get("results", [])
        for r in results[:max_results]:
            title = r.get("title", "")
            content = r.get("content", "").strip()[:400]
            url = r.get("url", "")
            if content:
                parts.append(f"**{title}**\n{content}\nFonte: {url}")

        if not parts:
            return f"Nessun risultato trovato per '{query}'."

        return "\n\n---\n\n".join(parts)

    except httpx.HTTPStatusError as e:
        logger.error("Tavily HTTP error %s: %s", e.response.status_code, e.response.text)
        return "Errore durante la ricerca web. Riprova più tardi."
    except Exception as e:
        logger.error("Tavily search error: %s", e)
        return "Ricerca web non disponibile al momento."
