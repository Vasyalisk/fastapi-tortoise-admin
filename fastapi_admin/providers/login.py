import typing
import uuid

from redis.asyncio import Redis
from fastapi import Depends, Form
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER, HTTP_401_UNAUTHORIZED

from fastapi_admin import constants
from fastapi_admin.depends import get_current_admin, get_redis, get_resources
from fastapi_admin.i18n import _
from fastapi_admin.providers import Provider
from fastapi_admin.template import templates
from fastapi_admin.utils import check_password, hash_password

if typing.TYPE_CHECKING:
    from fastapi_admin.app import FastAPIAdmin


class UsernamePasswordProvider(Provider):
    name = "login_provider"

    access_token = "access_token"

    def __init__(
            self,
            admin_model,
            login_path="/login",
            logout_path="/logout",
            template="admin/providers/login/login.html",
            login_title="Login to your account",
            login_logo_url: str = None,
            username_field_name="username",
            password_checker=check_password,
            password_hasher=hash_password,
    ):
        self.login_path = login_path
        self.logout_path = logout_path
        self.template = template
        self.admin_model = admin_model
        self.login_title = login_title
        self.login_logo_url = login_logo_url
        self.username_field_name = username_field_name
        self.password_checker = password_checker
        self.password_hasher = password_hasher

    async def login_view(
            self,
            request: Request,
    ):
        request.state.username_field_name = self.username_field_name

        return templates.TemplateResponse(
            self.template,
            context={
                "request": request,
                "login_logo_url": self.login_logo_url,
                "login_title": self.login_title,
            },
        )

    async def register(self, app: "FastAPIAdmin"):
        await super().register(app)
        login_path = self.login_path
        app.get(login_path)(self.login_view)
        app.post(login_path)(self.login)
        app.get(self.logout_path)(self.logout)
        app.add_middleware(BaseHTTPMiddleware, dispatch=self.authenticate)
        app.get("/init")(self.init_view)
        app.post("/init")(self.init)
        app.get("/password")(self.password_view)
        app.post("/password")(self.password)

    async def login(self, request: Request, redis: Redis = Depends(get_redis)):
        form = await request.form()

        if not form.keys():
            form = await request.json()

        username = form.get(self.username_field_name)
        password = form.get("password")
        remember_me = form.get("remember_me")
        admin = await self.admin_model.get_or_none(**{self.username_field_name: username})
        if not admin or not self.password_checker(password, admin.password):
            return templates.TemplateResponse(
                self.template,
                status_code=HTTP_401_UNAUTHORIZED,
                context={"request": request, "error": _("login_failed")},
            )
        response = RedirectResponse(url=request.app.admin_path, status_code=HTTP_303_SEE_OTHER)
        if remember_me == "on":
            expire = 3600 * 24 * 30
            response.set_cookie("remember_me", "on")
        else:
            expire = 3600
            response.delete_cookie("remember_me")
        token = uuid.uuid4().hex
        response.set_cookie(
            self.access_token,
            token,
            expires=expire,
            path=request.app.admin_path,
            httponly=True,
        )
        await redis.set(constants.LOGIN_USER.format(token=token), admin.pk, ex=expire)
        return response

    async def logout(self, request: Request):
        response = self.redirect_login(request)
        response.delete_cookie(self.access_token, path=request.app.admin_path)
        token = request.cookies.get(self.access_token)
        await request.app.redis.delete(constants.LOGIN_USER.format(token=token))
        return response

    async def authenticate(
            self,
            request: Request,
            call_next: RequestResponseEndpoint,
    ):
        redis: Redis = request.app.redis
        token = request.cookies.get(self.access_token)
        path = request.scope["path"]
        admin = None
        if token:
            token_key = constants.LOGIN_USER.format(token=token)
            admin_id = await redis.get(token_key)
            admin = await self.admin_model.get_or_none(pk=admin_id)
        request.state.admin = admin
        request.state.username_field_name = self.username_field_name

        if path == self.login_path and admin:
            return RedirectResponse(url=request.app.admin_path, status_code=HTTP_303_SEE_OTHER)

        if path not in (self.login_path, "/init") and admin is None:
            return self.redirect_login(request)

        response = await call_next(request)
        return response

    async def create_user(self, username: str, password: str, **kwargs):
        return await self.admin_model.create(
            **{self.username_field_name: username.lower()},
            password=self.password_hasher(password),
            **kwargs,
        )

    async def init_view(self, request: Request):
        exists = await self.admin_model.all().limit(1).exists()
        if exists:
            return self.redirect_login(request)
        return templates.TemplateResponse("admin/init.html", context={"request": request})

    async def init(
            self,
            request: Request,
    ):
        exists = await self.admin_model.all().limit(1).exists()

        if exists:
            return self.redirect_login(request)

        form = await request.form()
        password = form.get("password")
        confirm_password = form.get("confirm_password")
        username = form.get(self.username_field_name)

        if password != confirm_password:
            return templates.TemplateResponse(
                "admin/init.html",
                context={"request": request, "error": _("confirm_password_different")},
            )

        await self.create_user(username, password)
        return self.redirect_login(request)

    def redirect_login(self, request: Request):
        return RedirectResponse(
            url=request.app.admin_path + self.login_path, status_code=HTTP_303_SEE_OTHER
        )

    async def password_view(
            self,
            request: Request,
            resources=Depends(get_resources),
    ):
        return templates.TemplateResponse(
            "admin/providers/login/password.html",
            context={
                "request": request,
                "resources": resources,
            },
        )

    async def password(
            self,
            request: Request,
            old_password: str = Form(...),
            new_password: str = Form(...),
            re_new_password: str = Form(...),
            admin=Depends(get_current_admin),
            resources=Depends(get_resources),
    ):
        error = None
        if not self.password_checker(old_password, admin.password):
            error = _("old_password_error")
        elif new_password != re_new_password:
            error = _("new_password_different")
        if error:
            return templates.TemplateResponse(
                "admin/providers/login/password.html",
                context={"request": request, "resources": resources, "error": error},
            )
        admin.password = self.password_hasher(new_password)
        await admin.save(update_fields=["password"])
        return await self.logout(request)
