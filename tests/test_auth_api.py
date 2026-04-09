from __future__ import annotations

import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi import HTTPException, Response
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from autotask_api.api.auth import login as login_endpoint
from autotask_api.api.auth import logout as logout_endpoint
from autotask_api.api.auth import me as me_endpoint
from autotask_api.database import Base
from autotask_api.schemas import LoginRequest
from autotask_api.services.auth import ensure_default_platform_user, require_authenticated_user


def create_test_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def attach_schema(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS jcgkzx_autotask")
        cursor.close()

    return engine


def build_request(cookie_name: str, cookie_value: str) -> Request:
    cookie_header = f"{cookie_name}={cookie_value}".encode("utf-8")
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"cookie", cookie_header)],
        }
    )


class AuthApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_test_engine()
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, future=True)
        with self.session_factory() as db:
            ensure_default_platform_user(db)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_default_admin_can_login_and_access_me(self) -> None:
        response = Response()
        with self.session_factory() as db:
            user = login_endpoint(
                LoginRequest(username="admin", password="qqq"),
                response=response,
                db=db,
            )

        self.assertEqual(user.username, "admin")
        self.assertEqual(user.display_name, "系统管理员")
        cookie_header = response.headers.get("set-cookie", "")
        self.assertIn("autotask_session=", cookie_header)
        token = cookie_header.split("autotask_session=", 1)[1].split(";", 1)[0]

        request = build_request("autotask_session", token)
        with self.session_factory() as db:
            current_user = require_authenticated_user(request=request, db=db)
            me_response = me_endpoint(current_user)

        self.assertEqual(current_user.username, "admin")
        self.assertEqual(me_response.username, "admin")

    def test_login_rejects_wrong_password(self) -> None:
        response = Response()
        with self.session_factory() as db:
            with self.assertRaises(HTTPException) as ctx:
                login_endpoint(
                    LoginRequest(username="admin", password="wrong-password"),
                    response=response,
                    db=db,
                )
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "用户名或密码错误。")

    def test_logout_clears_cookie_and_invalidates_request(self) -> None:
        response = Response()
        with self.session_factory() as db:
            login_endpoint(
                LoginRequest(username="admin", password="qqq"),
                response=response,
                db=db,
            )

        cookie_header = response.headers.get("set-cookie", "")
        token = cookie_header.split("autotask_session=", 1)[1].split(";", 1)[0]
        request = build_request("autotask_session", token)

        logout_response = Response()
        result = logout_endpoint(logout_response)
        self.assertEqual(result, {"status": "ok"})
        self.assertIn("Max-Age=0", logout_response.headers.get("set-cookie", ""))

        with self.session_factory() as db:
            logged_in_user = require_authenticated_user(request=request, db=db)
            self.assertEqual(logged_in_user.username, "admin")

            empty_request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
            with self.assertRaises(HTTPException) as ctx:
                require_authenticated_user(request=empty_request, db=db)

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "未登录或登录已失效，请重新登录。")
