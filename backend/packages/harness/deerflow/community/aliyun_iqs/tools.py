"""Web Search Tool - Search the web using Alibaba Cloud IQS."""

from typing import Any

from langchain.tools import tool

from deerflow.config import get_app_config

from .aliyun_iqs_client import AliyunIQSClient


def _get_model_extra_value(config: Any, key: str, default: Any = None) -> Any:
    if config is not None and key in config.model_extra:
        return config.model_extra.get(key, default)
    return default


def _get_aliyun_iqs_client() -> AliyunIQSClient:
    config = get_app_config().get_tool_config("web_search")
    return AliyunIQSClient(
        api_key=_get_model_extra_value(config, "api_key"),
        endpoint=_get_model_extra_value(config, "endpoint", "https://cloud-iqs.aliyuncs.com/search/unified"),
        engine_type=_get_model_extra_value(config, "engine_type", "LiteAdvanced"),
        time_range=_get_model_extra_value(config, "time_range", "NoLimit"),
        contents=_get_model_extra_value(config, "contents"),
        advanced_params=_get_model_extra_value(config, "advanced_params"),
        timeout=_get_model_extra_value(config, "timeout", 30),
    )


@tool("web_search", parse_docstring=True)
def web_search_tool(
    query: str,
    max_results: int = 5,
) -> str:
    """Search the web for information using Alibaba Cloud IQS. Use this tool to find current information, news, articles, and facts from the internet.

    Args:
        query: Search keywords describing what you want to find. Be specific for better results.
        max_results: Maximum number of results to return. Default is 5.
    """
    config = get_app_config().get_tool_config("web_search")
    if config is not None and "max_results" in config.model_extra:
        max_results = config.model_extra.get("max_results", max_results)

    client = _get_aliyun_iqs_client()
    return client.web_search(query=query, max_results=max_results)
