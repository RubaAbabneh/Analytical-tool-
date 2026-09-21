# -*- coding: utf-8 -*-
"""
nlu.py — فهم النيّة من النص المنطوق.
المنهجية: TF-IDF + Cosine Similarity لتحديد النية
         + Fuzzy Matching لأسماء الأماكن
         + محلّل عمري ذكي يفهم الأرقام والكلمات والنطاقات
"""

import re
import numpy as np
from difflib import SequenceMatcher
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import analysis as A

# ─────────────────────────────────────────────
# الفئات العمرية الثابتة
# ─────────────────────────────────────────────
FIXED_AGE_GROUPS = [
    (0,  4,  "0-4"),   (5,  9,  "5-9"),
    (10, 14, "10-14"), (15, 19, "15-19"),
    (20, 24, "20-24"), (25, 29, "25-29"),
    (30, 34, "30-34"), (35, 39, "35-39"),
    (40, 44, "40-44"), (45, 49, "45-49"),
    (50, 54, "50-54"), (55, 59, "55-59"),
    (60, 64, "60-64"), (65, 69, "65-69"),
    (70, 74, "70-74"), (75, 79, "75-79"),
    (80, 999, "80+"),
]

# ─────────────────────────────────────────────
# 1. تطبيع النص العربي
# ─────────────────────────────────────────────
_DIAC  = re.compile(r"[\u0617-\u061A\u064B-\u0652\u0670\u0640]")
_AR_DG = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def normalize(s: str) -> str:
    s = str(s).translate(_AR_DG)
    s = _DIAC.sub("", s)
    s = re.sub("[إأآا]", "ا", s)
    s = s.replace("ى","ي").replace("ؤ","و").replace("ئ","ي").replace("ة","ه")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


# ─────────────────────────────────────────────
# 2. Corpus التدريب لكل نية
# ─────────────────────────────────────────────
INTENT_CORPUS = {
    "by_governorate": [
        "عدد السكان حسب المحافظة",
        "توزيع السكان على المحافظات",
        "السكان لكل محافظة",
        "ترتيب المحافظات حسب عدد السكان",
        "مقارنة المحافظات في عدد السكان",
        "كم عدد سكان كل محافظة",
        "أي محافظة فيها أكثر سكان",
        "أكثر محافظة في عدد السكان",
        "وين أكثر ناس",
        "فين أكبر محافظة بالسكان",
        "شو توزيع الناس على المحافظات",
        "احكيلي عن المحافظات",
        "قارن المحافظات ببعض",
        "رتب المحافظات من حيث عدد السكان",
        "وين أكثر عدد سكان",
        # إضافات عامّية
        "أي محافظة الأكثر سكاناً",
        "أي منطقة فيها ناس أكثر",
        "أي محافظة الأكبر",
        "وين أكبر تجمّع سكاني",
        "محافظات الأردن وسكانها",
        "أعطيني السكان لكل محافظة",
        "كم بكل محافظة",
        "المحافظة الأكثر ازدحاماً بالسكان",
        "رتبلي المحافظات بعدد السكان",
        "وزّعلي السكان على المحافظات",
        "أي محافظة عدد سكانها أعلى",
        "قارنلي المحافظات",
        "المحافظات مرتّبة حسب الناس",
        "أعلى محافظة بعدد السكان",
        "أقل محافظة بعدد السكان",
        "توزيع سكان الأردن جغرافياً",
        "الكثافة السكانية حسب المحافظة",
        "كم ناس بكل محافظة",
        "أعطيني ترتيب المحافظات",
    ],
    "age_distribution": [
        "التوزيع حسب الفئة العمرية",
        "توزيع السكان على الفئات العمرية",
        "الفئات العمرية للسكان",
        "تركيبة السكان حسب العمر",
        "السكان حسب الأعمار",
        "كم نسبة الشباب",
        "كم نسبة كبار السن",
        "توزيع الأعمار",
        "حسب الفئة العمرية",
        "كيف موزعة الأعمار",
        "كم نسبة الشباب من السكان",
        "شو نسبة الصغار والكبار",
        "وين الشباب أكثر",
        "كيف تتوزع الفئات العمرية",
        "شو الفئة الأكثر",
        "شو عدد كبار السن",
        # إضافات عامّية
        "شو أكثر فئة عمرية",
        "أي فئة عمرية الأكبر",
        "كيف موزعين حسب العمر",
        "نسبة الأطفال كم",
        "قديش نسبة الشباب عنا",
        "توزيع الناس حسب أعمارهم",
        "مين أكثر الصغار ولا الكبار",
        "شو التركيب العمري للسكان",
        "أعمار السكان كيف موزعة",
        "كم عدد الأطفال",
        "كم عدد كبار السن",
        "نسبة المسنين من السكان",
        "الهرم السكاني حسب العمر",
        "توزيع الأعمار بالمحافظة",
        "شرائح الأعمار للسكان",
        "كم واحد بعمر معيّن",
        "الفئات العمرية ونسبها",
    ],
    "timeseries": [
        "تطوّر السكان عبر السنوات",
        "كيف تغيّر عدد السكان",
        "السلسلة الزمنية للسكان",
        "تغيّر السكان مع مرور الوقت",
        "عدد السكان خلال السنوات الماضية",
        "تطور السكان مع الزمن",
        "النمو السكاني عبر السنوات",
        "السكان من سنة إلى سنة",
        "تاريخ السكان",
        "كيف تطور عدد الناس",
        "كيف تغيرت الأعداد",
        "شو كان عدد السكان قبل",
        "شو صار بالسكان مع الوقت",
        "اعطيني تطور السكان",
        "ارسملي السلسلة الزمنية",
        "ابين لي تغيرات السكان",
        # إضافات عامّية
        "شو صار للسكان على مر السنين",
        "كيف تغيّر عدد الناس مع الوقت",
        "ابينلي تطور السكان",
        "شو كان عدد السكان زمان",
        "السكان من زمان لهلأ",
        "كيف السكان تغيروا عبر الزمن",
        "منحنى السكان عبر السنين",
        "تطوّر الأعداد سنة بسنة",
        "تاريخ تغيّر السكان",
        "شو تاريخ الأعداد",
        "كيف كانت الأعداد وكيف صارت",
        "اعرض لي تغيّر السكان زمنياً",
        "تغيّر السكان خلال الفترة الماضية",
        "السكان على مدى السنوات",
        "رسم بياني لتطور السكان",
    ],
    "growth": [
        "مقارنة النمو بين سنتين",
        "الفرق بين عامين",
        "التغيّر من سنة إلى سنة",
        "معدل النمو بين سنة وأخرى",
        "كم زاد عدد السكان",
        "نسبة الزيادة السكانية",
        "التغيّر المطلق والنسبي",
        "مقارنة عام مع عام",
        "كم كان الفرق",
        "كم زادت الأعداد",
        "شو الفرق بين سنتين",
        "كم ارتفع عدد السكان",
        "قارن بين سنة وسنة",
        "شو معدل الزيادة",
        "كم تضاعفت الأعداد",
        "شو الزيادة من سنة لسنة",
        # إضافات عامّية (مع تلميحات سنتين)
        "كم زادوا الناس بين سنة وسنة",
        "شو الفرق بالسكان بين عامين",
        "قارنلي سنة مع سنة",
        "كم صار الفرق بين العامين",
        "قدّيش النمو من عام لعام",
        "شو التغيّر بين هالسنتين",
        "كم الزيادة من هون لهون",
        "قارن الأعداد بين فترتين",
        "معدل النمو السنوي بين سنتين",
        "كم كبر العدد بين سنتين",
        "الفرق بالنسبة المئوية بين عامين",
        "شو نسبة التغيّر بين سنة وسنة",
    ],
    "custom": [
        "احسب المجموع",
        "إجمالي عدد السكان",
        "المتوسط الحسابي للسكان",
        "الوسيط",
        "أعلى قيمة",
        "أدنى قيمة",
        "القيمة العظمى",
        "القيمة الصغرى",
        "الانحراف المعياري",
        "كم عدد السكان",
        "ما مجموع السكان",
        "احسب مجموع السكان",
        "شو المتوسط",
        "شو أكبر قيمة",
        "شو أصغر قيمة",
        "اجمع الأعداد",
        "احسبلي المجموع",
        "شو مجموع الناس",
        "كم بلغ العدد",
        # إضافات عامّية
        "جمعلي كل الأعداد",
        "اجمعلي السكان",
        "احسبلي متوسط السكان",
        "شو متوسط الأعداد",
        "أعطيني أعلى قيمة بالسكان",
        "أعطيني أقل قيمة",
        "شو أعلى رقم بالسكان",
        "شو أدنى رقم",
        "احسب الوسيط للأعداد",
        "شو الانحراف المعياري",
        "اطلعلي إجمالي السكان",
        "كم المجموع الكلي للسكان",
        "بدي متوسط الأعداد",
        "بدي مجموع الأعداد",
        "احسب لي القيمة المتوسطة",
    ],
    "forecast": [
        "تنبؤ بعدد السكان",
        "توقّع السكان للمستقبل",
        "نموذج ARIMA للتنبؤ",
        "ما هو المتوقع لعدد السكان",
        "توقعات السكان للسنوات القادمة",
        "كم سيكون عدد السكان",
        "تنبؤ بالأعداد القادمة",
        "التوقعات المستقبلية",
        "تنبؤ للسنوات القادمة",
        "ارسم التنبؤ لخمس سنوات قادمة",
        "احكيلي عن مستقبل السكان",
        "شو متوقع للمستقبل",
        "كم رح يكون عدد السكان",
        "توقعلي الأعداد",
        "توقعلي السكان للخمس سنوات",
        "شو بيصير بالسكان بعدين",
        "اتنبأ للسنوات القادمة",
        "رح يزيد أو ينقص",
        "شو توقعات السكان",
        "خمّن الأعداد الجاية",
        "تنبأ بعدد سكان اربد",
        "شو السكان القادمه",
        "التوقعات المستقبليه",
        # إضافات عامّية
        "شو رح يصير بعدد السكان بعد كم سنة",
        "قديش بدهم يصيروا سكان بعد خمس سنين",
        "توقعلي كم بيصير عدد الناس",
        "بدي اعرف مستقبل السكان",
        "احزرلي الأعداد الجاية",
        "رح يزيدوا ولا ينقصوا الناس",
        "ممكن تحسبلي كم بصيروا لعشر سنين جاي",
        "وين رح توصل الأعداد",
        "بدي اشوف الأعداد المتوقعة",
        "شو بتوقّع عدد السكان بالمستقبل",
        "كم بصير عدد السكان السنة الجاية",
        "توقّع تقريبي لعدد السكان بالسنوات الجاية",
        "كم رح يصيروا بعد سنوات",
        "شو المتوقّع للأعداد مستقبلاً",
        "تنبؤ بالمستقبل السكاني",
        "قدّيش بيصيروا سكان بعدين",
        "اعطيني توقّع للسنوات القادمة",
        "شو بيكون عدد السكان لاحقاً",
        "بدّي إسقاط مستقبلي للسكان",
    ],
}

INTENT_LABELS = {
    "forecast":         "تنبؤ بعدد السكان (ARIMA)",
    "by_governorate":   "السكان حسب المحافظة",
    "age_distribution": "التوزيع حسب الفئة العمرية",
    "timeseries":       "تطوّر السكان زمنياً",
    "growth":           "مقارنة النمو بين سنتين",
    "custom":           "عملية حسابية مخصّصة",
}

PRIORITY     = ["forecast","by_governorate","age_distribution","growth","timeseries","custom"]
USES_FILTERS = {"age_distribution","timeseries","growth","custom","forecast"}


# ─────────────────────────────────────────────
# 3. نموذج TF-IDF
# ─────────────────────────────────────────────
_TRAIN_DOCS, _TRAIN_LABELS = [], []
for intent, sentences in INTENT_CORPUS.items():
    for s in sentences:
        _TRAIN_DOCS.append(normalize(s))
        _TRAIN_LABELS.append(intent)

_vectorizer = TfidfVectorizer(
    analyzer="char_wb", ngram_range=(2, 4),
    min_df=1, sublinear_tf=True,
)
_TRAIN_MATRIX = _vectorizer.fit_transform(_TRAIN_DOCS)


def _tfidf_intent(query_norm: str):
    qvec  = _vectorizer.transform([query_norm])
    sims  = cosine_similarity(qvec, _TRAIN_MATRIX).flatten()
    scores: dict = {}
    for label, score in zip(_TRAIN_LABELS, sims):
        if score > scores.get(label, 0.0):
            scores[label] = float(score)
    if not scores:
        return "custom", 0.0, {}
    best = max(scores, key=scores.__getitem__)
    return best, scores[best], scores


# ─────────────────────────────────────────────
# 3ب. طبقة الإشارات القاطعة (قواعد فوق TF-IDF)
# ─────────────────────────────────────────────
# لكل نية: كلمات/جذور قوية تميل للنية بثقة عالية حتى لو خدع TF-IDF.
# القيم مطبَّعة مسبقاً (بلا تشكيل، الألف موحّدة، إلخ).
_SIGNALS = {
    "forecast": [
        "توقع", "توقعلي", "تنبا", "تنبؤ", "اتنبا", "خمن", "احزر",
        "رح يصير", "رح يكون", "رح يوصل", "رح توصل", "رح يزيد", "رح ينقص",
        "بيصير", "بصير", "بصيروا", "بيصيروا", "بيكون", "يصيروا",
        "المستقبل", "مستقبل", "المتوقع", "متوقع", "الجايه", "الجايه",
        "القادمه", "القادمة", "لاحقا", "بعدين", "اسقاط",
    ],
    "growth": [
        "الفرق بين", "الفرق بالسكان", "قارن", "قارنلي", "مقارنه",
        "الزياده", "معدل النمو", "التغير بين", "بين سنتين", "بين عامين",
        "من سنه لسنه", "من عام لعام", "كم زاد", "كم زادوا", "كم ارتفع",
    ],
    "by_governorate": [
        "حسب المحافظه", "لكل محافظه", "بكل محافظه", "المحافظات",
        "اي محافظه", "رتب المحافظات", "رتبلي المحافظات", "توزيع المحافظات",
        "اكثر محافظه", "اكبر محافظه", "اعلى محافظه", "اقل محافظه",
        "اي منطقه الاكثر", "المحافظه الاكثر",
    ],
    "age_distribution": [
        "الفئه العمريه", "الفئات العمريه", "فئه عمريه", "فئات عمريه",
        "حسب العمر", "حسب الاعمار", "توزيع الاعمار", "توزيع الاعمار",
        "التركيب العمري", "الهرم السكاني", "نسبه الشباب", "نسبه الاطفال",
        "نسبه كبار السن", "نسبه المسنين", "كبار السن", "الشباب", "الاطفال",
        "شرائح الاعمار", "اكثر فئه", "اي فئه",
    ],
    "timeseries": [
        "تطور السكان", "تطور الاعداد", "عبر السنوات", "عبر السنين",
        "مع الوقت", "مع الزمن", "على مر السنين", "من زمان", "زمان",
        "السلسله الزمنيه", "سنه بسنه", "خلال السنوات", "على مدى",
    ],
    "custom": [
        "المجموع", "مجموع", "اجمع", "اجمعلي", "جمعلي", "احسب",
        "المتوسط", "متوسط", "الوسيط", "وسيط", "الانحراف المعياري",
        "اعلى قيمه", "ادنى قيمه", "اعلى رقم", "ادنى رقم", "اقصى", "القيمه العظمى",
        "القيمه الصغرى", "اجمالي",
    ],
}

# عبارات «قاطعة» جداً: وجودها يرجّح النية بقوة كبيرة (وزن أعلى).
_STRONG_SIGNALS = {
    "forecast": ["توقع", "تنبا", "تنبؤ", "المستقبل", "رح يصير", "رح يكون",
                 "بيصير", "بصيروا", "بيكونوا", "بيوصل", "المتوقع", "خمن", "احزر",
                 "الجايه", "القادمه", "اسقاط", "بيكون"],
    "growth":   ["الفرق بين", "قارن", "معدل النمو", "بين سنتين", "بين عامين",
                 "نسبه الزياده", "الزياده بين", "كم زاد", "كم زادوا"],
    "age_distribution": ["الفئه العمريه", "الفئات العمريه", "حسب العمر",
                         "توزيع الاعمار", "التركيب العمري", "الهرم السكاني",
                         "توزيع الاعمار", "الاعمار"],
    "by_governorate": ["حسب المحافظه", "لكل محافظه", "المحافظات", "اي محافظه"],
    "timeseries": ["تطور السكان", "عبر السنوات", "السلسله الزمنيه", "على مر السنين"],
    "custom": ["الانحراف المعياري", "المتوسط", "الوسيط", "المجموع"],
}

# نطبّع كل الإشارات مرة واحدة
_SIGNALS = {k: [normalize(x) for x in v] for k, v in _SIGNALS.items()}
_STRONG_SIGNALS = {k: [normalize(x) for x in v] for k, v in _STRONG_SIGNALS.items()}


def _signal_scores(norm_text: str) -> dict:
    """يحسب درجة إشارات لكل نية بناءً على وجود كلمات مفتاحية."""
    sc = {}
    for intent, kws in _SIGNALS.items():
        hits = sum(1 for kw in kws if kw and kw in norm_text)
        strong = sum(1 for kw in _STRONG_SIGNALS.get(intent, []) if kw and kw in norm_text)
        if hits or strong:
            sc[intent] = hits + strong * 3   # الإشارات القوية تزن أكثر
    return sc


def _blend_intent(norm_text: str):
    """
    يدمج TF-IDF مع الإشارات القاطعة.
    المنطق:
      - نبدأ بأفضل نية من TF-IDF ودرجتها.
      - نحسب درجات الإشارات لكل نية.
      - إن تعدّدت النوايا ذات الإشارة القوية، نفاضل بمجموع درجات الإشارات
        (الأكثر تحديداً يفوز)، ثم بدرجة TF-IDF عند التعادل.
      - إن وُجدت نية بإشارة قوية، ترجّح بقوة حتى لو TF-IDF اختار غيرها.
    يعيد (intent, confidence).
    """
    tfidf_best, tfidf_score, tfidf_all = _tfidf_intent(norm_text)
    sig = _signal_scores(norm_text)

    if not sig:
        return tfidf_best, tfidf_score

    # النوايا التي تملك إشارة قوية فعلية
    strong_intents = {
        it: sig[it] for it in sig
        if any(kw in norm_text for kw in _STRONG_SIGNALS.get(it, []))
    }

    if strong_intents:
        # عند تعدّد النوايا القوية: الأعلى مجموع درجات إشارات يفوز،
        # ثم درجة TF-IDF كفاصل عند التعادل.
        best_strong = max(
            strong_intents,
            key=lambda it: (strong_intents[it], tfidf_all.get(it, 0.0)),
        )
        if best_strong == tfidf_best:
            return tfidf_best, min(tfidf_score + 0.10 * sig[best_strong], 0.99)
        blended = max(tfidf_all.get(best_strong, 0.0), 0.55 + 0.08 * strong_intents[best_strong])
        return best_strong, min(blended, 0.99)

    # لا إشارات قوية — نستخدم الإشارات الضعيفة كترجيح بسيط
    sig_best = max(sig, key=sig.__getitem__)
    sig_best_val = sig[sig_best]
    if sig_best == tfidf_best:
        return tfidf_best, min(tfidf_score + 0.10 * sig_best_val, 0.99)
    if tfidf_all.get(sig_best, 0.0) >= tfidf_score - 0.05 and sig_best_val >= 2:
        return sig_best, tfidf_all.get(sig_best, tfidf_score)
    return tfidf_best, tfidf_score


# ─────────────────────────────────────────────
# 4. Fuzzy Matching لأسماء الأماكن
# ─────────────────────────────────────────────
DIM_THRESHOLD = 0.82

# كلمات وظيفية شائعة يجب ألا تُطابَق أبداً كاسم مكان (تفادي إيجابيات كاذبة
# مثل «الفئة» ← «الطفيلة»). كلها مطبَّعة.
_STOPWORDS_FUZZY = {normalize(w) for w in [
    "الفئه", "الفيه", "العمريه", "العمر", "الاعمار", "السكان", "الناس",
    "عدد", "العدد", "الاعداد", "نسبه", "النسبه", "توزيع", "التوزيع",
    "حسب", "على", "في", "من", "الى", "بين", "عام", "سنه", "سنوات",
    "متوسط", "المتوسط", "مجموع", "المجموع", "توقع", "تنبؤ", "المستقبل",
    "المحافظه", "المحافظات", "منطقه", "المنطقه", "حي", "الحي", "المعياري",
]}

def _ratio(a, b):
    return SequenceMatcher(None, a, b).ratio()

def _match_dimension(norm_text: str, long_df, col: str):
    """يطابق محافظة/منطقة/حي في النص — مطابقة حرفية ثم Fuzzy."""
    tokens = norm_text.split()
    exact_val, exact_len = None, 0
    fuzzy_val, fuzzy_score = None, 0.0
    for val in long_df[col].unique():
        if val == A.ALL:
            continue
        nv = normalize(val)
        if not nv:
            continue
        if nv in norm_text:
            if len(nv) > exact_len:
                exact_val, exact_len = val, len(nv)
        else:
            nwords = len(nv.split())
            for i in range(max(1, len(tokens) - nwords + 1)):
                window = " ".join(tokens[i: i + nwords])
                # تجاهل النوافذ التي تتكوّن من كلمات وظيفية فقط
                if all(w in _STOPWORDS_FUZZY for w in window.split()):
                    continue
                # لا نطابق أسماء أماكن قصيرة جداً fuzzy (عرضة للضجيج)
                if len(nv) < 4:
                    continue
                r = _ratio(window, nv)
                if r > fuzzy_score and r >= DIM_THRESHOLD:
                    fuzzy_score, fuzzy_val = r, val
    return exact_val or fuzzy_val


# ─────────────────────────────────────────────
# 5. محلّل الفئة العمرية الذكي
# ─────────────────────────────────────────────
_WORD_TO_NUM_RAW = {
    "صفر":0,  "واحد":1,  "اثنين":2,  "اثنان":2,
    "ثلاث":3, "ثلاثه":3, "ثلاثة":3,
    "اربع":4, "اربعه":4, "اربعة":4,
    "خمس":5,  "خمسه":5,  "خمسة":5,
    "ست":6,   "سته":6,   "ستة":6,
    "سبع":7,  "سبعه":7,  "سبعة":7,
    "ثماني":8,"ثمانيه":8,"ثمانية":8,
    "تسع":9,  "تسعه":9,  "تسعة":9,
    "عشر":10, "عشره":10, "عشرة":10,
    "احدى عشر":11,  "اثنا عشر":12,
    "ثلاثة عشر":13, "ثلاثه عشر":13,
    "اربعة عشر":14, "اربعه عشر":14,
    "خمسة عشر":15,  "خمسه عشر":15,
    "ستة عشر":16,   "سته عشر":16,
    "سبعة عشر":17,  "سبعه عشر":17,
    "ثمانية عشر":18,"ثمانيه عشر":18,
    "تسعة عشر":19,  "تسعه عشر":19,
    "عشرين":20, "ثلاثين":30, "اربعين":40,
    "خمسين":50, "ستين":60,   "سبعين":70,
    "ثمانين":80,"تسعين":90,
}
_WORD_TO_NUM = {normalize(k): v for k, v in _WORD_TO_NUM_RAW.items()}

_TIME_UNITS = {normalize(u) for u in
               ["سنه","سنة","سنوات","عام","عاما","عامًا","سنين","سنوه"]}

_AGE_VOCAB_RAW = {
    "اطفال":(0,14),  "أطفال":(0,14),  "الاطفال":(0,14), "صغار":(0,14),
    "شباب":(15,29),  "الشباب":(15,29),"الشبان":(15,29),
    "بالغين":(20,59),"البالغين":(20,59),
    "متوسطي العمر":(35,54),"منتصف العمر":(35,54),
    "كبار السن":(60,999),"كبار":(60,999),
    "المسنين":(65,999),"مسنين":(65,999),
    "شيوخ":(70,999),"المشايخ":(70,999),
}
_AGE_VOCAB = {normalize(k): v for k, v in _AGE_VOCAB_RAW.items()}

# حروف الوصل لنطاقات "من X إلى Y"
_TO  = r"(?:الي|الى|حتي|حتى|ل)\s*"
_AND = r"(?:و|الي|الى|حتي|حتى|ل)\s*"


def _strip_time_unit(s: str) -> str:
    """يحذف وحدة الزمن من نهاية النص (سنوات، عام، ...)."""
    words = normalize(s).split()
    while words and words[-1] in _TIME_UNITS:
        words = words[:-1]
    return " ".join(words).strip()


def _text_to_num(s: str) -> int:
    """يحوّل نص (أرقام أو كلمات عربية) لعدد صحيح. يعيد -1 إن فشل."""
    s = _strip_time_unit(s)
    if not s:
        return -1
    if re.match(r"^\d+$", s):
        return int(s)
    # مطابقة تامة أولاً (من الأطول)
    for word in sorted(_WORD_TO_NUM, key=len, reverse=True):
        if word == s:
            return _WORD_TO_NUM[word]
    # مطابقة جزئية (الكلمة ضمن جملة)
    for word in sorted(_WORD_TO_NUM, key=len, reverse=True):
        if len(word) >= 3 and re.search(r'(?<!\w)' + re.escape(word) + r'(?!\w)', s):
            return _WORD_TO_NUM[word]
    return -1


def _num_to_age_groups(lo: int, hi: int) -> list:
    """يعيد قائمة الفئات التي تتقاطع مع النطاق [lo, hi]."""
    return [lbl for (a, b, lbl) in FIXED_AGE_GROUPS if a <= hi and b >= lo]


def extract_age_groups(text: str) -> list:
    """
    يستخرج قائمة الفئات العمرية من النص العربي.
    يدعم: أرقام مباشرة، كلمات، نطاقات، كلمات مجموعة، أكبر/أصغر من.
    يعيد [] إن لم يجد شيئاً.
    """
    t = normalize(text)

    # ── 1أ. نطاق أرقام مباشرة: "من 0 إلى 9" ──
    m = re.search(r"من\s+(\d+)\s+" + _TO + r"(\d+)", t)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi: lo, hi = hi, lo
        r = _num_to_age_groups(lo, hi)
        if r: return r

    # ── 1ب. نطاق كلامي أو مختلط ──
    for pat in [
        r"من\s+(?:سن\s+|عمر\s+)?(.+?)\s+" + _TO + r"(?:سن\s+|عمر\s+)?(.+?)(?:\s+(?:سنه|سنة|سنوات|عام)|$)",
        r"بين\s+(?:سن\s+|عمر\s+)?(.+?)\s+" + _AND + r"(?:سن\s+|عمر\s+)?(.+?)(?:\s+(?:سنه|سنة|سنوات|عام)|$)",
    ]:
        m = re.search(pat, t)
        if m:
            lo = _text_to_num(m.group(1))
            hi = _text_to_num(m.group(2))
            if lo >= 0 and hi >= 0:
                if lo > hi: lo, hi = hi, lo
                r = _num_to_age_groups(lo, hi)
                if r: return r

    # ── 2. كلمات مجموعة (الأطول أولاً) ──
    for word, (lo, hi) in sorted(_AGE_VOCAB.items(), key=lambda x: len(x[0]), reverse=True):
        if word in t:
            return _num_to_age_groups(lo, hi)

    # ── 3. رقم مفرد مع كلمة مرشّدة ──
    for pat in [
        r"(?:عمر|العمر|عمره|عمرها|ابن|بنت|سن)\s+(\d+|\w+)",
        r"(\d+|\w+)\s+(?:سنه|سنة|سنوات|عام|عاما)\b",
    ]:
        for m in re.finditer(pat, t):
            n = _text_to_num(m.group(1))
            if 0 <= n <= 120:
                r = _num_to_age_groups(n, n)
                if r: return r

    # ── 4. أكبر/أصغر من X — مع دعم "ال" التعريف ──
    m = re.search(r"(?:ال)?(?:اكبر|فوق|اعلى)\s+من\s+(\d+|\w+(?:\s+\w+)?)", t)
    if m:
        n = _text_to_num(m.group(1))
        if n >= 0:
            return _num_to_age_groups(n, 999)   # "أكبر من 60" يشمل 60

    m = re.search(r"(?:ال)?(?:اقل|اصغر|تحت|دون)\s+من\s+(\d+|\w+(?:\s+\w+)?)", t)
    if m:
        n = _text_to_num(m.group(1))
        if n >= 1:
            return _num_to_age_groups(0, n - 1)  # "أقل من 10" → [0,9]
        if n == 0:
            return []

    return []


# ─────────────────────────────────────────────
# 6. استخراج الكيانات الرقمية (سنوات، أفق، عملية)
# ─────────────────────────────────────────────
_HORIZON_WORDS = {
    normalize(k): v for k, v in {
        "سنتين":2,"سنتان":2,"ثلاث":3,"ثلاثه":3,"اربع":4,"اربعه":4,
        "خمس":5,"خمسه":5,"ست":6,"سبع":7,"ثماني":8,"تسع":9,
        "عشر":10,"خمسه عشر":15,"عشرين":20,
    }.items()
}

_OP_KW = {
    "mean":   ["المتوسط","متوسط","معدل"],
    "median": ["الوسيط","وسيط"],
    "max":    ["اعلى","اكبر","اقصى","القيمه العظمى"],
    "min":    ["ادنى","اقل","اصغر","القيمه الصغرى"],
    "std":    ["الانحراف","انحراف"],
    "sum":    ["المجموع","اجمالي","مجموع","احسب"],
}


def _extract_years(norm_text: str, available: list) -> list:
    found = [int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", norm_text)]
    return [y for y in found if y in set(available)]


def _extract_horizon(norm_text: str, max_year: int) -> int:
    # سنة مستقبلية صريحة
    for y in re.findall(r"\b(?:19|20)\d{2}\b", norm_text):
        yi = int(y)
        if yi > max_year:
            return max(1, min(20, yi - max_year))
    # رقم صغير صريح
    for m in re.findall(r"\b\d{1,2}\b", norm_text):
        n = int(m)
        if 1 <= n <= 20:
            return n
    # كلمات عربية
    for w, n in _HORIZON_WORDS.items():
        if w in norm_text:
            return n
    return 5


def _extract_op(norm_text: str) -> str:
    for op, kws in _OP_KW.items():
        if any(normalize(k) in norm_text for k in kws):
            return op
    return "sum"


# ─────────────────────────────────────────────
# 7. الدالة الرئيسية
# ─────────────────────────────────────────────
COSINE_THRESHOLD = 0.08


def match(text: str, long_df) -> dict:
    """
    يحلل نص المستخدم ويعيد:
      intent, intent_label, filters (age قد تكون قائمة), params, message
    """
    t = normalize(text)
    if not t:
        return {
            "intent": None, "intent_label": "", "filters": {}, "params": {},
            "message": "لم ألتقط أي كلام. يُرجى التحدّث بوضوح بعد الضغط على الميكروفون.",
        }

    # ── تحديد النية (TF-IDF مدموج مع الإشارات القاطعة) ──
    intent, score = _blend_intent(t)
    if score < COSINE_THRESHOLD:
        return {
            "intent": None, "intent_label": "", "filters": {}, "params": {},
            "message": (
                "لم أتعرّف على سؤال محدّد. "
                "مثال: «توقّع عدد سكان إربد للخمس سنوات القادمة»، "
                "أو «السكان حسب الفئة العمرية في الهاشمية عام 2021»."
            ),
        }

    available_years = sorted(long_df[A.YEAR].unique().tolist())
    years_in_text   = _extract_years(t, available_years)

    # حسم growth vs timeseries
    # الأصل: سنتان رقميتان ⇒ growth. لكن أيضاً إشارات لفظية صريحة للمقارنة
    # بين فترتين ("بين عامين"، "بين سنتين"، "الفرق بين"، "نسبة الزيادة"، "قارن")
    # ترجّح growth حتى بلا أرقام.
    if intent in ("growth", "timeseries"):
        growth_phrases = ["بين عامين", "بين سنتين", "بين سنه وسنه", "بين سنة وسنة",
                          "الفرق بين", "نسبه الزياده", "معدل النمو", "من سنه لسنه",
                          "من عام لعام", "كم زاد", "كم زادوا", "كم ارتفع", "بين فترتين"]
        has_growth_phrase = any(normalize(p) in t for p in growth_phrases)
        if len(years_in_text) >= 2 or has_growth_phrase:
            intent = "growth"
        else:
            intent = "timeseries"

    # ── الفلاتر الجغرافية (Fuzzy) ──
    filters = {
        "governorate":  _match_dimension(t, long_df, A.GOV) or A.ALL,
        "region":       _match_dimension(t, long_df, A.REG) or A.ALL,
        "neighborhood": _match_dimension(t, long_df, A.NEI) or A.ALL,
    }

    # ── الفئة العمرية (المحلّل الذكي) ──
    age_groups = extract_age_groups(text)   # قائمة [] أو ["0-4"] أو ["0-4","5-9"]
    if age_groups:
        filters["age"] = age_groups         # قائمة
    else:
        # fallback: Fuzzy على أسماء الفئات كما كان
        age_fuzzy = _match_dimension(t, long_df, A.AGE)
        filters["age"] = [age_fuzzy] if age_fuzzy else [A.ALL]

    # ── المعاملات ──
    last_year = available_years[-1]
    params: dict = {}
    if intent in ("by_governorate", "age_distribution"):
        params["year"] = years_in_text[-1] if years_in_text else last_year
    elif intent == "growth":
        if len(years_in_text) >= 2:
            params["year_from"] = min(years_in_text)
            params["year_to"]   = max(years_in_text)
        else:
            params["year_from"] = available_years[0]
            params["year_to"]   = last_year
    elif intent == "custom":
        params["op"] = _extract_op(t)
    elif intent == "forecast":
        params["horizon"] = _extract_horizon(t, last_year)

    # ── رسالة الفهم ──
    age_display = "، ".join(filters["age"]) if isinstance(filters["age"], list) else filters["age"]
    flt_parts = []
    for col, val in [
        (A.GOV, filters["governorate"]),
        (A.REG, filters["region"]),
        (A.NEI, filters["neighborhood"]),
    ]:
        if val != A.ALL:
            flt_parts.append(f"{col}: {val}")
    age_val = filters["age"]
    if isinstance(age_val, list) and age_val != [A.ALL]:
        flt_parts.append(f"الفئة العمرية: {age_display}")
    elif age_val != A.ALL:
        flt_parts.append(f"الفئة العمرية: {age_val}")

    msg_parts = [f"الفهم: {INTENT_LABELS[intent]}"]
    if flt_parts:
        msg_parts.append("؛ ".join(flt_parts))
    if "year"      in params: msg_parts.append(f"السنة: {params['year']}")
    if "year_from" in params: msg_parts.append(f"من {params['year_from']} إلى {params['year_to']}")
    if "horizon"   in params: msg_parts.append(f"أفق التنبؤ: {params['horizon']} سنوات")
    if "op"        in params:
        op_ar = {"sum":"المجموع","mean":"المتوسط","median":"الوسيط",
                 "max":"القيمة العظمى","min":"القيمة الصغرى","std":"الانحراف المعياري"}
        msg_parts.append(f"العملية: {op_ar.get(params['op'], params['op'])}")
    msg_parts.append(f"(ثقة: {score:.0%})")

    return {
        "intent":       intent,
        "intent_label": INTENT_LABELS[intent],
        "filters":      filters,
        "params":       params,
        "message":      " — ".join(msg_parts),
    }