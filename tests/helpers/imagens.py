"""Imagens mínimas, montadas byte a byte, para testar a remoção de metadados."""

import struct
import zlib


def segmento_jpeg(marcador: int, corpo: bytes) -> bytes:
    return bytes([0xFF, marcador]) + struct.pack(">H", len(corpo) + 2) + corpo


# Dados comprimidos com FF 00 (byte FF escapado) e FF D0 (restart), que não são marcadores.
DADOS_DA_IMAGEM_JPEG = b"\x12\x34\xff\x00\x56\xff\xd0\x78"
APP0_JFIF = segmento_jpeg(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
APP1_EXIF = segmento_jpeg(0xE1, b"Exif\x00\x00GPS-LAT-LONG")
TABELA_JPEG = segmento_jpeg(0xDB, b"\x00" + b"\x01" * 64)
INICIO_DA_IMAGEM_JPEG = segmento_jpeg(0xDA, b"\x01\x01\x00\x00\x3f\x00")


def quadro_jpeg(largura: int, altura: int) -> bytes:
    # SOF0: precisão, altura, largura, 1 componente.
    return segmento_jpeg(0xC0, b"\x08" + struct.pack(">HH", altura, largura) + b"\x01\x01\x11\x00")


def jpeg(com_exif: bool = False, largura: int = 1, altura: int = 1) -> bytes:
    conteudo = b"\xff\xd8" + APP0_JFIF
    if com_exif:
        conteudo += APP1_EXIF
    conteudo += (
        TABELA_JPEG
        + quadro_jpeg(largura, altura)
        + INICIO_DA_IMAGEM_JPEG
        + DADOS_DA_IMAGEM_JPEG
        + b"\xff\xd9"
    )
    return conteudo


def chunk_png(tipo: bytes, dados: bytes) -> bytes:
    crc = zlib.crc32(tipo + dados)
    return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", crc)


def ihdr(largura: int, altura: int) -> bytes:
    return chunk_png(b"IHDR", struct.pack(">IIBBBBB", largura, altura, 8, 0, 0, 0, 0))


IDAT = chunk_png(b"IDAT", zlib.compress(b"\x00\x00"))
IEND = chunk_png(b"IEND", b"")
EXIF_PNG = chunk_png(b"eXIf", b"MM\x00*GPS-LAT-LONG")
TEXTO_PNG = chunk_png(b"tEXt", b"Author\x00Fulano")


def png(com_metadados: bool = False, largura: int = 1, altura: int = 1) -> bytes:
    conteudo = b"\x89PNG\r\n\x1a\n" + ihdr(largura, altura)
    if com_metadados:
        conteudo += EXIF_PNG + TEXTO_PNG
    return conteudo + IDAT + IEND


def chunk_webp(tipo: bytes, dados: bytes) -> bytes:
    preenchimento = b"\x00" if len(dados) % 2 else b""
    return tipo + struct.pack("<I", len(dados)) + dados + preenchimento


# Flags 0x0C: EXIF e XMP presentes. Os outros 9 bytes são reservado e dimensões.
VP8X_COM_METADADOS = chunk_webp(b"VP8X", b"\x0c" + b"\x00" * 9)
VP8X_SEM_METADADOS = chunk_webp(b"VP8X", b"\x00" + b"\x00" * 9)
VP8L = chunk_webp(b"VP8L", b"\x2f\x00\x00\x00\x00")
EXIF_WEBP = chunk_webp(b"EXIF", b"MM\x00*GPS")
XMP_WEBP = chunk_webp(b"XMP ", b"<x:xmpmeta/>")


def webp(chunks: bytes) -> bytes:
    return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WEBP" + chunks


def vp8x(largura: int, altura: int) -> bytes:
    tamanhos = (largura - 1).to_bytes(3, "little") + (altura - 1).to_bytes(3, "little")
    return chunk_webp(b"VP8X", b"\x00\x00\x00\x00" + tamanhos)


def vp8(largura: int, altura: int) -> bytes:
    return chunk_webp(b"VP8 ", b"\x00\x00\x00\x9d\x01\x2a" + struct.pack("<HH", largura, altura))


def vp8l(largura: int, altura: int) -> bytes:
    bits = (largura - 1) | ((altura - 1) << 14)
    return chunk_webp(b"VP8L", b"\x2f" + struct.pack("<I", bits))
