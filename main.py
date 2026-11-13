from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

auto_app = FastAPI(title='FastAPI Auto Salon')
auto_app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:3000'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@auto_app.get('/health', response_model=dict)
async def health():
    return {'status': 'ok'}
