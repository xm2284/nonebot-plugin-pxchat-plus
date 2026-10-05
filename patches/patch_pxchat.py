"""Patch pxchat:
1. 给 AsyncOpenAI 调用加超时和重试上限
2. 私聊消息带上发送者 QQ 号（便于主人识别）
3. 系统提示词注入当前时间（北京时间）
4. 错误以私聊纯文本提醒主人；不向普通用户发报错提示
5. 限制并发 AI 请求（防刷屏导致 API 失败）
6. 限制分段回复（95% 单段）
7. 联网搜索增强（关键词触发多引擎预搜索：360/搜狗/Bing RSS）
8. 图片识别加超时 + 每条消息只识别 1 张图 + 先下载转 base64
9. 图片识别失败不再打扰主人
10. 模型故障自动切换（opus4.8 / kimik3 free）
11. 自动兜底：回复像“不知道”时联网搜索后重试一次
12. 全局发送限速（每条间隔 2 秒，防刷屏触发 QQ 风控）
"""

import site
from pathlib import Path

candidates = []
for sp in site.getsitepackages():
    p = Path(sp) / "nonebot_plugin_pxchat"
    if p.exists():
        candidates.append(p)

assert candidates, "nonebot_plugin_pxchat not found"
pkg = candidates[0]

# ---- 1. 超时补丁（chat.py）----
chat_py = pkg / "chat.py"
text = chat_py.read_text(encoding="utf-8")

old = 'base_url=ai_config.get("api_url", ""),\n        )'
new = (
    'base_url=ai_config.get("api_url", ""),\n'
    "            timeout=45.0,\n"
    "            max_retries=1,\n"
    "        )"
)
count = text.count(old)
assert count == 3, f"timeout patch: expected 3 matches, got {count}"
text = text.replace(old, new)

# ---- 3. 系统提示词注入当前时间（chat.py）----
old_sp = (
    "def get_system_prompt(is_group: bool = False):\n"
    "    personality = chat_manager.get_personality()\n"
    "    return personality + get_reply_format(is_group)"
)
new_sp = (
    "def get_system_prompt(is_group: bool = False):\n"
    "    import datetime as _dt\n"
    "    personality = chat_manager.get_personality()\n"
    "    _now = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=8)))\n"
    '    _wd = "一二三四五六日"[_now.weekday()]\n'
    '    _ts = _now.strftime("%Y年%m月%d日 %H:%M") + " 星期" + _wd\n'
    '    return personality + "\\n（当前时间：" + _ts + "）" + get_reply_format(is_group)'
)
assert old_sp in text, "system prompt patch: target not found"
text = text.replace(old_sp, new_sp)

# ---- 6. 分段限制（chat.py）----
old_seg = "2. 回复段数随机，80%的情况下保持一段内容，保持简洁"
new_seg = "2. 永远只返回一段内容（reply 数组只能有 1 个元素），绝不分段，保持极简"
assert old_seg in text, "segment patch: target not found"
text = text.replace(old_seg, new_seg)

# ---- 7. 联网搜索增强（chat.py）----
old_req = (
    "        # 构建请求参数\n"
    "        request_params = {\n"
    '            "model": ai_config.get("model", ""),\n'
    '            "messages": [{"role": "system", "content": get_system_prompt(is_group)}] + messages,\n'
    '            "response_format": {\n'
    "                'type': 'json_object'\n"
    "            }\n"
    "        }"
)
new_req = (
    "        # 构建请求参数（含联网搜索增强）\n"
    "        _sys_prompt = get_system_prompt(is_group)\n"
    '        _last_msg = _extract_text(messages[-1].get("content", "")) if messages else ""\n'
    "        _searched = False\n"
    '        _sr = ""\n'
    "        if _need_search(_last_msg):\n"
    "            _sr = await _bing_search_text(_build_query(_last_msg))\n"
    "            if _sr:\n"
    '                _sys_prompt += "\\n【联网搜索结果·以此为准（必须据此回答，绝不许说不知道；若你之前说过与此矛盾的内容，一律以搜索结果为准，不许重复自己之前的错误）】\\n" + _sr\n'
    "                _searched = True\n"
    "        request_params = {\n"
    '            "model": ai_config.get("model", ""),\n'
    '            "messages": [{"role": "system", "content": _sys_prompt}] + messages,\n'
    '            "response_format": {\n'
    "                'type': 'json_object'\n"
    "            }\n"
    "        }"
)
assert old_req in text, "search patch: target not found"
text = text.replace(old_req, new_req)

# 搜索辅助函数（chat.py 顶部）
old_head = "def get_current_time() -> str:"
new_head = (
    '_SEARCH_KEYWORDS = (\n'
    '    "天气", "气温", "下雨", "下雪", "新闻", "热搜", "最新", "股价", "汇率",\n'
    '    "油价", "房价", "票房", "比分", "谁赢", "发售", "开播", "直播", "比赛",\n'
    '    "分数线", "多少钱", "价格", "发生了什么",\n'
    '    "接下一句", "下一句", "上一句", "什么梗", "啥梗", "什么意思", "什么歌",\n'
    '    "谁唱的", "歌词", "台词", "出自", "出处", "是谁",\n'
    '    "你知道", "你认识", "听说过", "是什么梗", "什么来头", "哪个人", "哪个主播",\n'
    ')\n\n\n'
    '_SEARCH_UA = (\n'
    '    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "\n'
    '    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"\n'
    ')\n'
    '_SEARCH_MUA = (\n'
    '    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "\n'
    '    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"\n'
    ')\n\n\n'
    'def _clean_serp(s) -> str:\n'
    '    import html as _html\n'
    '    import re as _re\n'
    '    s = _re.sub(r"<!--.*?-->", "", s)\n'
    '    s = _re.sub(r"<(script|style)[^>]*>.*?</\\1>", " ", s, flags=_re.S)\n'
    '    s = _re.sub(r"<[^>]*$", "", s)\n'
    '    s = _re.sub(r"^[^>]*>", "", s)\n'
    '    s = _re.sub(r"<[^>]+>", "", s)\n'
    '    return _re.sub(r"\\s+", " ", _html.unescape(s)).strip()\n\n\n'
    'def _extract_text(content) -> str:\n'
    '    if isinstance(content, str):\n'
    '        return content\n'
    '    if isinstance(content, list):\n'
    '        return " ".join(\n'
    '            b.get("text", "") for b in content\n'
    '            if isinstance(b, dict) and b.get("type") == "text"\n'
    '        )\n'
    '    return ""\n\n\n'
    'def _clean_search_query(query: str) -> str:\n'
    '    import re as _re\n'
    '    q = _re.sub(r"^[^\\d]{0,6}\\d+(?:[（(][^）)]*[)）])?说[：:]\\s*", "", query)\n'
    '    q = _re.sub(r"^[\\s:：、，,。.！!~～]+", "", q)\n'
    '    return q.strip()[:80]\n\n\n'
    'def _build_query(text: str) -> str:\n'
    '    import re as _re\n'
    '    _orig = _clean_search_query(text)\n'
    '    _q = _re.sub(r"^(请问|你?知道|你?认识|听说过|认得|了解)[一下]?[，,]?\\s*", "", _orig).strip()\n'
    '    _q = _re.sub(r"[吗呢吧啊嘛么]([？?！!。]*)$", "", _q).strip()\n'
    '    _q = _q.strip("？?！!。~～ ")\n'
    '    if _q and any(k in text for k in ("是谁", "你知道", "你认识", "听说过", "哪个主播", "哪个人", "什么来头")) and len(_q) <= 8:\n'
    '        _q = _q + " 是谁"\n'
    '    return _q[:80] if _q else _orig\n\n\n'
    'def _need_search(text) -> bool:\n'
    '    import re as _re\n'
    '    if not isinstance(text, str):\n'
    '        return False\n'
    '    _t = text.strip()\n'
    '    if 3 <= len(_t) <= 12 and _re.fullmatch(r"[A-Za-z]+", _t) and _t.lower() not in _ABBR_STOP:\n'
    '        return True\n'
    '    return any(k in _t for k in _SEARCH_KEYWORDS)\n\n\n'
    '_ABBR_STOP = {\n'
    '    "ok", "okay", "yes", "no", "yep", "nope", "gg", "lol", "haha", "hahaha",\n'
    '    "hi", "hey", "hello", "bye", "thx", "thanks", "pls", "please", "emmm",\n'
    '    "emm", "hhhh", "www", "awa", "qwq", "orz", "cya", "sup", "yo", "bro",\n'
    '    "hmm", "uh", "oh", "ah", "yeah", "nah", "wtf", "omg", "lmao", "xd",\n'
    '    "hhd", "hxdm", "xdm", "emm", "eem", "aa", "ab", "ac", "ad",\n'
    '}\n\n\n'
    'def _parse_360(t, n=5):\n'
    '    import re as _re\n'
    '    _out = []\n'
    '    for _m in _re.finditer(r\'<h3[^>]*class="res-title"[^>]*>(.*?)</h3>(.{0,900})\', t, _re.S):\n'
    '        _title = _clean_serp(_m.group(1))\n'
    '        if _title:\n'
    '            _out.append((_title[:70], _clean_serp(_m.group(2))[:140]))\n'
    '        if len(_out) >= n:\n'
    '            break\n'
    '    return _out\n\n\n'
    'def _parse_sogou(t, n=5):\n'
    '    import re as _re\n'
    '    _out = []\n'
    '    for _b in _re.split(r\'class="vrwrap"\', t)[1:]:\n'
    '        _m = _re.search(r"<h3[^>]*>(.*?)</h3>(.{0,900})", _b, _re.S)\n'
    '        if not _m:\n'
    '            continue\n'
    '        _title = _clean_serp(_m.group(1))\n'
    '        if _title:\n'
    '            _out.append((_title[:70], _clean_serp(_m.group(2))[:140]))\n'
    '        if len(_out) >= n:\n'
    '            break\n'
    '    return _out\n\n\n'
    'def _parse_sogou_wap(t, n=6):\n'
    '    import re as _re\n'
    '    _out = []\n'
    '    for _m in _re.finditer(r\'<h3[^>]*class="vr-tit[^"]*"[^>]*>(.*?)</h3>(.{0,600})\', t, _re.S):\n'
    '        _title = _clean_serp(_m.group(1))\n'
    '        if _title and len(_title) >= 3 and "大家还在搜" not in _title:\n'
    '            _out.append((_title[:70], _clean_serp(_m.group(2))[:140]))\n'
    '        if len(_out) >= n:\n'
    '            break\n'
    '    return _out\n\n\n'
    'def _parse_bing_rss(t, n=5):\n'
    '    import html as _html\n'
    '    import re as _re\n'
    '    _out = []\n'
    '    for _it in _re.findall(r"<item>(.*?)</item>", t, _re.S):\n'
    '        _tt = _re.search(r"<title>(.*?)</title>", _it, _re.S)\n'
    '        _dd = _re.search(r"<description>(.*?)</description>", _it, _re.S)\n'
    '        if _tt:\n'
    '            _out.append((_html.unescape(_tt.group(1))[:70], _clean_serp(_dd.group(1))[:140] if _dd else ""))\n'
    '        if len(_out) >= n:\n'
    '            break\n'
    '    return _out\n\n\n'
    'def _search_relevant(query, items) -> bool:\n'
    '    import re as _re\n'
    '    _runs = _re.findall(r"[A-Za-z0-9]{3,}|[\\u4e00-\\u9fa5]{2,}", query)\n'
    '    _subs = set()\n'
    '    for _run in _runs:\n'
    '        if len(_run) <= 4:\n'
    '            _subs.add(_run)\n'
    '        else:\n'
    '            for _i in range(0, len(_run) - 1):\n'
    '                _subs.add(_run[_i:_i + 2])\n'
    '    if not _subs:\n'
    '        return True\n'
    '    _joined = " ".join(_t + _d for _t, _d in items)\n'
    '    return any(_s in _joined for _s in _subs)\n\n\n'
    'async def _bing_search_text(query: str) -> str:\n'
    '    """多引擎联网搜索（搜狗 → 360 → Bing RSS），带相关性过滤。"""\n'
    '    import urllib.parse as _up\n'
    '    import asyncio as _asyncio\n'
    '    import httpx as _httpx\n'
    '    _q = _up.quote(query)\n'
    '    _engines = (\n'
    '        ("https://www.sogou.com/web?query=" + _q, _parse_sogou, _SEARCH_UA),\n'
    '        ("https://wap.sogou.com/web/searchList.jsp?keyword=" + _q, _parse_sogou_wap, _SEARCH_MUA),\n'
    '        ("https://cn.bing.com/search?q=" + _q + "&format=rss", _parse_bing_rss, _SEARCH_UA),\n'
    '        ("https://www.so.com/s?q=" + _q, _parse_360, _SEARCH_UA),\n'
    '    )\n'
    '    try:\n'
    '        async with _httpx.AsyncClient(\n'
    '            timeout=20,\n'
    '            follow_redirects=True,\n'
    '            headers={"Accept-Language": "zh-CN,zh;q=0.9"},\n'
    '        ) as _c:\n'
    '            for _round in range(2):\n'
    '                for _url, _parser, _ua in _engines:\n'
    '                    try:\n'
    '                        _r = await _c.get(_url, headers={"User-Agent": _ua})\n'
    '                        if _r.status_code != 200:\n'
    '                            continue\n'
    '                        _items = _parser(_r.text)\n'
    '                    except Exception:\n'
    '                        continue\n'
    '                    if _items and _search_relevant(query, _items):\n'
    '                        return "\\n".join(\n'
    '                            "- " + _t + ("：" + _d if _d else "") for _t, _d in _items\n'
    '                        )\n'
    '                await _asyncio.sleep(0.8)\n'
    '        return ""\n'
    '    except Exception:\n'
    '        return ""\n\n\n'
    '_UNKNOWN_PATTERNS = (\n'
    '    "不知道", "不清楚", "不了解", "没听说", "没听过", "接不上", "不会接",\n'
    '    "不太懂", "不懂", "认输", "看不出来", "看不出", "说不上", "答不上",\n'
    '    "不晓得", "说不好", "难以回答", "无法回答", "无从得知", "我不会",\n'
    '    "神秘代码", "摩斯电码", "转不动", "没听说过", "第一次听说", "头一次听说",\n'
    '    "啥玩意儿", "看不懂", "不懂这个", "什么鬼", "没搞懂",\n'
    ')\n\n\n'
    'def _looks_unknown(reply) -> bool:\n'
    '    """判断回复是否像“不知道”。"""\n'
    '    if not isinstance(reply, str):\n'
    '        return False\n'
    '    return any(p in reply for p in _UNKNOWN_PATTERNS)\n\n\n'
    "def get_current_time() -> str:"
)
assert old_head in text, "search helper patch: target not found"
text = text.replace(old_head, new_head, 1)

# ---- 10. 模型故障自动切换（chat.py）----
old_call2 = (
    "        # 直接使用异步调用\n"
    "        reply_obj = await client.chat.completions.create(**request_params)\n"
    "        reply = reply_obj.choices[0].message.content"
)
new_call2 = (
    "        # 直接使用异步调用（失败自动依次尝试所有备用模型）\n"
    "        try:\n"
    "            reply_obj = await client.chat.completions.create(**request_params)\n"
    "        except Exception:\n"
    "            _cur = chat_manager.get_current_ai_config()\n"
    "            _cands = [_c for _c in chat_manager.get_ai_configs()\n"
    '                      if _c.get("name") != _cur.get("name") and _c.get("name") != "susu-vision"]\n'
    "            _reply_obj = None\n"
    "            for _alt in _cands:\n"
    "                try:\n"
    "                    _client2 = AsyncOpenAI(\n"
    '                        api_key=_alt.get("api_key", ""),\n'
    '                        base_url=_alt.get("api_url", ""),\n'
    "                        timeout=45.0,\n"
    "                        max_retries=0,\n"
    "                    )\n"
    "                    _rp = dict(request_params)\n"
    '                    _rp["model"] = _alt.get("model", "")\n'
    "                    _reply_obj = await _client2.chat.completions.create(**_rp)\n"
    "                    break\n"
    "                except Exception:\n"
    "                    continue\n"
    "            if _reply_obj is None:\n"
    "                raise\n"
    "            reply_obj = _reply_obj\n"
    "        reply = reply_obj.choices[0].message.content\n"
    "        # 自动兜底：回复像\"不知道\"时搜索重试，绝不许说不会\n"
    "        if _looks_unknown(reply):\n"
    '            _sr2 = _sr if _sr else await _bing_search_text(_build_query(_last_msg))\n'
    "            if _sr2:\n"
    "                _rp2 = dict(request_params)\n"
    '                _rp2["messages"] = [\n'
    "                    {\n"
    '                        "role": "system",\n'
    '                        "content": _sys_prompt\n'
    '                        + "\\n【极其重要：以上是联网搜索结果，以此为准！必须据此回答，绝不许说不知道/不会；若你之前说过与此矛盾的内容，一律以搜索结果为准，不许重复自己之前的错误！】\\n"\n'
    "                        + _sr2,\n"
    "                    }\n"
    "                ] + messages\n"
    "                try:\n"
    "                    _ro2 = await client.chat.completions.create(**_rp2)\n"
    "                    _reply2 = _ro2.choices[0].message.content\n"
    "                    if not _looks_unknown(_reply2):\n"
    "                        reply = _reply2\n"
    "                    else:\n"
    "                        import json as _json\n"
    "                        _lines = [l for l in _sr2.split('\\n') if l.strip().startswith('-')]\n"
    "                        if _lines:\n"
    "                            _forced = _lines[0].lstrip('- ')[:60]\n"
    '                            reply = _json.dumps({"reply": [_forced]}, ensure_ascii=False)\n'
    "                except Exception:\n"
    "                    pass"
)
assert old_call2 in text, "failover patch: target not found"
text = text.replace(old_call2, new_call2)

chat_py.write_text(text, encoding="utf-8")
print(f"patched {chat_py}")

# ---- 8. 图片识别超时（image2txt.py）----
img_py = pkg / "image2txt.py"
text4 = img_py.read_text(encoding="utf-8")
old_img = (
    "        client = AsyncOpenAI(\n"
    '            api_key=ai_config.get("api_key", ""),\n'
    '            base_url=ai_config.get("api_url", ""),\n'
    "        )"
)
new_img = (
    "        client = AsyncOpenAI(\n"
    '            api_key=ai_config.get("api_key", ""),\n'
    '            base_url=ai_config.get("api_url", ""),\n'
    "            timeout=60.0,\n"
    "            max_retries=2,\n"
    "        )"
)
assert old_img in text4, "image2txt patch: target not found"
text4 = text4.replace(old_img, new_img)

# ---- 8c. 图片先下载转 base64（image2txt.py）----
old_comp = (
    "        completion = await client.chat.completions.create(\n"
    '            model=ai_config.get("model", ""),'
)
new_comp = (
    "        # 先把图片下载转 base64，避免上游拉取 QQ 链接失败\n"
    "        import base64 as _b64\n"
    "        import httpx as _httpx\n"
    "        _img_ref = image_url\n"
    "        try:\n"
    "            async with _httpx.AsyncClient(timeout=20, follow_redirects=True) as _hc:\n"
    '                _hr = await _hc.get(image_url, headers={"User-Agent": "Mozilla/5.0"})\n'
    "            if _hr.status_code == 200 and _hr.content:\n"
    '                _mime = (_hr.headers.get("content-type") or "image/jpeg").split(";")[0]\n'
    '                _img_ref = "data:%s;base64,%s" % (_mime, _b64.b64encode(_hr.content).decode())\n'
    "        except Exception:\n"
    "            pass\n"
    "        completion = await client.chat.completions.create(\n"
    '            model=ai_config.get("model", ""),'
)
assert old_comp in text4, "image base64 patch: target not found"
text4 = text4.replace(old_comp, new_comp)

old_url = '                                "url": image_url,'
new_url = '                                "url": _img_ref,'
assert old_url in text4, "image url patch: target not found"
text4 = text4.replace(old_url, new_url)

img_py.write_text(text4, encoding="utf-8")
print(f"patched {img_py}")

# ---- 2. 私聊带 QQ 号（__init__.py）----
init_py = pkg / "__init__.py"
text2 = init_py.read_text(encoding="utf-8")

old_priv = '# 私聊直接记录\n        add_message(key, "user", user_msg)'
new_priv = (
    '# 私聊直接记录（带QQ号/备注/画像，便于主人识别）\n'
    '        _rm = _get_remark(str(user_id))\n'
    '        _pf = _get_profile(str(user_id))\n'
    '        add_message(key, "user", f"用户{user_id}" + (f"({_rm})" if _rm else "") + f"说：{user_msg}" + (f"\\n[关于此人：{_pf}]" if _pf else ""))'
)
assert old_priv in text2, "private patch: target not found"
text2 = text2.replace(old_priv, new_priv)

# ---- 2b. 群聊备注/画像注入（__init__.py）----
old_grpn = '        user_info = f"用户{user_id}({event.sender.nickname if event.sender else \'未知用户\'})说："'
new_grpn = (
    '        _rm = _get_remark(str(user_id))\n'
    '        _pf = _get_profile(str(user_id))\n'
    '        user_info = f"用户{user_id}({_rm or (event.sender.nickname if event.sender else \'未知用户\')})说："\n'
    '        _pf_tail = ("\\n[关于此人：" + _pf + "]") if _pf else ""'
)
assert old_grpn in text2, "remark group patch: target not found"
text2 = text2.replace(old_grpn, new_grpn)

old_grpm = '        user_message_with_info = f"{user_info}: {user_msg}"'
new_grpm = '        user_message_with_info = f"{user_info}: {user_msg}" + _pf_tail'
assert old_grpm in text2, "remark group msg patch: target not found"
text2 = text2.replace(old_grpm, new_grpm)

# ---- 5. 并发限制（__init__.py）----
old_sem = "# 初始化管理器和上下文\nload_contexts()"
new_sem = (
    "# 限制并发 AI 请求，避免快速刷屏导致 API 失败\n"
    "_chat_semaphore = asyncio.Semaphore(2)\n\n\n"
    "def _get_remark(user_id):\n"
    "    try:\n"
    "        import json as _j\n"
    "        _d = _j.loads(open('/app/data/remarks.json', encoding='utf-8').read())\n"
    "        return str(_d.get(str(user_id), '') or '')\n"
    "    except Exception:\n"
    "        return ''\n\n\n"
    "def _get_profile(user_id):\n"
    "    try:\n"
    "        import json as _j\n"
    "        _d = _j.loads(open('/app/data/profiles.json', encoding='utf-8').read())\n"
    "        return str((_d.get(str(user_id)) or {}).get('summary', '') or '')\n"
    "    except Exception:\n"
    "        return ''\n\n\n"
    "# 初始化管理器和上下文\n"
    "load_contexts()"
)
assert old_sem in text2, "semaphore patch: target not found"
text2 = text2.replace(old_sem, new_sem)

old_call = (
    "    # 调用聊天接口（群聊和私聊使用不同的系统提示词）\n"
    "    try:\n"
    "        # 获取回复，没有开启MCP的话会切换到普通对话\n"
    "        reply = await get_chat_reply_with_tools(get_context(key), is_group)"
)
new_call = (
    "    # 调用聊天接口（群聊和私聊使用不同的系统提示词）\n"
    "    try:\n"
    "        # 获取回复，没有开启MCP的话会切换到普通对话\n"
    "        async with _chat_semaphore:\n"
    "            reply = await get_chat_reply_with_tools(get_context(key), is_group)"
)
assert old_call in text2, "semaphore call patch: target not found"
text2 = text2.replace(old_call, new_call)

# ---- 4b. 不向普通用户发送报错提示（__init__.py）----
old_reply = (
    "        # 发送异常信息给超级用户\n"
    "        await send_error_to_super_users(error_msg, event)\n"
    "        # 给用户返回统一回复\n"
    '        await chat.send("抱歉，处理消息时出现了问题，已通知管理员")'
)
new_reply = (
    "        # 发送异常信息给超级用户\n"
    "        await send_error_to_super_users(error_msg, event)"
)
assert old_reply in text2, "user error reply patch: target not found"
text2 = text2.replace(old_reply, new_reply)

# ---- 8b. 每条消息只识别 1 张图（__init__.py）----
old_imgs = "for i, image_url in enumerate(image_urls):"
new_imgs = "for i, image_url in enumerate(image_urls[:1]):"
assert old_imgs in text2, "image limit patch: target not found"
text2 = text2.replace(old_imgs, new_imgs)

# ---- 9. 图片识别失败不再打扰主人（__init__.py）----
old_img_err = (
    '                error_msg = f"图片识别失败: {str(e)}"\n'
    "                logger.info(error_msg)\n"
    "                await send_error_to_super_users(error_msg, event)\n"
    '                recognition_msg += f"\\n[图片识别失败](你现在还没有图片识别的能力)"'
)
new_img_err = (
    '                error_msg = f"图片识别失败: {str(e)}"\n'
    "                logger.info(error_msg)\n"
    '                recognition_msg += f"\\n[图片识别失败](你现在还没有图片识别的能力)"'
)
assert old_img_err in text2, "image error report patch: target not found"
text2 = text2.replace(old_img_err, new_img_err)

# ---- 11. 发送限速（__init__.py）----
old_def = "async def send_split_messages("
new_def = (
    "# 全局发送限速：任意两条消息至少间隔 2 秒，防止刷屏触发 QQ 风控\n"
    "_LAST_SEND_TS = [0.0]\n\n\n"
    "async def _throttled_send(handler, msg):\n"
    "    import time as _time\n"
    "    _gap = 2.0 - (_time.time() - _LAST_SEND_TS[0])\n"
    "    if _gap > 0:\n"
    "        await asyncio.sleep(_gap)\n"
    "    _LAST_SEND_TS[0] = _time.time()\n"
    "    await handler.send(msg)\n\n\n"
    "async def send_split_messages("
)
assert old_def in text2, "throttle def patch: target not found"
text2 = text2.replace(old_def, new_def, 1)

# 把 send_split_messages 内的发送改为限速发送
assert "await chat_handler.send(at_message)" in text2, "throttle at patch: target not found"
text2 = text2.replace("await chat_handler.send(at_message)", "await _throttled_send(chat_handler, at_message)")
assert "await chat_handler.send(segment)" in text2, "throttle seg patch: target not found"
text2 = text2.replace("await chat_handler.send(segment)", "await _throttled_send(chat_handler, segment)")

# ---- 12. 表情包并进回复消息（__init__.py，用 k3 模型挑选）----
_stk_helper = (
    "# ---- 表情包：并进回复消息（AI 挑选）----\n"
    "import json as _stk_json, re as _stk_re\n"
    "_STK_DB = []\n"
    "_STK_AI = {}\n"
    "try:\n"
    "    _raw = _stk_json.loads(open('/app/data/stickers.json', encoding='utf-8').read())\n"
    "    for _u, _n in _raw.items():\n"
    "        _n = str(_n)\n"
    "        if _n.startswith('ERR'):\n"
    "            continue\n"
    "        _d, _, _k = _n.partition('|')\n"
    "        _STK_DB.append((_u, _d.strip(), [x.strip() for x in _k.replace('，', ',').split(',') if x.strip()]))\n"
    "except Exception:\n"
    "    _STK_DB = []\n"
    "try:\n"
    "    _pxc = _stk_json.loads(open('/app/data/nonebot_config/nonebot_plugin_pxchat/px_chat_manager.json', encoding='utf-8').read())\n"
    "    _v = None\n"
    "    for _i, _a in enumerate(_pxc.get('ai_configs', [])):\n"
    "        if 'kimi' in str(_a.get('name', '')).lower() or 'kimi' in str(_a.get('model', '')).lower():\n"
    "            _v = _a; break\n"
    "    if not _v:\n"
    "        _v = (_pxc.get('ai_configs') or [{}])[0]\n"
    "    _STK_AI = {'url': str(_v.get('api_url', '')).rstrip('/') + '/chat/completions',\n"
    "               'key': _v.get('api_key', ''), 'model': _v.get('model', '')}\n"
    "except Exception:\n"
    "    _STK_AI = {}\n\n\n"
    "async def _stk_pick(text):\n"
    "    if not _STK_DB:\n"
    "        return None\n"
    "    _fallback = None\n"
    "    for _u, _d, _ks in _STK_DB:\n"
    "        if any(k and k in text for k in _ks):\n"
    "            _fallback = _u; break\n"
    "    if not _STK_AI.get('key'):\n"
    "        return _fallback\n"
    "    try:\n"
    "        import httpx as _hx\n"
    "        _lines = '\\n'.join(f'{i+1}. {it[1]}（{\"、\".join(it[2])}）' for i, it in enumerate(_STK_DB))\n"
    "        _p = '下面是QQ表情包列表（编号. 描述（关键词））：\\n' + _lines + '\\n\\n请根据用户这句话的语气，选最贴切的一张，只回复编号数字；都不合适回复0。如果语气是调侃/嘴硬/装大胆/欠揍/嚣张，且列表里有『胆子肥嘟嘟』（美团黄色袋鼠）那张，优先选它。\\n用户的话：' + text[:200]\n"
    "        _body = {'model': _STK_AI['model'], 'messages': [{'role': 'user', 'content': _p}], 'max_tokens': 500, 'temperature': 0.3}\n"
    "        async with _hx.AsyncClient(timeout=40) as _c:\n"
    "            _r = await _c.post(_STK_AI['url'], json=_body, headers={'Authorization': 'Bearer ' + _STK_AI['key'], 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0) Chrome/126.0.0.0'})\n"
    "        _m = _r.json()['choices'][0]['message']\n"
    "        _t = (_m.get('content') or _m.get('reasoning_content') or '')\n"
    "        _nums = _stk_re.findall(r'\\d+', _t)\n"
    "        if not _nums:\n"
    "            return _fallback\n"
    "        _idx = int(_nums[0])\n"
    "        if _idx == 0 or _idx > len(_STK_DB):\n"
    "            return _fallback\n"
    "        return _STK_DB[_idx - 1][0]\n"
    "    except Exception:\n"
    "        return _fallback\n\n\n"
)
assert old_def in text2, "sticker helper: target not found"
text2 = text2.replace(old_def, _stk_helper + old_def, 1)

_old_seg = "    if not segments:\n        return\n"
_new_seg = (
    "    if not segments:\n"
    "        return\n"
    "    try:\n"
    "        _stk = await _stk_pick(' '.join(str(s) for s in segments))\n"
    "        if _stk:\n"
    "            segments[-1] = Message(str(segments[-1])) + MessageSegment.image(_stk)\n"
    "    except Exception:\n"
    "        pass\n"
)
assert _old_seg in text2, "sticker merge: target not found"
text2 = text2.replace(_old_seg, _new_seg, 1)

init_py.write_text(text2, encoding="utf-8")
print(f"patched {init_py}")

# ---- 4. 错误提醒主人（私聊纯文本，稳定可靠）（send2root.py）----
root_py = pkg / "send2root.py"
text3 = root_py.read_text(encoding="utf-8")

start = text3.find("async def send_error_to_super_users")
assert start != -1, "send2root patch: target not found"
new_func = (
    '_last_report_ts = 0.0\n\n\n'
    'async def send_error_to_super_users(error_msg: str, event: MessageEvent = None):\n'
    '    """发送错误信息给管理员：15 分钟节流 + 优先合并转发，失败降级纯文本。"""\n'
    '    global _last_report_ts\n'
    '    import time as _time\n'
    '    _now = _time.time()\n'
    '    if _now - _last_report_ts < 900:\n'
    '        logger.warning(f"聊天异常（节流中，仅记录）: {error_msg[:200]}")\n'
    '        return\n'
    '    _last_report_ts = _now\n'
    '    super_users = chat_manager.get_super_users()\n'
    '    if not super_users:\n'
    '        logger.warning("没有配置管理员，无法发送错误信息")\n'
    '        return\n'
    '    bot = get_bot()\n'
    '    error_summary = extract_error_summary(error_msg)\n'
    '    overview = "聊天插件错误报告"\n'
    '    if event:\n'
    '        overview += f"\\n触发用户: {event.user_id}"\n'
    '        if getattr(event, "group_id", None):\n'
    '            overview += f"\\n触发群组: {event.group_id}"\n'
    '        trigger_msg = event.get_plaintext()\n'
    '        if len(trigger_msg) > 100:\n'
    '            trigger_msg = trigger_msg[:100] + "..."\n'
    '        overview += f"\\n触发消息: {trigger_msg}"\n'
    '    messages = [\n'
    '        await create_text_node("系统监控", bot.self_id, overview),\n'
    '        await create_text_node("错误信息", bot.self_id, f"错误详情:\\n{error_summary}"),\n'
    '    ]\n'
    '    for user_id in super_users:\n'
    '        result = await send_forward_message(user_id=int(user_id), messages=messages)\n'
    '        if result is None:\n'
    '            try:\n'
    '                await bot.send_private_msg(\n'
    '                    user_id=int(user_id), message=overview + f"\\n错误详情:\\n{error_summary}"\n'
    '                )\n'
    '                logger.info(f"已用纯文本发送错误信息给管理员 {user_id}")\n'
    '            except Exception as e:\n'
    '                logger.error(f"发送错误信息给管理员 {user_id} 失败: {e}")\n'
    '        else:\n'
    '            logger.info(f"已发送错误信息给管理员 {user_id}")\n'
)
text3 = text3[:start] + new_func
root_py.write_text(text3, encoding="utf-8")
print(f"patched {root_py}")
