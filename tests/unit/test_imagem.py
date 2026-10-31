import pytest

from app.core.exceptions import ValidationError
from app.utils.imagem import dimensoes, remover_metadados
from tests.helpers import imagens


def test_jpeg_perde_o_exif_e_mantem_o_resto():
    resultado = remover_metadados(imagens.jpeg(com_exif=True), "image/jpeg")

    assert b"Exif" not in resultado
    assert b"GPS" not in resultado
    assert resultado == imagens.jpeg(com_exif=False)


def test_jpeg_sem_metadados_fica_igual():
    original = imagens.jpeg()

    assert remover_metadados(original, "image/jpeg") == original


def test_jpeg_descarta_o_que_vem_depois_do_fim_da_imagem():
    # Celulares anexam uma segunda imagem, com EXIF próprio, depois do FF D9.
    original = imagens.jpeg() + imagens.jpeg(com_exif=True)

    assert remover_metadados(original, "image/jpeg") == imagens.jpeg()


def test_jpeg_mantem_o_perfil_de_cor_icc():
    icc = imagens.segmento_jpeg(0xE2, b"ICC_PROFILE\x00\x01\x01perfil")
    original = imagens.jpeg()
    com_icc = original[:2] + icc + original[2:]

    assert remover_metadados(com_icc, "image/jpeg") == com_icc


@pytest.mark.parametrize(
    "quebrado",
    [
        b"\xff\xd8",
        b"\xff\xd8\xff\xe1\x00\xff",
        imagens.jpeg()[:-2],
        b"\xff\xd8\x00\x00",
    ],
)
def test_jpeg_quebrado_e_recusado(quebrado):
    with pytest.raises(ValidationError):
        remover_metadados(quebrado, "image/jpeg")


def test_png_perde_exif_e_texto_e_mantem_o_resto():
    resultado = remover_metadados(imagens.png(com_metadados=True), "image/png")

    assert b"eXIf" not in resultado
    assert b"tEXt" not in resultado
    assert resultado == imagens.png()


def test_png_com_crc_errado_e_recusado():
    original = bytearray(imagens.png())
    original[-1] ^= 0xFF

    with pytest.raises(ValidationError):
        remover_metadados(bytes(original), "image/png")


def test_png_sem_iend_e_recusado():
    with pytest.raises(ValidationError):
        remover_metadados(imagens.png()[:-12], "image/png")


def test_webp_perde_exif_e_xmp_e_as_flags():
    original = imagens.webp(
        imagens.VP8X_COM_METADADOS + imagens.VP8L + imagens.EXIF_WEBP + imagens.XMP_WEBP
    )

    resultado = remover_metadados(original, "image/webp")

    assert resultado == imagens.webp(imagens.VP8X_SEM_METADADOS + imagens.VP8L)


def test_webp_com_tamanho_errado_e_recusado():
    original = imagens.webp(imagens.VP8L)
    quebrado = original[:4] + b"\xff\x00\x00\x00" + original[8:]

    with pytest.raises(ValidationError):
        remover_metadados(quebrado, "image/webp")


@pytest.mark.parametrize(
    "conteudo, tipo",
    [
        (imagens.png(largura=4000, altura=3000), "image/png"),
        (imagens.jpeg(com_exif=True, largura=4000, altura=3000), "image/jpeg"),
        (imagens.webp(imagens.vp8x(4000, 3000) + imagens.VP8L), "image/webp"),
        (imagens.webp(imagens.vp8(4000, 3000)), "image/webp"),
        (imagens.webp(imagens.vp8l(4000, 3000)), "image/webp"),
    ],
)
def test_dimensoes_lidas_do_cabecalho(conteudo, tipo):
    assert dimensoes(conteudo, tipo) == (4000, 3000)


def test_dimensoes_acima_do_limite_sao_lidas_inteiras():
    # 14 bits é o máximo do VP8L; o serviço compara com o limite de pixels.
    assert dimensoes(imagens.webp(imagens.vp8l(16384, 16384)), "image/webp") == (16384, 16384)
    assert dimensoes(imagens.png(largura=100_000, altura=100_000), "image/png") == (
        100_000,
        100_000,
    )


@pytest.mark.parametrize(
    "conteudo, tipo",
    [
        (imagens.png(largura=0, altura=10), "image/png"),
        (imagens.jpeg(largura=10, altura=0), "image/jpeg"),
        (imagens.webp(imagens.vp8(0, 10)), "image/webp"),
    ],
)
def test_dimensao_zero_e_recusada(conteudo, tipo):
    with pytest.raises(ValidationError):
        dimensoes(conteudo, tipo)


@pytest.mark.parametrize(
    "conteudo, tipo",
    [
        (imagens.png()[:20], "image/png"),
        (imagens.jpeg()[:30], "image/jpeg"),
        (imagens.webp(imagens.vp8l(10, 10))[:22], "image/webp"),
        (imagens.webp(imagens.vp8(10, 10))[:26], "image/webp"),
        # Sem SOFn antes do início da imagem, e WEBP sem chunk de imagem.
        (b"\xff\xd8" + imagens.APP0_JFIF + imagens.INICIO_DA_IMAGEM_JPEG, "image/jpeg"),
        (imagens.webp(imagens.EXIF_WEBP), "image/webp"),
        # IHDR fora do primeiro lugar.
        (b"\x89PNG\r\n\x1a\n" + imagens.TEXTO_PNG + imagens.ihdr(1, 1), "image/png"),
    ],
)
def test_cabecalho_cortado_ou_ausente_e_recusado(conteudo, tipo):
    with pytest.raises(ValidationError):
        dimensoes(conteudo, tipo)
