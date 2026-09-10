# app/models/__init__.py
#
# Domain models for the PaqTcPB product. Empty on purpose: this is the
# skeleton commit, before any RF is scoped into columns. See
# docs/adr/0001-produto-do-zero-em-vez-de-fork.md for why this repo starts
# here instead of continuing the fork of municipal-backend.
#
# As each model gains real fields, import it here (suppressing the unused-
# import lint) so SQLAlchemy registers its table (see base.py's `db` instance).
