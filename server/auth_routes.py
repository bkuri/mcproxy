"""OAuth token endpoint for MCProxy."""

from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import OAuthError, OAuthHandler
from logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/oauth", tags=["oauth"])


class TokenRequest(BaseModel):
    grant_type: str
    client_id: str
    client_secret: str
    scope: Optional[str] = None
    ttl_hours: Optional[int] = None


def _oauth_error_response(
    error: str, description: str, status_code: int
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": error, "error_description": description},
    )


def _get_oauth_handler(request: Request) -> OAuthHandler:
    handler = getattr(request.app.state, "oauth_handler", None)
    if not handler:
        raise HTTPException(status_code=500, detail="OAuth not configured")
    return handler


@router.post("/token")
async def token_endpoint(
    request: Request,
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    scope: Optional[str] = Form(None),
    ttl_hours: Optional[int] = Form(None),
) -> JSONResponse:
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        try:
            body = await request.json()
            grant_type = body.get("grant_type", "")
            client_id = body.get("client_id", "")
            client_secret = body.get("client_secret", "")
            scope = body.get("scope")
            ttl_hours = body.get("ttl_hours")
        except Exception:
            return _oauth_error_response(
                "invalid_request",
                "Invalid JSON body",
                400,
            )

    if not grant_type:
        return _oauth_error_response(
            "invalid_request",
            "Missing required parameter: grant_type",
            400,
        )

    if not client_id:
        return _oauth_error_response(
            "invalid_request",
            "Missing required parameter: client_id",
            400,
        )

    if not client_secret:
        return _oauth_error_response(
            "invalid_request",
            "Missing required parameter: client_secret",
            400,
        )

    oauth_handler = _get_oauth_handler(request)

    try:
        token_response = await oauth_handler.handle_token_request(
            grant_type=grant_type,
            client_id=client_id,
            client_secret=client_secret,
            scope=scope,
            ttl_hours=ttl_hours,
        )
        logger.info(f"Token issued for client_id={client_id}")
        return JSONResponse(content=token_response)
    except OAuthError as e:
        logger.warning(
            f"OAuth error for client_id={client_id}: {e.error} - {e.description}"
        )
        status_code = 401 if e.error == "invalid_client" else 400
        return _oauth_error_response(e.error, e.description, status_code)
    except Exception as e:
        logger.error(f"Unexpected error during token request: {e}")
        return _oauth_error_response(
            "server_error",
            "Internal server error",
            500,
        )


def register_auth_routes(app, oauth_handler: OAuthHandler) -> None:
    app.state.oauth_handler = oauth_handler
    app.include_router(router)
