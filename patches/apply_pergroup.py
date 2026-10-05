"""为 nonebot_plugin_pxchat 增加「按群参与概率」（幂等，可重复运行）。

用法：
    python apply_pergroup.py            # 自动定位 site-packages
    PXCHAT_PKG=/path/to/pkg python ...  # 指定包目录（用于本地测试）
"""
import os
import site
from pathlib import Path

override = os.environ.get("PXCHAT_PKG")
if override:
    pkg = Path(override)
else:
    cands = []
    for sp in site.getsitepackages():
        p = Path(sp) / "nonebot_plugin_pxchat"
        if p.exists():
            cands.append(p)
    assert cands, "nonebot_plugin_pxchat not found"
    pkg = cands[0]

# ---- manager.py：新增按群概率存取 ----
mp = pkg / "manager.py"
t = mp.read_text(encoding="utf-8")
if "def get_group_probability" in t:
    print("manager.py already patched")
else:
    anchor = "    # 管理员管理\n    def is_super_user(self, user_id: str) -> bool:"
    assert anchor in t, "manager anchor not found"
    ins = (
        "    # 按群参与概率\n"
        "    def get_group_probability(self, group_id: str) -> float:\n"
        '        """获取指定群的参与概率（无单独设置则回退全局值）"""\n'
        '        gp = self._data.get("group_probabilities", {}) or {}\n'
        "        if str(group_id) in gp:\n"
        "            try:\n"
        "                return float(gp[str(group_id)])\n"
        "            except (TypeError, ValueError):\n"
        "                pass\n"
        "        return self.get_group_chat_probability()\n\n"
        "    def set_group_probability(self, group_id: str, probability=None) -> bool:\n"
        '        """设置/清除指定群的参与概率（probability 为 None 表示清除，回退全局）"""\n'
        '        gp = self._data.get("group_probabilities")\n'
        "        if not isinstance(gp, dict):\n"
        "            gp = {}\n"
        "        if probability is None:\n"
        "            gp.pop(str(group_id), None)\n"
        "        else:\n"
        "            if not 0 <= probability <= 1:\n"
        "                return False\n"
        "            gp[str(group_id)] = round(float(probability), 2)\n"
        '        self._data["group_probabilities"] = gp\n'
        "        self._save_manager_config()\n"
        "        return True\n\n"
        "    def get_group_probabilities(self):\n"
        '        """获取所有单独设置过概率的群"""\n'
        '        gp = self._data.get("group_probabilities", {})\n'
        "        return dict(gp) if isinstance(gp, dict) else {}\n\n"
    )
    t = t.replace(anchor, ins + anchor, 1)
    mp.write_text(t, encoding="utf-8")
    print("patched", mp)

# ---- __init__.py：续租时按群取基准概率 ----
ip = pkg / "__init__.py"
t2 = ip.read_text(encoding="utf-8")
old = "base_prob = chat_manager.get_group_chat_probability()"
new = "base_prob = chat_manager.get_group_probability(group_id)"
if new in t2:
    print("__init__.py already patched")
else:
    assert old in t2, "init anchor not found"
    t2 = t2.replace(old, new, 1)
    ip.write_text(t2, encoding="utf-8")
    print("patched", ip)

print("done")
