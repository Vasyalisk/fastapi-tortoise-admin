from fastapi import Depends, Form
from starlette.requests import Request

from fastapi_admin.depends import get_current_admin, get_resources
from fastapi_admin.providers.login import UsernamePasswordProvider
from examples.models import Admin


class LoginProvider(UsernamePasswordProvider):
    async def password(
        self,
        request: Request,
        old_password: str = Form(...),
        new_password: str = Form(...),
        re_new_password: str = Form(...),
        admin: Admin = Depends(get_current_admin),
        resources=Depends(get_resources),
    ):
        return await self.logout(request)
