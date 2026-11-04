"""FRED ASGI application. Run from backend: uvicorn app.main:app --reload."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.routes import router
from app.core.config import Settings
from app.core.logging import operational_event
from app.core.rate_limit import RateLimiter
from app.services.events import EventHub
from app.services.lifecycle import ServiceManager


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        logging.basicConfig(level=logging.INFO, format='%(message)s')
        manager = ServiceManager(config, application.state.events)
        application.state.service = manager
        await manager.start()
        application.state.engine = manager.engine
        application.state.session_factory = manager.factory
        application.state.ai_provider = manager.provider
        application.state.assistant = manager.assistant
        try:
            yield
        finally:
            await manager.stop()

    application = FastAPI(title='FRED Intelligence Service', version='0.1.0', lifespan=lifespan,
                          docs_url=None, redoc_url=None, openapi_url=None)
    application.state.settings = config
    application.state.limiter = RateLimiter()
    application.state.events = EventHub()
    application.add_middleware(CORSMiddleware, allow_origins=config.allowed_origins, allow_credentials=True,
                               allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
                               allow_headers=['Content-Type', 'X-CSRF-Token'])

    @application.middleware('http')
    async def security_headers(request: Request, call_next):
        origin = request.headers.get('origin')
        if origin and origin not in config.allowed_origins:
            return JSONResponse({'detail': 'Request origin is not authorized.'}, status_code=403)
        try:
            content_length = int(request.headers.get('content-length', '0') or '0')
        except ValueError:
            return JSONResponse({'detail': 'Invalid Content-Length header.'}, status_code=400)
        if content_length < 0:
            return JSONResponse({'detail': 'Invalid Content-Length header.'}, status_code=400)
        if content_length > 64_000:
            return JSONResponse({'detail': 'Request is too large.'}, status_code=413)
        # Also bound chunked/incorrectly declared bodies before JSON parsing.
        if request.method in {'POST', 'PUT', 'PATCH'}:
            body_size = 0
            chunks = []
            async for chunk in request.stream():
                body_size += len(chunk)
                if body_size > 64_000:
                    return JSONResponse({'detail': 'Request is too large.'}, status_code=413)
                chunks.append(chunk)
            request._body = b''.join(chunks)
        if request.url.path.startswith('/api') and request.url.path != '/api/health':
            address = request.client.host if request.client else 'unknown'
            if not application.state.limiter.allow(f'api:{address}', config.api_rate_limit_per_minute):
                return JSONResponse({'detail': 'Request rate limit reached. Retry in one minute.'}, status_code=429,
                                    headers={'Retry-After': '60'})
        try:
            response = await call_next(request)
        except Exception as exc:
            # Never log exception strings: SQL/SDK errors can embed private values.
            operational_event('request.failed', level=logging.ERROR, error_type=type(exc).__name__)
            response = JSONResponse({'detail': 'FRED is temporarily unavailable. Check service health and retry.'}, status_code=503)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        first = exc.errors()[0]
        field = '.'.join(str(part) for part in first['loc'] if part != 'body')
        return JSONResponse({'detail': f'Invalid {field or "request"}: {first["msg"]}'}, status_code=422)

    application.include_router(router)
    return application


app = create_app()
