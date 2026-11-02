"""Strip metadata (EXIF, GPS, XMP, text) from JPEG, PNG and WEBP photos.

Reads only the file structure (segments/chunks) and copies the pixels as is,
without decoding the image. A file with a broken structure raises ValidationError.
"""

import zlib

from app.core.exceptions import ValidationError

IMAGEM_INVALIDA = "Imagem inválida ou corrompida"

# PNG chunks that only carry text, dates or EXIF.
CHUNKS_PNG_DE_METADADOS = {b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"}

# Bits of the flags byte of the WEBP VP8X chunk.
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
    # APP0 (JFIF) and APP14 (Adobe, says how to convert colors) change the displayed image.
    if marcador == 0xE0 or marcador == 0xEE:
        return True
    # APP2 also holds the ICC color profile, which changes colors; the rest of APP2 goes.
    if marcador == 0xE2:
        return corpo.startswith(b"ICC_PROFILE\x00")
    # Other APPn (APP1 = EXIF/XMP) and comments (COM).
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
            # Fill byte before the marker.
            pos += 1
            continue
        if marcador == 0xD9:
            # End of image. Whatever comes after (other images, with their own EXIF) is dropped.
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
            # Compressed image data: runs until the next marker. FF 00 and FF D0..D7
            # are part of the data, not markers.
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
        # An odd-sized chunk carries a padding byte.
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


def dimensoes(conteudo: bytes, tipo: str) -> tuple[int, int]:
    """Width and height read from the header, without decoding the image."""
    if tipo == "image/jpeg":
        largura, altura = _dimensoes_jpeg(conteudo)
    elif tipo == "image/png":
        largura, altura = _dimensoes_png(conteudo)
    elif tipo == "image/webp":
        largura, altura = _dimensoes_webp(conteudo)
    else:
        raise ValidationError(IMAGEM_INVALIDA)
    if largura == 0 or altura == 0:
        raise ValidationError(IMAGEM_INVALIDA)
    return largura, altura


def _dimensoes_png(dados: bytes) -> tuple[int, int]:
    # IHDR is always the first chunk: 8 for the signature, 4 for length, 4 for type.
    if len(dados) < 24 or dados[12:16] != b"IHDR":
        raise ValidationError(IMAGEM_INVALIDA)
    largura = int.from_bytes(dados[16:20], "big")
    altura = int.from_bytes(dados[20:24], "big")
    return largura, altura


def _dimensoes_jpeg(dados: bytes) -> tuple[int, int]:
    pos = 2
    while True:
        if pos + 4 > len(dados) or dados[pos] != 0xFF:
            raise ValidationError(IMAGEM_INVALIDA)
        marcador = dados[pos + 1]
        if marcador == 0xFF:
            pos += 1
            continue
        if marcador == 0xD9 or marcador == 0xDA:
            # Reached the image data without passing the frame header (SOFn).
            raise ValidationError(IMAGEM_INVALIDA)
        if marcador == 0x01 or 0xD0 <= marcador <= 0xD7:
            pos += 2
            continue

        tamanho = int.from_bytes(dados[pos + 2 : pos + 4], "big")
        # SOF0..SOF15. C4 (DHT), C8 (JPG) and CC (DAC) are in the range but are not frames.
        e_quadro = 0xC0 <= marcador <= 0xCF and marcador not in (0xC4, 0xC8, 0xCC)
        if e_quadro:
            # Body: precision (1 byte), height (2), width (2).
            if tamanho < 7 or pos + 9 > len(dados):
                raise ValidationError(IMAGEM_INVALIDA)
            altura = int.from_bytes(dados[pos + 5 : pos + 7], "big")
            largura = int.from_bytes(dados[pos + 7 : pos + 9], "big")
            return largura, altura
        if tamanho < 2:
            raise ValidationError(IMAGEM_INVALIDA)
        pos = pos + 2 + tamanho


def _dimensoes_webp(dados: bytes) -> tuple[int, int]:
    pos = 12
    while pos + 8 <= len(dados):
        tipo = dados[pos : pos + 4]
        tamanho = int.from_bytes(dados[pos + 4 : pos + 8], "little")
        corpo = dados[pos + 8 : pos + 8 + tamanho]
        if len(corpo) < tamanho:
            raise ValidationError(IMAGEM_INVALIDA)

        if tipo == b"VP8X":
            # Flags (1), reserved (3), width - 1 (3), height - 1 (3).
            if tamanho < 10:
                raise ValidationError(IMAGEM_INVALIDA)
            largura = int.from_bytes(corpo[4:7], "little") + 1
            altura = int.from_bytes(corpo[7:10], "little") + 1
            return largura, altura
        if tipo == b"VP8 ":
            # Frame tag (3), start code 9D 01 2A, width and height with 14 bits each.
            if tamanho < 10 or corpo[3:6] != b"\x9d\x01\x2a":
                raise ValidationError(IMAGEM_INVALIDA)
            largura = int.from_bytes(corpo[6:8], "little") & 0x3FFF
            altura = int.from_bytes(corpo[8:10], "little") & 0x3FFF
            return largura, altura
        if tipo == b"VP8L":
            # Signature 0x2F, then width - 1 and height - 1 with 14 bits each.
            if tamanho < 5 or corpo[0] != 0x2F:
                raise ValidationError(IMAGEM_INVALIDA)
            bits = int.from_bytes(corpo[1:5], "little")
            largura = (bits & 0x3FFF) + 1
            altura = ((bits >> 14) & 0x3FFF) + 1
            return largura, altura

        pos = pos + 8 + tamanho + (tamanho % 2)
    raise ValidationError(IMAGEM_INVALIDA)
