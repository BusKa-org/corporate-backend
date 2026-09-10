# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Changed
- Rebuilt as a from-scratch skeleton instead of a fork of `municipal-backend`.
  See `docs/adr/0001-produto-do-zero-em-vez-de-fork.md`. Pipeline (Flask,
  SQLAlchemy + PostGIS, `uv`, pytest/ruff/black/mypy, pre-commit, CI, Docker)
  carried over as-is; all forked domain code (`Aluno`, `Instituicao`,
  `Organizacao` multi-tenancy, route/trip controllers and services) removed.

### Added
- App factory with config, error handling, security headers, `/health` and
  `/ready`, no domain namespaces registered yet.
- Empty domain packages (`models`, `schemas`, `services`, `api`, `tasks`)
  with one stub file per future model, each documenting what lands there.

### To do
See `TODO.md` for the full plan list.
