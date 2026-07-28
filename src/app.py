"""
🚀 CORE AGENT APP (Dành cho Role 4: Core Agent Developer)

Ghép Tools + Prompts + Test Cases + Multi-Provider thành một ứng dụng hoàn chỉnh,
và chạy vòng lặp ReAct thật: parser -> executor -> loop.

Chạy:
    Terminal 1:  uvicorn src.rental_api.server:app --port 8000
    Terminal 2:  python src/app.py                 (chạy toàn bộ test cases)
                 python src/app.py 4               (chỉ chạy test case số 4)
                 python src/app.py "câu hỏi ..."   (chạy câu hỏi tự nhập)
"""

import json
import os
import re
import sys
import time

from dotenv import load_dotenv

# Đảm bảo import các module cùng thư mục src/ hoạt động mượt mà
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Đảm bảo in ra Tiếng Việt và Emojis không bị lỗi trên Windows Console
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Import các thành phần từ file của Role 2, Role 3 & Multi-Provider Adapter
from tools import AVAILABLE_TOOLS, WRITE_TOOLS, check_api_health
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    MAX_ITERATIONS,
    MAX_ITERATIONS_FALLBACK,
    WRITE_GUARD_REFUSAL,
    build_react_system_prompt,
    has_booking_intent,
)
from providers import get_llm_provider

load_dotenv()

# Bắt dòng Action: tên_tool[...]
ACTION_RE = re.compile(r"^\s*Action:\s*(\w+)\s*\[(.*)\]\s*$", re.MULTILINE | re.DOTALL)

# providers.py trả lỗi API dưới dạng chuỗi "[Gemini Exception]: ..." chứ không ném exception.
# Nhận diện sớm để dừng vòng lặp, tránh đốt hết MAX_ITERATIONS lượt gọi vào một API đang chết.
PROVIDER_ERROR_RE = re.compile(r"^\[[^\]]*(Error|Exception)[^\]]*\]:", re.IGNORECASE)


# Lỗi tạm thời của nhà cung cấp: quá tải, quá hạn mức, nghẽn mạng. Thử lại là qua.
TRANSIENT_MARKERS = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "overloaded", "timeout")
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 3


def is_provider_error(text: str) -> bool:
    """Phát hiện phản hồi thực chất là lỗi từ nhà cung cấp LLM, không phải nội dung suy luận."""
    return bool(PROVIDER_ERROR_RE.match(text.strip()))


def is_transient(text: str) -> bool:
    """Lỗi này thử lại được hay hỏng hẳn?"""
    return any(marker.lower() in text.lower() for marker in TRANSIENT_MARKERS)


def generate_with_retry(provider, prompt: str) -> str:
    """
    Gọi LLM, tự thử lại khi gặp lỗi tạm thời (503 quá tải, 429 quá hạn mức).

    Cần thiết vì lúc demo trước lớp mà model nghẽn một nhịp là mất luôn cả câu hỏi.
    """
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        output = provider.generate(prompt) or ""
        if not (is_provider_error(output) and is_transient(output)):
            return output
        if attempt < RETRY_ATTEMPTS:
            print(f"   ⏳ LLM tạm thời quá tải, thử lại lần {attempt + 1}/{RETRY_ATTEMPTS}...")
            time.sleep(RETRY_DELAY_SECONDS)
    return output


def load_test_cases():
    """Đọc bộ test cases từ config/test_cases.json của Role 1"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "test_cases.json")

    # Fallback kiểm tra nếu file ở thư mục hiện tại
    if not os.path.exists(config_path):
        config_path = "test_cases.json"

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================================
# CẤP 2 — CHATBOT BASELINE
# ============================================================================


def run_baseline_chatbot(user_query: str, provider) -> str:
    """Chatbot gốc: chỉ có LLM, không có công cụ nào."""
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot trả lời:\n{response}")
    return response


# ============================================================================
# CẤP 3 — REACT AGENT: PARSER
# ============================================================================


def split_arguments(raw_args: str) -> list:
    """
    Tách tham số trong dấu ngoặc vuông, chỉ cắt ở dấu phẩy NẰM NGOÀI chuỗi trích dẫn.

    Nhờ vậy 'Cầu Giấy, Hà Nội' nằm trong nháy kép vẫn được coi là một tham số.
    Số nguyên trần được ép về int để 5000000 không bị truyền thành chuỗi "5000000".
    """
    args, current, quote = [], [], None

    for char in raw_args:
        if quote:
            if char == quote:
                quote = None
            else:
                current.append(char)
        elif char in "\"'":
            quote = char
        elif char == ",":
            args.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    args.append("".join(current).strip())

    cleaned = []
    for arg in args:
        arg = arg.strip().strip("\"'").strip()
        if not arg:
            continue
        cleaned.append(int(arg) if re.fullmatch(r"-?\d+", arg) else arg)
    return cleaned


def truncate_at_observation(text: str) -> str:
    """
    Cắt bỏ phần LLM tự bịa ra sau khi nó đã viết Action.

    Model rất hay tự viết luôn dòng 'Observation:' kèm kết quả tưởng tượng. Nếu để
    nguyên, cả trace log sẽ là dữ liệu giả. Application mới là nơi chèn Observation thật.
    """
    for marker in ("\nObservation:", "\nObservation ", "\nQuan sát:"):
        index = text.find(marker)
        if index != -1:
            text = text[:index]
    return text.strip()


def parse_action(text: str):
    """Bóc (tên_tool, danh_sách_tham_số) từ dòng Action. Trả None nếu không có Action hợp lệ."""
    match = ACTION_RE.search(text)
    if not match:
        return None
    tool_name = match.group(1).strip()
    return tool_name, split_arguments(match.group(2))


# ============================================================================
# CẤP 3 — REACT AGENT: EXECUTOR (nơi cài phanh an toàn)
# ============================================================================


def execute_tool(tool_name: str, args: list, user_query: str) -> str:
    """
    Chạy tool và trả về Observation.

    Đây là chốt chặn an toàn cuối cùng: mọi phanh đều đặt ở đây chứ không chỉ
    nằm trong prompt, vì prompt chỉ là lời khuyên còn executor mới là luật.
    """
    tool = AVAILABLE_TOOLS.get(tool_name)
    if tool is None:
        available = ", ".join(AVAILABLE_TOOLS)
        return f"LỖI: không có công cụ tên '{tool_name}'. Các công cụ hợp lệ: {available}."

    # 🛡️ PHANH HÀNH ĐỘNG GHI: không cho đặt lịch nếu người dùng chưa hề yêu cầu
    if tool_name in WRITE_TOOLS and not has_booking_intent(user_query):
        return WRITE_GUARD_REFUSAL

    try:
        return tool(*args)
    except TypeError as e:
        # Sai số lượng tham số — trả lại chữ ký đúng để Agent tự sửa ở lượt sau
        import inspect

        signature = str(inspect.signature(tool))
        return (
            f"LỖI: gọi sai tham số cho '{tool_name}' ({e}). "
            f"Chữ ký đúng: {tool_name}{signature}."
        )
    except Exception as e:
        return f"LỖI: công cụ '{tool_name}' gặp sự cố: {type(e).__name__}: {e}"


# ============================================================================
# CẤP 3 — REACT AGENT: VÒNG LẶP
# ============================================================================


def run_react_agent(user_query: str, provider, verbose: bool = True) -> str:
    """
    Vòng lặp ReAct thật: Thought -> Action -> Observation, lặp tới khi có Final Answer
    hoặc chạm phanh MAX_ITERATIONS.
    """
    print(f"\n🤖 [REACT AGENT] Câu hỏi: {user_query}")

    # Prompt được điền ngày hôm nay để Agent tự quy đổi được "ngày mai" sang YYYY-MM-DD
    transcript = f"{build_react_system_prompt()}\nCâu hỏi: {user_query}\n"

    for step in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- 🔄 Vòng lặp ReAct (Step {step}/{MAX_ITERATIONS}) ---")

        raw_output = generate_with_retry(provider, transcript)

        # LLM chết hẳn thì dừng ngay, lặp tiếp chỉ tốn thêm lượt gọi API vô ích
        if is_provider_error(raw_output):
            print(f"❌ Lỗi từ LLM Provider, dừng vòng lặp: {raw_output.strip()}")
            return raw_output.strip()

        output = truncate_at_observation(raw_output)

        if verbose and output:
            for line in output.splitlines():
                if line.strip():
                    print(f"   {line.strip()}")

        # Agent đã có câu trả lời cuối cùng
        if "Final Answer:" in output:
            answer = output.split("Final Answer:", 1)[1].strip()
            print(f"\n🏁 Final Answer: {answer}")
            return answer

        parsed = parse_action(output)
        if parsed is None:
            observation = (
                "LỖI: không đọc được dòng Action. Hãy viết đúng định dạng "
                'Action: tên_công_cụ["tham số 1", "tham số 2"] rồi dừng lại chờ Observation.'
            )
        else:
            tool_name, args = parsed
            observation = execute_tool(tool_name, args, user_query)

        print(f"👁️ Observation: {observation}")
        transcript += f"{output}\nObservation: {observation}\n"

    # 🛡️ Chạm trần vòng lặp
    fallback = MAX_ITERATIONS_FALLBACK.format(max_iterations=MAX_ITERATIONS)
    print(f"\n{fallback}")
    return fallback


# ============================================================================
# ĐIỂM CHẠY CHÍNH
# ============================================================================


def main() -> int:
    print("=" * 62)
    print("🏫 ĐẠI HỌC VINUNI - BÀI LAB 3: CHATBOT VS REACT AGENT")
    print("🏠 Đề tài: Trợ lý Tìm & Đặt lịch Xem Nhà Trọ / Căn hộ Cho thuê")
    print("=" * 62)

    # Kiểm tra API trước, báo lỗi sớm thay vì chết giữa vòng lặp
    healthy, info = check_api_health()
    if not healthy:
        print(f"\n❌ Không kết nối được API cho thuê ({info}).")
        print("   Hãy mở một terminal khác và chạy:")
        print("   uvicorn src.rental_api.server:app --port 8000")
        return 1
    print(f"🌐 API cho thuê: OK ({info})")

    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    print(f"🔌 LLM Provider: {provider.__class__.__name__} (Model: {model_name})")

    tests = load_test_cases()
    print(f"✅ Đã tải {len(tests)} Test Cases từ config/test_cases.json")

    argument = sys.argv[1] if len(sys.argv) > 1 else None

    # Chạy một câu hỏi tự nhập
    if argument and not argument.isdigit():
        run_baseline_chatbot(argument, provider)
        run_react_agent(argument, provider)
        return 0

    # Chạy một test case cụ thể theo id
    if argument:
        selected = [t for t in tests if str(t["id"]) == argument]
        if not selected:
            print(f"\n❌ Không có test case id={argument}.")
            return 1
    else:
        selected = tests

    for case in selected:
        print("\n" + "=" * 62)
        print(f"📋 TEST CASE #{case['id']} — {case['category']}")
        print(f"❓ {case['question']}")
        print(f"🎯 Kỳ vọng: {case['expected_behavior']}")
        print("=" * 62)

        run_baseline_chatbot(case["question"], provider)
        run_react_agent(case["question"], provider)

    print("\n" + "=" * 62)
    print("🎉 Đã chạy xong toàn bộ test cases.")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
