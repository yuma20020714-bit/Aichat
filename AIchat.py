import streamlit as st
from google import genai
from google.genai import types
import PIL.Image
import io
import base64

# ==========================================
# ⚙️ 画面・CSS（背景画像設定）
# ==========================================
st.set_page_config(page_title="完全無料AIシミュレーター", page_icon="🎭", layout="wide")

# 背景画像をCSSで動的にセットする関数
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
    /* チャット吹き出し背景を見やすく半透明化 */
    div[data-testid="stChatMessage"] {{
        background-color: rgba(0, 0, 0, 0.5) !important;
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 10px;
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# セッション状態の初期化
if "messages" not in st.session_state:
    st.session_state.messages = []
if "bg_image_bytes" not in st.session_state:
    st.session_state.bg_image_bytes = None

# すでに背景画像があればセット
if st.session_state.bg_image_bytes:
    set_bg_image(st.session_state.bg_image_bytes)

st.title("🎭 自作AIロールプレイ")

# --- サイドバー（設定エリア・スマホで折りたたみ可能） ---
with st.sidebar:
    st.header("⚙️ システム設定")
    google_api_key = st.text_input("Google API Keyを入力", type="password")
    
    st.markdown("---")
    st.subheader("👤 キャラクター設定")
    char_name = st.text_input("キャラの名前", "ツンデレな幼なじみ")
    char_setting = st.text_area("詳細設定・ルール", 
        "・名前：アリス\n"
        "・口調：ツンツンしているけど本当は心配性。「〜じゃない！」「べ、別に…」など\n"
        "・関係：幼なじみ\n"
        "・絶対ルール：勝手にユーザーの行動やセリフを描写しないこと。"
    , height=150)
    
    story_summary = st.text_area("📌 固定の記憶（あらすじ）", "放課後、2人で誰もいない教室で残って話している。", height=100)

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


# ==========================================
# 🖼️ スマホ縦長（9:16）＆背景連動画像生成
# ==========================================
def generate_smartphone_image(context_prompt):
    if not google_api_key:
        st.error("左のサイドバーにGoogle API Keyを入力してください！")
        return

    with st.spinner("🎨 スマホサイズの背景画像を生成中..."):
        try:
            client = get_client()

            # 1. 画像生成用プロンプト作成（スマホ壁紙・縦長用）
            prompt_request = f"""
            以下の設定と文脈から、縦長（9:16）のスマートフォン壁紙風・高品質アニメイラストの英語プロンプトを1つ作成してください。
            文字出力はプロンプトのみ。
            キャラ設定: {char_setting}
            あらすじ: {story_summary}
            直近の会話: {context_prompt}
            """
            p_res = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[{"role": "user", "parts": [{"text": prompt_request}]}]
            )
            image_prompt = p_res.text.strip()

            # 2. スマホ用縦長（aspect_ratio="9:16"）で画像生成
            result = client.models.generate_images(
                model='imagen-3.0-generate-002',
                prompt=image_prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="9:16",  # ★スマホぴったり（9:16）に指定
                    output_mime_type="image/jpeg",
                )
            )

            for generated_image in result.generated_images:
                img_bytes = generated_image.image.image_bytes
                image_pil = PIL.Image.open(io.BytesIO(img_bytes))
                
                # ① チャットログ（履歴）に画像を追加
                st.session_state.messages.append({"role": "assistant", "content": image_pil, "type": "image"})
                # ② 画面全体の背景画像データとして保存（次回生成まで固定）
                st.session_state.bg_image_bytes = img_bytes
                st.rerun()

        except Exception as e:
            st.error(f"画像生成エラー: {e}")


# ==========================================
# 💬 チャット表示・処理
# ==========================================

# 1. チャットログの描画
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("type") == "image":
            st.image(msg["content"], caption="📱 生成画像", use_container_width=True)
        else:
            st.write(msg["content"])

# 2. ボタンによる画像生成
if gen_img_btn:
    last_reply = next((m["content"] for m in reversed(st.session_state.messages) if m["role"] == "assistant" and m.get("type") != "image"), "物語のシーン")
    generate_smartphone_image(last_reply)

# 3. チャット入力（「(画像生成)」キーワードで自動トリガー）
if user_input := st.chat_input("メッセージを入力... (画像変更は「(画像生成)」)"):
    if not google_api_key:
        st.error("左のサイドバーにGoogle API Keyを入力してください！")
    else:
        st.chat_message("user").write(user_input)
        st.session_state.messages.append({"role": "user", "content": user_input})

        client = get_client()

        system_instruction = f"""
あなたは【{char_name}】になりきってロールプレイをしてください。
【キャラクター設定】
{char_setting}
【現在までの物語のあらすじ（絶対忘れてはいけない記憶）】
{story_summary}
"""

        contents = []
        for m in st.session_state.messages:
            if m.get("type") == "image": continue
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": str(m["content"])}]})

        with st.chat_message("assistant"):
            try:
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=contents,
                    config={'system_instruction': system_instruction}
                )
                reply = response.text
                st.write(reply)
                
                st.session_state.messages.append({"role": "assistant", "content": reply})

                # (画像生成) キーワードがあれば縦長画像＆背景変更処理を実行
                if "(画像生成)" in user_input:
                    generate_smartphone_image(reply)

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")