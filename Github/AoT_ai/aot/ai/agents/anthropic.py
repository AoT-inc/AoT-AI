# coding=utf-8
import logging
import requests
from aot.ai.agents.base_ai import AbstractAI
from flask_babel import lazy_gettext as lg

logger = logging.getLogger(__name__)

AI_INFORMATION = {
    'ai_name_unique': 'anthropic',
    'ai_manufacturer': 'Anthropic',
    'ai_name': 'Anthropic (Claude)',
    'ai_type': 'LLM',
    'auth_methods': ['api_key'],
    'auth_link': 'https://console.anthropic.com/settings/keys',
    'default_endpoint': 'https://api.anthropic.com/v1/messages',
    'endpoint_hint': 'Official Anthropic API',
    'models': [
        {'value': 'claude-sonnet-4-5-20250929', 'label': 'Claude Sonnet 4.5'},
        {'value': 'claude-haiku-4-5-20251001', 'label': 'Claude Haiku 4.5'},
        {'value': 'claude-3-5-sonnet-20241022', 'label': 'Claude 3.5 Sonnet'},
    ],
    'description': lg("Anthropic's Claude engine, known for human-like reasoning, sophisticated analysis, and safe response generation."),
    'url_manufacturer': 'https://www.anthropic.com/',
    'custom_options': [
        {'id': 'temperature', 'type': 'float', 'default': 0.7, 'name': 'Temperature (0.0 - 1.0)'},
        {'id': 'max_tokens', 'type': 'int', 'default': 1024, 'name': 'Max Output Tokens'}
    ]
}

class AnthropicAI(AbstractAI):
    """
    Anthropic (Claude) AI Engine Implementation.
    Uses the Anthropic Messages API for general-purpose reasoning.

    @phase active
    @stability stable
    @dependency AbstractAI, BrainResolver
    """
    MCP_SPECIALTY = "General Purpose Assistant (Claude Analysis)"
    
    def __init__(self, agent_config):
        super().__init__(agent_config)
        if not self.api_endpoint:
            self.api_endpoint = "https://api.anthropic.com/v1/messages"
        logger.info(f"Initializing AnthropicAI with endpoint: {self.api_endpoint}")

    def run_reasoning(self, context, goal):
        """
        Executes reasoning via Anthropic Messages API.
        """
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "prompt-caching-2024-07-16",  # @ANCHOR: PROMPT_CACHE [2026-03-25]
            "content-type": "application/json"
        }

        prompt = self._build_prompt(context, goal)

        payload = {
            "model": self.model_name or "claude-sonnet-4-20250514",
            "system": [
                {
                    "type": "text",
                    "text": self.system_prompt or "You are a helpful AI assistant.",
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            "max_tokens": self.max_tokens or 1024,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature or 0.7
        }

        logger.info(f"[AnthropicAI] POST {self.api_endpoint} model={payload['model']}")

        try:
            response = requests.post(
                self.api_endpoint, json=payload, headers=headers, timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            raw_text = data["content"][0]["text"]

            logger.debug(f"[AnthropicAI] Raw response: {raw_text[:300]}")
            return self._safe_api_result(raw_text, "AnthropicAI")

        except requests.exceptions.Timeout:
            logger.error(f"[AnthropicAI] API timeout ({self.timeout}s)")
            return {"insight": f"[AnthropicAI] API 호출 시간 초과 ({self.timeout}초)", "actions": []}
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else "unknown"
            body = e.response.text[:300] if e.response is not None else ""
            logger.error(f"[AnthropicAI] HTTP {status_code}: {body}")
            return {"insight": f"[AnthropicAI] API 오류 (HTTP {status_code}): {body}", "actions": []}
        except requests.exceptions.ConnectionError:
            logger.error("[AnthropicAI] Connection failed")
            return {"insight": "[AnthropicAI] API 서버 연결 실패", "actions": []}
        except (KeyError, IndexError) as e:
            logger.error(f"[AnthropicAI] Unexpected response structure: {e}")
            return {"insight": "[AnthropicAI] 예상치 못한 응답 형식", "actions": []}

    def parse_actions(self, raw_response):
        return raw_response.get('actions', [])
