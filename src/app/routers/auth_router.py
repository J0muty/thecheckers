from fastapi import APIRouter, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from src.settings.settings import templates
from src.base.postgres import create_user, authenticate_user, get_2fa_info
from src.app.utils.session_manager import create_session, delete_session
from src.app.utils.totp import verify_code
from src.app.utils.csrf import get_csrf_token, validate_csrf

auth_router = APIRouter()

def _get_ip(request: Request) -> str:
    xfwd = request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip")
    if xfwd:
        return xfwd.split(",")[0].strip()
    return request.client.host or ""

@auth_router.get("/login", response_class=HTMLResponse, name="login")
async def login_page(request: Request):
    token = await get_csrf_token(request)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "require_2fa": False, "csrf_token": token},
    )

@auth_router.post("/login", response_class=HTMLResponse, name="login_post")
async def process_login(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
):
    if not await validate_csrf(request, csrf_token):
        token = await get_csrf_token(request)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "CSRF validation failed", "require_2fa": False, "csrf_token": token},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        user = await authenticate_user(login, password)
    except Exception:
        token = await get_csrf_token(request)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Внутренняя ошибка при проверке пользователя. Попробуйте позже.", "require_2fa": False, "csrf_token": token},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    if not user:
        token = await get_csrf_token(request)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неправильный логин или пароль.", "require_2fa": False, "csrf_token": token},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    info = await get_2fa_info(user.id)
    if info["enabled"]:
        request.session.clear()
        request.session["pending_2fa_user"] = user.id
        return RedirectResponse(url="/login/2fa", status_code=status.HTTP_302_FOUND)
    request.session["user_id"] = user.id
    token = await create_session(user.id, request.headers.get("User-Agent", ""), _get_ip(request))
    request.session["session_token"] = token
    request.session["flash"] = {"message": "Вы успешно вошли", "type": "success"}
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return response

@auth_router.get("/login/2fa", response_class=HTMLResponse, name="login_2fa")
async def login_2fa_page(request: Request):
    if not request.session.get("pending_2fa_user"):
        return RedirectResponse("/login", status_code=status.HTTP_302_FOUND)
    token = await get_csrf_token(request)
    return templates.TemplateResponse(
        "login.html", {"request": request, "require_2fa": True, "csrf_token": token}
    )

@auth_router.post("/login/2fa", response_class=HTMLResponse, name="login_2fa_post")
async def process_login_2fa(
    request: Request, code: str = Form(...), csrf_token: str = Form(...)
):
    if not await validate_csrf(request, csrf_token):
        token = await get_csrf_token(request)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "CSRF validation failed", "require_2fa": True, "csrf_token": token},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    uid = request.session.get("pending_2fa_user")
    if not uid:
        return RedirectResponse("/login", status_code=status.HTTP_302_FOUND)
    info = await get_2fa_info(int(uid))
    if not info["enabled"] or not verify_code(info["secret"], code):
        token = await get_csrf_token(request)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный код.", "require_2fa": True, "csrf_token": token},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    token = await create_session(int(uid), request.headers.get("User-Agent", ""), _get_ip(request))
    request.session.clear()
    request.session["user_id"] = int(uid)
    request.session["session_token"] = token
    request.session["flash"] = {"message": "Вы успешно вошли", "type": "success"}
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

@auth_router.get("/register", response_class=HTMLResponse, name="register")
async def register_page(request: Request):
    token = await get_csrf_token(request)
    return templates.TemplateResponse(
        "register.html", {"request": request, "csrf_token": token}
    )

@auth_router.post("/register", response_class=HTMLResponse, name="register_post")
async def process_register(
    request: Request,
    login: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(...),
):
    if not await validate_csrf(request, csrf_token):
        token = await get_csrf_token(request)
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "CSRF validation failed", "csrf_token": token},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if password != confirm_password:
        token = await get_csrf_token(request)
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Пароли не совпадают.", "login": login, "email": email, "csrf_token": token},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        user = await create_user(login=login, email=email, password=password)
    except ValueError as ve:
        token = await get_csrf_token(request)
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": str(ve), "login": login, "email": email, "csrf_token": token},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except Exception:
        token = await get_csrf_token(request)
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Внутренняя ошибка при создании пользователя. Попробуйте позже.", "csrf_token": token},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    request.session["user_id"] = user.id
    token = await create_session(user.id, request.headers.get("User-Agent", ""), _get_ip(request))
    request.session["session_token"] = token
    request.session["flash"] = {"message": "Вы успешно зарегистрированы", "type": "success"}
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return response

@auth_router.get("/logout")
async def logout(request: Request):
    token = request.session.get("session_token")
    uid = request.session.get("user_id")
    if token and uid:
        await delete_session(int(uid), token)
    request.session.clear()
    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)
