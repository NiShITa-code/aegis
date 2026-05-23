import os
import json
import re
from litellm import completion
import litellm.exceptions
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type, RetryError
from pydantic import BaseModel, ValidationError

class LLMUtilsError(Exception):
    pass

class SchemaValidationError(LLMUtilsError):
    pass

class LLMTimeoutError(LLMUtilsError):
    pass

class LLMRateLimitError(LLMUtilsError):
    pass

def extract_json_from_text(raw_text: str) -> dict:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r'```(?:json)?\n(.*?)\n```', raw_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        start = raw_text.find('{')
        end = raw_text.rfind('}')
        if start != -1 and end != -1:
            try:
                return json.loads(raw_text[start:end+1])
            except:
                pass
    raise ValueError("Could not extract valid JSON from LLM response.")

# Telemetry
LLM_TELEMETRY = {
    "total_calls": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
}

def get_llm_telemetry() -> dict:
    return LLM_TELEMETRY

# We retry on transient errors (rate limit, timeout) and validation errors.
# We stop after 3 attempts.
@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((
        litellm.exceptions.RateLimitError,
        litellm.exceptions.Timeout,
        litellm.exceptions.APIConnectionError,
        litellm.exceptions.ServiceUnavailableError,
        ValueError,
        ValidationError,
        SchemaValidationError
    )),
    reraise=True
)
def call_llm_with_retries(messages: list, response_format: type[BaseModel]) -> BaseModel:
    """
    Calls the LLM securely and deterministically with bounded exponential backoff.
    Returns the validated Pydantic model.
    """
    model = os.environ.get("AEGIS_MODEL", "gemini/gemini-1.5-pro")
    
    # Note: Determinism is not a security boundary, but setting temperature=0.0
    # ensures consistent, predictable output for security-critical generation.
    try:
        LLM_TELEMETRY["total_calls"] += 1
        response = completion(
            model=model,
            messages=messages,
            temperature=0.0,
            response_format=response_format
        )
        
        # Track token usage
        if hasattr(response, 'usage') and response.usage:
            LLM_TELEMETRY["prompt_tokens"] += getattr(response.usage, 'prompt_tokens', 0)
            LLM_TELEMETRY["completion_tokens"] += getattr(response.usage, 'completion_tokens', 0)
            LLM_TELEMETRY["total_tokens"] += getattr(response.usage, 'total_tokens', 0)
            
    except litellm.exceptions.RateLimitError as e:
        print("[Aegis - LLM] Rate limit hit. Backing off...")
        raise e
    except litellm.exceptions.Timeout as e:
        print("[Aegis - LLM] Timeout hit. Backing off...")
        raise e
        
    raw_text = response.choices[0].message.content
    if not raw_text:
        raise ValueError("Empty response from LLM")
        
    try:
        data_dict = extract_json_from_text(raw_text)
    except ValueError as e:
        print(f"[Aegis - LLM] JSON extraction failed: {e}")
        raise e
        
    try:
        validated_data = response_format(**data_dict)
    except ValidationError as e:
        print(f"[Aegis - LLM] Schema validation failed: {e}")
        raise SchemaValidationError(f"Schema validation failed: {e}")
        
    return validated_data

def safe_call_llm(messages: list, response_format: type[BaseModel]):
    """
    Wrapper that catches the RetryError and translates it to safe status codes.
    Returns (data, status_code).
    """
    try:
        data = call_llm_with_retries(messages, response_format)
        return data, "SUCCESS"
    except RetryError as e:
        original_error = e.last_attempt.exception()
        if isinstance(original_error, litellm.exceptions.RateLimitError):
            return None, "RATE_LIMIT_EXHAUSTION"
        elif isinstance(original_error, litellm.exceptions.Timeout):
            return None, "TIMEOUT"
        elif isinstance(original_error, (ValueError, ValidationError, SchemaValidationError)):
            return None, "SCHEMA_VALIDATION_FAILURE"
        else:
            return None, "LLM_FAILURE"
    except Exception as e:
        # Fallback for unexpected immediate failures
        if isinstance(e, litellm.exceptions.RateLimitError):
            return None, "RATE_LIMIT_EXHAUSTION"
        elif isinstance(e, litellm.exceptions.Timeout):
            return None, "TIMEOUT"
        elif isinstance(e, (ValueError, ValidationError, SchemaValidationError)):
            return None, "SCHEMA_VALIDATION_FAILURE"
        return None, "LLM_FAILURE"
