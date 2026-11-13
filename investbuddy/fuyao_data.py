"""Fuyao REST snapshots and annual statements for trusted local tasks."""
import json
import math
import os
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE = "https://fuyao.aicubes.cn/api/a-share/"
SOURCE = "同花顺扶摇"
MARKET_TZ = timezone(timedelta(hours=8))
DATASETS = (
    ("prices/snapshot", {"last_price": ("last_price", "元/股", "行情快照最新成交价")}),
    ("financials/income-statements", {
        "operating_income": ("operating_income", "元", "年报营业收入（扶摇 operating_income）"),
        "parent_holder_net_profit": ("net_income", "元", "年报归属于母公司股东的净利润"),
    }),
    ("valuations/snapshot", {"pe_ttm": ("pe_ttm", "倍", "最新估值快照 PE TTM")}),
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_json(url, key):
    request = Request(url, headers={"X-api-key": key, "Accept": "application/json"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        status = exc.code
        exc.close()
        return status, {}
    except (URLError, TimeoutError, ValueError):
        raise ValueError("扶摇请求超时、网络异常或响应不是有效 JSON。") from None


def data_time(value, path):
    if type(value) is not int or value <= 0:
        raise ValueError(f"扶摇 {path} 缺少有效数据时点。")
    try:
        return datetime.fromtimestamp(value / 1000, MARKET_TZ)
    except (ValueError, OverflowError, OSError):
        raise ValueError(f"扶摇 {path} 数据时点无效。") from None


def query_fuyao(task, fetch=fetch_json):
    key = os.environ.get("FUYAO_API_KEY", "").strip()
    if not key:
        raise ValueError("请先在本机启动进程中配置 FUYAO_API_KEY。")
    symbol = task["symbol"]
    from investbuddy.data import DEMO_STOCKS
    if symbol not in DEMO_STOCKS:
        raise ValueError("扶摇本机验收仅支持三只演示标的的完整证券代码。")
    evidence = []
    for path, fields in DATASETS:
        annual = path.startswith("financials/")
        params = {"thscode": symbol, "period": "annual", "limit": 1} if annual else {"thscodes": symbol}
        url = BASE + path + "?" + urlencode(params)
        status, payload = fetch(url, key)
        queried = datetime.now(timezone.utc)
        code = payload.get("code") if isinstance(payload, dict) else None
        if status == 429 or code == 429:
            raise ValueError(f"扶摇 {path} 达到调用频率或额度限制。")
        if status in (401, 403) or code in (2001, 2003):
            raise ValueError(f"扶摇 {path} 鉴权失败或权限不足（HTTP {status}，业务码 {code}）。")
        if status != 200 or type(code) is not int or code != 0:
            safe_code = code if type(code) is int else "无效"
            raise ValueError(f"扶摇 {path} 调用失败（HTTP {status}，业务码 {safe_code}）。")
        data = payload.get("data")
        rows = data.get("item") if isinstance(data, dict) else None
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise ValueError(f"扶摇 {path} 未返回一条有效记录。")
        row = rows[0]
        if row.get("thscode") != symbol:
            raise ValueError(f"扶摇 {path} 返回的证券代码不匹配。")
        observed = data_time(row.get("period_end_ms") if annual else data.get("timestamp"), path)
        currency = row.get("currency") if annual else "CNY"
        request_id = payload.get("request_id")
        if not isinstance(request_id, str) or not request_id.strip() or key in request_id:
            raise ValueError(f"扶摇 {path} 缺少有效请求编号。")
        if annual and (row.get("period") != "annual" or row.get("fiscal_period") != "FY"
                       or not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha()):
            raise ValueError("扶摇利润表的年报口径或币种无效。")
        for raw, (field, unit, basis) in fields.items():
            value = row.get(raw)
            if type(value) not in (int, float) or not math.isfinite(value) or (field == "last_price" and value <= 0):
                raise ValueError(f"扶摇 {path} 必需字段 {raw} 缺失或无效。")
            evidence.append(dict(
                id=f"E{len(evidence) + 1}", symbol=symbol, date=observed.date().isoformat(),
                field=field, value=value, unit=unit, basis=basis, source=SOURCE,
                dataset=path, source_url=url, raw_field=raw, currency=None if unit == "倍" else currency,
                report_period=observed.date().isoformat() if annual else None,
                data_at=observed.isoformat(), queried_at=queried.isoformat(), request_id=request_id,
            ))
    return evidence
