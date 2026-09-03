'''
home_library_v2/services/recognition.py

OCR 기능을 삽입하는 기능을 넣은 파일
→ main.py에 넣지 않고 별도 파일로 빼서 관심사 분리
→ main.py : API 요청을 어떻게 처리할지에만 집중
→ recognition.py : OCR을 어떻게 돌릴지 집중
                   나중에 OCR 방식을 바꾸더라도(다른 OCR 엔진으로 교체) 이 파일만 수정하면 된다

`uv add pytesseract`
라이브러리 설치 → OCR을 인식해주는 라이브러리

Version 4 - ISBN 체크섬 검증 추가
'''

import json
import os
import re
import urllib.parse
import urllib.request
from dotenv import load_dotenv

def normalize_isbn(value: str) -> str | None:
    """
    v4에서 새로 추가한 함수
    "숫자처럼 생긴 것"과 "진짜 유효한 ISBN"은 다르다 → 각각의 공식 체크섬 규칙으로 진위 검증
    ISBN-10 / ISBN-13
    """
    digits = re.sub(r"[^0-9Xx]", "", value) # 하이픈 제거

    if len(digits) == 10:
        # 각 자리 숫자에 10,9,...,1을 곱해서 다 더한 값이 11의 배수여야 유효
        # upper() : 대문자로
        total = sum((10 - i) * (10 if c.upper() == "X" else int(c)) for i, c in enumerate(digits))
        return digits.upper() if total % 11 == 0 else None

    if len(digits) == 13:
        # 홀수 번째 자리는 1을 곱하고 짝수 번째 자리는 3을 곱해서 다 더한 뒤 마지막 검증 숫자와 비교
        total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(digits[:12]))
        return digits if (10 - total % 10) % 10 == int(digits[-1]) else None

    return None     # 10자리도, 13자리도 아니면 애초에 ISBN이 아니므로, None 반환

def extract_isbn(image_path) -> str | None:
    """
    표지 사진에서 ISBN처럼 생긴 문자열을 뽑아내는 함수

    매개변수
        - image_path : 이미지 경로

    반환값
        - isbn 문자열 또는 못 찾으면 None
    """
    try:
        # 함수 안에서 import 하는 이유
        #   - Tesseract가 없는 pc에서도 서버가 죽지 않고 실행되게 하기 위해
        #   - OCR을 안 쓰는 다른 기능들은 영향을 받지 않고 원활하게 진행하기 위해
        import pytesseract
        from PIL import Image, ImageEnhance, ImageOps
    except ImportError:
        return None

    # ── PATH에 Tesseract가 등록 안 됐을 때를 대비해 경로를 직접 지정 ──
    import os
    default_path = r"C:/Program Files/Tesseract-OCR/tesseract.exe"
    if os.path.exists(default_path):
        pytesseract.pytesseract.tesseract_cmd = default_path

    with Image.open(image_path) as source:
        # ImageOps.grayscale(source) : 컬러 사진을 흑백(grayscale)로 변환
        #   - OCR은 색상 정보가 필요없고, 흑백으로 바꾸면 글자와 배경의 명암 대비가 또렷해져서 인식률이 올라간다
        image = ImageOps.grayscale(source)

        # ImageEnhance.Contrast(image).enhance(2) : 명암 대비(contrast)를 2배로 강화
        #   - 책 표지는 화려한 경우가 많아서 대비를 높이면 글자가 배경에서 더 잘 분리된다
        image = ImageEnhance.Contrast(image).enhance(2)

        try:
            # ── 추가된 부분: Tesseract "엔진"이 PC에 설치 안 된 경우도 함께 방어 ──
            ## config='--psm 11' : PSM(페이지 분석 모드) 11번
            ##                     → 정해진 문단 구조 없이 흩어진 텍스트를 최대한 다 찾아라
            ## pytesseract.image_to_string(...) : 이미지를 Tesseract 엔진에 넘겨서 이 안에 있는 글자를 다 텍스트로 뽑아줘
            text = pytesseract.image_to_string(image, config="--psm 11")
            print("=== OCR 원본 결과 ===")   # ← 임시 디버깅용
            print(repr(text))                  # ← 임시 디버깅용
        except pytesseract.TesseractNotFoundError:
            return None

	# ── v3 대비 추가된 부분 ──
    ## 정규식으로 ISBN처럼 생긴 부분만 후보로 골라내기
    ## re.findall(...) : 안의 패턴에 맞는 문자열 전체를 찾아서 리스트로 돌려준다
    for candidate in re.findall(r"(?:97[89][\s-]?)?[0-9][0-9Xx\s-]{8,16}", text):
        # := (바다코끼리 연산자, walrus operator) → 대입과 조건 확인을 한 줄에서 동시에 처리
        #       - normalize_isbn(candidate) 호출한 결과를 isbn에 담고,
        #       - 조건이 참이면 isbn을 반환
        if isbn := normalize_isbn(candidate):
            return isbn
    return None

load_dotenv()
NLK_SEARCH_KEY = os.environ.get('BOOK_API_KEY')
NLK_SEARCH_URL = 'https://www.nl.go.kr/NL/search/openApi/search.do'

def clean_title(raw_title: str | None) -> str | None:
    """순수 제목 추출"""
    if not raw_title:
        return None
    return raw_title.split(' : ')[0].strip()

def clean_author(raw_author: str | None) -> str | None:
    if not raw_author:
        return None
    cleaned = re.sub(r'[가-힣]{2,4}\s*:\s*', '', raw_author)
    return cleaned.strip()

def clean_publisher(raw_pub: str | None) -> str | None:
    if not raw_pub:
        return None
    parts = [p.strip() for p in raw_pub.split(':') if p.strip()]
    return parts[-1] if parts else None

def lookup_metadata(isbn: str) -> dict | None:
    """
    책에 관한 메타데이터를 가지고 isbn, 책 제목, 저자, 출판사 반환
    """
    if not NLK_SEARCH_KEY:
        return None

    params = {
        'key': NLK_SEARCH_KEY,
        'detailSearch': 'true',
        'isbnOp': 'isbn',
        'isbnCode': isbn,
        'apiType': 'json',
    }
    url = f'{NLK_SEARCH_URL}?{urllib.parse.urlencode(params)}'

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.load(response)
    except (OSError, ValueError):
        return None

    results = payload.get('result') or []
    if not results:
        return None

    item = results[0]

    title = clean_title(item.get('titleInfo'))
    if not title:
        return None

    return {
        'isbn': item.get('isbn', isbn),
        'title': title,
        'author': clean_author(item.get('authorInfo')),
        'publisher': clean_publisher(item.get('pubInfo')),
    }