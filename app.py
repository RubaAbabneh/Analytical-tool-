# -*- coding: utf-8 -*-
"""
app.py — تطبيق Flask لمرصد التقديرات السكانية.
للتشغيل محلياً:  python app.py
ثم فتح المتصفّح على:  http://127.0.0.1:5000
"""

import os
import uuid
import tempfile
from flask import Flask, render_template, request, jsonify

import analysis as A
import nlu
import voice

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB

# مخزن بيانات في الذاكرة (تطبيق محلي بمستخدم واحد). المفتاح: data_id.
STORE = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files or request.files["file"].filename == "":
        return jsonify({"ok": False, "error": "لم يتم اختيار أي ملف."}), 400
    f = request.files["file"]
    name = f.filename
    if not name.lower().endswith((".xlsx", ".xls", ".csv")):
        return jsonify({"ok": False, "error": "الصيغة غير مدعومة. يُرجى رفع ملف Excel‏ (.xlsx) أو CSV."}), 400
    try:
        raw = A.read_table(f.read(), name)
        long_df, meta = A.standardize(raw)
        if long_df.empty:
            return jsonify({"ok": False, "error": "الملف لا يحتوي على بيانات صالحة بعد المعالجة."}), 400
        brief = A.build_brief(long_df, raw)
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"تعذّرت معالجة الملف: {e}"}), 400

    data_id = uuid.uuid4().hex
    STORE[data_id] = {"long": long_df, "raw": raw, "meta": meta}
    return jsonify({"ok": True, "data_id": data_id, "filename": name, "meta": meta, "brief": brief})


def _get(data_id):
    return STORE.get(data_id)


@app.route("/api/filters", methods=["POST"])
def api_filters():
    body = request.get_json(force=True)
    d = _get(body.get("data_id"))
    if not d:
        return jsonify({"ok": False, "error": "انتهت صلاحية البيانات. يُرجى إعادة رفع الملف."}), 400
    opts = A.cascading_options(
        d["long"], body.get("governorate"), body.get("region"), body.get("neighborhood")
    )
    return jsonify({"ok": True, "options": opts, "years": sorted(d["long"][A.YEAR].unique().tolist())})


@app.route("/api/query", methods=["POST"])
def api_query():
    body = request.get_json(force=True)
    d = _get(body.get("data_id"))
    if not d:
        return jsonify({"ok": False, "error": "انتهت صلاحية البيانات. يُرجى إعادة رفع الملف."}), 400

    long_df = d["long"]
    intent = body.get("intent")
    f = body.get("filters") or {}
    params = body.get("params") or {}

    try:
        if intent == "by_governorate":
            res = A.q_by_governorate(long_df, params.get("year"))
        elif intent == "age_distribution":
            res = A.q_age_distribution(long_df, f, params.get("year"))
        elif intent == "timeseries":
            res = A.q_timeseries(long_df, f)
        elif intent == "growth":
            res = A.q_growth(long_df, f, params.get("year_from"), params.get("year_to"))
        elif intent == "custom":
            res = A.q_custom(long_df, f, params.get("op", "sum"))
        elif intent == "forecast":
            res = A.q_forecast(long_df, f, params.get("horizon", 5))
        else:
            return jsonify({"ok": False, "error": "سؤال غير معروف."}), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"تعذّر تنفيذ العملية: {e}"}), 400

    return jsonify({"ok": True, "result": res})

@app.route("/api/voice_text", methods=["POST"])
def api_voice_text():
    """يستقبل نصاً مُعرَّفاً من Web Speech API ويحلّله مباشرة دون تفريغ صوتي."""
    body = request.get_json(force=True)
    data_id = body.get("data_id")
    text = (body.get("text") or "").strip()

    d = _get(data_id)
    if not d:
        return jsonify({"ok": False, "error": "انتهت صلاحية البيانات. يُرجى إعادة رفع الملف."}), 400
    if not text:
        return jsonify({"ok": False, "error": "النص فارغ."}), 400

    try:
        res = nlu.match(text, d["long"])
        res["ok"] = True
        res["text"] = text
        return jsonify(res)
    except Exception as e:
        return jsonify({"ok": False, "error": f"تعذّر تحليل السؤال: {e}"}), 400
    

    
@app.route("/api/voice", methods=["POST"])
def api_voice():
    """يستقبل تسجيلاً صوتياً، يفرّغه نصاً، ثم يطابقه بإحدى الأسئلة المتاحة."""
    data_id = request.form.get("data_id")
    d = _get(data_id)
    if not d:
        return jsonify({"ok": False, "error": "انتهت صلاحية البيانات. يُرجى إعادة رفع الملف."}), 400
    if "audio" not in request.files:
        return jsonify({"ok": False, "error": "لم يصل أي تسجيل صوتي."}), 400

    f = request.files["audio"]
    tmp_path = None
    try:
        suffix = os.path.splitext(f.filename or "")[1] or ".webm"
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        f.save(tmp_path)
        text = voice.transcribe(tmp_path, language="ar")
        if not text:
            return jsonify({"ok": True, "text": "", "intent": None,
                            "message": "لم ألتقط كلاماً واضحاً. يُرجى المحاولة مجدّداً بصوت أعلى."})
        res = nlu.match(text, d["long"])
        res["ok"] = True
        res["text"] = text
        return jsonify(res)
    except voice.VoiceUnavailable as e:
        return jsonify({"ok": False, "error": str(e)}), 503
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"تعذّر معالجة الطلب الصوتي: {e}"}), 400
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


if __name__ == "__main__":
    # debug=True يسهّل التطوير محلياً؛ عطّليه عند النشر.
    app.run(host="0.0.0.0", port=5000, debug=True)