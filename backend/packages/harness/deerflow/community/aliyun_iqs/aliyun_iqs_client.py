"""Client for Alibaba Cloud IQS UnifiedSearch."""

import json
import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://cloud-iqs.aliyuncs.com/search/unified"
DEFAULT_ENGINE_TYPE = "LiteAdvanced"
DEFAULT_TIME_RANGE = "NoLimit"
DEFAULT_CONTENTS = {
    "mainText": False,
    "markdownText": False,
    "summary": False,
    "rerankScore": True,
}


class AliyunIQSClient:
    """Client for Alibaba Cloud Information Query Service UnifiedSearch."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str = DEFAULT_ENDPOINT,
        engine_type: str = DEFAULT_ENGINE_TYPE,
        time_range: str | None = DEFAULT_TIME_RANGE,
        contents: dict[str, Any] | None = None,
        advanced_params: dict[str, Any] | None = None,
        timeout: int | float = 30,
    ):
        self.api_key = api_key or os.getenv("ALIYUN_IQS_API_KEY")
        self.endpoint = endpoint
        self.engine_type = engine_type
        self.time_range = time_range
        self.contents = {**DEFAULT_CONTENTS, **(contents or {})}
        self.advanced_params = dict(advanced_params or {})
        self.timeout = timeout

    def _prepare_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _prepare_search_request_data(self, query: str, max_results: int = 5) -> dict[str, Any]:
        advanced_params = dict(self.advanced_params)
        advanced_params["numResults"] = str(max_results)

        data: dict[str, Any] = {
            "query": query,
            "engineType": self.engine_type,
            "contents": self.contents,
            "advancedParams": advanced_params,
        }
        if self.time_range:
            data["timeRange"] = self.time_range
        return data

    def web_search_raw_results(self, query: str, max_results: int = 5) -> dict[str, Any]:
        """Call Aliyun IQS UnifiedSearch and return the decoded JSON payload."""
        headers = self._prepare_headers()
        data = self._prepare_search_request_data(query=query, max_results=max_results)

        response = requests.post(self.endpoint, headers=headers, json=data, timeout=self.timeout)
        if response.status_code != 200:
            return {
                "error": f"Aliyun IQS API returned status {response.status_code}",
                "status_code": response.status_code,
                "body": response.text,
            }

        try:
            return response.json()
        except ValueError:
            return {"error": "Aliyun IQS API returned invalid JSON", "body": response.text}

    @staticmethod
    def _first_text(item: dict[str, Any], fields: tuple[str, ...]) -> str:
        for field in fields:
            value = item.get(field)
            if isinstance(value, str) and value:
                return value
        return ""

    @classmethod
    def clean_results(cls, page_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize IQS PageItem results into DeerFlow web_search results."""
        normalized_results = []
        for item in page_items:
            if not isinstance(item, dict):
                continue

            normalized_results.append(
                {
                    "title": cls._first_text(item, ("title",)),
                    "url": cls._first_text(item, ("link", "url")),
                    "content": cls._first_text(item, ("snippet", "summary", "mainText", "markdownText")),
                    "published_time": item.get("publishedTime") or item.get("published_time") or "",
                    "rerank_score": item.get("rerankScore") if "rerankScore" in item else item.get("rerank_score", ""),
                }
            )
        return normalized_results

    @staticmethod
    def _json_error(message: str, query: str, **extra: Any) -> str:
        payload = {"error": message, "query": query}
        payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)

    def web_search(self, query: str, max_results: int = 5) -> str:
        """Search the web using Aliyun IQS and return normalized JSON results."""
        if not self.api_key:
            logger.warning("Aliyun IQS API key is not set. Set ALIYUN_IQS_API_KEY or configure api_key for web_search.")
            return self._json_error("Aliyun IQS API key is not set", query)

        try:
            raw_results = self.web_search_raw_results(query=query, max_results=max_results)
        except requests.RequestException as e:
            logger.error("Aliyun IQS search request failed: %s", e)
            return self._json_error("Aliyun IQS search request failed", query, detail=str(e))
        except Exception as e:
            logger.error("Aliyun IQS search failed: %s", e)
            return self._json_error("Aliyun IQS search failed", query, detail=str(e))

        if "error" in raw_results:
            return self._json_error(
                raw_results["error"],
                query,
                status_code=raw_results.get("status_code"),
            )

        page_items = raw_results.get("pageItems", [])
        if not isinstance(page_items, list):
            return self._json_error("Aliyun IQS API returned invalid pageItems", query)

        normalized_results = self.clean_results(page_items)
        if not normalized_results:
            return json.dumps(
                {
                    "error": "No results found",
                    "query": query,
                    "total_results": 0,
                    "results": [],
                },
                ensure_ascii=False,
            )

        output = {
            "query": query,
            "request_id": raw_results.get("requestId", ""),
            "total_results": len(normalized_results),
            "results": normalized_results,
        }
        return json.dumps(output, indent=2, ensure_ascii=False)
