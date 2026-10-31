"""Remoção de metadados (EXIF, GPS, XMP, textos) de fotos JPEG, PNG e WEBP.

Lê só a estrutura do arquivo (segmentos/chunks) e copia os pixels como estão, sem
decodificar a imagem. Arquivo com estrutura quebrada vira ValidationError.
"""

import zlib

from app.core.exceptions import ValidationError

IMAGEM_INVALIDA = "Imagem inválida ou corrompida"

# Chunks de PNG que só carregam texto, data ou EXIF.
CHUNKS_PNG_DE_METADADOS = {b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"}

# Bits do byte de flags do chunk VP8X do WEBP.
FLAG_WEBP_EXIF = 0x08
FLAG_WEBP_XMP = 0x04


def remover_metadados(conteudo: bytes, tipo: str) -> bytes:
    if tipo == "image/jpeg":
        return _jpeg_sem_metadados(conteudo)
    if tipo == "image/png":
        return _png_sem_metadados(conteudo)
    if tipo == "image/webp":
        return _webp_sem_metadados(conteudo)
    raise ValidationError(IMAGEM_INVALIDA)


def _manter_segmento_jpeg(marcador: int, corpo: bytes) -> bool:
    # APP0 (JFIF) e APP14 (Adobe, diz como converter as cores) mudam a imagem exibida.
    if marcador == 0xE0 or marcador == 0xEE:
        return True
    # APP2 também guarda o perfil de cor ICC, que muda as cores; o resto do APP2 sai.
    if marcador == 0xE2:
        return corpo.startswith(b"ICC_PROFILE\x00")
    # Demais APPn (APP1 = EXIF/XMP) e comentários (COM).
    if 0xE1 <= marcador <= 0xEF or marcador == 0xFE:
        return False
    return True


def _jpeg_sem_metadados(dados: bytes) -> bytes:
    if not dados.startswith(b"\xff\xd8"):
        raise ValidationError(IMAGEM_INVALIDA)

    saida = bytearray(b"\xff\xd8")
    pos = 2
    while True:
        if pos + 2 > len(dados) or dados[pos] != 0xFF:
            raise ValidationError(IMAGEM_INVALIDA)
        marcador = dados[pos + 1]

        if marcador == 0xFF:
            # Byte de preenchimento antes do marcador.
            pos += 1
            continue
        if marcador == 0xD9:
            # Fim da imagem. O que vem depois (outras imagens, com EXIF próprio) é descartado.
            saida += b"\xff\xd9"
            return bytes(saida)
        if marcador == 0x01 or 0xD0 <= marcador <= 0xD7:
            saida += dados[pos : pos + 2]
            pos += 2
            continue

        if pos + 4 > len(dados):
            raise ValidationError(IMAGEM_INVALIDA)
        tamanho = int.from_bytes(dados[pos + 2 : pos + 4], "big")
        fim = pos + 2 + tamanho
        if tamanho < 2 or fim > len(dados):
            raise ValidationError(IMAGEM_INVALIDA)

        if _manter_segmento_jpeg(marcador, dados[pos + 4 : fim]):
            saida += dados[pos:fim]
        pos = fim

        if marcador == 0xDA:
            # Dados comprimidos da imagem: vão até o próximo marcador. FF 00 e FF D0..D7
            # fazem parte dos dados, não são marcadores.
            inicio = pos
            while True:
                pos = dados.find(b"\xff", pos)
                if pos == -1 or pos + 1 >= len(dados):
                    raise ValidationError(IMAGEM_INVALIDA)
                seguinte = dados[pos + 1]
                if seguinte == 0x00 or 0xD0 <= seguinte <= 0xD7:
                    pos += 2
                    continue
                break
            saida += dados[inicio:pos]


def _png_sem_metadados(dados: bytes) -> bytes:
    assinatura = b"\x89PNG\r\n\x1a\n"
    if not dados.startswith(assinatura):
        raise ValidationError(IMAGEM_INVALIDA)

    saida = bytearray(assinatura)
    pos = len(assinatura)
    while True:
        if pos + 12 > len(dados):
            raise ValidationError(IMAGEM_INVALIDA)
        tamanho = int.from_bytes(dados[pos : pos + 4], "big")
        tipo = dados[pos + 4 : pos + 8]
        fim = pos + 12 + tamanho
        if fim > len(dados):
            raise ValidationError(IMAGEM_INVALIDA)
        crc = int.from_bytes(dados[fim - 4 : fim], "big")
        if zlib.crc32(dados[pos + 4 : fim - 4]) != crc:
            raise ValidationError(IMAGEM_INVALIDA)

        if tipo not in CHUNKS_PNG_DE_METADADOS:
            saida += dados[pos:fim]
        pos = fim

        if tipo == b"IEND":
            return bytes(saida)


def _webp_sem_metadados(dados: bytes) -> bytes:
    if len(dados) < 12 or dados[0:4] != b"RIFF" or dados[8:12] != b"WEBP":
        raise ValidationError(IMAGEM_INVALIDA)
    tamanho_riff = int.from_bytes(dados[4:8], "little")
    fim_riff = 8 + tamanho_riff
    if fim_riff > len(dados):
        raise ValidationError(IMAGEM_INVALIDA)

    chunks = bytearray()
    pos = 12
    while pos < fim_riff:
        if pos + 8 > fim_riff:
            raise ValidationError(IMAGEM_INVALIDA)
        tipo = dados[pos : pos + 4]
        tamanho = int.from_bytes(dados[pos + 4 : pos + 8], "little")
        # Chunk de tamanho ímpar leva um byte de preenchimento.
        fim = pos + 8 + tamanho + (tamanho % 2)
        if fim > fim_riff:
            raise ValidationError(IMAGEM_INVALIDA)

        if tipo == b"VP8X":
            if tamanho < 1:
                raise ValidationError(IMAGEM_INVALIDA)
            chunk = bytearray(dados[pos:fim])
            chunk[8] = chunk[8] & ~(FLAG_WEBP_EXIF | FLAG_WEBP_XMP)
            chunks += chunk
        elif tipo != b"EXIF" and tipo != b"XMP ":
            chunks += dados[pos:fim]
        pos = fim

    novo_tamanho = 4 + len(chunks)
    return b"RIFF" + novo_tamanho.to_bytes(4, "little") + b"WEBP" + bytes(chunks)
