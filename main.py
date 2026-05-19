import json
import os
import sys
from enum import Enum

import pandas as pd
import plotly.express as px
import asyncio
from fastapi import FastAPI, Response, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

# ==========================================
# 1. コンフィグの読み込みと動的セットアップ
# ==========================================
CONFIG_FILE = "config.json"

if not os.path.exists(CONFIG_FILE):
    print(f"[FATAL ERROR] {CONFIG_FILE} が見つかりません。作成してください。")
    sys.exit(1)

try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
except json.JSONDecodeError as e:
    print(
        f"[FATAL ERROR] {CONFIG_FILE} のフォーマットが不正です（カンマ抜けや空ファイルなど）: {e}"
    )
    sys.exit(1)

# 許可するフェーズのリストを自動生成
allowed_phases_dict = {"WAITING": "WAITING"}
for q in config["questions"]:
    allowed_phases_dict[f"EVALUATE_{q['id']}"] = f"EVALUATE_{q['id']}"
    allowed_phases_dict[f"SHOW_RESULT_{q['id']}"] = f"SHOW_RESULT_{q['id']}"

# FastAPIのバリデーション用に動的なEnumクラスを作成
AllowedPhase = Enum("AllowedPhase", allowed_phases_dict)

# Load HTML templates into memory for performance
with open("client.html", "r", encoding="utf-8") as f:
    CLIENT_HTML = f.read()

with open("screen.html", "r", encoding="utf-8") as f:
    SCREEN_HTML = f.read()

app = FastAPI()


class ExperimentState:
    def __init__(self):
        self.current_phase = AllowedPhase["WAITING"]  # type: ignore[index]
        self.client_queues = set()
        self.screen_queues = set()


state = ExperimentState()
DATA_FILE = "data.jsonl"


def save_data(data_dict):
    with open(DATA_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(data_dict) + "\n")


# ==========================================
# 2. HTML配信 (コントローラーは動的生成)
# ==========================================
@app.get("/")
async def get_client_html():
    return HTMLResponse(CLIENT_HTML)


@app.get("/screen")
async def get_screen_html():
    return HTMLResponse(SCREEN_HTML)


@app.get("/controller")
async def generate_controller_html():
    """config.jsonからコントローラー画面を動的に生成する"""

    # 質問ごとのボタンHTMLを生成
    buttons_html = ""
    for q in config["questions"]:
        buttons_html += f"""
        <div class="group">
            <h3>{q["id"]}: {q["title"]}</h3>
            <div class="grid">
                <button onclick="sendPhase('EVALUATE_{q["id"]}')">START {q["id"]}</button>
                <button onclick="sendPhase('SHOW_RESULT_{q["id"]}')">SHOW RESULT {q["id"]}</button>
            </div>
        </div>
        """

    # ベースとなるHTMLに埋め込む
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <title>SITU コントローラー</title>
        <style>
            body {{ font-family: sans-serif; background: #1a1a1c; color: #eee; padding: 30px; text-align: center; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
            .status-card {{ background: #2a2a2e; padding: 20px; border-radius: 12px; margin-bottom: 30px; border: 1px solid #444; }}
            .current-phase {{ font-size: 1.5rem; color: #ccff00; font-weight: bold; }}
            .group {{ background: #2a2a2e; padding: 15px; border-radius: 12px; margin-bottom: 20px; text-align: left; }}
            h3 {{ margin-top: 0; border-left: 4px solid #ccff00; padding-left: 10px; }}
            .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
            button {{ padding: 15px; font-size: 1rem; cursor: pointer; background: #3a3a3e; color: #fff; border: 1px solid #555; border-radius: 8px; transition: 0.2s; }}
            button:hover {{ background: #4a4a4e; border-color: #ccff00; }}
            button:active {{ transform: scale(0.98); }}
            .btn-waiting {{ grid-column: span 2; background: #442222; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{config["workshop_title"]}</h1>
            <div class="status-card">
                <div>CURRENT PHASE</div>
                <div id="status" class="current-phase">WAITING</div>
            </div>

            <div class="group">
                <h3>Common</h3>
                <div class="grid">
                    <button class="btn-waiting" onclick="sendPhase('WAITING')">RESET / WAITING</button>
                </div>
            </div>

            {buttons_html}

        </div>

        <script>
            async function sendPhase(phase) {{
                try {{
                    const res = await fetch(`/control/phase/${{phase}}`, {{ method: 'POST' }});
                    if (!res.ok) throw new Error("Invalid Phase");
                    document.getElementById('status').innerText = phase;
                }} catch (e) {{
                    alert("Error: " + e.message);
                }}
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html_content)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


# ==========================================
# 3. API & SSE ロジック
# ==========================================
class SubmitData(BaseModel):
    client_id: str
    response: str
    rt: int


@app.post("/submit")
async def submit_response(data: SubmitData):
    if not state.current_phase.value.startswith("EVALUATE"):
        return {"status": "ignored", "reason": "not in evaluate phase"}

    save_data(
        {
            "client_id": data.client_id,
            "phase": state.current_phase.value,
            "response": data.response,
            "rt": data.rt,
        }
    )
    await update_screen()
    return {"status": "ok"}


@app.post("/control/phase/{new_phase}")
async def set_phase(new_phase: AllowedPhase):
    state.current_phase = new_phase

    message = json.dumps({"type": "phase_change", "phase": new_phase.value})
    for q in list(state.client_queues):
        try:
            await q.put(message)
        except Exception:
            pass

    if new_phase.value.startswith("SHOW_RESULT"):
        await update_screen()

    return {"status": "ok", "current_phase": state.current_phase}


async def update_screen():
    try:
        # 1. データの読み込み
        df = pd.read_json(DATA_FILE, lines=True)
        if not isinstance(df, pd.DataFrame) or "phase" not in df.columns:
            print("[DEBUG] データが存在しないか、空です")
            return

        # 2. ターゲットフェーズの特定 (例: SHOW_RESULT_Q3 -> EVALUATE_Q3)
        target_phase = state.current_phase.value.replace("SHOW_RESULT", "EVALUATE")
        df_filtered = df[df["phase"] == target_phase]

        print(
            f"[DEBUG] {target_phase} の集計を開始。抽出されたデータ: {len(df_filtered)}件"
        )

        # 3. グラフ用データの生成
        if df_filtered.empty:
            counts = pd.DataFrame({"response": ["No Data"], "count": [0]})
        else:
            # 通常の集計処理
            counts = df_filtered["response"].value_counts().reset_index()  # type: ignore[union-attr]
            counts.columns = ["response", "count"]

        title_text = f"RESULT: {target_phase}"  # グラフにタイトルをつける

        # 4. グラフの描画
        fig = px.bar(
            counts,
            x="response",
            y="count",
            template="plotly_dark",
            color_discrete_sequence=["#ccff00"],
            title=title_text,
        )

        # 5. デザインの適用
        fig.update_layout(
            font=dict(family="Zen Kaku Gothic New", size=24),
            margin=dict(
                l=20, r=20, t=80, b=20
            ),  # タイトルのために上部の余白(t)を広げる
            paper_bgcolor="#0f0f11",
            plot_bgcolor="#0f0f11",
            xaxis_title=None,
            yaxis_title="Votes",
            title_x=0.5,
            title_font_color="#ffffff",  # タイトルを中央揃え
        )

        # 6. スクリーンへの送信
        graph_json = fig.to_json()
        message = json.dumps({"type": "show_result", "chart_data": graph_json})
        for q in list(state.screen_queues):
            try:
                await q.put(message)
            except Exception:
                pass
    except Exception as e:
        print(f"[ERROR] Update error: {e}")


@app.get("/sse/client")
async def sse_client(request: Request):
    async def event_generator():
        q = asyncio.Queue()
        state.client_queues.add(q)
        try:
            # 接続時に現在のフェーズを送信
            initial_msg = json.dumps({"type": "phase_change", "phase": state.current_phase.value})
            yield f"data: {initial_msg}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                # キューからメッセージを取得
                message = await q.get()
                yield f"data: {message}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            state.client_queues.remove(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/sse/screen")
async def sse_screen(request: Request):
    async def event_generator():
        q = asyncio.Queue()
        state.screen_queues.add(q)
        try:
            while True:
                if await request.is_disconnected():
                    break
                message = await q.get()
                yield f"data: {message}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            state.screen_queues.remove(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
