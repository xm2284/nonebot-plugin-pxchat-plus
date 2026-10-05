"""额外修复（幂等）：模型返回纯文本时不再误报「处理聊天发生异常」。

问题：opus4.8 等模型虽有 response_format=json_object，仍可能返回纯文本，
导致 __init__.py 的 send_split_messages 里 json.loads 抛错并给主人发错误报告；
chat.py 的 should_reply_in_group 也会 json.loads 助手内容导致群聊判断异常。

本脚本在 patch_pxchat.py 之后运行，用容错解析替换这两处。
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

CHANGED = []

init_py = pkg / "__init__.py"
text2 = init_py.read_text(encoding="utf-8")

old_parse = (
    "    # 尝试解析JSON格式\n"
    "    try:\n"
    "        data = json.loads(message)\n"
    '        if isinstance(data, dict) and "reply" in data and isinstance(data["reply"], list):\n'
    '            segments = [segment for segment in data["reply"] if segment and segment.strip()]\n'
    "    except (json.JSONDecodeError, TypeError) as e:\n"
    "        # 如果不是JSON，直接使用原消息\n"
    '        error_msg = f"处理聊天请求时发生异常:\\n {str(e)}"\n'
    "        await send_error_to_super_users(error_msg, event)\n"
    "        return\n"
)

new_parse = (
    "    # 解析模型输出：兼容纯文本 / ```json 围栏 / {\"reply\":[...]} 两种格式\n"
    "    def _parse_reply(_m):\n"
    "        import re as _re\n"
    "        _t = (_m or '').strip()\n"
    "        if _t.startswith('```'):\n"
    "            _t = _re.sub(r'^```[a-zA-Z]*\\s*', '', _t)\n"
    "            _t = _re.sub(r'\\s*```$', '', _t).strip()\n"
    "        try:\n"
    "            _d = json.loads(_t)\n"
    "        except (json.JSONDecodeError, TypeError):\n"
    "            return [_m] if (_m or '').strip() else []\n"
    "        if isinstance(_d, dict) and 'reply' in _d:\n"
    "            _r = _d['reply']\n"
    "            if isinstance(_r, list):\n"
    "                return [s for s in _r if s and str(s).strip()]\n"
    "            if isinstance(_r, str):\n"
    "                return [_r] if _r.strip() else []\n"
    "        if isinstance(_d, list):\n"
    "            return [s for s in _d if s and str(s).strip()]\n"
    "        return [_m]\n"
    "    segments = _parse_reply(message)\n"
)

if old_parse in text2:
    text2 = text2.replace(old_parse, new_parse, 1)
    init_py.write_text(text2, encoding="utf-8")
    CHANGED.append("__init__.py: send_split_messages 容错解析")
elif ("_parse_reply(" in text2) or ("兼容纯文本/JSON 两种模型输出" in text2):
    CHANGED.append("__init__.py: already fixed")
else:
    raise AssertionError("__init__.py parse block not found")

chat_py = pkg / "chat.py"
text = chat_py.read_text(encoding="utf-8")

old_judge = (
    "            else:\n"
    "                data = json.loads(msg['content'])\n"
    "                judge_content.append(f\"你(px)回复说: {data.get('reply', [''])}\")"
)
new_judge = (
    "            else:\n"
    "                try:\n"
    "                    data = json.loads(msg['content'])\n"
    "                    _rep = data.get('reply', ['']) if isinstance(data, dict) else msg['content']\n"
    "                except Exception:\n"
    "                    _rep = msg['content']\n"
    "                judge_content.append(f\"你(px)回复说: {_rep}\")"
)

if old_judge in text:
    text = text.replace(old_judge, new_judge, 1)
    chat_py.write_text(text, encoding="utf-8")
    CHANGED.append("chat.py: should_reply_in_group 容错解析")
elif new_judge in text:
    CHANGED.append("chat.py: already fixed")
else:
    raise AssertionError("chat.py judge block not found")

print("patch_pxchat_fixes done:", "; ".join(CHANGED))
