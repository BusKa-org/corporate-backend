from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource

from app.api.contracts import user_contract
from app.extensions import limite_sensivel
from app.schemas.user_schema import (
    ChangePasswordRequestSchema,
    ChangePasswordResponseSchema,
    ExcluirContaRequestSchema,
    FcmTokenRequestSchema,
    FcmTokenResponseSchema,
    MotoristaCreateRequestSchema,
    MotoristaUpdateRequestSchema,
    UpdateProfileRequestSchema,
    UserListResponseSchema,
    UserResponseSchema,
)
from app.services import consentimento_service, conta_service, user_service

api = Namespace("users", description="Gerenciamento de Usuários e Perfil")

# API contracts (Swagger documentation)
models = user_contract.register_models(api)

# Validation schemas (Marshmallow)
user_list_response_schema = UserListResponseSchema()
motorista_create_schema = MotoristaCreateRequestSchema()
motorista_update_schema = MotoristaUpdateRequestSchema()
change_password_schema = ChangePasswordRequestSchema()
user_response_schema = UserResponseSchema()
change_password_response_schema = ChangePasswordResponseSchema()
fcm_token_request_schema = FcmTokenRequestSchema()
fcm_token_response_schema = FcmTokenResponseSchema()
update_profile_schema = UpdateProfileRequestSchema()
excluir_conta_schema = ExcluirContaRequestSchema()


@api.route("")
class UserList(Resource):
    @api.doc("list_users", responses={200: "Success", 403: "Forbidden - not a gestor"})
    @api.response(200, "Success", models["user_list_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """Lists all users in the organization (Manager only)"""
        current_user_id = get_jwt_identity()
        users = user_service.get_all_users(current_user_id)
        return (
            user_list_response_schema.dump(
                {
                    "items": users,
                    "total": len(users),
                }
            ),
            200,
        )


@api.route("/me")
class UserProfile(Resource):
    @api.doc("get_my_profile", responses={200: "Success", 404: "User not found"})
    @api.response(200, "Success", models["user_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """Logged-in user's profile"""
        current_user_id = get_jwt_identity()
        user = user_service.get_user_by_id(current_user_id)
        data = user_response_schema.dump(user)
        data["consentimento_pendente"] = consentimento_service.consentimento_pendente(
            current_user_id
        )
        return data, 200

    @api.doc(
        "update_my_profile",
        responses={200: "Updated", 400: "Validation error", 409: "Conflict"},
    )
    @api.expect(models["update_profile_request"])
    @api.response(200, "Success", models["user_response"])
    @jwt_required()
    def patch(self) -> tuple[dict[str, Any], int]:
        """Updates the logged-in user's profile (nome, telefone, receber_notificacoes, cnh)"""
        current_user_id = get_jwt_identity()
        payload = update_profile_schema.load(request.get_json(silent=True) or {})
        user = user_service.update_profile(current_user_id, payload)
        return user_response_schema.dump(user), 200

    @api.doc(
        "delete_my_account",
        responses={
            200: "Conta excluída",
            401: "Credenciais inválidas",
            403: "Somente passageiros podem excluir a conta",
            409: "Viagem em andamento",
        },
    )
    @jwt_required()
    def delete(self) -> tuple[dict[str, str], int]:
        """Deletes the logged-in passenger's account and personal data. Body: {"email", "senha"}"""
        current_user_id = get_jwt_identity()
        payload = excluir_conta_schema.load(request.get_json(silent=True) or {})
        conta_service.excluir_conta(current_user_id, payload["email"], payload["senha"])
        return {"message": "Conta excluída com sucesso"}, 200


@api.route("/<string:id>")
@api.param("id", "O UUID do usuário")
class UserResource(Resource):
    @api.doc("get_user_by_id", responses={200: "Success", 403: "Forbidden", 404: "User not found"})
    @api.response(200, "Success", models["user_response"])
    @jwt_required()
    def get(self, id: str) -> tuple[dict[str, Any], int]:
        """Gets a user by ID (own profile, or same organization if Manager)"""
        current_user_id = get_jwt_identity()
        user = user_service.get_user_by_id(id, current_user_id)
        return user_response_schema.dump(user), 200


@api.route("/motoristas/<string:motorista_id>")
class MotoristaResource(Resource):
    @api.doc(
        "update_motorista",
        responses={200: "Updated", 400: "Validation error", 403: "Forbidden", 404: "Not found"},
    )
    @api.expect(models["motorista_update_request"])
    @api.response(200, "Success", models["user_response"])
    @jwt_required()
    def patch(self, motorista_id: str) -> tuple[dict[str, Any], int]:
        """Manager edits a driver (data and working hours)"""
        current_user_id = get_jwt_identity()
        payload = motorista_update_schema.load(request.get_json(silent=True) or {})
        motorista = user_service.update_motorista(current_user_id, motorista_id, payload)
        return user_response_schema.dump(motorista), 200

    @api.doc(
        "delete_motorista",
        responses={200: "Deleted", 403: "Forbidden", 404: "Not found", 400: "Has linked trips"},
    )
    @jwt_required()
    def delete(self, motorista_id: str) -> tuple[dict[str, Any], int]:
        """Manager removes a driver"""
        current_user_id = get_jwt_identity()
        user_service.delete_motorista(current_user_id, motorista_id)
        return {"message": "Motorista removido com sucesso"}, 200


@api.route("/motoristas")
class MotoristaCreateResource(Resource):
    @api.doc("list_motoristas", responses={200: "Success", 403: "Forbidden - not a gestor"})
    @api.marshal_with(models["user_list_response"], code=200)
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """Lists drivers in the Manager's organization"""
        current_user_id = get_jwt_identity()
        motoristas = user_service.get_motoristas_by_municipio(current_user_id)
        return (
            user_list_response_schema.dump(
                {
                    "items": motoristas,
                    "total": len(motoristas),
                }
            ),
            200,
        )

    @api.doc(
        "create_motorista",
        responses={
            201: "Motorista created",
            400: "Validation error",
            403: "Forbidden - not a gestor",
            409: "Conflict",
        },
    )
    @api.expect(models["motorista_create_request"])
    @api.response(201, "Motorista created", models["user_response"])
    @jwt_required()
    def post(self) -> tuple[dict[str, Any], int]:
        """Manager creates a new Driver"""
        current_user_id = get_jwt_identity()
        payload = motorista_create_schema.load(request.get_json(silent=True) or {})

        motorista = user_service.create_motorista(current_user_id, payload)
        return user_response_schema.dump(motorista), 201


@api.route("/change-password")
class UserChangePassword(Resource):
    @api.doc(
        "change_user_password",
        responses={
            200: "Password changed successfully",
            400: "Validation error",
            401: "Incorrect current password",
            429: "Too many attempts - rate limited",
        },
    )
    @api.expect(models["change_password_request"])
    @api.response(200, "Password changed successfully", models["change_password_response"])
    @jwt_required()
    @limite_sensivel
    def post(self) -> tuple[dict[str, Any], int]:
        """Changes the logged-in user's password (requires the current password)."""
        current_user_id = get_jwt_identity()
        payload = change_password_schema.load(request.get_json(silent=True) or {})

        user_service.change_password(current_user_id, payload)
        return change_password_response_schema.dump({"message": "Senha alterada com sucesso"}), 200


@api.route("/fcm-token")
class UserFcmToken(Resource):
    @api.doc("update_fcm_token", responses={200: "Token atualizado", 400: "Token não enviado"})
    @api.expect(models["fcm_token_request"])
    @api.response(200, "Token updated successfully")
    @jwt_required()
    def patch(self) -> tuple[dict[str, str], int]:
        """Updates the Firebase (push notifications) token of the user's device"""
        current_user_id = get_jwt_identity()
        data = request.get_json() or {}
        payload = fcm_token_request_schema.load(data)

        user_service.update_fcm_token(current_user_id, payload)
        return (
            fcm_token_response_schema.dump(
                {"message": "Token de notificação atualizado com sucesso"}
            ),
            200,
        )
