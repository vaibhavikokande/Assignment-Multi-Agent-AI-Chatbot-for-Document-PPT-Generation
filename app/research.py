from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

from .models import SourceCitation


@dataclass
class ResearchResult:
    query: str
    provider: str
    sources: list[SourceCitation]
    summary: str
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "provider": self.provider,
            "sources": [asdict(source) for source in self.sources],
            "summary": self.summary,
            "fallback_reason": self.fallback_reason,
        }


DEMO_SOURCES = [
    SourceCitation("Stanford AI Index", "https://aiindex.stanford.edu/report/", "The AI Index tracks model capability, adoption, responsible AI, and the cost of deploying advanced systems.", "demo_web"),
    SourceCitation("NIST AI Risk Management Framework", "https://www.nist.gov/itl/ai-risk-management-framework", "NIST provides a structured reference for governing, mapping, measuring, and managing AI risk.", "demo_web"),
    SourceCitation("McKinsey State of AI", "https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-state-of-ai", "Enterprise adoption is moving from experimentation toward workflow redesign, value measurement, and operating-model change.", "demo_web"),
]


def _parse_results(page: str, limit: int) -> list[SourceCitation]:
    clean = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.I | re.S)
    matches = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', clean, flags=re.I | re.S)
    sources: list[SourceCitation] = []
    for url, title_html in matches[:limit]:
        title = re.sub(r"<[^>]+>", "", title_html)
        title = html.unescape(re.sub(r"\s+", " ", title)).strip()
        url = html.unescape(url)
        if url.startswith("//"):
            url = "https:" + url
        if title and url.startswith("http"):
            sources.append(SourceCitation(title, url, "Live search result returned by the configured web provider."))
    return sources


class WebSearchProvider:
    def __init__(self, enabled: bool = True, timeout: int = 8, provider: str = "duckduckgo_html", api_url: str | None = None, api_key: str | None = None) -> None:
        self.enabled = enabled
        self.timeout = timeout
        self.provider = provider
        self.api_url = api_url
        self.api_key = api_key

    def _fallback(self, query: str, reason: str, limit: int = 5) -> ResearchResult:
        return ResearchResult(
            query,
            "deterministic_demo_fallback",
            DEMO_SOURCES[:limit],
            f"Offline research fallback returned {min(limit, len(DEMO_SOURCES))} labeled sources for: {query}",
            reason,
        )

    def _search_json_api(self, query: str, limit: int) -> ResearchResult:
        if not self.api_url:
            return self._fallback(query, "WEB_SEARCH_API_URL is not configured", limit)
        encoded = urllib.parse.urlencode({"q": query, "count": limit})
        request = urllib.request.Request(f"{self.api_url}?{encoded}", headers={"Accept": "application/json", "User-Agent": "DocumentPPTPOC/1.0"})
        if self.api_key:
            request.add_header("Authorization", f"Bearer {self.api_key}")
            request.add_header("X-API-Key", self.api_key)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
        candidates = payload.get("results", payload.get("web", {}).get("results", [])) if isinstance(payload, dict) else []
        sources = []
        for item in candidates[:limit]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", item.get("link", ""))).strip()
            snippet = str(item.get("snippet", item.get("description", "Live JSON search result."))).strip()
            if title and url.startswith("http"):
                sources.append(SourceCitation(title, url, snippet, "web_api"))
        if not sources:
            return self._fallback(query, "Configured JSON web provider returned no usable sources", limit)
        return ResearchResult(query, "json_web_api", sources, f"Live JSON web search returned {len(sources)} sources for: {query}")

    def _search_tavily(self, query: str, limit: int) -> ResearchResult:
        if not self.api_key:
            return self._fallback(query, "TAVILY_API_KEY is not configured", limit)
        payload = json.dumps(
            {
                "query": query,
                "max_results": limit,
                "search_depth": "basic",
                "include_answer": False,
                "include_raw_content": False,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            "https://api.tavily.com/search",
            data=payload,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "DocumentPPTPOC/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8", "ignore"))
        candidates = response_payload.get("results", []) if isinstance(response_payload, dict) else []
        sources: list[SourceCitation] = []
        for item in candidates[:limit]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            snippet = str(item.get("content", "Live Tavily search result.")).strip()
            if title and url.startswith("http"):
                sources.append(SourceCitation(title, url, snippet, "tavily"))
        if not sources:
            return self._fallback(query, "Tavily returned no usable sources", limit)
        return ResearchResult(query, "tavily_live", sources, f"Tavily live search returned {len(sources)} sources for: {query}")

    def search(self, query: str, limit: int = 5) -> ResearchResult:
        if not self.enabled:
            return self._fallback(query, "WEB_SEARCH_ENABLED=false", limit)
        if self.provider == "json_api":
            try:
                return self._search_json_api(query, limit)
            except (OSError, ValueError, TimeoutError, json.JSONDecodeError) as exc:
                return self._fallback(query, f"Configured JSON web provider failed: {type(exc).__name__}", limit)
        if self.provider == "tavily":
            try:
                return self._search_tavily(query, limit)
            except (OSError, ValueError, TimeoutError, json.JSONDecodeError) as exc:
                return self._fallback(query, f"Tavily request failed: {type(exc).__name__}", limit)
        if self.provider != "duckduckgo_html":
            return self._fallback(query, f"Unknown web search provider: {self.provider}", limit)
        try:
            encoded = urllib.parse.urlencode({"q": query})
            request = urllib.request.Request(
                f"https://html.duckduckgo.com/html/?{encoded}",
                headers={"User-Agent": "DocumentPPTPOC/1.0 research agent"},
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                page = response.read().decode("utf-8", "ignore")
            if "anomaly-modal" in page.lower() or "challenge-form" in page.lower():
                return self._fallback(query, "DuckDuckGo returned an anti-bot challenge", limit)
            sources = _parse_results(page, limit)
            if sources:
                return ResearchResult(query, "duckduckgo_live", sources, f"Live research returned {len(sources)} sources for: {query}")
            return self._fallback(query, "DuckDuckGo returned no parseable sources", limit)
        except (OSError, ValueError, TimeoutError) as exc:
            return self._fallback(query, f"DuckDuckGo request failed: {type(exc).__name__}", limit)
