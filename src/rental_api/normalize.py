"""
🧹 CHUẨN HOÁ DỮ LIỆU CRAWL (databds.csv -> bản ghi listing chuẩn)

File CSV crawl từ phongtro123.com chỉ có 7 cột toàn chuỗi văn bản:
    Ngày đăng, Tiêu đề, Giá, Diện tích, Địa chỉ, Mô tả, Link

Module này bóc tách chúng thành bản ghi có kiểu dữ liệu rõ ràng để API dùng được:
giá thành số nguyên VNĐ, diện tích thành số, quận tách khỏi địa chỉ, tiện ích rút
từ tiêu đề + mô tả, và ID lấy từ slug trong đường dẫn.
"""

import csv
import os
import re
import unicodedata
from datetime import datetime

# Đường dẫn file CSV nằm ở thư mục gốc dự án
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CSV_PATH = os.path.join(BASE_DIR, "databds.csv")

# 🛡️ Ẩn số điện thoại thật của chủ nhà trước khi dữ liệu đi vào prompt/log
PHONE_RE = re.compile(r"(?<!\d)(0\d{9,10})(?!\d)")
PHONE_MASK = "[đã ẩn SĐT]"

# Bóc ID từ slug: .../ccmn-full-do-...-pr710370.html -> pr710370
ID_RE = re.compile(r"-(pr\d+)\.html")

# "Thứ 2, 18:16 27/07/2026" -> bỏ phần thứ, chỉ lấy giờ và ngày
POSTED_RE = re.compile(r"(\d{1,2}):(\d{2})\s+(\d{1,2})/(\d{1,2})/(\d{4})")

AREA_RE = re.compile(r"^([\d.,]+)\s*m2$", re.IGNORECASE)

# Từ điển tiện ích: khoá là dạng đã bỏ dấu để so khớp bất kể người đăng gõ có dấu hay không
AMENITY_VOCAB = {
    "khep kin": "khép kín",
    "full do": "full đồ",
    "day du noi that": "full đồ",
    "ban cong": "ban công",
    "dieu hoa": "điều hòa",
    "nong lanh": "nóng lạnh",
    "thang may": "thang máy",
    "de xe": "chỗ để xe",
    "cua so": "cửa sổ",
    "may giat": "máy giặt",
    "tu lanh": "tủ lạnh",
    "bep tu": "bếp từ",
    "an ninh": "an ninh",
    "gio giac tu do": "giờ giấc tự do",
}


def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt: 'Cầu Giấy' -> 'Cau Giay'. Xử lý riêng chữ đ/Đ."""
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def district_key(text: str) -> str:
    """Khoá so khớp quận: 'Cầu Giấy' và 'cau giay' đều ra 'caugiay'."""
    return re.sub(r"[^a-z0-9]", "", strip_accents(text).lower())


def parse_price(raw: str, area_m2: float) -> int | None:
    """
    Bóc giá thuê thành số nguyên VNĐ. Bốn định dạng gặp trong dữ liệu thật:

        '4.8 triệu/tháng'       -> 4_800_000   (dấu chấm là phần thập phân)
        '800.000 đồng/tháng'    ->   800_000   (dấu chấm là phân cách nghìn)
        '20.000 đồng/m2/tháng'  -> 20_000 * diện tích
        'Thỏa thuận'            -> None        (thương lượng, không có giá niêm yết)

    Trả None khi không có giá — bản ghi vẫn giữ lại nhưng bị loại khỏi bộ lọc max_price.
    """
    raw = raw.strip()

    m = re.match(r"^([\d.,]+)\s*triệu/tháng$", raw)
    if m:
        # Ở đơn vị triệu, dấu . và , đều là phần thập phân (1.6 / 5,2)
        return int(float(m.group(1).replace(",", ".")) * 1_000_000)

    m = re.match(r"^([\d.,]+)\s*đồng/m2/tháng$", raw)
    if m:
        rate = int(m.group(1).replace(".", "").replace(",", ""))
        return int(rate * area_m2)

    m = re.match(r"^([\d.,]+)\s*đồng/tháng$", raw)
    if m:
        # Ở đơn vị đồng, dấu . là phân cách nghìn (800.000)
        return int(m.group(1).replace(".", "").replace(",", ""))

    return None


def parse_area(raw: str) -> float | None:
    """'25 m2' -> 25.0. Dữ liệu có một bản ghi lẻ '16.18 m2' nên phải nhận số thực."""
    m = AREA_RE.match(raw.strip())
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def parse_posted_at(raw: str) -> datetime | None:
    """'Thứ 2, 18:16 27/07/2026' -> datetime(2026, 7, 27, 18, 16)."""
    m = POSTED_RE.search(raw)
    if not m:
        return None
    hour, minute, day, month, year = (int(g) for g in m.groups())
    try:
        return datetime(year, month, day, hour, minute)
    except ValueError:
        return None


def extract_amenities(*texts: str) -> list[str]:
    """Quét từ khoá tiện ích trong tiêu đề + mô tả, giữ thứ tự khai báo trong từ điển."""
    haystack = strip_accents(" ".join(texts)).lower()
    found = []
    for keyword, label in AMENITY_VOCAB.items():
        if keyword in haystack and label not in found:
            found.append(label)
    return found


def scrub_phones(text: str) -> str:
    """Thay số điện thoại thật của chủ nhà bằng nhãn ẩn (tránh lộ PII vào prompt/log)."""
    return PHONE_RE.sub(PHONE_MASK, text)


def normalize_row(row: dict, index: int, now: datetime) -> dict | None:
    """
    Chuyển 1 dòng CSV thô thành bản ghi chuẩn.
    Trả None nếu dòng đó là rác và phải loại bỏ.
    """
    link = (row.get("Link") or "").strip()
    title = (row.get("Tiêu đề") or "").strip()
    address = (row.get("Địa chỉ") or "").strip()
    price_label = (row.get("Giá") or "").strip()

    area_m2 = parse_area(row.get("Diện tích") or "")
    # Loại rác: diện tích 0 m2 hoặc không đọc được
    if not area_m2:
        return None

    # Loại rác: có đúng một tin ghi giá '2 đồng/tháng'
    price_vnd = parse_price(price_label, area_m2)
    if price_vnd is not None and price_vnd < 100_000:
        return None

    m = ID_RE.search(link)
    listing_id = m.group(1) if m else f"gen{index:04d}"

    posted_at = parse_posted_at(row.get("Ngày đăng") or "")
    days_old = (now - posted_at).days if posted_at else None

    district = address.split(",")[0].strip() if address else "Không rõ"
    description = scrub_phones((row.get("Mô tả") or "").strip())

    return {
        "id": listing_id,
        "title": scrub_phones(title),
        "price_vnd": price_vnd,
        "price_label": price_label,
        "area_m2": area_m2,
        "district": district,
        "district_key": district_key(district),
        "address": address,
        "amenities": extract_amenities(title, description),
        "description": description,
        "posted_at": posted_at.isoformat() if posted_at else None,
        "days_old": days_old,
        "url": link,
    }


def load_listings(csv_path: str = CSV_PATH, now: datetime | None = None) -> list[dict]:
    """
    Đọc toàn bộ CSV và trả danh sách bản ghi chuẩn đã khử trùng lặp.

    Trùng lặp khử theo Link (dữ liệu có 1 dòng lặp y hệt), dòng đầu tiên thắng.
    """
    now = now or datetime.now()
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Không tìm thấy file dữ liệu: {csv_path}")

    listings: list[dict] = []
    seen_links: set[str] = set()

    # utf-8-sig để nuốt BOM ở đầu file, nếu không cột đầu sẽ có tên lạ
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        for index, row in enumerate(csv.DictReader(f)):
            link = (row.get("Link") or "").strip()
            if link and link in seen_links:
                continue
            record = normalize_row(row, index, now)
            if record is None:
                continue
            seen_links.add(link)
            listings.append(record)

    return listings


if __name__ == "__main__":
    import sys

    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    data = load_listings()
    print(f"✅ Đã chuẩn hoá {len(data)} tin đăng từ {os.path.basename(CSV_PATH)}")
    print(f"   Không có giá niêm yết (Thỏa thuận): {sum(1 for d in data if d['price_vnd'] is None)}")
    print(f"   Số quận: {len(set(d['district'] for d in data))}")
    print("\nVí dụ bản ghi đầu tiên:")
    for key, value in data[0].items():
        print(f"   {key}: {value}")
