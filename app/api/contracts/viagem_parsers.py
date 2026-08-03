# viagem_parsers.py

from flask_restx import reqparse

viagem_list_parser = reqparse.RequestParser()
viagem_list_parser.add_argument(
    "data_inicio",
    type=str,
    required=False,
    help="Data inicial (YYYY-MM-DD)",
)

viagem_list_parser.add_argument(
    "data_fim",
    type=str,
    required=False,
    help="Data final (YYYY-MM-DD)",
)

viagem_list_parser.add_argument(
    "status",
    type=str,
    required=False,
    help="Status da viagem",
)

viagem_list_parser.add_argument(
    "motorista_id",
    type=str,
    required=False,
    help="UUID do motorista",
)

viagem_list_parser.add_argument(
    "rota_id",
    type=str,
    required=False,
    help="UUID da rota",
)

parsers = {
    "viagem_list": viagem_list_parser,
}
