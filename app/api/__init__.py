from fastapi import APIRouter

from app.api.categories import router as categories_router
from app.api.products import router as products_router
from app.api.search import router as search_router

api_router = APIRouter()
api_router.include_router(categories_router, prefix="/categories", tags=["categories"])
api_router.include_router(products_router, prefix="/products", tags=["products"])
api_router.include_router(search_router, prefix="/products", tags=["search"])
