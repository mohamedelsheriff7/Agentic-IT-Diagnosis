from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from fastapi.responses import JSONResponse
from .config import Settings
from .models import database
from .policy import DomainError
from .api import router, admin


def create_app(settings=None):
    settings=settings or Settings.from_env()
    settings.now()
    app=FastAPI(title='Workstream C: Synthetic IT Diagnostics Backend',version='1.0.0',description='Deterministic mock tools; no account changes, LLM, external notifications or hidden answers. Admin API is excluded from agent export.')
    app.state.settings=settings
    app.state.engine,app.state.sessions=database(settings.database_url)
    @app.middleware('http')
    async def request_id(request,call_next):
        request.state.request_id=str(uuid4())
        response=await call_next(request)
        response.headers['X-Request-ID']=request.state.request_id
        return response
    def error(request,status,code,message,details=None):
        return JSONResponse(status_code=status,content=dict(code=code,message=message,details=details or [],request_id=getattr(request.state,'request_id',str(uuid4()))))
    @app.exception_handler(DomainError)
    async def domain_error(request,exc): return error(request,exc.status,exc.code,exc.message,exc.details)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        return error(request,422,'VALIDATION_ERROR','Invalid request',[str(e['loc'])+': '+e['type'] for e in exc.errors()])
    @app.exception_handler(HTTPException)
    async def http_error(request,exc): return error(request,exc.status_code,'HTTP_ERROR',str(exc.detail))
    @app.exception_handler(Exception)
    async def unexpected(request,exc): return error(request,500,'INTERNAL_ERROR','Unexpected server error')
    @app.get('/health',tags=['developer'])
    def health(): return {'status':'ok','synthetic':True}
    app.include_router(router);app.include_router(admin)
    original_openapi=app.openapi
    def documented_openapi():
        from .examples import enrich
        return enrich(original_openapi())
    app.openapi=documented_openapi
    return app

app=create_app()
