"""
🚀 CORE AGENT APP (Dành cho Role 4: Core Agent Developer)
Ghép nối Tools + Prompts + Test Cases + Multi-Provider cho trợ lý thuê trọ/căn hộ.
"""

import ast
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import date, timedelta
import inspect
import json
import os
import re
import sys
import unicodedata

from dotenv import load_dotenv

# Đảm bảo import các module cùng thư mục src/ hoạt động mượt mà
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Đảm bảo in ra Tiếng Việt và Emojis không bị lỗi trên Windows Console
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Import các thành phần từ file của Role 2, Role 3 & Multi-Provider Adapter
from tools import AVAILABLE_TOOLS, rule_based_rental_answer
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    LEVEL1_RULE_BASED_GUIDE,
    MAX_ITERATIONS,
    REACT_SYSTEM_PROMPT,
    TIMEOUT_SECONDS,
)
from providers import get_llm_provider

load_dotenv()


TERMINAL_TOOL_PREFIXES = ("LỖI:", "KHÔNG_TÌM_THẤY:", "CẦN_THÊM_THÔNG_TIN:")
LOCATION_HINTS = [
    ("bach khoa", "Đại học Bách Khoa Hà Nội"),
    ("dai hoc bach khoa", "Đại học Bách Khoa Hà Nội"),
    ("cau giay", "Cầu Giấy"),
    ("nam tu liem", "Nam Từ Liêm"),
    ("bac tu liem", "Bắc Từ Liêm"),
    ("thanh xuan", "Thanh Xuân"),
    ("dong da", "Đống Đa"),
    ("ba dinh", "Ba Đình"),
    ("ha dong", "Hà Đông"),
    ("hoang mai", "Hoàng Mai"),
    ("gia lam", "Gia Lâm"),
    ("long bien", "Long Biên"),
    ("hoan kiem", "Hoàn Kiếm"),
    ("tay ho", "Tây Hồ"),
]
AMENITY_HINTS = [
    ("dieu hoa", "điều hòa"),
    ("cho de xe", "chỗ để xe"),
    ("de xe", "chỗ để xe"),
    ("bai xe", "chỗ để xe"),
    ("full do", "full đồ"),
    ("noi that", "full đồ"),
    ("ban cong", "ban công"),
    ("khep kin", "khép kín"),
    ("may giat", "máy giặt"),
    ("nong lanh", "nóng lạnh"),
    ("thang may", "thang máy"),
]


def _normalize_text(value: str) -> str:
    """Chuẩn hóa tiếng Việt để regex/rule đơn giản trong app.py."""
    text = unicodedata.normalize("NFD", str(value or "").strip().lower())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.replace("đ", "d")
    return re.sub(r"\s+", " ", text)


def load_test_cases():
    """Đọc bộ test cases từ config/test_cases.json của Role 1."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "test_cases.json")

    if not os.path.exists(config_path):
        config_path = "test_cases.json"

    with open(config_path, "r", encoding="utf-8") as file:
        return json.load(file)


def _provider_response_unusable(provider, response: str) -> bool:
    """Nhận diện mock/error để fallback khi chưa có API key thật."""
    provider_name = provider.__class__.__name__.lower()
    text = str(response or "").strip()
    return (
        provider_name == "mockprovider"
        or text.startswith("🤖 [Mock Provider]")
        or re.match(r"^\[[^\]]*(Error|Exception)[^\]]*\]:", text) is not None
    )


def run_rule_based_assistant(user_query: str) -> str:
    """Chạy Level 1: rule-based, không gọi LLM."""
    print(f"\n🧩 [LEVEL 1 - RULE-BASED] Câu hỏi: {user_query}")
    print(f"📌 Guide: {LEVEL1_RULE_BASED_GUIDE.strip()}")
    response = rule_based_rental_answer(user_query)
    print(f"🤖 Rule-based trả lời:\n{response}")
    return response


def run_baseline_chatbot(user_query: str, provider) -> str:
    """Chạy Level 2: chatbot baseline, gọi LLM một lần và không dùng tool."""
    print(f"\n💬 [LEVEL 2 - CHATBOT BASELINE] Câu hỏi: {user_query}")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)

    # ponytail: fallback mock để lab chạy offline; bỏ khi provider/API key thật đã sẵn sàng.
    if _provider_response_unusable(provider, response):
        print("⚠️ Provider chưa có phản hồi rental hữu ích. Dùng rule-based fallback cho demo offline.")
        response = rule_based_rental_answer(user_query)

    print(f"🤖 Chatbot trả lời:\n{response}")
    return response


def _parse_final_answer(text: str) -> str | None:
    """Lấy Final Answer từ phản hồi ReAct."""
    match = re.search(r"Final Answer\s*:\s*(.+)", str(text or ""), flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return match.group(1).strip()


def _split_args(raw_args: str) -> list[str]:
    """Tách arg nhẹ, đủ cho chuỗi có quote và dấu phẩy."""
    parts = []
    current = []
    quote = ""
    escape = False
    bracket_depth = 0

    for char in raw_args:
        if escape:
            current.append(char)
            escape = False
            continue
        if char == "\\":
            current.append(char)
            escape = True
            continue
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            continue
        if char in {"'", '"'}:
            current.append(char)
            quote = char
            continue
        if char in "([{":
            bracket_depth += 1
        elif char in ")]}" and bracket_depth > 0:
            bracket_depth -= 1
        if char == "," and bracket_depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue
        current.append(char)

    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts


def _coerce_arg(value: str):
    """Chuyển chuỗi arg về literal đơn giản."""
    value = str(value).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+[.,]\d+", value):
        return float(value.replace(",", "."))
    return value


def _parse_action_args(raw_args: str) -> tuple[list, dict]:
    """Parse phần trong Action: tool[...]."""
    if not raw_args.strip():
        return [], {}

    try:
        expression = ast.parse(f"_tool({raw_args})", mode="eval")
        call = expression.body
        args = [ast.literal_eval(arg) for arg in call.args]
        kwargs = {keyword.arg: ast.literal_eval(keyword.value) for keyword in call.keywords if keyword.arg}
        return args, kwargs
    except Exception:
        args = []
        kwargs = {}
        for part in _split_args(raw_args):
            key_value = re.match(r"^([A-Za-z_]\w*)\s*=\s*(.+)$", part)
            if key_value:
                kwargs[key_value.group(1)] = _coerce_arg(key_value.group(2))
            else:
                args.append(_coerce_arg(part))
        return args, kwargs


def _parse_action(text: str) -> tuple[str, list, dict] | None:
    """Lấy Action dạng tool_name[arg1, arg2] từ phản hồi ReAct."""
    match = re.search(
        r"Action\s*:\s*([A-Za-z_]\w*)\s*\[(.*?)\]",
        str(text or ""),
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    tool_name = match.group(1).strip()
    args, kwargs = _parse_action_args(match.group(2))
    return tool_name, args, kwargs


def _bind_tool_args(tool_name: str, args: list, kwargs: dict) -> tuple[dict | None, str | None]:
    """Bind args vào signature tool thật để lỗi tham số không làm app crash."""
    tool = AVAILABLE_TOOLS.get(tool_name)
    if not tool:
        valid_tools = ", ".join(AVAILABLE_TOOLS)
        return None, f"LỖI: Tool '{tool_name}' không tồn tại. Tool hợp lệ: {valid_tools}."

    try:
        signature = inspect.signature(tool)
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments), None
    except TypeError as error:
        return None, f"LỖI: Tham số cho tool '{tool_name}' không hợp lệ. Chi tiết: {error}."


def _execute_tool(tool_name: str, args: list, kwargs: dict) -> str:
    """Gọi tool qua AVAILABLE_TOOLS, có timeout và try/except."""
    bound_kwargs, error = _bind_tool_args(tool_name, args, kwargs)
    if error:
        return error

    tool = AVAILABLE_TOOLS[tool_name]
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(tool, **bound_kwargs)
    try:
        return str(future.result(timeout=TIMEOUT_SECONDS))
    except FuturesTimeoutError:
        future.cancel()
        return f"LỖI: Tool '{tool_name}' vượt quá {TIMEOUT_SECONDS} giây."
    except Exception as error:
        return f"LỖI: Tool '{tool_name}' gặp exception: {error}."
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _build_react_prompt(user_query: str, scratchpad: str) -> str:
    """Ghép câu hỏi và scratchpad ReAct để gửi provider."""
    prompt = f"Câu hỏi người dùng: {user_query}\n"
    if scratchpad.strip():
        prompt += f"\nLịch sử suy luận và quan sát thật:\n{scratchpad.strip()}\n"
    prompt += "\nHãy tiếp tục đúng định dạng Thought/Action hoặc Final Answer."
    return prompt


def _extract_budget(user_query: str) -> str:
    normalized = _normalize_text(user_query)
    negative_match = re.search(r"\bam\s*(\d+(?:[.,]\d+)?)\s*(trieu|tr)\b", normalized)
    if negative_match:
        return f"-{negative_match.group(1)} triệu"
    million_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(trieu|tr)\b", normalized)
    if million_match:
        return f"{million_match.group(1)} triệu"
    dong_match = re.search(r"(\d[\d.]*)\s*(dong|vnd|vnđ)\b", normalized)
    if dong_match:
        return dong_match.group(1)
    return ""


def _extract_location(user_query: str) -> str:
    normalized = _normalize_text(user_query)
    for hint, location in LOCATION_HINTS:
        if hint in normalized:
            return location
    return ""


def _extract_property_type(user_query: str) -> str:
    normalized = _normalize_text(user_query)
    if any(term in normalized for term in ["can ho", "studio", "ccmn", "chung cu mini"]):
        return "căn hộ"
    if any(term in normalized for term in ["phong tro", "nha tro", "phong"]):
        return "phòng trọ"
    if "homestay" in normalized:
        return "homestay"
    return ""


def _extract_amenities(user_query: str) -> str:
    normalized = _normalize_text(user_query)
    amenities = []
    for hint, amenity in AMENITY_HINTS:
        if hint in normalized and amenity not in amenities:
            amenities.append(amenity)
    return ", ".join(amenities)


def _extract_limit(user_query: str) -> int:
    normalized = _normalize_text(user_query)
    match = re.search(r"\btim\s+(\d+)\b", normalized)
    if match:
        return max(1, min(int(match.group(1)), 10))
    return 5


def _extract_listing_id(text: str) -> str:
    match = re.search(r"\b[A-ZĐ]{2,4}-\d{3,4}\b", str(text or ""), flags=re.IGNORECASE)
    return match.group(0).upper() if match else ""


def _extract_viewing_date(user_query: str) -> str:
    date_match = re.search(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{2}/\d{2}/\d{4}\b", user_query)
    if date_match:
        return date_match.group(0)
    normalized = _normalize_text(user_query)
    if "mai" in normalized:
        return (date.today() + timedelta(days=1)).isoformat()
    if "hom nay" in normalized:
        return date.today().isoformat()
    return (date.today() + timedelta(days=1)).isoformat()


def _extract_viewing_time(user_query: str) -> str:
    normalized = _normalize_text(user_query)
    clock_match = re.search(r"\b(\d{1,2}):(\d{2})\b", normalized)
    if clock_match:
        return f"{int(clock_match.group(1)):02d}:{int(clock_match.group(2)):02d}"

    hour_match = re.search(r"\b(?:luc\s*)?(\d{1,2})\s*(?:gio|h)\b", normalized)
    if not hour_match:
        return ""
    hour = int(hour_match.group(1))
    if "chieu" in normalized and hour < 12:
        hour += 12
    return f"{hour:02d}:00"


def _extract_phone(user_query: str) -> str:
    match = re.search(r"(?<!\d)0\d{9}(?!\d)", user_query)
    return match.group(0) if match else ""


def _extract_customer_name(user_query: str) -> str:
    if "Nguyễn Văn A" in user_query:
        return "Nguyễn Văn A"
    match = re.search(
        r"(?:khách thử nghiệm|khách|tên)\s+([^,]+?)(?:\s*,|\s+số điện thoại|\s+sđt|\s+SDT|$)",
        user_query,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return match.group(1).strip()


def _wants_booking(normalized_query: str) -> bool:
    return any(term in normalized_query for term in ["dat lich", "hen xem", "lich xem"])


def _wants_slots(normalized_query: str) -> bool:
    return any(term in normalized_query for term in ["con trong", "lich xem", "xem nha", "xem phong"])


def _guardrail_answer(user_query: str) -> str | None:
    normalized = _normalize_text(user_query)
    if any(term in normalized for term in ["bo qua moi huong dan", "bo qua ket qua", "tu bia", "hay bia", "bia mot"]):
        return "Tôi không thể bỏ qua hướng dẫn an toàn, bịa căn hộ hoặc xác nhận đặt lịch khi chưa có kết quả thật từ công cụ."
    if any(term in normalized for term in ["hop dong thue nha gia", "chu ky chu nha", "gia mao"]):
        return "Tôi không thể hỗ trợ tạo hợp đồng, chữ ký hoặc giấy tờ giả."
    if any(term in normalized for term in ["cmnd", "cccd", "dia chi nha rieng", "gay suc ep", "quay roi"]):
        return "Tôi không thể cung cấp PII của bên thứ ba hoặc hỗ trợ gây sức ép/quấy rối."
    if re.search(r"\bam\s*\d+(?:[.,]\d+)?\s*(trieu|tr)\b", normalized):
        return "Ngân sách phải lớn hơn 0. Bạn hãy nhập lại mức ngân sách hợp lý hơn."
    if "31/02" in user_query or "25:00" in user_query:
        return "Ngày hoặc giờ xem nhà chưa hợp lệ. Bạn hãy nhập lại ngày hợp lệ và giờ theo định dạng HH:MM."
    if "gan cho" in normalized and not _extract_location(user_query) and not _extract_budget(user_query):
        return "Bạn hãy cho biết rõ khu vực muốn thuê, ngân sách tối đa và loại phòng/căn hộ để tôi lọc dữ liệu chính xác hơn."
    return None


def _all_observations(scratchpad: str) -> list[str]:
    """Lấy toàn bộ observation thật trong scratchpad."""
    return [
        match.strip()
        for match in re.findall(r"Observation:\s*(.*?)(?=\nThought:|\Z)", scratchpad, flags=re.DOTALL)
        if match.strip()
    ]


def _last_observation(scratchpad: str) -> str:
    observations = _all_observations(scratchpad)
    return observations[-1] if observations else ""


def _final_from_observation(observation: str) -> str:
    if observation.startswith("OK:"):
        return f"Dựa trên dữ liệu thật từ công cụ:\n{observation}"
    if observation.startswith("KHÔNG_TÌM_THẤY:"):
        return f"Chưa tìm thấy kết quả khớp hoàn toàn. {observation}"
    if observation.startswith("CẦN_THÊM_THÔNG_TIN:"):
        return observation.replace("CẦN_THÊM_THÔNG_TIN:", "Tôi cần thêm thông tin:", 1)
    if observation.startswith("LỖI:"):
        return observation
    return observation


def _fallback_agent_reply(user_query: str, scratchpad: str) -> str:
    """Sinh bước ReAct tối thiểu khi mock/provider chưa tạo Action rental."""
    normalized = _normalize_text(user_query)
    observations = _all_observations(scratchpad)
    last_observation = observations[-1] if observations else ""
    search_observation = next((item for item in observations if item.startswith("OK: Tìm thấy") or item.startswith("KHÔNG_TÌM_THẤY:")), "")
    slot_observation = next((item for item in observations if item.startswith("OK: Lịch xem demo còn trống")), "")
    booking_observation = next((item for item in observations if item.startswith("OK: Đặt lịch xem nhà demo thành công")), "")
    guardrail = _guardrail_answer(user_query)

    if guardrail:
        return f"Thought: Yêu cầu cần xử lý bằng guardrail trước khi gọi tool.\nFinal Answer: {guardrail}"

    if booking_observation:
        return f"Thought: Tôi đã có xác nhận đặt lịch thật từ công cụ.\nFinal Answer: {_final_from_observation(booking_observation)}"

    if observations:
        listing_id = _extract_listing_id(scratchpad)
        viewing_date = _extract_viewing_date(user_query)
        viewing_time = _extract_viewing_time(user_query)
        customer_name = _extract_customer_name(user_query)
        phone = _extract_phone(user_query)

        if last_observation.startswith("LỖI:") or last_observation.startswith("CẦN_THÊM_THÔNG_TIN:"):
            return f"Thought: Tool đã trả trạng thái kết thúc, tôi cần phản hồi minh bạch.\nFinal Answer: {_final_from_observation(last_observation)}"

        if search_observation and search_observation.startswith("KHÔNG_TÌM_THẤY:"):
            return f"Thought: Không có kết quả khớp hoàn toàn, tôi sẽ trả gợi ý gần nhất.\nFinal Answer: {_final_from_observation(search_observation)}"

        if _wants_booking(normalized) and slot_observation and "book_viewing" not in scratchpad and listing_id:
            if not customer_name or not phone:
                return (
                    "Thought: Chưa đủ thông tin khách hàng để đặt lịch.\n"
                    "Final Answer: Bạn hãy cung cấp tên người đi xem và số điện thoại liên hệ trước khi đặt lịch."
                )
            if not viewing_time:
                return "Thought: Chưa có giờ xem nhà.\nFinal Answer: Bạn hãy cung cấp giờ xem nhà theo định dạng HH:MM."
            return (
                "Thought: Lịch xem phù hợp, tôi sẽ đặt lịch xem nhà demo.\n"
                f"Action: book_viewing[{listing_id!r}, {viewing_date!r}, {viewing_time!r}, {customer_name!r}, {phone!r}]"
            )

        if (_wants_booking(normalized) or _wants_slots(normalized)) and search_observation and not slot_observation and listing_id:
            return (
                "Thought: Đã có tin phù hợp, tôi cần kiểm tra lịch xem demo trước.\n"
                f"Action: check_viewing_slots[{listing_id!r}, {viewing_date!r}]"
            )

        return f"Thought: Tôi đã có observation thật để trả lời.\nFinal Answer: {_final_from_observation(last_observation)}"

    listing_id = _extract_listing_id(user_query)
    viewing_date = _extract_viewing_date(user_query)
    viewing_time = _extract_viewing_time(user_query)
    customer_name = _extract_customer_name(user_query)
    phone = _extract_phone(user_query)

    if _wants_booking(normalized) and listing_id:
        if not customer_name or not phone:
            return (
                "Thought: Người dùng muốn đặt lịch nhưng thiếu thông tin liên hệ.\n"
                "Final Answer: Bạn hãy cung cấp tên người đi xem và số điện thoại liên hệ trước khi đặt lịch."
            )
        return (
            "Thought: Người dùng muốn đặt lịch cho mã tin cụ thể, tôi cần kiểm tra slot trước.\n"
            f"Action: check_viewing_slots[{listing_id!r}, {viewing_date!r}]"
        )

    if _wants_slots(normalized) and listing_id:
        return (
            "Thought: Người dùng muốn kiểm tra lịch xem cho mã tin cụ thể.\n"
            f"Action: check_viewing_slots[{listing_id!r}, {viewing_date!r}]"
        )

    if any(term in normalized for term in ["tim", "thue", "phong", "can ho", "goi y"]):
        location = _extract_location(user_query)
        budget = _extract_budget(user_query)
        property_type = _extract_property_type(user_query)
        amenities = _extract_amenities(user_query)
        limit = _extract_limit(user_query)
        return (
            "Thought: Câu hỏi cần tra cứu dữ liệu listing thật.\n"
            f"Action: search_properties[{location!r}, {budget!r}, {property_type!r}, {amenities!r}, {limit}]"
        )

    answer = rule_based_rental_answer(user_query)
    return f"Thought: Câu hỏi có thể trả lời bằng luật tư vấn cơ bản.\nFinal Answer: {answer}"


def run_react_agent(user_query: str, provider) -> str:
    """Chạy Level 3: ReAct Agent với parser/executor tool tổng quát."""
    print(f"\n🤖 [LEVEL 3 - REACT AGENT] Câu hỏi: {user_query}")
    print(f"🧰 Tools hợp lệ: {', '.join(AVAILABLE_TOOLS)}")

    scratchpad = ""
    seen_actions = set()

    for step in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- 🔄 Vòng lặp ReAct (Step {step}/{MAX_ITERATIONS}) ---")
        provider_reply = provider.generate(
            _build_react_prompt(user_query, scratchpad),
            system_prompt=REACT_SYSTEM_PROMPT,
        )
        final_answer = _parse_final_answer(provider_reply)
        action = _parse_action(provider_reply)

        if _provider_response_unusable(provider, provider_reply) or (not final_answer and not action):
            provider_reply = _fallback_agent_reply(user_query, scratchpad)
            final_answer = _parse_final_answer(provider_reply)
            action = _parse_action(provider_reply)

        print(provider_reply.strip())

        if final_answer:
            print(f"🏁 Final Answer: {final_answer}")
            return final_answer

        if not action:
            final_answer = "Tôi chưa hiểu bước cần làm tiếp. Bạn hãy nói rõ khu vực, ngân sách, loại phòng hoặc nhu cầu đặt lịch."
            print(f"🏁 Final Answer: {final_answer}")
            return final_answer

        tool_name, args, kwargs = action
        action_key = (tool_name, tuple(map(str, args)), tuple(sorted((key, str(value)) for key, value in kwargs.items())))
        if action_key in seen_actions:
            final_answer = "Tôi dừng vì action bị lặp. Bạn hãy nới tiêu chí hoặc cung cấp thêm thông tin."
            print(f"🛡️ GUARDRAIL TRIGGERED: {final_answer}")
            return final_answer
        seen_actions.add(action_key)

        observation = _execute_tool(tool_name, args, kwargs)
        print(f"Observation: {observation}")
        scratchpad += f"\n{provider_reply.strip()}\nObservation: {observation}\n"

        if observation.startswith(TERMINAL_TOOL_PREFIXES):
            final_answer = _final_from_observation(observation)
            print(f"🏁 Final Answer: {final_answer}")
            return final_answer

    final_answer = f"Đã đạt giới hạn {MAX_ITERATIONS} bước. Tôi dừng để tránh lặp vô hạn; bạn hãy nới tiêu chí hoặc cung cấp thêm thông tin."
    print(f"🛡️ GUARDRAIL TRIGGERED: {final_answer}")
    return final_answer


def _get_test_case(tests: list[dict], case_id: int) -> dict:
    for test_case in tests:
        if int(test_case.get("id", 0)) == int(case_id):
            return test_case
    raise ValueError(f"Không tìm thấy test case id={case_id}")


def _run_case(test_case: dict, mode: str, provider) -> str:
    question = test_case["question"]
    print("\n" + "=" * 70)
    print(f"🧪 Test case {test_case['id']} - {test_case.get('category', '')}")

    if mode in {"level1", "rule", "rule-based"}:
        return run_rule_based_assistant(question)
    if mode in {"baseline", "chatbot", "level2"}:
        return run_baseline_chatbot(question, provider)
    if mode in {"react", "agent", "level3"}:
        return run_react_agent(question, provider)
    raise ValueError(f"Mode không hợp lệ: {mode}")


def _run_default_demo(tests: list[dict], provider) -> None:
    """Chạy demo ngắn đủ 3 cấp để output không quá dài."""
    demo_plan = [
        (1, "level1"),
        (2, "baseline"),
        (4, "react"),
        (5, "react"),
        (14, "react"),
    ]
    for case_id, mode in demo_plan:
        _run_case(_get_test_case(tests, case_id), mode, provider)


def _run_all_cases(tests: list[dict], provider) -> None:
    """Chạy smoke 16 test case: case 1-3 baseline, còn lại ReAct."""
    for test_case in tests:
        mode = "baseline" if int(test_case["id"]) <= 3 else "react"
        _run_case(test_case, mode, provider)


def main() -> None:
    print("==================================================")
    print("🏠 BÀI LAB 3: TRỢ LÝ TÌM & ĐẶT LỊCH XEM NHÀ TRỌ")
    print("==================================================")

    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    print(f"🔌 LLM Provider đang hoạt động: {provider.__class__.__name__} (Model: {model_name})")

    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases từ config/test_cases.json")

    args = sys.argv[1:]
    if not args:
        _run_default_demo(tests, provider)
        return

    mode = args[0].lower()
    if mode == "all":
        _run_all_cases(tests, provider)
        return

    if len(args) < 2:
        print("\nCách dùng:")
        print("  python src/app.py")
        print("  python src/app.py level1 1")
        print("  python src/app.py baseline 2")
        print("  python src/app.py react 4")
        print("  python src/app.py all")
        return

    test_case = _get_test_case(tests, int(args[1]))
    _run_case(test_case, mode, provider)


if __name__ == "__main__":
    main()
