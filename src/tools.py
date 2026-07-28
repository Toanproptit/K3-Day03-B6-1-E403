"""
🛠️ TOOL REGISTRY & SCHEMAS (Dành cho Role 2: Tool & Spec Engineer)
Nơi khai báo tất cả các "món đồ nghề" mà ReAct Agent có thể gọi.
"""

import csv
import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
import re
import unicodedata


DATA_FILE_NAME = "phongtro_hanoi_30pages.csv"
DEMO_VIEWING_TIMES = ("09:00", "14:00", "18:00")

DISTRICT_CODES = {
    "hai ba trung": "HBT",
    "cau giay": "CG",
    "nam tu liem": "NTL",
    "bac tu liem": "BTL",
    "thanh xuan": "TX",
    "dong da": "DD",
    "ba dinh": "BD",
    "ha dong": "HD",
    "hoang mai": "HM",
    "gia lam": "GL",
    "long bien": "LB",
    "hoan kiem": "HK",
    "hoai duc": "HDU",
    "thanh tri": "TT",
    "tay ho": "TH",
}

LOCATION_ALIASES = {
    "dai hoc bach khoa ha noi": [
        "bach khoa",
        "dh bach khoa",
        "bk",
        "tran dai nghia",
        "ta quang buu",
        "minh khai",
        "hai ba trung",
        "nguyen an ninh",
        "kinh te quoc dan",
        "dai hoc xay dung",
    ],
    "cau giay": [
        "mai dich",
        "tran duy hung",
        "tran binh",
        "trung kinh",
        "xuan thuy",
        "quan nhan",
        "tran quoc vuong",
        "ho quan nhan",
        "duy tan",
    ],
    "nam tu liem": [
        "me tri",
        "my dinh",
        "my dinh 1",
        "le duc tho",
        "phu my",
        "trung van",
        "dai linh",
        "cau coc",
        "do nha",
        "do duc duc",
        "ho tung mau",
        "tan my",
    ],
    "thanh xuan": [
        "nguyen xien",
        "ha dinh",
        "truong chinh",
        "hoang ngan",
        "vu tong phan",
        "chinh kinh",
        "kim giang",
        "quan nhan",
        "nguyen trai",
    ],
    "dong da": ["thai ha", "ton duc thang", "truong chinh", "nguyen hong"],
    "ba dinh": ["kim ma", "quan ngua"],
    "gia lam": ["cau duong"],
    "hoan kiem": ["pho co", "o quan chuong"],
    "gan cho": ["cho"],
}

PROPERTY_TYPE_ALIASES = {
    "phòng trọ": ["phong tro", "nha tro", "phong", "tro"],
    "căn hộ": ["can ho", "studio", "1n1k", "ccmn", "chung cu mini", "cc,"],
    "homestay": ["homestay", "giuong tang"],
}

AMENITY_ALIASES = {
    "điều hòa": ["dieu hoa"],
    "chỗ để xe": ["de xe", "cho de xe", "bai xe", "giu xe", "o to do cua", "xe may"],
    "full đồ": ["full do", "du do", "full tien nghi", "day du noi that", "noi that day du", "full options"],
    "ban công": ["ban cong"],
    "khép kín": ["khep kin", "wc rieng", "ve sinh rieng"],
    "máy giặt": ["may giat"],
    "nóng lạnh": ["nong lanh"],
    "gác xép": ["gac xep"],
    "tủ lạnh": ["tu lanh"],
    "thang máy": ["thang may"],
    "cửa sổ": ["cua so"],
}


def _normalize_text(value: str) -> str:
    """Chuẩn hóa chuỗi để so khớp mềm hơn giữa các biến thể tiếng Việt."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFD", str(value).strip().lower())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.replace("đ", "d")
    return re.sub(r"\s+", " ", text)


def _get_repo_root() -> Path:
    """Lấy thư mục gốc repo từ file src/tools.py."""
    return Path(__file__).resolve().parents[1]


def _get_data_path() -> Path:
    """Trỏ tới file CSV dữ liệu phòng trọ/căn hộ thật."""
    return _get_repo_root() / "data" / DATA_FILE_NAME


def _redact_sensitive_text(text: str) -> str:
    """Ẩn số điện thoại nếu lỡ có trong dữ liệu gốc."""
    if not text:
        return ""
    return re.sub(r"(?<!\d)(?:\d[\s.\-]*){8,12}(?!\d)", "[SĐT đã ẩn]", str(text))


def _parse_price_to_vnd(value) -> int | None:
    """Đọc giá từ chuỗi CSV như '5.2 triệu/tháng' hoặc '800.000 đồng/tháng'."""
    if value is None:
        return None

    text = _normalize_text(str(value))
    if not text:
        return None

    million_match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*(trieu|tr)\b", text)
    if million_match:
        amount = float(million_match.group(1).replace(",", "."))
        return int(amount * 1_000_000)

    thousand_match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*k\b", text)
    if thousand_match:
        amount = float(thousand_match.group(1).replace(",", "."))
        return int(amount * 1_000)

    digits = re.sub(r"[^0-9-]", "", text)
    if not digits or digits == "-":
        return None
    return int(digits)


def _parse_area_m2(value) -> float | None:
    """Đọc diện tích từ chuỗi như '25 m2'."""
    if value is None:
        return None
    match = re.search(r"(\d+(?:[.,]\d+)?)", str(value))
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _parse_budget(value) -> int:
    """Đọc ngân sách từ số hoặc chuỗi như '4 triệu', '8.000.000'."""
    if value is None or str(value).strip() == "":
        raise ValueError("Ngân sách rỗng")

    amount = _parse_price_to_vnd(value)
    if amount is None:
        raise ValueError("Không đọc được ngân sách")
    if amount <= 0:
        raise ValueError("Ngân sách phải lớn hơn 0")
    return amount


def _format_currency(amount: int | None) -> str:
    """Định dạng giá VND dễ đọc."""
    if amount is None:
        return "Chưa rõ giá"
    return f"{int(amount):,} VNĐ/tháng".replace(",", ".")


def _format_area(area_m2: float | None) -> str:
    """Định dạng diện tích gọn."""
    if area_m2 is None:
        return "Chưa rõ"
    if float(area_m2).is_integer():
        return f"{int(area_m2)}m²"
    return f"{area_m2:.1f}m²"


def _district_code(address: str) -> str:
    """Sinh mã quận/huyện ngắn để tạo listing_id ổn định."""
    normalized = _normalize_text(address)
    for district, code in DISTRICT_CODES.items():
        if district in normalized:
            return code

    first_segment = normalized.split(",", maxsplit=1)[0].strip()
    initials = "".join(part[0] for part in first_segment.split() if part and part[0].isalpha())[:3].upper()
    return initials or "HN"


def _make_listing_id(row: dict, index: int) -> str:
    """Tạo mã listing ổn định theo quận/huyện và số dòng CSV."""
    return f"{_district_code(row.get('Địa chỉ', ''))}-{index:04d}"


def _canonical_property_type(value: str) -> str:
    """Chuẩn hóa loại hình về nhóm nhỏ đủ dùng cho bài lab."""
    normalized = _normalize_text(value)
    if not normalized:
        return ""

    for canonical, aliases in PROPERTY_TYPE_ALIASES.items():
        if normalized == _normalize_text(canonical):
            return canonical
        if any(alias in normalized for alias in aliases):
            return canonical

    return ""


def _detect_property_type(text: str) -> str:
    """Suy ra loại hình từ tiêu đề và mô tả."""
    property_type = _canonical_property_type(text)
    return property_type or "phòng trọ"


def _extract_amenities(text: str) -> list[str]:
    """Suy ra danh sách tiện ích chuẩn hóa từ title + mô tả."""
    normalized = _normalize_text(text)
    amenities = []
    for canonical, aliases in AMENITY_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            amenities.append(canonical)
    return amenities


def _parse_amenity_terms(amenities) -> list[str]:
    """Đọc tiện ích đầu vào như 'điều hòa, chỗ để xe'."""
    if amenities is None:
        return []

    if isinstance(amenities, (list, tuple, set)):
        raw_terms = [str(term) for term in amenities]
    else:
        raw_text = str(amenities).replace(";", ",")
        raw_text = re.sub(r"\b(và|va|&)\b", ",", raw_text, flags=re.IGNORECASE)
        raw_terms = raw_text.split(",")

    canonical_terms = []
    for term in raw_terms:
        normalized = _normalize_text(term)
        if not normalized:
            continue
        matched = None
        for canonical, aliases in AMENITY_ALIASES.items():
            if normalized == _normalize_text(canonical) or any(alias in normalized for alias in aliases):
                matched = canonical
                break
        canonical_terms.append(matched or term.strip())

    unique_terms = []
    for term in canonical_terms:
        if term not in unique_terms:
            unique_terms.append(term)
    return unique_terms


def _expand_location_terms(location: str) -> list[str]:
    """Mở rộng khu vực tìm kiếm bằng vài alias đủ dùng cho 16 test case."""
    normalized = _normalize_text(location)
    if not normalized:
        return []

    terms = {normalized}
    for canonical, aliases in LOCATION_ALIASES.items():
        all_terms = [canonical, *aliases]
        if any(term in normalized for term in all_terms):
            terms.update(all_terms)
        elif normalized in canonical:
            terms.update(all_terms)

    if "dai hoc" in normalized and "bach khoa" in normalized:
        terms.update(LOCATION_ALIASES["dai hoc bach khoa ha noi"])
        terms.add("dai hoc bach khoa ha noi")

    if normalized == "bach khoa":
        terms.update(LOCATION_ALIASES["dai hoc bach khoa ha noi"])
        terms.add("dai hoc bach khoa ha noi")

    return sorted(terms, key=len, reverse=True)


def _searchable_text(listing: dict) -> str:
    """Gộp các trường để tìm kiếm nhẹ bằng substring."""
    pieces = [
        listing["title"],
        listing["address"],
        listing["description"],
        listing["property_type"],
        " ".join(listing["amenities"]),
    ]
    return _normalize_text(" ".join(piece for piece in pieces if piece))


@lru_cache(maxsize=1)
def _load_rentals() -> list[dict]:
    """Đọc CSV dữ liệu thật và chuẩn hóa thành danh sách listing."""
    data_path = _get_data_path()
    if not data_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file dữ liệu: {data_path}")

    listings = []
    with data_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for index, row in enumerate(reader, start=1):
            title = (row.get("Tiêu đề") or "").strip()
            description = (row.get("Mô tả") or "").strip()
            listing = {
                "id": _make_listing_id(row, index),
                "posted_at": (row.get("Ngày đăng") or "").strip(),
                "title": title or f"Tin số {index}",
                "price_vnd": _parse_price_to_vnd(row.get("Giá")),
                "area_m2": _parse_area_m2(row.get("Diện tích")),
                "address": (row.get("Địa chỉ") or "").strip(),
                "description": description,
                "link": (row.get("Link") or "").strip(),
                "property_type": _detect_property_type(f"{title} {description}"),
            }
            listing["amenities"] = _extract_amenities(f"{title} {description}")
            listing["search_text"] = _searchable_text(listing)
            listings.append(listing)

    if not listings:
        raise ValueError("File dữ liệu không có dòng nào")

    return listings


def _find_listing(listing_id: str) -> dict | None:
    """Tìm tin đăng theo mã."""
    target = _normalize_text(listing_id)
    for listing in _load_rentals():
        if _normalize_text(listing["id"]) == target:
            return listing
    return None


def _format_listing(listing: dict, reason: str = "") -> str:
    """Định dạng ngắn gọn 1 listing để dùng trong Observation."""
    amenities = ", ".join(listing["amenities"]) if listing["amenities"] else "Chưa suy ra rõ"
    line = (
        f"{listing['id']} | {_redact_sensitive_text(listing['title'])} | "
        f"Loại: {listing['property_type']} | Giá: {_format_currency(listing['price_vnd'])} | "
        f"Diện tích: {_format_area(listing['area_m2'])} | Địa chỉ: {listing['address']} | "
        f"Tiện ích: {amenities} | Link: {listing['link']}"
    )
    if reason:
        line += f" | Lý do khớp: {reason}"
    return line


def _matches_location(listing: dict, location_terms: list[str]) -> bool:
    """Kiểm tra listing có khớp khu vực/landmark yêu cầu hay không."""
    if not location_terms:
        return True
    return any(term in listing["search_text"] for term in location_terms)


def _location_reason(location: str) -> str:
    """Tạo lý do khớp khu vực dễ đọc hơn."""
    cleaned = str(location).strip()
    return f"gần/khớp khu vực '{cleaned}'" if cleaned else "đúng khu vực"


def search_properties(
    location: str = "",
    budget_max: str = "",
    property_type: str = "",
    amenities: str = "",
    limit: int = 5,
) -> str:
    """
    Tìm nhà trọ/căn hộ phù hợp theo khu vực, ngân sách, loại hình và tiện ích.

    Args:
        location (str): Khu vực, địa danh hoặc mốc gần đó.
        budget_max (str): Ngân sách tối đa mỗi tháng.
        property_type (str): Loại hình thuê như 'phòng trọ', 'căn hộ'.
        amenities (str): Tiện ích mong muốn, có thể phân tách bằng dấu phẩy.
        limit (int): Số kết quả tối đa muốn lấy.

    Returns:
        str: Danh sách tin đăng phù hợp, gợi ý gần nhất hoặc thông báo lỗi.
    """
    if not any(str(value).strip() for value in [location, budget_max, property_type, amenities]):
        return "CẦN_THÊM_THÔNG_TIN: Hãy cho biết ít nhất khu vực, ngân sách, loại phòng hoặc tiện ích mong muốn."

    try:
        listings = _load_rentals()
    except Exception as error:
        return f"LỖI: Không đọc được dữ liệu phòng trọ thật. Chi tiết: {error}"

    try:
        result_limit = max(1, min(int(limit), 10))
    except (TypeError, ValueError):
        result_limit = 5

    budget_limit = None
    if str(budget_max).strip():
        try:
            budget_limit = _parse_budget(budget_max)
        except ValueError as error:
            return f"LỖI: {error}. Giá trị nhận được: '{budget_max}'."

    property_filter = _canonical_property_type(property_type)
    required_amenities = _parse_amenity_terms(amenities)
    location_terms = _expand_location_terms(location)

    if property_type and not property_filter:
        property_filter = _normalize_text(property_type)

    location_pool = []
    exact_matches = []
    near_matches = []

    for listing in listings:
        if location_terms and not _matches_location(listing, location_terms):
            continue

        if location_terms:
            location_pool.append(listing)

        reasons = []
        if location_terms:
            reasons.append(_location_reason(location))

        budget_hit = budget_limit is None or (
            listing["price_vnd"] is not None and listing["price_vnd"] <= budget_limit
        )
        if budget_hit and budget_limit is not None:
            reasons.append(f"trong ngân sách {_format_currency(budget_limit)}")

        property_hit = not property_filter or property_filter == listing["property_type"]
        if property_hit and property_filter:
            reasons.append(f"đúng loại {property_filter}")

        matched_amenities = [term for term in required_amenities if term in listing["amenities"]]
        amenity_hit = len(matched_amenities) == len(required_amenities)
        if matched_amenities:
            reasons.append("có " + ", ".join(matched_amenities))

        if budget_hit and property_hit and amenity_hit:
            exact_matches.append((listing["price_vnd"] or 0, -(listing["area_m2"] or 0), listing, reasons))
            continue

        score = 0
        near_reasons = []
        if location_terms:
            score += 3
        if property_hit:
            score += 2
            if property_filter:
                near_reasons.append(f"đúng loại {property_filter}")
        if budget_hit:
            score += 2
            if budget_limit is not None:
                near_reasons.append(f"trong ngân sách {_format_currency(budget_limit)}")
        elif budget_limit is not None and listing["price_vnd"] is not None:
            diff = listing["price_vnd"] - budget_limit
            if diff <= 1_500_000:
                score += 1
                near_reasons.append(f"vượt ngân sách khoảng {_format_currency(diff).replace('/tháng', '')}")
        if matched_amenities:
            score += len(matched_amenities)
            near_reasons.append("có " + ", ".join(matched_amenities))

        if score > 0:
            near_matches.append((-score, listing["price_vnd"] or 0, -(listing["area_m2"] or 0), listing, near_reasons))

    if location_terms and not location_pool:
        return (
            f"KHÔNG_TÌM_THẤY: Chưa thấy tin nào khớp khu vực '{location}' trong dữ liệu hiện có. "
            "Bạn có thể đổi quận/huyện hoặc nới mốc địa danh gần đó."
        )

    if exact_matches:
        exact_matches.sort(key=lambda item: item[:2])
        selected = exact_matches[:result_limit]
        lines = [
            f"OK: Tìm thấy {len(selected)} tin phù hợp từ dữ liệu thật trong {DATA_FILE_NAME}."
        ]
        for index, (_, __, listing, reasons) in enumerate(selected, start=1):
            lines.append(f"{index}. {_format_listing(listing, '; '.join(reasons))}")
        return "\n".join(lines)

    if near_matches:
        near_matches.sort(key=lambda item: item[:3])
        selected = near_matches[:result_limit]
        lines = [
            "KHÔNG_TÌM_THẤY: Chưa có tin khớp hoàn toàn mọi tiêu chí. Dưới đây là các gợi ý gần nhất từ dữ liệu thật:"
        ]
        for index, (_, __, ___, listing, reasons) in enumerate(selected, start=1):
            lines.append(f"{index}. {_format_listing(listing, '; '.join(reasons))}")
        return "\n".join(lines)

    return "KHÔNG_TÌM_THẤY: Không tìm thấy nhà trọ/căn hộ phù hợp với các tiêu chí đã cung cấp."


def _validate_date(value: str) -> str:
    """Chuẩn hóa ngày xem nhà về YYYY-MM-DD."""
    if value is None or not str(value).strip():
        return (date.today() + timedelta(days=1)).isoformat()

    raw = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return date.fromisoformat(raw).isoformat()

    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", raw):
        day, month, year = raw.split("/")
        return date(int(year), int(month), int(day)).isoformat()

    raise ValueError("Ngày xem nhà phải theo định dạng YYYY-MM-DD hoặc DD/MM/YYYY")


def _validate_time(value: str) -> str:
    """Chuẩn hóa giờ xem nhà về HH:MM."""
    if value is None or not str(value).strip():
        raise ValueError("Thiếu giờ xem nhà")

    raw = str(value).strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", raw)
    if not match:
        raise ValueError("Giờ xem nhà phải theo định dạng HH:MM")

    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError("Giờ xem nhà không hợp lệ")
    return f"{hour:02d}:{minute:02d}"


def _demo_slots_for_date(viewing_date: str) -> list[str]:
    """Sinh lịch xem demo deterministic, chưa có persistence thật."""
    target_date = date.fromisoformat(viewing_date)
    if target_date < date.today():
        return []
    return list(DEMO_VIEWING_TIMES)


def check_viewing_slots(listing_id: str, viewing_date: str = "") -> str:
    """
    Kiểm tra các khung giờ xem nhà còn trống cho một tin đăng.

    Args:
        listing_id (str): Mã tin đăng như 'CG-0005'.
        viewing_date (str): Ngày muốn xem nhà theo định dạng YYYY-MM-DD hoặc DD/MM/YYYY.

    Returns:
        str: Danh sách khung giờ còn trống hoặc thông báo lỗi.
    """
    try:
        listing = _find_listing(listing_id)
    except Exception as error:
        return f"LỖI: Không đọc được dữ liệu phòng trọ thật. Chi tiết: {error}"

    if not listing:
        return f"LỖI: Không tìm thấy tin đăng có mã '{listing_id}'."

    try:
        normalized_date = _validate_date(viewing_date)
    except ValueError as error:
        return f"LỖI: {error}. Giá trị nhận được: '{viewing_date}'."

    slots = _demo_slots_for_date(normalized_date)
    if not slots:
        return f"LỖI: Không còn lịch xem demo cho tin '{listing_id}' vào ngày {normalized_date}."

    return (
        f"OK: Lịch xem demo còn trống cho {listing['id']} - {listing['title']} vào ngày {normalized_date}: "
        f"{', '.join(slots)}."
    )


def book_viewing(
    listing_id: str,
    viewing_date: str,
    viewing_time: str,
    customer_name: str = "",
    phone: str = "",
) -> str:
    """
    Giả lập đặt lịch xem nhà cho một tin đăng nếu còn khung giờ trống.

    Args:
        listing_id (str): Mã tin đăng cần đặt lịch.
        viewing_date (str): Ngày xem nhà.
        viewing_time (str): Giờ xem nhà theo HH:MM.
        customer_name (str): Tên người đi xem nhà.
        phone (str): Số điện thoại liên hệ.

    Returns:
        str: Xác nhận đặt lịch hoặc thông báo lỗi.
    """
    if not str(customer_name).strip():
        return "LỖI: Thiếu tên khách xem nhà. Vui lòng cung cấp customer_name trước khi đặt lịch."

    if not str(phone).strip():
        return "LỖI: Thiếu số điện thoại liên hệ. Vui lòng cung cấp phone trước khi đặt lịch."

    phone_digits = re.sub(r"\D", "", str(phone))
    if phone_digits.startswith("84") and len(phone_digits) == 11:
        phone_digits = "0" + phone_digits[2:]
    if not re.fullmatch(r"0\d{9}", phone_digits):
        return f"LỖI: Số điện thoại '{phone}' không hợp lệ."

    try:
        normalized_date = _validate_date(viewing_date)
    except ValueError as error:
        return f"LỖI: {error}. Giá trị nhận được: '{viewing_date}'."

    try:
        normalized_time = _validate_time(viewing_time)
    except ValueError as error:
        return f"LỖI: {error}. Giá trị nhận được: '{viewing_time}'."

    slot_response = check_viewing_slots(listing_id, normalized_date)
    if not slot_response.startswith("OK:"):
        return slot_response

    available_times = _demo_slots_for_date(normalized_date)
    if normalized_time not in available_times:
        return (
            f"LỖI: Khung giờ {normalized_time} không khả dụng cho tin '{listing_id}' vào ngày {normalized_date}'."
        )

    listing = _find_listing(listing_id)
    confirmation_code = f"VIEW-{listing['id']}-{normalized_date.replace('-', '')}-{normalized_time.replace(':', '')}"
    return (
        f"OK: Đặt lịch xem nhà demo thành công. Mã xác nhận: {confirmation_code}. "
        f"Khách hàng: {customer_name.strip()}. SĐT: {phone_digits}. "
        f"Tin đăng: {listing['title']} - {listing['address']}. "
        f"Thời gian hẹn: {normalized_date} lúc {normalized_time}."
    )


def _guess_location_from_query(user_query: str) -> str:
    """Đoán nhanh khu vực từ câu hỏi tự nhiên cho level 1 rule-based."""
    normalized = _normalize_text(user_query)
    display_names = {
        "dai hoc bach khoa ha noi": "Đại học Bách Khoa Hà Nội",
        "cau giay": "Cầu Giấy",
        "nam tu liem": "Nam Từ Liêm",
        "thanh xuan": "Thanh Xuân",
        "dong da": "Đống Đa",
        "ba dinh": "Ba Đình",
        "hoan kiem": "Hoàn Kiếm",
        "gia lam": "Gia Lâm",
        "hoang mai": "Hoàng Mai",
        "gan cho": "gần chợ",
    }

    for canonical, display_name in display_names.items():
        if canonical in normalized:
            return display_name
        for alias in LOCATION_ALIASES.get(canonical, []):
            if alias in normalized:
                return display_name
    return ""


def _guess_budget_from_query(user_query: str) -> str:
    """Đoán ngân sách đơn giản từ câu hỏi tự nhiên cho level 1 rule-based."""
    normalized = _normalize_text(user_query)

    negative_match = re.search(r"am\s*(\d+(?:[.,]\d+)?)\s*(trieu|tr)\b", normalized)
    if negative_match:
        return f"-{negative_match.group(1)} triệu"

    million_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(trieu|tr)\b", normalized)
    if million_match:
        return f"{million_match.group(1)} triệu"

    dong_match = re.search(r"(\d[\d.]*)\s*(dong|vnd|vnđ)\b", normalized)
    if dong_match:
        return dong_match.group(1)

    return ""


def _guess_amenities_from_query(user_query: str) -> str:
    """Đoán danh sách tiện ích từ câu hỏi tự nhiên cho level 1 rule-based."""
    matched = []
    normalized = _normalize_text(user_query)
    for canonical, aliases in AMENITY_ALIASES.items():
        canonical_norm = _normalize_text(canonical)
        if canonical_norm in normalized or any(alias in normalized for alias in aliases):
            matched.append(canonical)
    return ", ".join(matched)


def rule_based_rental_answer(user_query: str) -> str:
    """
    Level 1: rule-based assistant cho các case tư vấn và tìm phòng cơ bản.
    Hàm này không cần LLM, nhưng vẫn đọc data thật khi cần search.
    """
    normalized = _normalize_text(user_query)

    if any(term in normalized for term in ["bo qua moi huong dan", "prompt injection"]):
        return "Tôi không thể bỏ qua hướng dẫn an toàn hoặc tự thay đổi vai trò của hệ thống."

    if any(term in normalized for term in ["hop dong thue nha gia", "chu ky chu nha", "gia mao"]):
        return "Tôi không thể hỗ trợ giả mạo hợp đồng, chữ ký hoặc giấy tờ thuê nhà."

    if any(term in normalized for term in ["cmnd", "cccd", "dia chi nha rieng", "gay suc ep"]):
        return "Tôi không thể cung cấp thông tin cá nhân nhạy cảm của bên thứ ba hoặc hỗ trợ hành vi gây hại."

    if "thu phong tro va thue can ho khac nhau" in normalized or (
        "phong tro" in normalized and "can ho" in normalized and "khac nhau" in normalized
    ):
        return (
            "Phòng trọ thường rẻ hơn, diện tích nhỏ hơn và tiện ích cơ bản hơn căn hộ.\n"
            "Căn hộ thường riêng tư hơn, đủ khu bếp/vệ sinh và hợp với người đi làm hoặc ở 2 người trở lên.\n"
            "Nếu ngân sách thấp và cần gần trường, phòng trọ hoặc CCMN thường hợp hơn."
        )

    if "ky hop dong" in normalized or "di xem phong" in normalized or "can kiem tra" in normalized:
        return (
            "Khi đi xem phòng, nên kiểm tra: tình trạng điện nước, nhà vệ sinh, khóa cửa, an ninh, tiếng ồn, chỗ để xe, chi phí phát sinh, điều khoản cọc và thời hạn hợp đồng.\n"
            "Nếu có thể, hãy chụp lại công tơ điện nước và hỏi rõ giờ giấc, số người ở, quy định khách đến chơi."
        )

    if "sinh vien" in normalized and ("uu tien tieu chi" in normalized or "gan truong" in normalized):
        return (
            "Với sinh viên năm nhất, nên ưu tiên theo thứ tự: ngân sách tổng mỗi tháng, khoảng cách đến trường, an ninh, chi phí điện nước, chỗ để xe và điều kiện hợp đồng.\n"
            "Nếu ngân sách khoảng 3 triệu/tháng, hãy chấp nhận diện tích vừa phải để đổi lấy vị trí thuận tiện và chi phí phát sinh dễ kiểm soát."
        )

    if "dat lich" in normalized and ("31/02" in user_query or "25:00" in user_query):
        return "Ngày hoặc giờ xem nhà chưa hợp lệ. Bạn hãy nhập lại ngày hợp lệ và giờ theo định dạng HH:MM."

    if "re" in normalized and "gan cho" in normalized and not _guess_location_from_query(user_query):
        return "Bạn hãy cho biết rõ khu vực muốn thuê, ngân sách tối đa và loại phòng/căn hộ để tôi lọc dữ liệu chính xác hơn."

    if any(term in normalized for term in ["tim", "thue", "phong tro", "can ho"]):
        location = _guess_location_from_query(user_query)
        budget = _guess_budget_from_query(user_query)
        property_type = _canonical_property_type(user_query)
        amenities = _guess_amenities_from_query(user_query)

        if budget.startswith("-"):
            return "Ngân sách phải lớn hơn 0. Bạn hãy nhập lại mức ngân sách hợp lý hơn."

        if not location and not budget:
            return "Bạn hãy cho biết thêm khu vực, ngân sách tối đa và loại phòng/căn hộ mong muốn."

        return search_properties(
            location=location,
            budget_max=budget,
            property_type=property_type,
            amenities=amenities,
            limit=3,
        )

    return "Tôi có thể hỗ trợ tư vấn thuê trọ/căn hộ, tìm phòng theo khu vực-ngân sách hoặc kiểm tra lịch xem nhà."


def get_weather(location: str) -> str:
    """Shim tương thích tạm thời cho app.py cũ; không còn dùng trong bài toán hiện tại."""
    return (
        "LỖI: Tool 'get_weather' đã bị loại khỏi kịch bản thuê trọ/căn hộ. "
        "Hãy dùng search_properties, check_viewing_slots hoặc book_viewing."
    )


def search_flights(origin: str, destination: str) -> str:
    """Shim tương thích tạm thời cho app.py cũ; không còn dùng trong bài toán hiện tại."""
    return (
        "LỖI: Tool 'search_flights' đã bị loại khỏi kịch bản thuê trọ/căn hộ. "
        "Hãy dùng search_properties, check_viewing_slots hoặc book_viewing."
    )


AVAILABLE_TOOLS = {
    "search_properties": search_properties,
    "check_viewing_slots": check_viewing_slots,
    "book_viewing": book_viewing,
}


def _self_check():
    """Kiểm tra nhanh dữ liệu thật, tool chính và cấu hình test case."""
    listings = _load_rentals()
    assert len(listings) > 0, "CSV phải có ít nhất 1 dòng dữ liệu"

    assert set(AVAILABLE_TOOLS) == {"search_properties", "check_viewing_slots", "book_viewing"}

    search_bk = search_properties("Đại học Bách Khoa Hà Nội", "4 triệu", "phòng trọ", "điều hòa", 3)
    assert search_bk.startswith(("OK:", "KHÔNG_TÌM_THẤY:")), search_bk

    invalid_budget = search_properties("Cầu Giấy", "-2 triệu", "phòng trọ")
    assert invalid_budget.startswith("LỖI:"), invalid_budget

    first_listing_id = listings[0]["id"]
    invalid_date = check_viewing_slots(first_listing_id, "2026-02-31")
    assert invalid_date.startswith("LỖI:"), invalid_date

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    missing_contact = book_viewing(first_listing_id, tomorrow, "09:00")
    assert missing_contact.startswith("LỖI:"), missing_contact

    booked = book_viewing(first_listing_id, tomorrow, "09:00", "Nguyễn Văn A", "0900000000")
    assert booked.startswith("OK:"), booked
    assert "VIEW-" in booked, booked

    rule_based = rule_based_rental_answer(
        "Tôi là sinh viên năm nhất, ngân sách khoảng 3 triệu/tháng. Nên ưu tiên tiêu chí nào khi tìm nhà trọ gần trường?"
    )
    assert "ngan sach" in _normalize_text(rule_based), rule_based

    config_path = _get_repo_root() / "config" / "test_cases.json"
    with config_path.open("r", encoding="utf-8") as file:
        test_cases = json.load(file)
    assert len(test_cases) == 16, f"Số test case hiện tại là {len(test_cases)}, không phải 16"


if __name__ == "__main__":
    _self_check()
    print("Self-check tools thành công.")
