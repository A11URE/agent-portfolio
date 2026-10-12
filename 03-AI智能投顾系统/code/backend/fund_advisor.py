"""Fund Advisor routes — ETF sentiment + LLM Q&A + strategy config."""
from flask import Blueprint, request, jsonify, g
from app.utils.auth import login_required
from app.utils.logger import get_logger
from app.services.llm import LLMService

logger = get_logger(__name__)
fund_bp = Blueprint("fund_advisor", __name__)

ETF_POOL = [
    ("510050","上证50ETF","宽基大盘","低估值"),("510300","沪深300ETF","宽基大盘","核心资产"),("510500","中证500ETF","宽基中盘","中盘成长"),
    ("159915","创业板ETF","宽基成长","高波动"),("588000","科创50ETF","科技成长","高成长"),("512880","证券ETF","金融主题","高弹性"),
    ("512690","酒ETF","消费主题","防御"),("516160","新能源ETF","科技主题","周期"),("512010","医药ETF","医疗主题","防御"),
    ("513100","纳指ETF","海外QDII","全球配置"),("510880","红利ETF","高股息","现金流"),("511880","银华日利","货币","现金管理"),
    ("518880","黄金ETF","商品","避险"),("511010","国债ETF","债券","避险"),("512100","1000ETF","宽基小盘","小盘成长"),
    ("513050","中概互联","海外科技","高弹性"),("515050","AI智能ETF","科技主题","高成长"),("515790","光伏ETF","新能源","周期"),
    ("512660","军工ETF","军工主题","高弹性"),("510900","H股ETF","港股QDII","全球配置"),
    # Extended pool
    ("159845","中证1000ETF","宽基小盘","小盘成长"),("510330","华夏300ETF","宽基大盘","核心资产"),
    ("588220","科创100ETF","科技成长","高成长"),
    ("512800","银行ETF","金融主题","高股息"),("512200","地产ETF","金融主题","周期"),
    ("515880","通信ETF","科技主题","高成长"),("516050","科技龙头ETF","科技主题","高成长"),
    ("516510","云计算ETF","科技主题","高成长"),("516780","稀土ETF","商品","周期"),
    ("159766","旅游ETF","消费主题","周期"),("513060","恒生医疗ETF","医疗主题","海外"),
    ("159605","中概互联ETF","海外科技","高弹性"),("159611","电力ETF","公用事业","防御"),
    ("516190","文娱ETF","消费主题","周期"),("159869","游戏ETF","消费主题","高弹性"),
]


def _fetch_etf_quotes():
    """Get real-time ETF prices from Tencent API."""
    import requests
    codes = ",".join(f"sh{c}" if c.startswith(("5","6","9")) else f"sz{c}" for c,*_ in ETF_POOL)
    try:
        r = requests.get(f"https://qt.gtimg.cn/q={codes}", timeout=5,
            headers={"User-Agent": "Mozilla/5.0"})
        results = []
        for line in r.text.strip().split("\n"):
            if "~" not in line: continue
            p = line.split("~")
            if len(p) < 40: continue
            results.append({
                "code": p[2], "name": p[1],
                "price": float(p[3]) if p[3] else 0,
                "change_pct": float(p[32]) if p[32] else 0,
                "volume": float(p[6]) if p[6] else 0,
                "amount": float(p[37]) if p[37] else 0,
                "high": float(p[33]) if p[33] else 0,
                "low": float(p[34]) if p[34] else 0,
                "open": float(p[5]) if p[5] else 0,
                "prev_close": float(p[4]) if p[4] else 0,
                "turnover": float(p[38]) if p[38] else 0,
            })
        return results
    except Exception as e:
        logger.warning(f"ETF quotes failed: {e}")
        return []


@fund_bp.route("/fund-advisor/sentiment", methods=["GET"])
@login_required
def get_sentiment():
    """ETF market sentiment dashboard."""
    try:
        quotes = _fetch_etf_quotes()
        if not quotes:
            return jsonify({"code": 0, "msg": "ETF data unavailable"})
        total = len(quotes)
        ups = [q for q in quotes if q["change_pct"] > 0]
        downs = [q for q in quotes if q["change_pct"] < 0]
        avg = sum(q["change_pct"] for q in quotes) / total
        top = sorted(quotes, key=lambda x: abs(x["change_pct"]), reverse=True)[:5]
        return jsonify({"code": 1, "data": {
            "total": total, "up_count": len(ups), "down_count": len(downs),
            "avg_change": round(avg, 2),
            "sentiment": "乐观" if avg > 0.5 else "悲观" if avg < -0.5 else "中性",
            "quotes": quotes,
            "top_movers": [{"code": q["code"], "name": q["name"],
                "change": round(q["change_pct"], 2)} for q in top],
        }})
    except Exception as e:
        return jsonify({"code": 0, "msg": str(e)}), 500


# Per-user conversation memory (in-memory dict, survives until worker restart)
_CHAT_MEMORY = {}  # {user_id: [{user, assistant}, ...]}

FUND_SYSTEM_PROMPT = """你是「简投·智顾」，一只专业的ETF基金投资助手。

【强制规则】回答任何关于ETF推荐/筛选/对比的问题时，直接从下方【ETF数据】中摘取相关行，原样输出Markdown表格。不得总结，不得改写数据，不得编造数值。

【输出格式】
### ETF列表
| 代码 | 名称 | 日涨跌 | PE分位 | 情绪 |
|------|------|--------|--------|------|
| <从数据中照抄> |

表格下方加一句简短建议和风险提示。中文回答。"""


@fund_bp.route("/fund-advisor/chat", methods=["POST"])
@login_required
def chat():
    """LLM-powered fund Q&A with multi-turn memory."""
    try:
        user_id = int(g.user_id or 1)
        payload = request.get_json() or {}
        question = str(payload.get("question", "")).strip()
        clear = payload.get("clear", False)
        if not question:
            return jsonify({"code": 0, "msg": "question required"})

        if clear:
            _CHAT_MEMORY.pop(user_id, None)

        quotes = _fetch_etf_quotes()

        # Build rich ETF context with PE percentiles and 30d returns
        pe_map = {}  # {code: pe_pct}
        ret30_map = {}  # {code: 30d_return}
        try:
            import akshare as ak
            idx_map = _derive_index_map()
            for idx_name, idx_code in idx_map.items():
                try:
                    df = ak.stock_zh_index_value_csindex(symbol=idx_code)
                    if len(df) > 0:
                        r = df.iloc[-1]
                        pe_col = "市盈率1" if "市盈率1" in df.columns else "动态市盈率"
                        pe_vals = df[pe_col].dropna().values
                        pe = float(r[pe_col])
                        pct = round((pe_vals < pe).sum() / len(pe_vals) * 100, 1) if len(pe_vals) > 100 else 50
                        pe_map[idx_code] = pct
                except Exception: pass
        except Exception: pass

        try:
            import requests as _r, numpy as _np
            for code in [q["code"] for q in quotes[:20]]:
                prefix = "sh" if code.startswith(("5","6","9")) else "sz"
                resp = _r.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                    params={"param": f"{prefix}{code},day,,,30,qfq"}, timeout=5,
                    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"})
                data = resp.json()
                root = ((data.get("data") or {}).get(f"{prefix}{code}") or {})
                rows = root.get("qfqday") or root.get("day") or []
                if len(rows) >= 2:
                    close = [float(r[2]) for r in rows]
                    ret30 = round((close[-1] / close[0] - 1) * 100, 2)
                    ret30_map[code] = ret30
        except Exception: pass

        # Build data rows for LLM
        ctx_rows = []
        for q in quotes:
            code = q["code"]
            chg = q["change_pct"]
            ret30 = ret30_map.get(code, 0)
            pe_pct = pe_map.get(code, 50)
            sentiment = "🔥强势" if chg > 1 else "❄️弱势" if chg < -1 else "💎低估" if pe_pct < 30 else "⚠️高估" if pe_pct > 70 else "适中"
            ctx_rows.append(f"| {code} | {q['name']} | {chg:+.1f}% | {ret30:+.1f}% | PE{pe_pct:.0f}% | {sentiment} |")

        ctx = "\n".join(ctx_rows)

        history = _CHAT_MEMORY.get(user_id, [])[-8:]  # Last 4 exchanges
        msgs = [{"role": "system", "content": f"{FUND_SYSTEM_PROMPT}\n\n【当前ETF实时行情】\n{ctx}"}]
        for h in history:
            msgs.append({"role": "user", "content": h["user"]})
            msgs.append({"role": "assistant", "content": h["assistant"]})
        msgs.append({"role": "user", "content": question})

        llm = LLMService()
        # Use direct text call — chat doesn't need JSON output
        try:
            model = llm.get_default_model()
            import requests as _r
            key = os.getenv("DEEPSEEK_API_KEY", "")
            resp = _r.post("https://api.deepseek.com/v1/chat/completions", json={
                "model": model, "messages": msgs, "temperature": 0.7, "max_tokens": 800,
            }, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=45)
            data = resp.json()
            reply_text = data["choices"][0]["message"]["content"]
        except Exception:
            reply_text = llm.safe_call_llm(
                FUND_SYSTEM_PROMPT,
                f"ETF行情：\n{ctx}\n\n用户问题：{question}\n\n请用JSON格式回答：{{\"answer\":\"你的回答\"}}",
                default_structure={"answer": ""}
            )
            if isinstance(reply_text, dict):
                reply_text = reply_text.get("answer", "") or str(reply_text)
        reply_text = str(reply_text or "").strip()
        if not reply_text:
            reply_text = "抱歉，AI 暂时无法处理此问题，请稍后重试。"

        history.append({"user": question, "assistant": reply_text})
        _CHAT_MEMORY[user_id] = history

        return jsonify({"code": 1, "data": {"reply": reply_text}})
    except Exception as e:
        return jsonify({"code": 0, "msg": str(e)}), 500


# ===== Benchmark Comparison =====

import os as _os

@fund_bp.route("/fund-advisor/benchmark", methods=["POST"])
@login_required
def benchmark():
    """Compare a fund against similar ETFs."""
    payload = request.get_json() or {}
    target_code = str(payload.get("code", "")).strip()
    if not target_code:
        return jsonify({"code": 0, "msg": "code required"})

    quotes = _fetch_etf_quotes()
    target = next((q for q in quotes if q["code"] == target_code), None)
    if not target:
        return jsonify({"code": 0, "msg": "fund not found"})

    # Score similarity: same broad category = same first digit group
    def _similarity(a, b):
        score = 0
        if a["code"][:2] == b["code"][:2]: score += 2  # Same exchange prefix
        if abs(a["change_pct"] - b["change_pct"]) < 0.5: score += 1  # Similar daily change
        if abs(a["price"] - b["price"]) < a["price"] * 0.3: score += 1  # Similar price range
        return score

    similar = sorted(
        [{"code": q["code"], "name": q["name"], "price": q["price"],
          "change_pct": q["change_pct"],
          "similarity": _similarity(target, q)} for q in quotes if q["code"] != target_code],
        key=lambda x: x["similarity"], reverse=True
    )[:5]

    target_detail = {
        "code": target["code"], "name": target["name"],
        "price": target["price"], "change_pct": target["change_pct"],
    }

    try:
        import akshare as ak
        df = ak.stock_zh_index_value_csindex(symbol="沪深300")
        target_detail["market_pe"] = round(float(df.iloc[-1].get("市盈率1", 0)), 2) if len(df) > 0 else 0
        target_detail["market_pe_pct"] = round(float(df.iloc[-1].get("静态市盈率分位", 50)) if "静态市盈率分位" in df.columns else 50, 1)
    except Exception:
        target_detail["market_pe"] = 0
        target_detail["market_pe_pct"] = 50

    return jsonify({"code": 1, "data": {"target": target_detail, "similar": similar}})


# ===== ETF Valuation & PE/PB Percentile =====

# Derive tracked indices dynamically from ETF pool categories
def _derive_index_map():
    """Return indices tracked by ETFs in the pool (only those with PE/PB data)."""
    idx_map = {}
    cats = set(cat for _,_,cat,_ in ETF_POOL)
    if any("宽基" in c for c in cats) or any("大盘" in c for c in cats):
        idx_map["沪深300"] = "000300"; idx_map["中证500"] = "000905"; idx_map["上证50"] = "000016"
    if not idx_map:
        idx_map = {"沪深300":"000300","中证500":"000905","上证50":"000016"}
    return idx_map

_VAL_CACHE = {"data": None, "time": 0}

@fund_bp.route("/fund-advisor/valuation", methods=["GET"])
@login_required
def get_valuation():
    global _VAL_CACHE
    import time as _t
    if _VAL_CACHE["data"] and _t.time() - _VAL_CACHE["time"] < 3600:
        return jsonify({"code": 1, "data": _VAL_CACHE["data"]})
    try:
        import akshare as ak
        result = []
        idx_map = _derive_index_map()
        for idx_name, idx_code in idx_map.items():
            try:
                df = ak.stock_zh_index_value_csindex(symbol=idx_code)
                pe, pe_pct, pb, pb_pct, div_y = 0, 50, 0, 50, 0
                if len(df) > 0:
                    r = df.iloc[-1]
                    pe_vals = df["市盈率1"].dropna().values
                    pe = float(r["市盈率1"]) if r["市盈率1"] else 0
                    pe_pct = round((pe_vals < pe).sum()/len(pe_vals)*100,1) if len(pe_vals)>5 and pe>0 else 50
                    div_y = float(r.get("股息率1", 0) or 0)

                status = "低估" if pe_pct < 30 else "高估" if pe_pct > 70 else "适中"
                result.append({"index_name":idx_name,"index_code":idx_code,
                    "pe":round(pe,2),"pe_percentile":round(pe_pct,1),
                    "pb":round(pb,2),"pb_percentile":round(pb_pct,1),
                    "div_yield":round(div_y,2),"status":status})
            except Exception: pass
        _VAL_CACHE = {"data": result, "time": _t.time()}
        return jsonify({"code": 1, "data": result})
    except Exception as e:
        return jsonify({"code": 0, "msg": str(e)}), 500


# ===== Theme Trend Scoring =====

@fund_bp.route("/fund-advisor/themes", methods=["GET"])
@login_required
def get_themes():
    """Theme/sector trend scoring — dynamically from ETF_POOL categories."""
    try:
        import requests as _req
        # Group ETFs by category
        theme_map = {}
        for code, name, cat, tag in ETF_POOL:
            theme_map.setdefault(cat, []).append(code)

        themes = []
        for theme_name, etf_list in theme_map.items():
            codes = ",".join(f"sh{c}" if c.startswith(("5","6","9")) else f"sz{c}" for c in etf_list[:10])
            r = _req.get(f"https://qt.gtimg.cn/q={codes}", timeout=5,
                headers={"User-Agent": "Mozilla/5.0"})
            changes = []
            etf_data = []
            for line in r.text.strip().split("\n"):
                if "~" not in line: continue
                p = line.split("~")
                if len(p) < 40: continue
                chg = float(p[32]) if p[32] else 0
                changes.append(chg)
                etf_data.append({"code": p[2], "name": p[1], "change_pct": round(chg,2)})
            if changes:
                avg_change = round(sum(changes)/len(changes), 2)
                score = round(50 + avg_change * 5, 1)
                score = max(0, min(100, score))
                trend = "强势" if score > 60 else "弱势" if score < 40 else "中性"
                themes.append({"name": theme_name, "trend": trend, "score": score, "avg_change": avg_change, "etfs": etf_data})

        themes.sort(key=lambda x: x["score"], reverse=True)
        return jsonify({"code": 1, "data": themes})
    except Exception as e:
        return jsonify({"code": 0, "msg": str(e)}), 500


# ===== 30-Day Performance Trend =====

@fund_bp.route("/fund-advisor/trend30", methods=["GET"])
@login_required
def get_trend30():
    """30-day K-line performance for key ETFs."""
    import requests as _r, pandas as _pd, numpy as _np
    key_etfs = [(c,n) for c,n,*_ in ETF_POOL[:6]]
    result = []
    for code, name in key_etfs:
        try:
            prefix = "sh" if code.startswith(("5","6","9")) else "sz"
            resp = _r.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                params={"param": f"{prefix}{code},day,,,30,qfq"}, timeout=10,
                headers={"User-Agent":"Mozilla/5.0","Referer":"https://gu.qq.com/"})
            data = resp.json()
            root = ((data.get("data") or {}).get(f"{prefix}{code}") or {})
            rows = root.get("qfqday") or root.get("day") or []
            if not rows: continue
            close = [float(r[2]) for r in rows]
            dates = [r[0] for r in rows]
            change_pct = round((close[-1]/close[0]-1)*100,2)
            # Simple trend line: linear regression slope
            x = _np.arange(len(close))
            slope = _np.polyfit(x, close, 1)[0]
            trend = "上升" if slope>0 else "下降"
            result.append({"code":code,"name":name,"dates":dates[-10:],"prices":[round(c,2) for c in close[-10:]],
                "change_30d":change_pct,"trend":trend,"slope":round(float(slope),4)})
        except Exception: pass
    return jsonify({"code":1,"data":result})


# ===== Dividend / Cash Flow Strategy =====

@fund_bp.route("/fund-advisor/dividend", methods=["GET"])
@login_required
def get_dividend():
    """High-dividend ETF ranking and cash flow calendar."""
    # Simulated dividend data from known ETFs + real prices
    # Build dividend ETF list from pool (高股息/红利/银行 tag)
    div_candidates = [(c,n,t) for c,n,cat,t in ETF_POOL if any(k in (cat+t) for k in ["股息","红利","银行","债券","货币"])]
    if not div_candidates: div_candidates = [(c,n,t) for c,n,cat,t in ETF_POOL[:5]]
    div_etfs = [{"code":c,"name":n,"div_yield":3.0+hash(c)%30/10,"div_per_year":2,"last_div":"2026-01-15"} for c,n,_ in div_candidates]
    import requests as _r
    codes = ",".join(f"sh{d['code']}" if d['code'].startswith(("5","6","9")) else f"sz{d['code']}" for d in div_etfs)
    resp = _r.get(f"https://qt.gtimg.cn/q={codes}", timeout=5, headers={"User-Agent":"Mozilla/5.0"})
    prices = {}
    for line in resp.text.strip().split("\n"):
        if "~" not in line: continue
        p=line.split("~")
        if len(p)<4: continue
        prices[p[2]]=float(p[3]) if p[3] else 0

    for d in div_etfs:
        d["price"] = prices.get(d["code"], 0)
        d["monthly_income"] = round(d["price"] * d["div_yield"] / 100 / 12, 3) if d["price"] else 0
        # Next dividend date: roughly 3/6/9/12 month cycle
        from datetime import datetime as _dt
        ld = _dt.strptime(d["last_div"], "%Y-%m-%d")
        next_div = _dt(ld.year, ld.month+3 if ld.month<10 else 1, 15)
        d["next_div"] = next_div.strftime("%Y-%m-%d")

    div_etfs.sort(key=lambda x: x["div_yield"], reverse=True)
    return jsonify({"code":1,"data":div_etfs})


# ===== All-Weather Rotation =====

@fund_bp.route("/fund-advisor/allweather", methods=["GET"])
@login_required
def get_allweather():
    """All-weather rotation: age-based base + volatility-adjusted allocation."""
    import requests as _r, numpy as _np
    age = int(request.args.get("age", 35))
    risk = str(request.args.get("risk", "平衡型"))
    # Calculate 20-day volatility for key asset classes
    # Find asset proxies from pool: use multiple stock ETFs for diversification
    stock_etfs = [(c,n) for c,n,cat,_ in ETF_POOL if "宽基" in cat][:4]
    if not stock_etfs: stock_etfs = [(c,n) for c,n,*_ in ETF_POOL[:3]]
    bond_etf = next(((c,n) for c,n,cat,_ in ETF_POOL if "债券" in cat), ("511010","国债ETF"))
    gold_etf = next(((c,n) for c,n,cat,_ in ETF_POOL if "黄金" in n), ("518880","黄金ETF"))
    cash_etf = next(((c,n) for c,n,cat,_ in ETF_POOL if "货币" in cat), ("511880","银华日利"))
    assets = { "股票": stock_etfs, "债券": bond_etf, "黄金": gold_etf, "现金": cash_etf }
    vols = {}
    for class_name, etf_list in [("股票",stock_etfs),("债券",[bond_etf]),("黄金",[gold_etf]),("现金",[cash_etf])]:
      class_vols = []
      for code, name in (etf_list if isinstance(etf_list,list) else [etf_list]):
        try:
            prefix = "sh" if code.startswith(("5","6","9")) else "sz"
            resp = _r.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                params={"param": f"{prefix}{code},day,,,30,qfq"}, timeout=10,
                headers={"User-Agent":"Mozilla/5.0","Referer":"https://gu.qq.com/"})
            data = resp.json()
            root = ((data.get("data") or {}).get(f"{prefix}{code}") or {})
            rows = root.get("qfqday") or root.get("day") or []
            if not rows: continue
            close = [float(r[2]) for r in rows]
            returns = _np.diff(close) / close[:-1]
            vol = round(float(_np.std(returns) * _np.sqrt(252) * 100), 1)  # Annualized vol %
            class_vols.append(vol)
        except Exception: pass

    stock_vol = vols.get("股票", 25)
    bond_vol = vols.get("债券", 5)
    gold_vol = vols.get("黄金", 15)

    # Step 1: Age-based base allocation (same logic as strategy config)
    if risk == "进攻型": base_equity = min(80, max(10, 120 - age)); base_gold = 5
    elif risk == "防守型": base_equity = min(60, max(10, 80 - age)); base_gold = 20
    else: base_equity = min(70, max(10, 100 - age)); base_gold = 10
    base_bond = max(5, 100 - base_equity - base_gold - 5)
    base_cash = max(5, 100 - base_equity - base_bond - base_gold)

    # Step 2: Volatility overlay — adjust each ETF from its base share
    def _adj(base, vol, high_th, low_th):
        if vol > high_th: return max(2, base - 8)
        if vol > low_th: return max(2, base - 4)
        return base

    equity = _adj(base_equity, stock_vol, 35, 28)
    bond = _adj(base_bond, bond_vol, 12, 8)
    gold = _adj(base_gold, gold_vol, 28, 22)
    cash = max(5, 100 - equity - bond - gold)

    alerts = []
    # Alert will be set after portfolio is built with per-ETF vol data

    rules = [
        {"asset":"股票","low":"<28%","mid":"28-35%","high":">35%","low_pct":50,"mid_pct":35,"high_pct":20},
        {"asset":"债券","low":"<8%","mid":"8-12%","high":">12%","low_pct":30,"mid_pct":20,"high_pct":5},
        {"asset":"黄金","low":"<22%","mid":"22-28%","high":">28%","low_pct":10,"mid_pct":5,"high_pct":5},
    ]
    # Each ETF independently adjusts based on its own volatility
    portfolio = []
    stock_vols = {}
    for code, name in stock_etfs:
        try:
            prefix = "sh" if code.startswith(("5","6","9")) else "sz"
            resp = _r.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                params={"param": f"{prefix}{code},day,,,30,qfq"}, timeout=10,
                headers={"User-Agent":"Mozilla/5.0","Referer":"https://gu.qq.com/"})
            data = resp.json()
            root = ((data.get("data") or {}).get(f"{prefix}{code}") or {})
            rows = root.get("qfqday") or root.get("day") or []
            if rows:
                close = [float(r[2]) for r in rows]
                returns = _np.diff(close) / close[:-1]
                vol = round(float(_np.std(returns) * _np.sqrt(252) * 100), 1)
                stock_vols[code] = vol
        except Exception: pass

    base_per_etf = equity // len(stock_etfs) if stock_etfs else equity
    for code, name in stock_etfs:
        v = stock_vols.get(code, 25)
        if v > 35: pct = max(2, base_per_etf - 8)
        elif v > 28: pct = max(2, base_per_etf - 4)
        else: pct = base_per_etf
        portfolio.append({"code":code,"name":name,"vol":v,"pct":pct})
    total_stock = sum(p["pct"] for p in portfolio)
    bond = max(5, 100 - total_stock - gold - 5)
    cash = max(5, 100 - total_stock - bond - gold)
    if bond > 0: portfolio.append({"code":bond_etf[0],"name":bond_etf[1],"pct":bond})
    if gold > 0: portfolio.append({"code":gold_etf[0],"name":gold_etf[1],"pct":gold})
    if cash > 0: portfolio.append({"code":cash_etf[0],"name":cash_etf[1],"pct":cash})

    # Build alert from per-ETF volatility
    high_vols = [(p["name"],p["vol"]) for p in portfolio if p.get("vol",0) > 35]
    mid_vols = [(p["name"],p["vol"]) for p in portfolio if 28 < p.get("vol",0) <= 35]
    if high_vols: alert = "⚠ " + "、".join(f"{n}({v:.0f}%)" for n,v in high_vols) + " 波动超标，自动减仓"
    elif mid_vols: alert = "⚡ " + "、".join(f"{n}({v:.0f}%)" for n,v in mid_vols) + " 波动偏高，适度减仓"
    else: alert = "✅ 各 ETF 波动均在正常范围"

    return jsonify({"code":1,"data":{
        "volatility": vols, "alert": alert, "rules": rules,
        "allocation": {"equity":equity,"bond":bond,"gold":gold,"cash":cash},
        "portfolio": portfolio,
        "rebalance_suggestion": "月度检视，偏离>5%时再平衡" if stock_vol<35 else "建议下周检视，波动率偏高",
    }})


# ===== Daily Briefing =====

@fund_bp.route("/fund-advisor/daily", methods=["GET"])
@login_required
def get_daily_briefing():
    """LLM-generated daily market briefing."""
    quotes = _fetch_etf_quotes()
    if not quotes:
        return jsonify({"code":0,"msg":"No data"})

    ups = [q for q in quotes if q["change_pct"]>0]
    downs = [q for q in quotes if q["change_pct"]<0]
    avg = sum(q["change_pct"] for q in quotes)/len(quotes)
    top3 = sorted(quotes, key=lambda x: x["change_pct"], reverse=True)[:3]
    bot3 = sorted(quotes, key=lambda x: x["change_pct"])[:3]

    ctx = f"今日ETF行情：{len(ups)}涨{len(downs)}跌，平均涨跌{avg:+.2f}%\n"
    top_str = ', '.join(f'{q["name"]}{q["change_pct"]:+.1f}%' for q in top3)
    bot_str = ', '.join(f'{q["name"]}{q["change_pct"]:+.1f}%' for q in bot3)
    ctx += f"领涨：{top_str}\n"
    ctx += f"领跌：{bot_str}\n"

    llm = LLMService()
    system = "你是基金投资顾问。根据ETF行情数据生成100字以内的每日简评，通俗易懂，面向普通投资者。用中文。"
    reply = llm.safe_call_llm(system, ctx, default_structure={"briefing":""})
    text = reply.get("briefing","") if isinstance(reply,dict) else str(reply)

    return jsonify({"code":1,"data":{"briefing":text,"date":__import__("datetime").datetime.now().strftime("%Y-%m-%d"),
        "market_summary":{"up":len(ups),"down":len(downs),"avg_change":round(avg,2)}}})


# ===== Fund Screening =====

@fund_bp.route("/fund-advisor/screen", methods=["POST"])
@login_required
def screen_funds():
    """Natural language fund screening — parse criteria from query."""
    payload = request.get_json() or {}
    query = str(payload.get("query","")).strip()
    if not query:
        return jsonify({"code":0,"msg":"query required"})

    quotes = _fetch_etf_quotes()
    if not quotes:
        return jsonify({"code":0,"msg":"No data"})

    # Simple NLP: extract keywords
    q_lower = query.lower()
    results = []
    for q in quotes:
        score = 0
        reasons = []
        # Check theme/category keywords
        if "高股息" in query or "红利" in query:
            if q["code"] in ("510880","512880","512800"): score+=3; reasons.append("高股息")
        if "科技" in query and any(k in q["name"] for k in ["科技","AI","智能","芯片"]):
            score+=3; reasons.append("科技主题")
        if "消费" in query and any(k in q["name"] for k in ["消费","酒"]):
            score+=3; reasons.append("消费主题")
        if "新能源" in query and "新能源" in q["name"]:
            score+=3; reasons.append("新能源主题")
        if "宽基" in query and any(k in q["name"] for k in ["300","500","创业板","50ETF"]):
            score+=2; reasons.append("宽基指数")
        if "医疗" in query or "医药" in query:
            if "医药" in q["name"]: score+=3; reasons.append("医药主题")
        if "军工" in query and "军工" in q["name"]:
            score+=3; reasons.append("军工主题")
        if "黄金" in query and "黄金" in q["name"]:
            score+=3; reasons.append("黄金")
        if "债券" in query or "国债" in query:
            if "国债" in q["name"]: score+=3; reasons.append("债券")
        if "纳指" in query or "海外" in query:
            if any(k in q["name"] for k in ["纳指","中概","H股"]): score+=2; reasons.append("海外")
        # Change threshold
        if "涨幅" in query or "涨" in query:
            if q["change_pct"]>0: score+=1
        if "跌" in query:
            if q["change_pct"]<0: score+=1
        # Volatility/dividend filters
        if "低波动" in query:
            if abs(q["change_pct"])<1: score+=2; reasons.append("低波动")
        # Include all if no specific theme
        if not reasons:
            score = 1
            reasons.append("全市场")
        if score > 0:
            results.append({"code":q["code"],"name":q["name"],"price":q["price"],
                "change_pct":q["change_pct"],"score":score,"reasons":reasons})

    results.sort(key=lambda x: x["score"], reverse=True)
    return jsonify({"code":1,"data":{"query":query,"results":results[:10]}})


# ===== Monthly Check =====

@fund_bp.route("/fund-advisor/monthly", methods=["POST"])
@login_required
def monthly_check():
    """Monthly portfolio review and rebalance prompt."""
    payload = request.get_json() or {}
    portfolio = payload.get("portfolio", [])  # [{code, name, target_pct, actual_pct?}]
    if not portfolio:
        return jsonify({"code":0,"msg":"portfolio required"})

    quotes = _fetch_etf_quotes()
    price_map = {q["code"]: q for q in quotes}

    checks = []
    total_drift = 0
    for item in portfolio:
        code = item.get("code","")
        target = float(item.get("target_pct",0))
        actual = float(item.get("actual_pct", target))
        drift = abs(target - actual)
        total_drift += drift
        q = price_map.get(code, {})
        checks.append({
            "code": code, "name": item.get("name", q.get("name","")),
            "target_pct": target, "actual_pct": actual,
            "drift": round(drift,1),
            "needs_rebalance": drift > 5,
            "current_price": q.get("price",0),
            "change_today": q.get("change_pct",0),
        })

    needs_rebalance = total_drift > 10
    return jsonify({"code":1,"data":{
        "total_drift": round(total_drift,1),
        "needs_rebalance": needs_rebalance,
        "suggestion": "建议再平衡：部分偏离超5%的资产调回目标比例" if needs_rebalance else "持仓偏离在合理范围内，无需调整",
        "items": checks,
    }})


# ===== ETF K-line Preview =====

@fund_bp.route("/fund-advisor/kline", methods=["GET"])
@login_required
def get_kline():
    """Get recent K-line for an ETF (quick preview)."""
    code = request.args.get("code","").strip()
    if not code: return jsonify({"code":0,"msg":"code required"})
    import requests as _r
    prefix = "sh" if code.startswith(("5","6","9")) else "sz"
    try:
        resp = _r.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
            params={"param":f"{prefix}{code},day,,,60,qfq"}, timeout=10,
            headers={"User-Agent":"Mozilla/5.0","Referer":"https://gu.qq.com/"})
        data = resp.json(); root = ((data.get("data") or {}).get(f"{prefix}{code}") or {})
        rows = root.get("qfqday") or root.get("day") or []
        result = [{"date":r[0],"open":float(r[1]),"close":float(r[2]),"high":float(r[3]),"low":float(r[4]),"volume":float(r[5])} for r in rows[-30:]]
        return jsonify({"code":1,"data":result})
    except Exception as e:
        return jsonify({"code":0,"msg":str(e)}),500


# ===== Portfolio Scenario Comparison =====

@fund_bp.route("/fund-advisor/compare", methods=["POST"])
@login_required
def compare_scenarios():
    """Compare hypothetical portfolio allocations."""
    # Simulate annual returns for different allocations
    scenarios = [
        {"name":"进攻型 (70/20/10)", "equity":70,"bond":20,"cash":10, "est_return":12.5, "est_vol":22, "max_dd":35,
         "desc":"适合年轻投资者，追求高收益"},
        {"name":"平衡型 (40/30/30)", "equity":40,"bond":30,"cash":30, "est_return":7.8, "est_vol":12, "max_dd":18,
         "desc":"稳健增长，控制回撤"},
        {"name":"防守型 (20/60/20)", "equity":20,"bond":60,"cash":20, "est_return":4.5, "est_vol":6, "max_dd":8,
         "desc":"保值为主，低波动"},
        {"name":"全天候 (30/40/20/10)", "equity":30,"bond":40,"gold":20,"cash":10, "est_return":6.5, "est_vol":10, "max_dd":12,
         "desc":"股债商现金四类分散"},
    ]
    return jsonify({"code":1,"data":scenarios})


# ===== DCA Calculator =====

@fund_bp.route("/fund-advisor/dca", methods=["POST"])
@login_required
def calc_dca():
    """Dollar-cost averaging calculator."""
    payload = request.get_json() or {}
    monthly = float(payload.get("monthly", 5000))
    years = int(payload.get("years", 5))
    annual_return = float(payload.get("annual_return", 8))

    months = years * 12
    monthly_rate = annual_return / 100 / 12
    # Future value of annuity
    if monthly_rate > 0:
        fv = monthly * ((1 + monthly_rate) ** months - 1) / monthly_rate
    else:
        fv = monthly * months
    total_invested = monthly * months
    profit = fv - total_invested

    # Year-by-year breakdown
    yearly = []
    for y in range(1, years + 1):
        m = y * 12
        if monthly_rate > 0:
            fv_y = monthly * ((1 + monthly_rate) ** m - 1) / monthly_rate
        else:
            fv_y = monthly * m
        invested_y = monthly * m
        yearly.append({"year": y, "invested": round(invested_y, 0),
            "value": round(fv_y, 0), "profit": round(fv_y - invested_y, 0)})

    return jsonify({"code": 1, "data": {
        "monthly": monthly, "years": years, "annual_return": annual_return,
        "total_invested": round(total_invested, 0), "future_value": round(fv, 0),
        "total_profit": round(profit, 0), "roi": round(profit / total_invested * 100, 1) if total_invested > 0 else 0,
        "yearly": yearly,
    }})


# ===== PE Trend =====

@fund_bp.route("/fund-advisor/pe_trend", methods=["GET"])
@login_required
def pe_trend():
    """PE percentile trend data for major indices."""
    trend_map = {"hs300":"沪深300","zz500":"中证500","sz50":"上证50","cyb":"创业板指","kc50":"科创50"}
    idx_key = request.args.get("index", "hs300")
    idx = trend_map.get(idx_key, "沪深300")
    try:
        import akshare as ak
        df = ak.stock_zh_index_value_csindex(symbol=idx)
        if len(df) == 0:
            return jsonify({"code": 0, "msg": "no data"})

        if "市盈率1" in df.columns:
            pe_col = "市盈率1"
        elif "动态市盈率" in df.columns:
            pe_col = "动态市盈率"
        else:
            return jsonify({"code": 0, "msg": "unknown columns"})

        vals = df[pe_col].dropna().values
        # Last 500 data points
        recent = vals[-500:]
        current_pe = float(recent[-1])
        pct = round((vals < current_pe).sum() / len(vals) * 100, 1)

        # Sample every ~20 points for chart
        sampled = [{"date": str(df.iloc[i].get("日期", "")), "pe": float(recent[j]),
            "pct": round((vals < float(recent[j])).sum() / len(vals) * 100, 1)}
            for j, i in enumerate(range(max(0, len(df) - 500), len(df), 20))]

        return jsonify({"code": 1, "data": {
            "index": idx, "current_pe": current_pe, "current_pct": pct,
            "min_pe": round(float(vals.min()), 2), "max_pe": round(float(vals.max()), 2),
            "trend": sampled[-25:],  # Last 25 sample points
        }})
    except Exception as e:
        return jsonify({"code": 0, "msg": str(e)}), 500


# ===== Dashboard Summary =====

@fund_bp.route("/fund-advisor/dashboard", methods=["GET"])
@login_required
def dashboard():
    """One-stop dashboard: sentiment + themes + valuation + top movers."""
    quotes = _fetch_etf_quotes()
    up_n = len([q for q in quotes if q["change_pct"]>0]) if quotes else 0
    dn_n = len([q for q in quotes if q["change_pct"]<0]) if quotes else 0
    avg = round(sum(q["change_pct"] for q in quotes)/len(quotes),2) if quotes else 0
    top5 = sorted(quotes, key=lambda x:x["change_pct"],reverse=True)[:5] if quotes else []
    bot5 = sorted(quotes, key=lambda x:x["change_pct"])[:5] if quotes else []

    # PE summary — dynamic from ETF pool
    pe_summary = []
    try:
        import akshare as ak
        idx_map = _derive_index_map()
        for idx_name in list(idx_map.keys())[:5]:
            try:
                df = ak.stock_zh_index_value_csindex(symbol=idx_map[idx_name])
                if len(df)>0:
                    r = df.iloc[-1]
                    pe = float(r["市盈率1"]) if r["市盈率1"] else 0
                    pe_vals = df["市盈率1"].dropna().values
                    pct = round((pe_vals<pe).sum()/len(pe_vals)*100,1) if len(pe_vals)>200 and pe>0 else 50
                    pe_summary.append({"index":idx_name,"pe":round(pe,2),"pct":pct,
                        "status":"低估" if pct<30 else "高估" if pct>70 else "适中"})
            except: pass
    except Exception: pass

    return jsonify({"code":1,"data":{
        "sentiment":{"up":up_n,"down":dn_n,"avg_change":avg,"total":len(quotes)},
        "top5":[{"code":q["code"],"name":q["name"],"change":round(q["change_pct"],2)} for q in top5],
        "bot5":[{"code":q["code"],"name":q["name"],"change":round(q["change_pct"],2)} for q in bot5],
        "pe_summary":pe_summary,
    }})


# ===== ETF Pool Management =====

@fund_bp.route("/fund-advisor/etf-pool", methods=["GET"])
@login_required
def get_etf_pool():
    """Return the full ETF pool."""
    items = [{"code":c,"name":n,"category":cat,"tag":t} for c,n,cat,t in ETF_POOL]
    return jsonify({"code":1,"data":items})

@fund_bp.route("/fund-advisor/etf-pool/add", methods=["POST"])
@login_required
def add_etf():
    """Add ETF to pool."""
    global ETF_POOL
    payload = request.get_json() or {}
    code = str(payload.get("code","")).strip()
    name = str(payload.get("name","")).strip()
    category = str(payload.get("category","宽基")).strip()
    tag = str(payload.get("tag","")).strip()
    if not code or not name:
        return jsonify({"code":0,"msg":"code and name required"})
    if any(c==code for c,*_ in ETF_POOL):
        return jsonify({"code":0,"msg":"already exists"})
    ETF_POOL.append((code,name,category,tag))
    return jsonify({"code":1,"data":{"code":code,"name":name}})

@fund_bp.route("/fund-advisor/etf-pool/remove", methods=["POST"])
@login_required
def remove_etf():
    """Remove ETF from pool."""
    global ETF_POOL
    payload = request.get_json() or {}
    code = str(payload.get("code","")).strip()
    ETF_POOL = [x for x in ETF_POOL if x[0] != code]
    return jsonify({"code":1,"msg":"removed"})


# ===== Strategy Config =====

@fund_bp.route("/fund-advisor/strategy", methods=["POST"])
@login_required
def strategy():
    """Risk-age based portfolio allocation."""
    try:
        payload = request.get_json() or {}
        age = int(payload.get("age", 35))
        risk = str(payload.get("risk", "平衡型"))

        if risk == "进攻型":
            equity = min(80, max(10, 120 - age))
            gold, bond_min = 5, 5
        elif risk == "防守型":
            equity = min(60, max(10, 80 - age))
            gold, bond_min = 20, 10
        else:
            equity = min(70, max(10, 100 - age))
            gold, bond_min = 10, 10
        bond = max(bond_min, min(50, 100 - equity - gold - 5))
        cash = max(0, 100 - equity - bond - gold)

        etfs = []
        if equity > 20:
            etfs.append({"code": "510300", "name": "沪深300ETF", "pct": equity // 3})
            etfs.append({"code": "510500", "name": "中证500ETF", "pct": (equity - equity // 3) // 2})
            etfs.append({"code": "159915", "name": "创业板ETF", "pct": equity - equity // 3 - (equity - equity // 3) // 2})
        else:
            etfs.append({"code": "510880", "name": "红利ETF", "pct": equity})
        if bond > 0: etfs.append({"code": "511010", "name": "国债ETF", "pct": bond})
        if gold > 0: etfs.append({"code": "518880", "name": "黄金ETF", "pct": gold})
        if cash > 0: etfs.append({"code": "511880", "name": "银华日利", "pct": cash})

        return jsonify({"code": 1, "data": {
            "age": age, "risk": risk,
            "allocation": {"equity": equity, "bond": bond, "gold": gold, "cash": cash},
            "portfolio": etfs,
        }})
    except Exception as e:
        return jsonify({"code": 0, "msg": str(e)}), 500
