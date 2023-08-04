from typing import Dict, List, Optional, Type

from redis.asyncio import Redis
from fastapi import FastAPI
from pydantic import HttpUrl
from tortoise import Model

from . import i18n

from . import template
from .providers import Provider
from .resources import Dropdown
from .resources import Model as ModelResource
from .resources import Resource
from .routes import router
from . import protocols
from .providers.login import UsernamePasswordProvider

from .exceptions import (
    forbidden_error_exception,
    not_found_error_exception,
    server_error_exception,
    unauthorized_error_exception,
)
from starlette.status import (
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
)


class FastAPIAdmin(FastAPI):
    logo_url: str
    login_logo_url: str
    admin_path: str
    resources: List[Type[Resource]] = []
    model_resources: Dict[Type[Model], Type[Resource]] = {}
    redis: Redis
    language_switch: bool = True
    favicon_url: Optional[HttpUrl] = None

    async def configure(
            self,
            app: FastAPI,
            *,
            admin_model: Type[protocols.AdminModel],
            redis: Redis,
            logo_url: str = None,
            default_locale: str = "en_US",
            language_switch: bool = False,
            admin_path: str = "/admin",
            template_folders: Optional[List[str]] = None,
            providers: Optional[List[Provider]] = None,
            favicon_url: Optional[str] = None,
            add_exception_handlers: bool = True,
    ):
        self.include_router(router)

        if add_exception_handlers:
            self.add_exception_handlers()

        self.redis = redis
        i18n.set_locale(default_locale)
        self.admin_path = admin_path
        self.language_switch = language_switch
        self.logo_url = logo_url
        self.favicon_url = favicon_url

        if template_folders:
            template.add_template_folder(*template_folders)

        if providers is None:
            providers = [UsernamePasswordProvider(
                login_logo_url="https://preview.tabler.io/static/logo.svg",
                admin_model=admin_model,
            )]

        await self._register_providers(providers)

    async def _register_providers(self, providers: Optional[List[Provider]] = None):
        for p in providers or []:
            await p.register(self)

    def register_resources(self, *resource: Type[Resource]):
        for r in resource:
            self.register(r)

    def _set_model_resource(self, resource: Type[Resource]):
        if issubclass(resource, ModelResource):
            self.model_resources[resource.model] = resource
        elif issubclass(resource, Dropdown):
            for r in resource.resources:
                self._set_model_resource(r)

    def register(self, resource: Type[Resource]):
        self._set_model_resource(resource)
        self.resources.append(resource)

    def get_model_resource(self, model: Type[Model]):
        r = self.model_resources.get(model)
        return r() if r else None

    def add_exception_handlers(self):
        self.add_exception_handler(HTTP_500_INTERNAL_SERVER_ERROR, server_error_exception)
        self.add_exception_handler(HTTP_404_NOT_FOUND, not_found_error_exception)
        self.add_exception_handler(HTTP_403_FORBIDDEN, forbidden_error_exception)
        self.add_exception_handler(HTTP_401_UNAUTHORIZED, unauthorized_error_exception)


admin_app = FastAPIAdmin(title="Fastapi Admin")
