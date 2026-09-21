# -*- coding: utf-8 -*-
"""
analysis.py
وحدة التحليل الإحصائي للتقديرات السكانية.
- قراءة ملفات Excel/CSV وتوحيدها إلى صيغة طولية موحّدة.
- إحصاءات وصفية وتجميعات.
- التنبؤ بعدد السكان باستخدام نموذج ARIMA (طريقة إحصائية كلاسيكية).

كل الأرقام تُحسب من الملف المرفوع فقط، ولا يتم توليد أي بيانات.
"""

import io
import warnings
import numpy as np
import pandas as pd

# الأعمدة القياسية الداخلية بعد التوحيد
GOV = "المحافظة"
REG = "المنطقة"
NEI = "الحي"
AGE = "الفئة العمرية"
YEAR = "السنة"
POP = "عدد السكان"

ALL = "الكل"  # خيار التجميع الشامل في المرشّحات


# ----------------------------- دوال مساعدة موحّدة -----------------------------

def compute_cagr(first, last, n):
    """
    معدّل النمو السنوي المركّب (CAGR) بصيغة موحّدة تُستخدم في كل المواضع.
        CAGR = ((last / first) ** (1 / n) - 1) * 100

    ترجع None إذا تعذّر الحساب بشكل ذي معنى، وذلك عندما:
      - عدد الفترات n ليس موجباً (n <= 0)، أو
      - قيمة البداية first غير موجبة (<= 0)، أو
      - قيمة النهاية last سالبة (< 0).
    هذا يمنع الأرقام المضلّلة عند اختيار السنة نفسها أو عكس ترتيب السنتين
    أو وجود قيم صفرية/سالبة.
    """
    try:
        first = float(first)
        last = float(last)
        n = int(n)
    except (TypeError, ValueError):
        return None
    if n <= 0 or first <= 0 or last < 0:
        return None
    return ((last / first) ** (1.0 / n) - 1.0) * 100.0


def _fmt_cagr(cagr):
    """صياغة نصية موحّدة لمعدّل النمو المركّب."""
    return "غير متاح" if cagr is None else f"{cagr:.2f}٪"

# مرادفات أسماء الأعمدة (عربي/إنجليزي) لاكتشافها تلقائياً
_SYNONYMS = {
    GOV: ["المحافظة", "محافظة", "governorate", "gov", "muhafaza"],
    REG: ["المنطقة", "اللواء", "منطقة", "لواء", "region", "district", "area", "liwa"],
    NEI: ["الحي", "حي", "المربع", "neighborhood", "neighbourhood", "locality", "block", "quarter"],
    AGE: ["الفئة العمرية", "فئة عمرية", "الفئة", "العمر", "age group", "age_group", "agegroup", "age"],
    YEAR: ["السنة", "العام", "سنة", "عام", "year", "yr"],
    POP: ["عدد السكان", "السكان", "العدد", "عدد", "population", "pop", "count", "value", "تعداد"],
}


def _norm(s):
    return str(s).strip().lower().replace("_", " ").replace("-", " ")


def _match_column(col_name, synonyms):
    c = _norm(col_name)
    for syn in synonyms:
        if c == _norm(syn) or _norm(syn) in c:
            return True
    return False


def _looks_like_year(value):
    try:
        v = int(float(str(value).strip()))
        return 1900 <= v <= 2100
    except (ValueError, TypeError):
        return False


def read_table(file_bytes, filename):
    """قراءة الملف (xlsx/xls/csv) إلى DataFrame خام."""
    name = filename.lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(file_bytes))
    # CSV: محاولة قراءة UTF-8 ثم windows-1256 (للعربية)
    for enc in ("utf-8-sig", "utf-8", "cp1256", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(file_bytes), encoding=enc)
        except (UnicodeDecodeError, Exception):
            continue
    raise ValueError("تعذّرت قراءة الملف. يُرجى التأكد من أنه ملف Excel أو CSV صالح.")


def standardize(df_raw):
    """
    توحيد الجدول الخام إلى صيغة طولية: [المحافظة، المنطقة، الحي، الفئة العمرية، السنة، عدد السكان].
    يدعم صيغتين:
      - عريضة: أعمدة الأبعاد + أعمدة لكل سنة (2015, 2016, ...).
      - طولية: أعمدة الأبعاد + عمود السنة + عمود عدد السكان.
    يعيد (df_long, meta) حيث meta يصف الأعمدة المكتشفة.
    """
    df = df_raw.copy()
    df.columns = [str(c).strip() for c in df.columns]

    # اكتشاف أعمدة الأبعاد
    dim_map = {}
    used = set()
    for canonical in [GOV, REG, NEI, AGE]:
        for col in df.columns:
            if col in used:
                continue
            if _match_column(col, _SYNONYMS[canonical]):
                dim_map[canonical] = col
                used.add(col)
                break

    # اكتشاف عمود السنة وعمود عدد السكان (للصيغة الطولية)
    year_col = next((c for c in df.columns if c not in used and _match_column(c, _SYNONYMS[YEAR])), None)
    pop_col = next((c for c in df.columns if c not in used and _match_column(c, _SYNONYMS[POP])), None)

    # اكتشاف أعمدة السنوات (للصيغة العريضة): رؤوس أعمدة تبدو كسنوات
    year_value_cols = [c for c in df.columns if c not in used and _looks_like_year(c)]

    detected_format = None
    if year_col is not None and pop_col is not None:
        detected_format = "long"
        # نأخذ فقط الأعمدة الأساسية المطلوبة ونتجاهل أي أعمدة زائدة تماماً،
        # حتى لا تؤثّر الأعمدة الإضافية على النموذج إطلاقاً.
        keep_dims = [k for k in dim_map if dim_map[k] not in (year_col, pop_col)]
        source_cols = [dim_map[k] for k in keep_dims] + [year_col, pop_col]
        long_df = df[source_cols].copy()
        rename_map = {dim_map[k]: k for k in keep_dims}
        rename_map[year_col] = YEAR
        rename_map[pop_col] = POP
        long_df = long_df.rename(columns=rename_map)
    elif len(year_value_cols) >= 1:
        detected_format = "wide"
        # في الصيغة العريضة، نُبقي أعمدة الأبعاد المكتشفة فقط كمُعرِّفات،
        # ونصهر أعمدة السنوات فقط. أي عمود زائد (نصّي أو رقمي) يُتجاهَل تلقائياً.
        id_vars = [dim_map[k] for k in dim_map]
        keep_cols = id_vars + list(year_value_cols)
        long_df = df[keep_cols].melt(
            id_vars=id_vars, value_vars=year_value_cols, var_name=YEAR, value_name=POP
        )
        long_df = long_df.rename(columns={dim_map[k]: k for k in dim_map})
    else:
        raise ValueError(
            "تعذّر التعرّف على بنية البيانات. يجب أن يحتوي الملف إمّا على عمود للسنة وعمود لعدد السكان، "
            "أو على أعمدة لكل سنة (مثل 2015، 2016، ...)."
        )

    # ضمان وجود كل أعمدة الأبعاد (إنشاء الناقص بقيمة موحّدة)
    for canonical in [GOV, REG, NEI, AGE]:
        if canonical not in long_df.columns:
            long_df[canonical] = ALL

    # تنظيف الأنواع
    long_df[YEAR] = pd.to_numeric(long_df[YEAR], errors="coerce")
    long_df[POP] = pd.to_numeric(long_df[POP], errors="coerce")
    for c in [GOV, REG, NEI, AGE]:
        long_df[c] = long_df[c].astype(str).str.strip().replace({"nan": ALL, "": ALL})

    long_df = long_df.dropna(subset=[YEAR, POP])
    long_df[YEAR] = long_df[YEAR].astype(int)
    long_df = long_df[[GOV, REG, NEI, AGE, YEAR, POP]].reset_index(drop=True)

    meta = {
        "format": detected_format,
        "dimensions_detected": {k: dim_map.get(k) for k in [GOV, REG, NEI, AGE]},
        "n_years": int(long_df[YEAR].nunique()),
    }
    return long_df, meta


# ----------------------------- الملخّص السريع -----------------------------

def build_brief(long_df, df_raw):
    """ملخّص سريع للبيانات المرفوعة + معاينة + سلسلة الإجمالي الزمنية."""
    years = sorted(long_df[YEAR].unique().tolist())
    latest = years[-1]
    total_series = (
        long_df.groupby(YEAR)[POP].sum().reindex(years).fillna(0).astype(float)
    )
    stat_cards = [
        {"label": "عدد السجلات", "value": f"{len(long_df):,}"},
        {"label": "المحافظات", "value": f"{long_df[GOV].nunique():,}"},
        {"label": "المناطق", "value": f"{long_df[REG].nunique():,}"},
        {"label": "الأحياء", "value": f"{long_df[NEI].nunique():,}"},
        {"label": "الفئات العمرية", "value": f"{long_df[AGE].nunique():,}"},
        {"label": "المدى الزمني", "value": f"{years[0]} – {latest}"},
        {"label": f"إجمالي السكان ({latest})", "value": f"{int(total_series.loc[latest]):,}"},
    ]
    preview = df_raw.head(10).fillna("").astype(str)
    return {
        "stat_cards": stat_cards,
        "years": years,
        "overview_chart": {"years": years, "totals": [float(v) for v in total_series.values]},
        "preview": {
            "columns": preview.columns.tolist(),
            "rows": preview.values.tolist(),
        },
    }


# ----------------------------- المرشّحات المتتالية -----------------------------

def cascading_options(long_df, governorate=None, region=None, neighborhood=None):
    """خيارات المرشّحات المتتالية بناءً على الاختيارات الأعلى."""
    df = long_df
    if governorate and governorate != ALL:
        df = df[df[GOV] == governorate]
    regions = sorted(df[REG].unique().tolist())
    if region and region != ALL:
        df = df[df[REG] == region]
    neighborhoods = sorted(df[NEI].unique().tolist())
    if neighborhood and neighborhood != ALL:
        df = df[df[NEI] == neighborhood]
    ages = sorted(df[AGE].unique().tolist())
    return {
        "governorates": [ALL] + sorted(long_df[GOV].unique().tolist()),
        "regions": [ALL] + regions,
        "neighborhoods": [ALL] + neighborhoods,
        "ages": [ALL] + ages,
    }


def _apply_filters(long_df, f):
    df = long_df
    for col, key in [(GOV, "governorate"), (REG, "region"), (NEI, "neighborhood")]:
        val = (f or {}).get(key)
        if val and val != ALL:
            df = df[df[col] == val]
    # age قد تكون قائمة أو قيمة مفردة
    age_val = (f or {}).get("age")
    if age_val:
        if isinstance(age_val, list):
            valid = [a for a in age_val if a and a != ALL]
            if valid:
                df = df[df[AGE].isin(valid)]
        elif age_val != ALL:
            df = df[df[AGE] == age_val]
    return df


def _filter_label(f):
    parts = []
    for col, key in [(GOV, "governorate"), (REG, "region"), (NEI, "neighborhood"), (AGE, "age")]:
        val = (f or {}).get(key)
        if not val or val == ALL:
            continue
        if isinstance(val, list):
            valid = [str(a) for a in val if a and a != ALL]
            if not valid:
                continue
            val = "، ".join(valid)
        parts.append(f"{col}: {val}")
    return "؛ ".join(parts) if parts else "كل البيانات"


# ----------------------------- الاستعلامات (نوايا) -----------------------------

def q_by_governorate(long_df, year=None):
    year = year or int(long_df[YEAR].max())
    sub = long_df[long_df[YEAR] == year]
    grp = sub.groupby(GOV)[POP].sum().sort_values(ascending=False)
    table = [[g, int(v)] for g, v in grp.items()]
    top = grp.index[0]
    report = (
        f"في عام {year}، بلغ إجمالي السكان {int(grp.sum()):,} نسمة موزّعين على {len(grp)} محافظة. "
        f"تصدّرت محافظة {top} بـ {int(grp.iloc[0]):,} نسمة "
        f"(نحو {grp.iloc[0]/grp.sum()*100:.1f}٪ من الإجمالي)."
    )
    return {
        "chart": {"type": "bar", "x": grp.index.tolist(), "y": [int(v) for v in grp.values],
                  "title": f"السكان حسب المحافظة — {year}"},
        "table": {"columns": [GOV, f"عدد السكان ({year})"], "rows": table},
        "report": report,
    }


def q_age_distribution(long_df, f, year=None):
    year = int(year) if year else int(long_df[YEAR].max())
    df = _apply_filters(long_df, f)
    df = df[df[YEAR] == year]
    grp = df.groupby(AGE)[POP].sum().sort_values(ascending=False)
    if grp.empty or grp.sum() == 0:
        return {"chart": None, "table": {"columns": [AGE, "عدد السكان"], "rows": []},
                "report": "لا توجد بيانات مطابقة للمرشّحات المختارة."}

    total = grp.sum()
    table = [[a, int(v), f"{v/total*100:.1f}٪"] for a, v in grp.items()]

    # ملاحظة توضيحية: عند اختيار فئة عمرية واحدة يصبح التوزيع 100٪ لتلك الفئة،
    # وهو أمر متوقّع. الرسالة تنبّه المستخدم لاختيار عدة فئات للمقارنة.
    if len(grp) == 1:
        only = grp.index[0]
        report = (
            f"لعام {year} ({_filter_label(f)}): الفئة «{only}» وحدها مختارة، "
            f"وعددها {int(grp.iloc[0]):,} نسمة (100٪ من المختار). "
            "لمقارنة توزيع الأعمار، اختاري أكثر من فئة عمرية أو اجعلي الفئة العمرية = الكل."
        )
    else:
        report = (
            f"توزيع الفئات العمرية لعام {year} ({_filter_label(f)}): "
            f"الإجمالي {int(total):,} نسمة عبر {len(grp)} فئة. الفئة الأكبر هي «{grp.index[0]}» "
            f"بـ {int(grp.iloc[0]):,} نسمة ({grp.iloc[0]/total*100:.1f}٪)."
        )
    return {
        "chart": {"type": "pie", "labels": grp.index.tolist(), "values": [int(v) for v in grp.values],
                  "title": f"التوزيع حسب الفئة العمرية — {year}"},
        "table": {"columns": [AGE, "عدد السكان", "النسبة"], "rows": table},
        "report": report,
    }


def q_timeseries(long_df, f):
    df = _apply_filters(long_df, f)
    grp = df.groupby(YEAR)[POP].sum().sort_index()
    if len(grp) == 0:
        return {"chart": None, "table": {"columns": [YEAR, POP], "rows": []},
                "report": "لا توجد بيانات مطابقة للمرشّحات المختارة."}
    years = grp.index.tolist()
    vals = [int(v) for v in grp.values]
    table = [[y, v] for y, v in zip(years, vals)]
    first, last = grp.iloc[0], grp.iloc[-1]
    n = len(grp) - 1
    cagr = compute_cagr(first, last, n)
    report = (
        f"السلسلة الزمنية ({_filter_label(f)}): تطوّر العدد من {int(first):,} نسمة عام {years[0]} "
        f"إلى {int(last):,} نسمة عام {years[-1]}. "
        + (f"متوسط معدّل النمو السنوي المركّب (CAGR) ≈ {_fmt_cagr(cagr)}." if cagr is not None else "")
    )
    return {
        "chart": {"type": "line", "x": years, "y": vals, "title": f"تطوّر عدد السكان — {_filter_label(f)}"},
        "table": {"columns": [YEAR, POP], "rows": table},
        "report": report,
    }


def q_growth(long_df, f, year_from, year_to):
    yf, yt = int(year_from), int(year_to)
    # ضمان ترتيب صحيح للسنتين حتى لو أدخلهما المستخدم معكوستين
    if yf > yt:
        yf, yt = yt, yf
    if yf == yt:
        return {"chart": None, "table": {"columns": ["", ""], "rows": []},
                "report": "يُرجى اختيار سنتين مختلفتين لحساب النمو."}

    df = _apply_filters(long_df, f)
    a = df[df[YEAR] == yf][POP].sum()
    b = df[df[YEAR] == yt][POP].sum()
    if a == 0:
        return {"chart": None, "table": {"columns": ["", ""], "rows": []},
                "report": "لا توجد بيانات كافية لحساب النمو للمرشّحات والسنوات المختارة."}

    change = b - a
    pct = change / a * 100
    n = yt - yf
    cagr = compute_cagr(a, b, n)  # مصدر واحد موحّد لمعادلة النمو المركّب
    table = [
        [f"السكان {yf}", int(a)],
        [f"السكان {yt}", int(b)],
        ["التغيّر المطلق", int(change)],
        ["نسبة التغيّر", f"{pct:.2f}٪"],
        ["النمو السنوي المركّب", _fmt_cagr(cagr)],
    ]
    direction = "ارتفاعاً" if change >= 0 else "انخفاضاً"
    cagr_txt = f"، بمعدّل نمو سنوي مركّب ≈ {_fmt_cagr(cagr)}" if cagr is not None else ""
    report = (
        f"بين عامي {yf} و{yt} ({_filter_label(f)}): "
        f"شهد العدد {direction} مقداره {int(abs(change)):,} نسمة "
        f"({pct:+.2f}٪){cagr_txt}."
    )
    return {
        "chart": {"type": "bar", "x": [str(yf), str(yt)], "y": [int(a), int(b)],
                  "title": f"مقارنة السكان: {yf} مقابل {yt}"},
        "table": {"columns": ["المؤشر", "القيمة"], "rows": table},
        "report": report,
    }


def _choose_breakdown(df, f):
    """
    يختار البُعد الذي ستُحسب عليه الإحصاءات (min/max/mean/median/std).
    المنطق: أدقّ بُعد «غير مثبّت» بمرشّح مفرد، بالترتيب:
        الحي ← المنطقة ← المحافظة ← الفئة العمرية.
    البُعد يُعدّ «مثبّتاً» إذا اختار المستخدم قيمة واحدة له (غير «الكل»)،
    أو إذا كان لا يحوي إلا قيمة واحدة فعلاً بعد الترشيح.
    يعيد (اسم_العمود, عنوان_عربي). إن تعذّر، يعيد (None, None).
    """
    fixed = set()
    for col, key in [(GOV, "governorate"), (REG, "region"), (NEI, "neighborhood")]:
        v = (f or {}).get(key)
        if v and v != ALL:
            fixed.add(col)
    age_v = (f or {}).get("age")
    if age_v and age_v != ALL and not (isinstance(age_v, list) and (ALL in age_v or len(age_v) == 0)):
        # فئة عمرية واحدة محدّدة تُعدّ تثبيتاً؛ عدة فئات لا تُعدّ تثبيتاً
        if not (isinstance(age_v, list) and len(age_v) > 1):
            fixed.add(AGE)

    labels = {NEI: "الحي", REG: "المنطقة", GOV: "المحافظة", AGE: "الفئة العمرية"}
    for col in [NEI, REG, GOV, AGE]:
        if col in fixed:
            continue
        if df[col].nunique() >= 2:      # لا معنى للتوزيع على قيمة واحدة
            return col, labels[col]
    # لم نجد بُعداً متعدّد القيم غير مثبّت
    return None, None


def q_custom(long_df, f, op):
    """
    عملية حسابية مخصّصة (مجموع/متوسط/وسيط/عظمى/صغرى/انحراف) للسنة الأحدث.

    الإصلاح الجوهري:
    الإحصاءات الوصفية (صغرى/عظمى/متوسط/وسيط/انحراف) تُحسب على توزيع القيم عبر
    بُعد ذي معنى (الحي أو المنطقة أو المحافظة أو الفئة العمرية) وليس على صفوف
    الجدول الخام. سابقاً، عند ترشيح البيانات حتى حيّ واحد وفئة واحدة كان يتبقّى
    صفّ واحد فقط، فتتساوى الصغرى والعظمى والمتوسط عند القيمة نفسها. الآن نُجمّع
    السكان حسب البُعد المختار ثم نطبّق العملية على المجاميع.
    """
    df = _apply_filters(long_df, f)
    if df.empty:
        return {"chart": None, "table": {"columns": ["", ""], "rows": []},
                "report": "لا توجد بيانات مطابقة للمرشّحات المختارة."}

    year = int(df[YEAR].max())
    df_y = df[df[YEAR] == year]
    if df_y.empty:
        return {"chart": None, "table": {"columns": ["", ""], "rows": []},
                "report": "لا توجد بيانات للسنة المتاحة بعد الترشيح."}

    op_labels = {
        "sum": "المجموع", "mean": "المتوسط", "median": "الوسيط",
        "max": "القيمة العظمى", "min": "القيمة الصغرى", "std": "الانحراف المعياري",
    }
    label = op_labels.get(op, op_labels["sum"])

    # المجموع الكلّي لا يحتاج بُعداً: هو ببساطة إجمالي السكان بعد الترشيح.
    if op == "sum":
        value = float(df_y[POP].sum())
        table = [[f"{label} (لعام {year})", f"{value:,.0f}"],
                 ["عدد السجلات المشمولة", f"{len(df_y):,}"]]
        report = (f"{label} لعدد السكان عام {year} ({_filter_label(f)}) = "
                  f"{value:,.0f} نسمة (على {len(df_y):,} سجلاً).")
        return {"chart": None, "table": {"columns": ["العملية", "النتيجة"], "rows": table},
                "report": report}

    # لبقية العمليات: نُجمّع حسب بُعد ذي معنى ثم نحسب الإحصاءة على المجاميع.
    dim_col, dim_label = _choose_breakdown(df_y, f)
    if dim_col is None:
        # لا يوجد بُعد متعدّد القيم — الإحصاءة الوصفية بلا معنى هنا.
        value = float(df_y[POP].sum())
        report = (
            f"العملية «{label}» تحتاج إلى توزيع على أكثر من فئة لتكون ذات معنى، "
            f"لكن المرشّحات الحالية ({_filter_label(f)}) تُبقي مجموعة واحدة فقط لعام {year}. "
            f"إجمالي السكان لهذه المجموعة = {value:,.0f} نسمة. "
            "للحصول على صغرى/عظمى/متوسط ذي معنى، وسّعي نطاق أحد المرشّحات (مثلاً اجعلي «الحي» = الكل)."
        )
        table = [[f"إجمالي السكان (لعام {year})", f"{value:,.0f}"]]
        return {"chart": None, "table": {"columns": ["العملية", "النتيجة"], "rows": table},
                "report": report}

    grp = df_y.groupby(dim_col)[POP].sum().sort_values(ascending=False)

    ops = {
        "mean": grp.mean(),
        "median": grp.median(),
        "max": grp.max(),
        "min": grp.min(),
        "std": grp.std(ddof=1) if len(grp) > 1 else 0.0,
    }
    value = float(ops.get(op, grp.mean()))

    # لأجل الصغرى/العظمى: نُبيّن أي فئة تحمل تلك القيمة.
    holder = None
    if op == "max":
        holder = grp.idxmax()
    elif op == "min":
        holder = grp.idxmin()

    table = [[f"{label} (لعام {year})", f"{value:,.2f}"],
             [f"عدد الفئات ({dim_label})", f"{len(grp):,}"]]
    if holder is not None:
        table.append([f"الفئة صاحبة {label}", f"{holder} ({int(grp.loc[holder]):,})"])

    holder_txt = ""
    if holder is not None:
        holder_txt = f" وهي «{holder}» بـ {int(grp.loc[holder]):,} نسمة"

    report = (
        f"{label} لعدد السكان عام {year} عبر توزيع «{dim_label}» ({_filter_label(f)}) = "
        f"{value:,.2f}{holder_txt}. حُسبت على {len(grp):,} فئة."
    )

    # رسم توزيع القيم عبر البُعد المختار (أعلى ١٢ فئة للوضوح).
    top = grp.head(12)
    chart = {
        "type": "bar",
        "x": [str(i) for i in top.index.tolist()],
        "y": [int(v) for v in top.values],
        "title": f"توزيع السكان حسب {dim_label} — {year}",
    }
    return {"chart": chart, "table": {"columns": ["العملية", "النتيجة"], "rows": table},
            "report": report}


# ----------------------------- التنبؤ بنموذج ARIMA -----------------------------

def _fit_best_arima(values):
    """بحث شبكي مصغّر عن أفضل ترتيب (p,d,q) وفق معيار AIC."""
    from statsmodels.tsa.arima.model import ARIMA
    n = len(values)
    max_p = 2 if n >= 6 else 1
    max_q = 2 if n >= 6 else 1
    max_d = 2 if n >= 5 else 1
    best = None
    for p in range(0, max_p + 1):
        for d in range(0, max_d + 1):
            for q in range(0, max_q + 1):
                if p == 0 and d == 0 and q == 0:
                    continue
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        model = ARIMA(values, order=(p, d, q)).fit()
                    if np.isfinite(model.aic) and (best is None or model.aic < best["aic"]):
                        best = {"order": (p, d, q), "aic": float(model.aic), "model": model}
                except Exception:
                    continue
    return best


def q_forecast(long_df, f, horizon=5):
    """تنبؤ بعدد السكان للسنوات القادمة باستخدام ARIMA."""
    horizon = int(horizon)
    df = _apply_filters(long_df, f)
    series = df.groupby(YEAR)[POP].sum().sort_index()
    years = series.index.tolist()
    values = series.values.astype(float)

    if len(values) < 4:
        return {
            "chart": None, "table": {"columns": ["", ""], "rows": []},
            "report": (
                f"التنبؤ يتطلّب ٤ سنوات على الأقل من البيانات للمرشّحات المختارة، "
                f"والمتاح حالياً {len(values)} سنة فقط ({_filter_label(f)}). "
                "يمكن تجربة تجميع أوسع (مثلاً على مستوى المحافظة أو «الكل»)."
            ),
        }

    best = _fit_best_arima(values)
    if best is None:
        return {"chart": None, "table": {"columns": ["", ""], "rows": []},
                "report": "تعذّر ملاءمة نموذج ARIMA لهذه السلسلة. يمكن تجربة تجميع أوسع."}

    model = best["model"]
    fc = model.get_forecast(steps=horizon)
    mean = np.asarray(fc.predicted_mean, dtype=float)
    ci = np.asarray(fc.conf_int(alpha=0.05), dtype=float)
    lower = np.clip(ci[:, 0], 0, None)
    upper = np.clip(ci[:, 1], 0, None)
    mean = np.clip(mean, 0, None)

    future_years = [years[-1] + i for i in range(1, horizon + 1)]

    table = [[y, f"{m:,.0f}", f"{lo:,.0f}", f"{hi:,.0f}"]
             for y, m, lo, hi in zip(future_years, mean, lower, upper)]

    last_actual = values[-1]
    last_pred = mean[-1]
    total_change = last_pred - last_actual
    pct = total_change / last_actual * 100 if last_actual > 0 else 0
    cagr = compute_cagr(last_actual, last_pred, horizon)
    direction = "ارتفاع" if total_change >= 0 else "انخفاض"

    cagr_txt = (f"بمعدّل نمو سنوي مركّب متوقّع ≈ {_fmt_cagr(cagr)}. "
                if cagr is not None else "")
    report = (
        f"باستخدام نموذج ARIMA{best['order']} (اختير آلياً وفق أدنى قيمة AIC = {best['aic']:.1f})، "
        f"وبناءً على بيانات {years[0]}–{years[-1]} ({_filter_label(f)}): "
        f"يُتوقّع أن يصل العدد عام {future_years[-1]} إلى نحو {last_pred:,.0f} نسمة، "
        f"أي {direction} مقداره {abs(total_change):,.0f} نسمة ({pct:+.1f}٪) خلال {horizon} سنوات، "
        f"{cagr_txt}"
        f"القيم محاطة بفترة ثقة 95٪ (الحدّان الأدنى والأعلى في الجدول). "
        f"تنبيه منهجي: تقلّ دقّة التنبؤ كلّما زاد عدد السنوات المستقبلية وقلّ طول السلسلة التاريخية."
    )

    return {
        "chart": {
            "type": "forecast",
            "hist_years": years, "hist_values": [float(v) for v in values],
            "fc_years": future_years, "fc_values": [float(v) for v in mean],
            "fc_lower": [float(v) for v in lower], "fc_upper": [float(v) for v in upper],
            "title": f"تنبؤ ARIMA لعدد السكان — {_filter_label(f)}",
        },
        "table": {"columns": ["السنة", "العدد المتوقّع", "الحدّ الأدنى (95٪)", "الحدّ الأعلى (95٪)"], "rows": table},
        "report": report,
    }