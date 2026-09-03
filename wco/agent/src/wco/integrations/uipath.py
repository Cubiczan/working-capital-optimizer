"""UiPath Orchestrator client for Microsoft inbox and document automation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Sequence

import httpx


DEFAULT_SCOPE = "OR.Default OR.Jobs"
DEFAULT_BASE_URL = "https://cloud.uipath.com"
TOKEN_URL = "https://cloud.uipath.com/identity_/connect/token"


@dataclass(slots=True)
class UiPathConfig:
    client_id: str
    client_secret: str
    organization_name: str
    tenant_name: str
    release_key: str | None = None
    folder_key: str | None = None
    base_url: str = DEFAULT_BASE_URL
    scope: str = DEFAULT_SCOPE


class UiPathError(RuntimeError):
    """Raised when UiPath token exchange or job launch fails."""


class UiPathClient:
    """Minimal UiPath Automation Cloud / Orchestrator API client."""

    def __init__(self, config: UiPathConfig) -> None:
        self.config = config

    async def _access_token(self) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                TOKEN_URL,
                data={
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "grant_type": "client_credentials",
                    "scope": self.config.scope,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if response.status_code >= 400:
            raise UiPathError(
                f"UiPath token request failed ({response.status_code}): {response.text}"
            )

        data = response.json()
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise UiPathError("UiPath token response did not include access_token.")
        return token

    async def start_job(
        self,
        *,
        release_key: str | None = None,
        input_arguments: dict[str, Any] | None = None,
        robot_ids: Sequence[int] | None = None,
        jobs_count: int = 0,
        strategy: str = "Specific",
        folder_key: str | None = None,
    ) -> dict[str, Any]:
        """Start a UiPath Orchestrator job and return the API response."""

        key = release_key or self.config.release_key
        if not key:
            raise UiPathError("release_key is required to start a UiPath job.")

        token = await self._access_token()
        target_url = (
            f"{self.config.base_url.rstrip('/')}"
            f"/{self.config.organization_name}/{self.config.tenant_name}"
            "/orchestrator_/odata/Jobs/UiPath.Server.Configuration.OData.StartJobs"
        )

        body: dict[str, Any] = {
            "startInfo": {
                "ReleaseKey": key,
                "Strategy": strategy,
                "RobotIds": list(robot_ids or []),
                "JobsCount": jobs_count,
            }
        }
        if input_arguments:
            body["startInfo"]["InputArguments"] = json.dumps(input_arguments, separators=(",", ":"))

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        folder = folder_key or self.config.folder_key
        if folder:
            headers["X-UIPATH-FolderKey"] = folder

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(target_url, json=body, headers=headers)

        if response.status_code >= 400:
            raise UiPathError(
                f"UiPath start job failed ({response.status_code}): {response.text}"
            )

        return response.json()


def uipath_client_from_settings(settings: Any) -> UiPathClient | None:
    """Build a client from WCO settings when credentials are configured."""

    client_id = getattr(settings, "uipath_client_id", None)
    client_secret = getattr(settings, "uipath_client_secret", None)
    organization_name = getattr(settings, "uipath_organization_name", None)
    tenant_name = getattr(settings, "uipath_tenant_name", None)

    if not client_id or not client_secret or not organization_name or not tenant_name:
        return None

    secret_value = (
        client_secret.get_secret_value()
        if hasattr(client_secret, "get_secret_value")
        else str(client_secret)
    )

    return UiPathClient(
        UiPathConfig(
            client_id=client_id,
            client_secret=secret_value,
            organization_name=organization_name,
            tenant_name=tenant_name,
            release_key=getattr(settings, "uipath_release_key", None),
            folder_key=getattr(settings, "uipath_folder_key", None),
            base_url=getattr(settings, "uipath_base_url", DEFAULT_BASE_URL),
            scope=getattr(settings, "uipath_scope", DEFAULT_SCOPE),
        )
    )
