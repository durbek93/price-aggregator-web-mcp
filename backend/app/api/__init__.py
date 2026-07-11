# -*- coding: utf-8 -*-
from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.settings import router as settings_router
from app.api.catalog import router as catalog_router
from app.api.files import router as files_router
from app.api.tasks import router as tasks_router
from app.api.analysis import router as analysis_router

router = APIRouter(prefix="/api")
router.include_router(auth_router)
router.include_router(settings_router)
router.include_router(catalog_router)
router.include_router(files_router)
router.include_router(tasks_router)
router.include_router(analysis_router)
