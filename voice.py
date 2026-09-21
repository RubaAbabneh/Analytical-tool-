# -*- coding: utf-8 -*-
"""
voice.py — تفريغ الكلام إلى نص باستخدام Vosk محلياً (يعمل على أي معالج، ودون إنترنت).
استبدل faster-whisper بـ Vosk لتفادي انهيار ctranslate2 (0xC0000005) على بعض المعالجات.

- التحميل كسول: لا يُحمّل النموذج إلا عند أول طلب صوتي.
- مدخلات transcribe: ملف WAV أحادي القناة 16-بت (يرسله المتصفّح بهذه الصيغة جاهزة).
- إن لم يكن Vosk مثبّتاً أو لم يوجد مجلّد النموذج، يُرفع VoiceUnavailable برسالة واضحة
  ويبقى المساعد النصي يعمل طبيعياً.

متغيّر البيئة:
  VOSK_MODEL  مسار مجلّد نموذج اللغة العربية (الافتراضي: ./models/vosk-ar)
"""

import os
import json
import wave

_model = None
_MODEL_PATH = os.environ.get(
    "VOSK_MODEL", os.path.join(os.path.dirname(__file__), "models", "vosk-ar")
)


class VoiceUnavailable(Exception):
    """يُرفع عندما يتعذّر تحميل محرّك أو نموذج التعرّف الصوتي."""


def get_model():
    global _model
    if _model is None:
        try:
            from vosk import Model, SetLogLevel
        except ImportError as e:
            raise VoiceUnavailable(
                "محرّك التعرّف الصوتي Vosk غير مثبّت. يُرجى تثبيته بالأمر: "
                "python -m pip install vosk"
            ) from e

        if not os.path.isdir(_MODEL_PATH):
            raise VoiceUnavailable(
                "لم يُعثر على نموذج اللغة العربية. يُرجى تنزيل "
                "vosk-model-ar-mgb2-0.4 وفكّ الضغط ووضعه في مجلّد: "
                f"{_MODEL_PATH}"
            )

        SetLogLevel(-1)  # إسكات سجلّات Vosk الداخلية
        print(f"[voice] تحميل نموذج Vosk من: {_MODEL_PATH} …", flush=True)
        _model = Model(_MODEL_PATH)
        print("[voice] تم تحميل نموذج التعرّف الصوتي بنجاح.", flush=True)
    return _model


def transcribe(path, language="ar"):
    """تفريغ ملف WAV (أحادي 16-بت) إلى نص عربي. يعيد سلسلة نصية."""
    from vosk import KaldiRecognizer

    model = get_model()
    wf = wave.open(path, "rb")
    try:
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getcomptype() != "NONE":
            raise ValueError("صيغة الصوت غير متوقّعة (يجب أن يكون WAV أحادي القناة 16-بت).")

        rec = KaldiRecognizer(model, wf.getframerate())
        rec.SetWords(False)
        texts = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                part = json.loads(rec.Result()).get("text", "")
                if part:
                    texts.append(part)
        final = json.loads(rec.FinalResult()).get("text", "")
        if final:
            texts.append(final)
        return " ".join(texts).strip()
    finally:
        wf.close()