# instituicao_parsers.py

from flask_restx import reqparse

instituicao_list_parser = reqparse.RequestParser()
instituicao_list_parser.add_argument(
    "search",
    type=str,
    required=False,
    help="Pesquisa por nome, sigla e/ou UF",
)

instituicao_list_parser.add_argument(
    "limit",
    type=int,
    required=False,
    default=10,
    help="Limite de resultados",
)

parsers = {
    "instituicao_list": instituicao_list_parser,
}
