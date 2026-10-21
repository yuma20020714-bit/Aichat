import streamlit as st
from google import genai
from google.genai import types
import base64
import json

# ==========================================
# ⚙️ 設定値
# ==========================================
# モデル名の初期値（サイドバーで書き換えられるので、古くなってもコード修正は不要）
DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_IMAGE_MODEL = "imagen-3.0-generate-002"  # ※無料キーだと使えないことが多い（有料枠向け）
KEEP_RECENT = 20      # 要約せずそのまま送る直近のメッセージ数（20 = 約10往復）
SUMMARIZE_CHUNK = 10  # 一度に要約へ回すメッセージ数
IMAGE_CONTEXT_MSGS = 10  # 画像の情景づくりに使う直近のメッセージ数（ユーザー発言も含む）

st.set_page_config(page_title="完全無料AIシミュレーター", page_icon="🎭", layout="wide")


# ==========================================
# 🎨 背景画像CSS
# ==========================================
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
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# ==========================================
# 🧠 セッション状態の初期化
# ==========================================
DEFAULTS = {
    "messages": [],            # 会話ログ（テキスト＋画像）
    "bg_image_bytes": None,
    "auto_summary": "",        # 自動で作られるあらすじ
    "facts": "",               # 自動で溜まる重要事実メモ
    "summarized_count": 0,     # 要約済みのテキストメッセージ数
    "summary_ver": 0,          # 自動欄の表示を更新するためのカウンタ
    "char_name": "ツンデレな幼なじみ",
    "char_setting": (
        "・名前：アリス\n"
        "・口調：ツンツンしているけど本当は心配性。「〜じゃない！」「べ、別に…」など\n"
        "・関係：幼なじみ\n"
        "・絶対ルール：勝手にユーザーの行動やセリフを描写しないこと。"
    ),
    "story_summary": "放課後、2人で誰もいない教室で残って話している。",
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# 読み込みボタンで予約されたデータを、ウィジェット生成の前に反映
if "pending_load" in st.session_state:
    data = st.session_state.pop("pending_load")
    st.session_state.messages = data.get("messages", [])
    st.session_state.auto_summary = data.get("auto_summary", "")
    st.session_state.facts = data.get("facts", "")
    st.session_state.summarized_count = data.get("summarized_count", 0)
    st.session_state.char_name = data.get("char_name", st.session_state.char_name)
    st.session_state.char_setting = data.get("char_setting", st.session_state.char_setting)
    st.session_state.story_summary = data.get("story_summary", st.session_state.story_summary)
    st.session_state.bg_image_bytes = None
    st.session_state.summary_ver += 1

if st.session_state.bg_image_bytes:
    set_bg_image(st.session_state.bg_image_bytes)


def text_msgs():
    """画像を除いたテキストの会話だけを返す"""
    return [m for m in st.session_state.messages if m.get("type") != "image"]


# ==========================================
# 📋 サイドバー
# ==========================================
st.title("🎭 自作AIロールプレイ")

with st.sidebar:
    st.header("⚙️ システム設定")
    google_api_key = (st.text_input("Google API Keyを入力", type="password") or "").strip()
    # APIキーに日本語・全角文字が混ざっていると 'ascii' codec エラーになるので事前にチェック
    if google_api_key and not google_api_key.isascii():
        st.error("APIキーに日本語や全角文字が混ざっています。キーだけを貼り直してください。（半角英数字と - _ のみ）")
        google_api_key = ""

    MODEL = st.text_input("💬 チャット用モデル名", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    IMAGE_MODEL = st.text_input("🎨 画像生成モデル名", DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL
    st.caption("「モデルが使えない」系のエラーが出たら、ここを新しい名前に変えればOK。")
    THINKING_LEVEL = st.selectbox(
        "⚡ 思考の深さ（低いほど速い）",
        ["low", "medium", "high", "指定しない"],
        index=0,
        help="返信が遅いときは low がおすすめ。モデルによっては対応していないので、エラーが出たら「指定しない」に。",
    )

    st.markdown("---")
    st.subheader("👤 キャラクター設定")
    char_name = st.text_input("キャラの名前", key="char_name")
    char_setting = st.text_area("詳細設定・ルール", height=150, key="char_setting")
    story_summary = st.text_area("📌 固定の記憶（あらすじ・手動）", height=100, key="story_summary")

    st.markdown("---")
    st.subheader("🧠 自動の記憶")
    st.caption("会話が長くなると自動で更新されます。手で直してもOK。")
    ver = st.session_state.summary_ver
    st.session_state.auto_summary = st.text_area(
        "📖 自動あらすじ",
        value=st.session_state.auto_summary,
        height=150,
        key=f"auto_summary_{ver}",
    )
    st.session_state.facts = st.text_area(
        "📝 重要な事実メモ",
        value=st.session_state.facts,
        height=150,
        key=f"facts_{ver}",
    )

    st.markdown("---")
    st.subheader("💾 セーブ / ロード")
    save_data = {
        "messages": text_msgs(),
        "auto_summary": st.session_state.auto_summary,
        "facts": st.session_state.facts,
        "summarized_count": st.session_state.summarized_count,
        "char_name": char_name,
        "char_setting": char_setting,
        "story_summary": story_summary,
    }
    st.download_button(
        "💾 会話をセーブ（JSONをダウンロード）",
        data=json.dumps(save_data, ensure_ascii=False, indent=2),
        file_name="roleplay_save.json",
        mime="application/json",
    )
    uploaded = st.file_uploader("📂 セーブデータを読み込む", type=["json"])
    if uploaded is not None and st.button("📂 このデータで再開"):
        try:
            st.session_state.pending_load = json.loads(uploaded.getvalue().decode("utf-8"))
            st.rerun()
        except Exception as e:
            st.error(f"読み込みエラー: {e}")

    st.markdown("---")
    st.subheader("🎨 スマホサイズ画像生成")
    gen_img_btn = st.button("🎨 今の状況を画像化 (背景更新)")

    st.markdown("---")
    if st.button("🗑️ 会話を最初からやり直す"):
        st.session_state.messages = []
        st.session_state.bg_image_bytes = None
        st.session_state.auto_summary = ""
        st.session_state.facts = ""
        st.session_state.summarized_count = 0
        st.session_state.summary_ver += 1
        st.rerun()


def get_client():
    return genai.Client(api_key=google_api_key)


def make_config(**kwargs):
    """思考の深さの設定を付けた GenerateContentConfig を作る"""
    if THINKING_LEVEL != "指定しない":
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=THINKING_LEVEL)
    return types.GenerateContentConfig(**kwargs)


def stream_text(stream):
    """ストリームから文字だけを取り出して順に返す（返信を少しずつ表示するため）"""
    for chunk in stream:
        if chunk.text:
            yield chunk.text


# ==========================================
# 🧠 自動要約＆事実メモの更新
# ==========================================
def maybe_update_memory(client):
    """古い会話が溜まったら、要約とメモを更新する。更新したらTrueを返す"""
    texts = text_msgs()
    done = st.session_state.summarized_count
    if len(texts) - done < KEEP_RECENT + SUMMARIZE_CHUNK:
        return False

    chunk = texts[done: done + SUMMARIZE_CHUNK]
    convo = "\n".join(
        f"{'ユーザー' if m['role'] == 'user' else char_name}: {m['content']}" for m in chunk
    )
    prompt = f"""あなたはロールプレイの「記憶係」です。
下の【これまでのあらすじ】【これまでの事実メモ】に、【新しい会話】の内容を反映して更新してください。

【これまでのあらすじ】
{st.session_state.auto_summary or '（まだなし）'}

【これまでの事実メモ】
{st.session_state.facts or '（まだなし）'}

【新しい会話】
{convo}

ルール:
- summary: 物語の流れが分かるあらすじ全体（新旧を統合）。800文字以内。時系列で、重要な出来事・感情の変化・今の状況を残す。
- facts: 後で必ず思い出すべき事実の一覧（ユーザーの好き嫌い・名前・約束・秘密・関係性の変化・持ち物・場所など）。既存の事実は残し、重複は統合し、変化した事実は新しい内容に更新する。1項目は短く1文で。
- 会話に出ていないことは書かない。

次のJSONのみを出力:
{{"summary": "...", "facts": ["...", "..."]}}"""

    try:
        res = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=make_config(response_mime_type="application/json"),
        )
        data = json.loads(res.text)
        st.session_state.auto_summary = str(data.get("summary", "")).strip()
        facts = data.get("facts", [])
        st.session_state.facts = "\n".join(f"・{str(f).lstrip('・- ')}" for f in facts)
        st.session_state.summarized_count = done + SUMMARIZE_CHUNK
        st.session_state.summary_ver += 1
        return True
    except Exception as e:
        # 失敗しても会話は続行（次回また試す）
        st.warning(f"記憶の更新に失敗しました（会話は続けられます）: {e}")
        return False


# ==========================================
# 🖼️ スマホ縦長（9:16）画像生成
# ==========================================
def generate_smartphone_image(context_prompt):
    """成功したらTrue。rerunは呼び出し側で行う"""
    if not google_api_key:
        st.error("左のサイドバーにGoogle API Keyを入力してください！")
        return False

    with st.spinner("🎨 スマホサイズの背景画像を生成中..."):
        try:
            client = get_client()
            # 直近の会話（ユーザーの発言も含めて）を情景の材料にする
            recent_log = "\n".join(
                f"{'ユーザー' if m['role'] == 'user' else char_name}: {m['content']}"
                for m in text_msgs()[-IMAGE_CONTEXT_MSGS:]
            ) or context_prompt
            prompt_request = f"""
            以下の設定と文脈から、縦長（9:16）のスマートフォン壁紙風・高品質アニメイラストの英語プロンプトを1つ作成してください。
            直近の会話の流れをふまえ、特に【最後のやり取り】の場面（場所・時間帯・光・キャラの表情や仕草・位置関係）を描いてください。
            文字出力はプロンプトのみ。
            キャラ設定: {char_setting}
            あらすじ: {story_summary}
            {st.session_state.auto_summary}
            直近の会話（古い順）:
            {recent_log}
            """
            # 画像用プロンプトを作る（返答が空だった場合は1回だけやり直す）
            image_prompt = None
            p_res = None
            for _ in range(2):
                p_res = client.models.generate_content(
                    model=MODEL, contents=prompt_request, config=make_config()
                )
                if p_res.text and p_res.text.strip():
                    image_prompt = p_res.text.strip()
                    break
            if not image_prompt:
                reason = ""
                try:
                    reason = f"（終了理由: {p_res.candidates[0].finish_reason}）"
                except Exception:
                    pass
                st.error(
                    f"画像用のプロンプトを作れませんでした。モデルの返答が空でした{reason}。"
                    "もう一度ボタンを押すか、「思考の深さ」を変えて試してください。"
                )
                return False

            result = client.models.generate_images(
                model=IMAGE_MODEL,
                prompt=image_prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="9:16",
                    output_mime_type="image/jpeg",
                ),
            )
            if not result.generated_images:
                st.error("画像が生成されませんでした（安全フィルタの可能性）。")
                return False

            img_bytes = result.generated_images[0].image.image_bytes
            st.session_state.messages.append(
                {"role": "assistant", "content": img_bytes, "type": "image"}
            )
            st.session_state.bg_image_bytes = img_bytes
            return True

        except Exception as e:
            msg = f"画像生成エラー: {e}"
            # 画像モデル側の問題っぽいときだけ、課金の注意書きを付ける
            if any(k in str(e).lower() for k in ["imagen", "billed", "billing", "permission", "not found", "404", "403"]):
                msg += "\n\n※ Imagenは無料のAPIキーだと使えないことがあります（課金設定が必要なモデルです）。"
            st.error(msg)
            return False


# ==========================================
# 💬 チャット表示
# ==========================================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("type") == "image":
            st.image(msg["content"], caption="📱 生成画像")
        else:
            st.write(msg["content"])

# ボタンによる画像生成
if gen_img_btn:
    last_reply = next(
        (m["content"] for m in reversed(st.session_state.messages)
         if m["role"] == "assistant" and m.get("type") != "image"),
        "物語のシーン",
    )
    if generate_smartphone_image(last_reply):
        st.rerun()

# ==========================================
# 💬 チャット入力・返信
# ==========================================
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

【固定の記憶（あらすじ・最重要）】
{story_summary}

【ここまでの物語のあらすじ（自動記録）】
{st.session_state.auto_summary or '（まだなし）'}

【忘れてはいけない事実メモ】
{st.session_state.facts or '（まだなし）'}

上の記憶と矛盾しないように返答してください。事実メモにある内容は自然に思い出して会話に活かしてください。
"""

        # 要約済みより後の会話だけを送る（要約に入った分は、あらすじとして渡している）
        recent = text_msgs()[st.session_state.summarized_count:]
        while recent and recent[0]["role"] != "user":
            recent = recent[1:]
        contents = [
            {"role": "user" if m["role"] == "user" else "model",
             "parts": [{"text": str(m["content"])}]}
            for m in recent
        ]

        reply = None
        with st.chat_message("assistant"):
            try:
                # ストリーミング：生成された分から順に表示する（待ち時間の体感が大きく減る）
                stream = client.models.generate_content_stream(
                    model=MODEL,
                    contents=contents,
                    config=make_config(system_instruction=system_instruction),
                )
                reply = st.write_stream(stream_text(stream))
                if not reply:
                    raise ValueError("返信が空でした（安全フィルタに引っかかった可能性があります）")
                st.session_state.messages.append({"role": "assistant", "content": reply})
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
                reply = None
                # 失敗した発言は取り消して、次回送り直せるようにする
                if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
                    st.session_state.messages.pop()

        # rerunはtry/exceptの外で呼ぶ
        if reply is not None:
            need_rerun = False
            with st.spinner("🧠 記憶を整理中..."):
                if maybe_update_memory(client):
                    need_rerun = True
            if "(画像生成)" in user_input:
                if generate_smartphone_image(reply):
                    need_rerun = True
            if need_rerun:
                st.rerun()
