"""
Flask-RESTX models for Swagger documentation (API Contracts).

These models are used ONLY for API documentation (Swagger UI).
Actual validation is handled by Marshmallow schemas in app/schemas/.

Usage in controllers:
    from app.api.contracts import auth_contract

    models = auth_contract.register_models(api)

    @api.expect(models['login_request'])
    @api.marshal_with(models['token_response'])
    def post(self):
        ...
"""
