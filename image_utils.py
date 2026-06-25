"""
업로드된 병원 사진을 Supabase Storage에 올리기 전, 적절한 크기/용량으로
가공하는 유틸리티입니다.

- 가로 최대 1280px로 리사이즈 (그 이하면 원본 비율 유지)
- JPEG로 통일, quality=85로 압축 (용량 절감 + 로딩 속도 개선)
- RGBA/팔레트(P) 모드는 JPEG 저장을 위해 RGB로 변환
"""
import io
from PIL import Image

MAX_WIDTH = 1280
JPEG_QUALITY = 85


def process_uploaded_image(uploaded_file) -> tuple[bytes, str]:
    """
    Streamlit의 UploadedFile 객체를 받아 (이미지 바이트, content-type)을 반환합니다.

    Args:
        uploaded_file: st.file_uploader()의 반환값 (단일 파일)

    Returns:
        (image_bytes, "image/jpeg")
    """
    image = Image.open(uploaded_file)

    # JPEG는 알파채널을 지원하지 않으므로 RGB로 변환
    if image.mode in ("RGBA", "P", "LA"):
        image = image.convert("RGB")

    if image.width > MAX_WIDTH:
        ratio = MAX_WIDTH / float(image.width)
        new_size = (MAX_WIDTH, int(image.height * ratio))
        image = image.resize(new_size, Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buffer.getvalue(), "image/jpeg"
