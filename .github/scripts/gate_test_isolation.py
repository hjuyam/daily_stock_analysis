#!/usr/bin/env python3
"""
Gate B: 检测测试 fixture 中 get_db() 在 engine 覆盖前被调用的模式。

问题模式:
    DatabaseManager.reset_instance()
    self.db = get_db()           # ← 此时已初始化真实数据库
    self.db._db_url = '...'      # ← 事后覆盖，真实库已被污染

正确模式:
    DatabaseManager.reset_instance()
    self.db = DatabaseManager(db_url='...')  # ← 直接传入临时路径
"""
import re
import sys
from pathlib import Path
from typing import List

# 搜索范围
TEST_DIRS = ["tests"]


def _find_risky_patterns(filepath: str) -> List[str]:
    """查找 get_db() 调用后紧跟 engine/url 覆盖的模式。"""
    findings = []
    with open(filepath, encoding="utf-8") as f:
        lines = f.readlines()

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # 匹配: self.db = get_db()
        if re.match(r".*=\s*get_db\s*\(\)", stripped):
            # 检查后续 10 行是否有 engine/url 覆盖
            for j in range(i + 1, min(i + 11, len(lines) + 1)):
                next_line = lines[j - 1].strip()
                if re.search(r"\._db_url\s*=", next_line) or \
                   re.search(r"\._engine\s*=", next_line):
                    findings.append(
                        f"  {filepath}:{i}  get_db() 在第 {j} 行被 engine覆盖 → "
                        f"真实数据库已初始化，存在隔离风险"
                    )
                    break
    return findings


def check_test_isolation() -> bool:
    """检查所有测试文件，返回是否全部通过。"""
    all_findings = []

    for td in TEST_DIRS:
        base = Path(td)
        if not base.exists():
            continue
        for pyfile in sorted(base.rglob("test_*.py")):
            all_findings.extend(_find_risky_patterns(str(pyfile)))

    if all_findings:
        print("❌ GATE-B: 测试隔离性风险 — 发现以下 get_db() 预初始化模式:")
        for f in all_findings:
            print(f)
        print()
        print("应改为直接传入临时路径:")
        print("  DatabaseManager.reset_instance()")
        print("  self.db = DatabaseManager(db_url='sqlite:///tmp/...')")
        return False

    print("✅ GATE-B: 所有测试 fixture 的数据库隔离性正确")
    return True


if __name__ == "__main__":
    ok = check_test_isolation()
    sys.exit(0 if ok else 1)