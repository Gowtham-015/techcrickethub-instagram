import logging
from typing import Any, Dict, Optional
import requests

from config import Config
from exceptions import (
    InstagramAPIError,
    InstagramConfigError,
    InstagramConnectionError,
    InstagramTimeoutError,
)
from security import RedactingFormatter, redact_token, redact_url


class InstagramAPIClient:
    """Standalone Meta Graph API Client for Instagram Business Account."""

    BASE_GRAPH_URL = "https://graph.instagram.com"

    def __init__(
        self,
        user_id: Optional[str] = None,
        access_token: Optional[str] = None,
        api_version: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        env_config = None
        if not (user_id and access_token and api_version and timeout is not None):
            try:
                env_config = Config.load_from_env(validate=False)
            except Exception:
                pass

        self.user_id = user_id or (env_config.user_id if env_config else "")
        self.access_token = access_token or (env_config.access_token if env_config else "")
        self.api_version = api_version or (env_config.api_version if env_config else "v26.0")
        self.timeout = timeout if timeout is not None else (env_config.timeout_seconds if env_config else 30.0)

        self._validate_init()

        self.logger = logging.getLogger("InstagramAPIClient")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = RedactingFormatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                token=self.access_token,
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.session = requests.Session()

    def _validate_init(self) -> None:
        """Validates that necessary configuration parameters are present."""
        if not self.user_id:
            raise InstagramConfigError("Instagram user_id is required.")
        if not self.access_token or self.access_token == "YOUR_ACCESS_TOKEN_HERE":
            raise InstagramConfigError("Instagram access_token is missing or set to placeholder.")

    def _build_url(self, endpoint: str) -> str:
        """Constructs the full Meta Graph API URL from endpoint."""
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint

        clean_endpoint = endpoint.lstrip("/")
        return f"{self.BASE_GRAPH_URL}/{self.api_version}/{clean_endpoint}"

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Performs a GET request against the Instagram Graph API."""
        return self._request("GET", endpoint, params=params)

    def post(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Performs a POST request against the Instagram Graph API."""
        return self._request("POST", endpoint, params=params, data=data, json_data=json_data)

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Sends an HTTP request with authentication, error handling, and secret redaction."""
        url = self._build_url(endpoint)

        req_params = dict(params) if params else {}
        if "access_token" not in req_params:
            req_params["access_token"] = self.access_token

        safe_log_url = redact_url(url, token=self.access_token)
        self.logger.debug(f"Sending {method} request to {safe_log_url}")

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=req_params,
                data=data,
                json=json_data,
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout as e:
            self.logger.error(f"Timeout connecting to Instagram API: {safe_log_url}")
            raise InstagramTimeoutError(
                f"Request to Instagram API timed out after {self.timeout}s",
                token=self.access_token,
            ) from e
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"Connection error to Instagram API: {safe_log_url}")
            raise InstagramConnectionError(
                f"Network connection to Instagram API failed: {redact_token(str(e), token=self.access_token)}",
                token=self.access_token,
            ) from e
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request exception: {safe_log_url}")
            raise InstagramConnectionError(
                f"HTTP request error: {redact_token(str(e), token=self.access_token)}",
                token=self.access_token,
            ) from e

        try:
            json_response = response.json()
        except Exception as e:
            if not response.ok:
                raise InstagramAPIError(
                    f"HTTP {response.status_code} Error: Non-JSON response received",
                    http_status=response.status_code,
                    token=self.access_token,
                ) from e
            raise InstagramAPIError(
                f"Failed to parse JSON response from Meta API: {redact_token(str(e), token=self.access_token)}",
                http_status=response.status_code,
                token=self.access_token,
            ) from e

        if not response.ok or (isinstance(json_response, dict) and "error" in json_response):
            error_data = json_response.get("error", {}) if isinstance(json_response, dict) else {}
            err_message = error_data.get("message", f"HTTP {response.status_code} Error")
            err_code = error_data.get("code")
            err_subcode = error_data.get("error_subcode")
            err_type = error_data.get("type")
            fbtrace_id = error_data.get("fbtrace_id")

            raise InstagramAPIError(
                message=err_message,
                error_code=err_code,
                error_subcode=err_subcode,
                error_type=err_type,
                fbtrace_id=fbtrace_id,
                http_status=response.status_code,
                token=self.access_token,
            )

        return json_response

    def verify_published_media(self, media_id: str) -> bool:
        """Verifies that a published Instagram media ID exists on Meta Graph API."""
        if not media_id or not str(media_id).strip():
            return False
        try:
            res = self.get(f"/{media_id}", params={"fields": "id,media_type,timestamp,permalink"})
            return str(res.get("id", "")) == str(media_id).strip()
        except Exception as e:
            self.logger.warning(f"Verification of published media_id '{media_id}' failed: {redact_token(str(e))}")
            return False
