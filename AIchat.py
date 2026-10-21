import streamlit as st
from google import genai
import PIL.Image
import io
import base64
import re
import urllib.parse
import requests

# ==========================================
# ⚙️ 画面・CSS（背景＆ナレーション用スタイル）
# ==========================================
st.set_page_config(page_title="完全無料AIシミュレーター", page_icon="🎭", layout="wide")

def set_bg_image(image_bytes):
    encoded = base64.b64encode(image_bytes).decode()
    css = f"""
    <style>
    .stApp {{
        background-image: linear-gradient(rgba(0, 0, 0, 0.65), rgba(0, 0, 0, 0.65)), url("data:image/jpeg;base64,{encoded}");
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}
    div[data-testid="stChatMessage"] {{
        background-color: rgba(0, 0, 0, 0.5) !important;
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 10px;
    }}
    .narration {{
        color: #d1d5db !important;
        font-style: italic;
        background-color: rgba(255, 255, 255, 0.08);
        padding: 2px 6px;
        border-radius: 4px;
        display: inline-block;
        margin: 2px 0;
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# セッション状態の初期化
if "messages" not in st.session_state:
    st.session_state.messages = []
if "bg_image_bytes" not in st.session_state:
    st.session_state.bg_image_bytes = None

DEFAULT_CHARACTERS = {
    "ツンデレ幼なじみ": {
        "name": "アリス",
        "setting": "・名前：アリス\n・口調：ツンツンしているけど本当は心配性。「〜じゃない！」「べ、別に…」など\n・関係：幼なじみ\n・描写ルール：セリフだけでなく、表情や仕草、周囲の情景などのナレーション（*〜*で囲む）を適度に交えて出力すること。",
        "summary": "放課後、2人で誰もいない教室で残って話している。"
    },
    "クーデレ先輩": {
        "name": "シオン",
        "setting": "・名前：シオン\n・口調：静かで冷静。感情を表に出さないが、時々優しい言葉をかける。\n・関係：図書委員の先輩\n・描写ルール：セリフだけでなく、表情や仕草、周囲の情景などのナレーション（*〜*で囲む）を適度に交えて出力すること。",
        "summary": "放課後の図書室で、2人で本棚の整理をしている。"
    }
}

if "characters" not in st.session_state:
    st.session_state.characters = DEFAULT_CHARACTERS

if st.session_state.bg_image_bytes:
    set_bg_image(st.session_state.bg_image_bytes)

st.title("🎭 自作AIロールプレイ (完全版)")

# --- サイドバー（設定エリア） ---
with st.sidebar:
    st.header("⚙️ システム設定")
    google_api_key = st.text_input("Google API Keyを入力", type="password")
    
    st.markdown("---")
    st.subheader("👥 キャラクター選択・保存")
    
    char_list = list(st.session_state.characters.keys())
    selected_name = st.selectbox("登録キャラから選ぶ", char_list)
    
    current_char = st.session_state.characters.get(selected_name, {})
    
    char_name = st.text_input("キャラの名前", current_char.get("name", ""))
    char_setting = st.text_area("詳細設定・ルール", current_char.get("setting", ""), height=120)
    story_summary = st.text_area("📌 記憶（あらすじ・自動更新）", current_char.get("summary", ""), height=100)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 設定を保存"):
            st.session_state.characters[selected_name] = {
                "name": char_name,
                "setting": char_setting,
                "summary": story_summary
            }
            st.success("保存しました！")
            st.rerun()
            
    with col2:
        if st.button("➕ 新規キャラ"):
            new_key = f"新規キャラ_{len(st.session_state.characters)+1}"
            st.session_state.characters[new_key] = {
                "name": "新規キャラ",
                "setting": "設定を入力してください",
                "summary": "あらすじを入力してください"
            }
            st.rerun()

    st.markdown("---")
    st.subheader("📊 リアルタイム記憶メーター")
    total_chars = sum(len(str(m.get("content", ""))) for m in st.session_state.messages) + len(char_setting) + len(story_summary)
    token_est = int(total_chars * 1.5)
    st.progress(min(token_est / 8000, 1.0))
    st.caption(f"現在の記憶容量: 約 {token_est} / 8000 トークン")

    st.markdown("---")
    st.subheader("🎨 スマホサイズ画像生成")
    gen_img_btn = st.button("🎨 今の状況を画像化 (背景更新)")

    st.markdown("---")
    if st.button("🗑️ 会話を最初からやり直す"):
        st.session_state.messages = []
        st.session_state.bg_image_bytes = None
        st.rerun()

def get_client():
    return genai.Client(api_key=google_api_key)

def format_narration_text(text):
    formatted = re.sub(r'\*(.*?)\*', r'<span class="narration">*\1*</span>', text)
    return formatted

# ==========================================
# 🧠 記憶圧縮（自動要約）機能
# ==========================================
def summarize_memory_if_needed(client):
    if len(st.session_state.messages) >= 10:
        with st.spinner("🧠 昔の会話を要約して記憶を整理中..."):
            try:
                chat_text = ""
                for m in st.session_state.messages:
                    if m.get("type") != "image":
                        chat_text += f"{m['role']}: {m['content']}\n"
                
                sum_prompt = f"""
以下のロールプレイのこれまでの会話履歴と現在のあらすじから、今後のロールプレイで絶対に忘れてはならない重要な出来事・感情の変化・約束事を含めた「最新のあらすじ（200文字程度）」を作成してください。
【現在のあらすじ】
{story_summary}
【これまでの会話】
{chat_text}
"""
                response = client.models.generate_content(
                    model='gemini-3.8-flash',
                    contents=sum_prompt
                )
                new_summary = response.text.strip()
                st.session_state.characters[selected_name]["summary"] = new_summary
                st.session_state.messages = st.session_state.messages[-2:]
                st.toast("🧠 記憶を要約してあらすじを更新しました！", icon="✨")
            except Exception as e:
                print(f"要約エラー: {e}")

# ==========================================
# 🖼️ 高速・エラーなし背景画像生成（無料API）
# ==========================================
def generate_smartphone_image(context_prompt):
    if not google_api_key:
        st.error("左のサイドバーにGoogle API Keyを入力してください！")
        return

    with st.spinner("🎨 スマホサイズの背景画像を生成中..."):
        try:
            client = get_client()
            prompt_request = f"""
            以下の設定と文脈から、スマートフォン壁紙風の美しいアニメ背景イラストの英語プロンプトを1つだけ作成してください（余計な文字は出力せずプロンプトの英語のみ）。
            キャラ設定: {char_setting}
            あらすじ: {story_summary}
            直近の会話: {context_prompt}
            """
            p_res = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=[{"role": "user", "parts": [{"text": prompt_request}]}]
            )
            image_prompt = p_res.text.strip()

            # 無料の高速画像生成URLを作成
            encoded_prompt = urllib.parse.quote(image_prompt + ", high quality anime background, masterpiece")
            img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=540&height=960&nologo=true&seed=42"

            # 画像データをダウンロード
            res = requests.get(img_url)
            if res.status_code == 200:
                img_bytes = res.content
                image_pil = PIL.Image.open(io.BytesIO(img_bytes))
                st.session_state.messages.append({"role": "assistant", "content": image_pil, "type": "image"})
                st.session_state.bg_image_bytes = img_bytes
                st.rerun()
            else:
                st.error("画像の取得に失敗しました。")

        except Exception as e:
            st.error(f"画像生成エラー: {e}")

# ==========================================
# 💬 チャット表示・処理
# ==========================================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("type") == "image":
            st.image(msg["content"], caption="📱 生成画像", use_container_width=True)
        else:
            st.markdown(format_narration_text(msg["content"]), unsafe_allow_html=True)

if gen_img_btn:
    last_reply = next((m["content"] for m in reversed(st.session_state.messages) if m["role"] == "assistant" and m.get("type") != "image"), "物語のシーン")
    generate_smartphone_image(last_reply)

if user_input := st.chat_input("メッセージを入力... (行動は *歯磨きする* , 画像変更は (画像生成))"):
    if not google_api_key:
        st.error("左のサイドバーにGoogle API Keyを入力してください！")
    else:
        st.chat_message("user").markdown(format_narration_text(user_input), unsafe_allow_html=True)
        st.session_state.messages.append({"role": "user", "content": user_input})

        client = get_client()
        summarize_memory_if_needed(client)

        system_instruction = f"""
あなたは【{char_name}】になりきってロールプレイをしてください。
【キャラクター設定】
{char_setting}
【現在までの物語の記憶（自動更新されるあらすじ）】
{story_summary}

【重要ルール・演出指示】
- セリフだけでなく、キャラクターの行動、心理描写、周囲の情景などのナレーションを必ず適度に交えて返答してください。
- 心情や行動、情景描写の箇所は必ず半角のアスタリスク `*` で囲んでください（例: *少し頬を赤らめてそっぽを向く*）。
"""

        contents = []
        for m in st.session_state.messages:
            if m.get("type") == "image": continue
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": str(m["content"])}]})

        with st.chat_message("assistant"):
            try:
                # ストリーミング（Geminiのように波のように文字が流れてくる演出）
                response = client.models.generate_content_stream(
                    model='gemini-3.8-flash',
                    contents=contents,
                    config={'system_instruction': system_instruction}
                )
                
                def stream_data():
                    for chunk in response:
                        if chunk.text:
                            yield chunk.text

                # 波のように文字をリアルタイム出力しつつ、ナレーション部分を装飾
                reply = st.write_stream(stream_data())
                
                st.session_state.messages.append({"role": "assistant", "content": reply})

                if "(画像生成)" in user_input:
                    generate_smartphone_image(reply)

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
