import streamlit as st
from google import genai
import PIL.Image
import io
import base64
import re
import urllib.parse
import requests

# ==========================================
# ⚙️ 画面・CSS（LINE風チャット＆デザイン調整）
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
    /* LINE風メッセージコンテナ */
    .chat-row-user {{
        display: flex;
        justify-content: flex-end;
        margin: 8px 0;
    }}
    .chat-row-ai {{
        display: flex;
        justify-content: flex-start;
        margin: 8px 0;
    }}
    .chat-bubble-user {{
        background-color: rgba(0, 120, 255, 0.8) !important;
        color: white;
        padding: 10px 14px;
        border-radius: 15px 15px 0 15px;
        max-width: 70%;
        word-break: break-all;
    }}
    .chat-bubble-ai {{
        background-color: rgba(30, 30, 30, 0.85) !important;
        color: white;
        padding: 10px 14px;
        border-radius: 15px 15px 15px 0;
        max-width: 70%;
        word-break: break-all;
    }}
    /* ナレーション（*〜*）のスタイル */
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

# APIキーの自動取得（Secretsまたはサイドバー）
api_key_from_secret = st.secrets.get("GOOGLE_API_KEY", "")

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

# --- サイドバー（設定エリア） ---
with st.sidebar:
    st.header("⚙️ 設定")
    if not api_key_from_secret:
        google_api_key = st.text_input("Google API Keyを入力", type="password")
    else:
        google_api_key = api_key_from_secret
        st.success("API Key読込済み（自動）")
    
    st.markdown("---")
    st.subheader("👥 キャラクター")
    
    char_list = list(st.session_state.characters.keys())
    selected_name = st.selectbox("登録キャラから選ぶ", char_list)
    
    current_char = st.session_state.characters.get(selected_name, {})
    
    char_name = st.text_input("キャラの名前", current_char.get("name", ""))
    char_setting = st.text_area("詳細設定・ルール", current_char.get("setting", ""), height=120)
    story_summary = st.text_area("📌 記憶（あらすじ・自動更新）", current_char.get("summary", ""), height=100)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 設定保存"):
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
    st.subheader("📊 記憶メーター")
    total_chars = sum(len(str(m.get("content", ""))) for m in st.session_state.messages) + len(char_setting) + len(story_summary)
    token_est = int(total_chars * 1.5)
    st.progress(min(token_est / 8000, 1.0))
    st.caption(f"容量: 約 {token_est} / 8000 トークン")

    st.markdown("---")
    st.subheader("🎨 背景画像")
    gen_img_btn = st.button("🎨 今の状況を画像化")

    st.markdown("---")
    if st.button("🗑️ 最初からやり直す"):
        st.session_state.messages = []
        st.session_state.bg_image_bytes = None
        st.rerun()

# タイトルは会話が始まっていない時だけ表示
if len(st.session_state.messages) == 0:
    st.title(f"🎭 {char_name} とのロールプレイ")

def get_client():
    return genai.Client(api_key=google_api_key)

def format_narration_text(text):
    return re.sub(r'\*(.*?)\*', r'<span class="narration">*\1*</span>', text)

def summarize_memory_if_needed(client):
    if len(st.session_state.messages) >= 10:
        with st.spinner("🧠 記憶を整理中..."):
            try:
                chat_text = ""
                for m in st.session_state.messages:
                    if m.get("type") != "image":
                        chat_text += f"{m['role']}: {m['content']}\n"
                
                sum_prompt = f"""
以下の会話とあらすじから、今後のロールプレイで重要な「最新のあらすじ（200文字程度）」を作成してください。
【現在のあらすじ】
{story_summary}
【これまでの会話】
{chat_text}
"""
                response = client.models.generate_content(model='gemini-3.8-flash', contents=sum_prompt)
                st.session_state.characters[selected_name]["summary"] = response.text.strip()
                st.session_state.messages = st.session_state.messages[-2:]
                st.toast("🧠 あらすじを自動更新しました！", icon="✨")
            except Exception as e:
                print(f"要約エラー: {e}")

def generate_smartphone_image(context_prompt):
    if not google_api_key:
        st.error("APIキーが設定されていません！")
        return

    with st.spinner("🎨 背景画像を生成中..."):
        try:
            client = get_client()
            prompt_request = f"""
            スマートフォン壁紙風の美しいアニメ背景イラストの英語プロンプトを1つ作成（英語のみ）。
            キャラ設定: {char_setting}
            あらすじ: {story_summary}
            直近の会話: {context_prompt}
            """
            p_res = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=[{"role": "user", "parts": [{"text": prompt_request}]}]
            )
            image_prompt = p_res.text.strip()
            encoded_prompt = urllib.parse.quote(image_prompt + ", high quality anime background, masterpiece")
            img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=540&height=960&nologo=true&seed=42"

            res = requests.get(img_url)
            if res.status_code == 200:
                img_bytes = res.content
                image_pil = PIL.Image.open(io.BytesIO(img_bytes))
                st.session_state.messages.append({"role": "assistant", "content": image_pil, "type": "image"})
                st.session_state.bg_image_bytes = img_bytes
                st.rerun()
        except Exception as e:
            st.error(f"画像生成エラー: {e}")

# ==========================================
# 💬 LINE風チャット表示（カスタムHTML）
# ==========================================
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(f'<div class="chat-row-user"><div class="chat-bubble-user">{format_narration_text(str(msg["content"]))}</div></div>', unsafe_allow_html=True)
    else:
        if msg.get("type") == "image":
            st.image(msg["content"], caption="📱 生成画像", use_container_width=True)
        else:
            st.markdown(f'<div class="chat-row-ai"><div class="chat-bubble-ai">{format_narration_text(str(msg["content"]))}</div></div>', unsafe_allow_html=True)

if gen_img_btn:
    last_reply = next((m["content"] for m in reversed(st.session_state.messages) if m["role"] == "assistant" and m.get("type") != "image"), "物語のシーン")
    generate_smartphone_image(last_reply)

if user_input := st.chat_input("メッセージを入力... (行動は *歯磨きする* , 画像変更は (画像生成))"):
    if not google_api_key:
        st.error("APIキーが設定されていません！")
    else:
        # ユーザー（自分）のメッセージを即座に右側に表示
        st.markdown(f'<div class="chat-row-user"><div class="chat-bubble-user">{format_narration_text(user_input)}</div></div>', unsafe_allow_html=True)
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

        # 相手（AI）のメッセージを左側にストリーミング出力
        with st.container():
            placeholder = st.empty()
            try:
                response = client.models.generate_content_stream(
                    model='gemini-3.8-flash',
                    contents=contents,
                    config={'system_instruction': service_instruction if 'service_instruction' in locals() else system_instruction}
                )
                
                full_reply = ""
                for chunk in response:
                    if chunk.text:
                        full_reply += chunk.text
                        placeholder.markdown(f'<div class="chat-row-ai"><div class="chat-bubble-ai">{format_narration_text(full_reply)}</div></div>', unsafe_allow_html=True)
                
                st.session_state.messages.append({"role": "assistant", "content": full_reply})

                if "(画像生成)" in user_input:
                    generate_smartphone_image(full_reply)

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
