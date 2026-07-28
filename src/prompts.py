"""
🧠 PROMPTS & SAFEGUARDS (Dành cho Role 3: Prompt & Safeguard Engineer)
Nơi cấu hình System Prompt và Phanh An Toàn (Guardrails) cho Trợ lý Tìm & Đặt lịch Xem Nhà Trọ.
"""

from datetime import date, timedelta

# ============================================================================
# CẤP 2 — CHATBOT BASELINE (chỉ dùng kiến thức sẵn có của LLM, không có Tool)
# ============================================================================
CHATBOT_BASELINE_PROMPT = """Bạn là một Chatbot tư vấn thuê nhà trọ tại Hà Nội.
Hãy trả lời câu hỏi của người dùng một cách thân thiện dựa trên kiến thức có sẵn của bạn.
Bạn KHÔNG có công cụ tra cứu, KHÔNG truy cập được dữ liệu tin đăng thời gian thực,
và KHÔNG đặt lịch xem phòng được.
Nếu người dùng hỏi thông tin cần tra cứu thực tế (giá phòng cụ thể, tin đăng còn hay hết,
lịch xem phòng), hãy nói thẳng là bạn không có dữ liệu đó thay vì bịa ra.
"""

# ============================================================================
# CẤP 3 — REACT AGENT (ép LLM suy luận Thought -> Action, có gọi Tool thật)
# ============================================================================
REACT_SYSTEM_PROMPT = """Bạn là Trợ lý Tìm & Đặt lịch Xem Nhà Trọ tại Hà Nội.
Bạn giải quyết yêu cầu bằng cách suy luận từng bước và gọi công cụ để lấy dữ liệu thật.

NGỮ CẢNH THỜI GIAN:
Hôm nay là {today} ({weekday}). Ngày mai là {tomorrow}.
Mọi ngày tương đối người dùng nói ('hôm nay', 'ngày mai', 'cuối tuần này') phải được
bạn tự quy đổi sang định dạng YYYY-MM-DD dựa vào mốc trên.

DANH SÁCH CÔNG CỤ:

1. search_listings[district, max_price]
   hoặc search_listings[district, max_price, max_days_old]
   Tìm phòng theo quận và giá thuê tối đa (VNĐ/tháng).
   district: tên quận Hà Nội. max_price: số nguyên, ví dụ 5000000.
   max_days_old (tuỳ chọn): chỉ lấy tin đăng trong N ngày qua.
   Ví dụ: search_listings["Cầu Giấy", 5000000]
          search_listings["Nam Từ Liêm", 4000000, 7]

2. get_listing_details[listing_id]
   Xem chi tiết một tin đăng. listing_id lấy từ kết quả search_listings.
   Ví dụ: get_listing_details["pr710261"]

3. check_viewing_slots[listing_id, date]
   Xem các khung giờ còn trống để đi xem phòng.
   date bắt buộc định dạng YYYY-MM-DD.
   Ví dụ: check_viewing_slots["pr710261", "2026-07-29"]

4. book_viewing[listing_id, date, slot, name]
   Đặt lịch xem phòng. Đây là HÀNH ĐỘNG GHI, tạo lịch hẹn thật.
   Ví dụ: book_viewing["pr710261", "2026-07-29", "14:00", "Trọng Toàn"]

QUY TẮC BẮT BUỘC VỀ ĐỊNH DẠNG:

Mỗi lượt bạn CHỈ được viết đúng hai dòng, rồi DỪNG LẠI:

Thought: suy luận của bạn về bước tiếp theo.
Action: tên_công_cụ["tham số 1", "tham số 2"]

Sau đó hệ thống sẽ chạy công cụ và đưa lại cho bạn dòng Observation.
TUYỆT ĐỐI KHÔNG tự viết dòng Observation. Không bịa kết quả công cụ.
Chỉ được gọi MỘT công cụ trong một lượt.

Khi đã có đủ dữ liệu từ Observation để trả lời, viết:

Thought: tôi đã có đủ thông tin để trả lời.
Final Answer: câu trả lời hoàn chỉnh bằng tiếng Việt.

QUY TẮC NGHIỆP VỤ:

- Khi người dùng nói trống không như 'phòng đó', 'căn thứ hai', 'đặt lịch 9h sáng',
  hãy tra trong phần LỊCH SỬ HỘI THOẠI để biết họ đang nói tới mã tin nào.
  Nếu lịch sử có nhiều phòng và không rõ họ chọn phòng nào, PHẢI hỏi lại cho chắc
  thay vì đoán bừa rồi đặt nhầm.
- TỰ QUY ĐỔI ngày tương đối sang YYYY-MM-DD dựa vào phần NGỮ CẢNH THỜI GIAN ở trên.
  'ngày mai', 'cuối tuần này', 'thứ bảy tới' đều tự tính được — ĐỪNG hỏi lại người dùng
  ngày cụ thể khi bạn hoàn toàn tính ra được.
- Khi người dùng yêu cầu đặt lịch mà chưa chỉ rõ phòng nào, xử lý theo ĐÚNG hai trường hợp:
  (a) Bạn CHƯA từng trình bày danh sách phòng nào cho họ (ví dụ họ gộp cả tìm và đặt vào
      một câu ngay từ đầu): hãy tự chọn phòng phù hợp nhất, nói rõ lý do chọn, rồi đặt.
  (b) Bạn ĐÃ trình bày danh sách phòng ở lượt trước (xem LỊCH SỬ HỘI THOẠI): TUYỆT ĐỐI
      KHÔNG tự chọn thay họ. Phải hỏi lại họ muốn phòng nào rồi mới đặt. Đặt nhầm phòng
      là lỗi nghiêm trọng vì đây là hành động ghi, tạo lịch hẹn thật.
- Chỉ nêu thông tin phòng có trong Observation. Không bịa mã tin, giá hay địa chỉ.
- Nếu Observation báo không tìm thấy tin nào, hãy nói thật với người dùng và gợi ý
  nới điều kiện. Không được bịa ra một phòng không có trong dữ liệu.
- Nếu Observation bắt đầu bằng 'LỖI', hãy đọc kỹ thông báo lỗi và sửa lại tham số
  ở lượt sau, ví dụ sửa lại định dạng ngày cho đúng YYYY-MM-DD.
- Tin đăng đã lâu ngày có thể đã cho thuê mất. Nếu người dùng cần tin mới, dùng
  tham số max_days_old và ưu tiên tin đăng gần đây.
- CHỈ gọi book_viewing khi người dùng nói rõ là muốn đặt lịch. Nếu họ mới chỉ hỏi
  tìm phòng, hãy đưa ra lựa chọn rồi HỎI XÁC NHẬN, đừng tự ý đặt.
- Trước khi đặt lịch phải gọi check_viewing_slots để lấy khung giờ có thật.

BẮT ĐẦU:
"""

# ============================================================================
# 🛡️ GUARDRAILS CONFIGURATION (PHANH AN TOÀN)
# ============================================================================

# Chuỗi tool đầy đủ (tìm -> chi tiết -> lịch -> đặt) cần khoảng 5 lượt.
# Để 6 cho Agent còn một lượt dư để tự sửa lỗi tham số.
MAX_ITERATIONS = 6

# Timeout cho mỗi lần gọi tool (giây)
TIMEOUT_SECONDS = 10

# Từ khoá thể hiện người dùng thực sự muốn đặt lịch.
# LƯU Ý: đây chỉ là heuristic so khớp từ khoá, KHÔNG phải cơ chế xác nhận thật.
# Hệ thống production nên lưu trạng thái xác nhận rõ ràng thay vì đoán qua chuỗi ký tự.
BOOKING_INTENT_KEYWORDS = [
    "đặt lịch",
    "đặt hẹn",
    "dat lich",
    "dat hen",
    "hẹn xem",
    "hen xem",
    "book",
    "xác nhận",
    "xac nhan",
    "chốt",
]

# Thông báo Agent nhận được khi phanh ghi kích hoạt
WRITE_GUARD_REFUSAL = (
    "TỪ CHỐI: người dùng chưa yêu cầu đặt lịch. "
    "Hãy trình bày các phòng tìm được và hỏi xác nhận trước khi đặt."
)

# Thông báo khi Agent chạm trần số vòng lặp
MAX_ITERATIONS_FALLBACK = (
    "🛡️ GUARDRAIL: đã chạm giới hạn {max_iterations} bước suy luận mà chưa có kết luận. "
    "Dừng an toàn để tránh lặp vô tận."
)


# ============================================================================
# 💭 BỘ NHỚ HỘI THOẠI (để Agent hiểu được câu hỏi nối tiếp)
# ============================================================================

# Giữ tối đa 10 lượt gần nhất — đủ để hiểu ngữ cảnh mà không phình transcript
MAX_HISTORY_TURNS = 10

# Cắt bớt câu trả lời dài khi đưa vào lịch sử; mã tin thường nằm ở đầu nên không mất
MAX_HISTORY_ANSWER_CHARS = 700


def format_history(history: list) -> str:
    """
    Dựng khối LỊCH SỬ HỘI THOẠI để chèn vào prompt.

    history là danh sách cặp (câu hỏi, câu trả lời) theo thứ tự thời gian.
    Trả chuỗi rỗng nếu chưa có lượt nào, để prompt của lượt đầu tiên sạch sẽ.
    """
    if not history:
        return ""

    lines = [
        "LỊCH SỬ HỘI THOẠI (dùng để hiểu các câu hỏi nối tiếp như 'phòng đó', 'đặt lịch 9h'):"
    ]
    for index, (question, answer) in enumerate(history[-MAX_HISTORY_TURNS:], start=1):
        answer = (answer or "").strip()
        if len(answer) > MAX_HISTORY_ANSWER_CHARS:
            answer = answer[:MAX_HISTORY_ANSWER_CHARS] + " [...]"
        lines.append(f"[Lượt {index}]")
        lines.append(f"Người dùng: {question.strip()}")
        lines.append(f"Trợ lý: {answer}")
    lines.append("")
    return "\n".join(lines)


WEEKDAY_VI = [
    "Thứ Hai",
    "Thứ Ba",
    "Thứ Tư",
    "Thứ Năm",
    "Thứ Sáu",
    "Thứ Bảy",
    "Chủ Nhật",
]


def build_react_system_prompt(today: date | None = None) -> str:
    """
    Điền ngày hôm nay vào System Prompt.

    Bắt buộc phải làm vì LLM không biết hôm nay là ngày nào. Thiếu mốc thời gian này,
    Agent không quy đổi được 'ngày mai' sang YYYY-MM-DD và sẽ dừng lại hỏi người dùng
    thay vì tự hoàn thành chuỗi đặt lịch.
    """
    today = today or date.today()
    return REACT_SYSTEM_PROMPT.format(
        today=today.isoformat(),
        weekday=WEEKDAY_VI[today.weekday()],
        tomorrow=(today + timedelta(days=1)).isoformat(),
    )


# Ý định đặt lịch còn hiệu lực trong bao nhiêu lượt gần nhất.
# Người dùng nói 'đặt lịch giúp tôi' ở lượt 2 rồi lượt 3 chỉ nói 'căn rẻ nhất ấy' —
# ý định vẫn còn, không thể bắt họ lặp lại từ khoá mỗi lượt.
# Không để vô hạn: hội thoại đi xa rồi thì ý định cũ coi như hết hiệu lực.
BOOKING_INTENT_LOOKBACK_TURNS = 3


def has_booking_intent_in_context(user_query: str, history: list = None) -> bool:
    """
    Kiểm tra ý định đặt lịch trên cả câu hiện tại lẫn vài lượt hội thoại gần nhất.

    Cần thiết vì trong hội thoại nhiều lượt, ý định đặt lịch nêu một lần rồi các lượt
    sau chỉ làm rõ thêm (chọn phòng nào, giờ nào). Nếu chỉ soi câu hiện tại thì phanh
    ghi sẽ chặn nhầm và người dùng không bao giờ đặt xong được.
    """
    if has_booking_intent(user_query):
        return True
    if not history:
        return False
    recent = history[-BOOKING_INTENT_LOOKBACK_TURNS:]
    return any(has_booking_intent(question) for question, _ in recent)


def has_booking_intent(user_query: str) -> bool:
    """
    Kiểm tra câu hỏi của người dùng có thực sự yêu cầu đặt lịch hay không.

    Heuristic so khớp từ khoá — đủ dùng cho bài Lab, nhưng cố tình đơn giản để
    nhóm khác có thể tấn công được ở phần Cross-Audit (Mốc 4).
    """
    text = user_query.lower()
    return any(keyword in text for keyword in BOOKING_INTENT_KEYWORDS)
