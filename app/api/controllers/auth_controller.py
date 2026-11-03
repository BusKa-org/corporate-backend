from typing import Any

from flask import request
from flask_restx import Namespace, Resource

from app.api.contracts import auth_contract
from app.extensions import (
    limite_auth_por_email,
    limite_sensivel_por_email_ou_token,
)
from app.schemas.auth_schema import (
    ForgotPasswordRequestSchema,
    LoginRequestSchema,
    ResetPasswordRequestSchema,
    TokenResponseSchema,
)
from app.services import auth_service

api = Namespace("auth", description="Autenticação e gerenciamento de sessão")

# API contracts (Swagger documentation)
models = auth_contract.register_models(api)

# Validation schemas (Marshmallow)
login_request_schema = LoginRequestSchema()
token_response_schema = TokenResponseSchema()
forgot_password_request_schema = ForgotPasswordRequestSchema()
reset_password_request_schema = ResetPasswordRequestSchema()


@api.route("/login")
class AuthLogin(Resource):
    @api.doc(
        "auth_login",
        responses={
            200: "Login successful - returns JWT token",
            400: "Validation error",
            401: "Invalid credentials",
            429: "Too many login attempts - rate limited",
        },
    )
    @api.expect(models["login_request"])
    @api.response(200, "Success", models["token_response"])
    @limite_auth_por_email
    def post(self) -> tuple[dict[str, Any], int]:
        """
        Authenticate user and get JWT token.

        Use the returned token in the `Authorization` header for authenticated requests:
        `Authorization: Bearer <token>`
        """
        data = request.get_json(silent=True) or {}
        payload = login_request_schema.load(data)

        response = auth_service.login_user(payload)
        return token_response_schema.dump(response), 200


@api.route("/forgot-password")
class AuthForgotPassword(Resource):
    @api.doc(
        "auth_forgot_password",
        responses={
            200: "If request accepted (email sent if user exists)",
            400: "Invalid email format",
        },
    )
    @api.expect(models["forgot_password_request"])
    @limite_auth_por_email
    def post(self) -> tuple[dict[str, Any], int]:
        """Request password recovery. Sends email with reset link if the user exists."""

        data = request.get_json(silent=True) or {}
        payload = forgot_password_request_schema.load(data)

        auth_service.request_password_reset(payload["email"])
        return {
            "message": "Se o e-mail estiver cadastrado, você receberá um link para redefinir a senha."
        }, 200


@api.route("/reset-password")
class AuthResetPassword(Resource):
    @api.doc(
        "auth_reset_password",
        responses={
            200: "Password reset",
            400: "Validation error, or invalid/expired token",
        },
    )
    @api.expect(models["reset_password_request"])
    @limite_sensivel_por_email_ou_token
    def post(self) -> tuple[dict[str, Any], int]:
        """Reset password with the token from the e-mail link (sent by the frontend)."""

        data = request.get_json(silent=True) or {}
        payload = reset_password_request_schema.load(data)

        auth_service.reset_password(payload["token"], payload["new_password"])
        return {"message": "Senha redefinida com sucesso. Faça login com a nova senha."}, 200
