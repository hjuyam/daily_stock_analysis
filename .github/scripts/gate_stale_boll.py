#!/usr/bin/env python3
"""
Gate C: 验证 save_daily_data() 在 OHLC 更新时正确处理陈旧 BOLL

核心契约：每次 upsert/update 后，DB 中的 BOLL 列状态必须精确等于
"在 _boll_columns 中的用新值，不在的置 NULL" —— 即遍历 _ALL_BOLL_COLUMNS
逐一决策，而非条件性跳过。

覆盖场景：
1. _df_has_boll=False → 全部 12 列置 NULL
2. _df_has_boll=True 但子集（如仅 10）→ 更新 10，NULL 化 5/20
3. _df_has_boll=True 全量 → 更新全部 12 列
"""
import ast
import sys

STORAGE_PATH = "src/storage.py"


def check_save_daily_data() -> bool:
    with open(STORAGE_PATH, encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    issues = []
    passes = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "save_daily_data":
            # 检查两个写入路径
            # 路径 1: SQLite upsert — 寻找 for col in _ALL_BOLL_COLUMNS: _update_set[col] = ...
            # 路径 2: ORM update — 寻找 for col in _ALL_BOLL_COLUMNS: setattr(existing, col, ...)
            
            for child in ast.walk(node):
                if isinstance(child, ast.For):
                    iter_name = _get_iter_source(child.iter)
                    if '_ALL_BOLL_COLUMNS' in iter_name:
                        body = child.body
                        # 检查 body 中是否有条件赋值 (if col in _boll_columns else None)
                        has_conditional = _check_conditional_assignment(body)
                        if has_conditional:
                            passes += 1
                        else:
                            issues.append(
                                f"  line {child.lineno}: 遍历 _ALL_BOLL_COLUMNS 但未使用条件赋值"
                            )

            # 检查是否还存在旧的 if _df_has_boll and _boll_columns: 模式
            for child in ast.walk(node):
                if isinstance(child, ast.If):
                    cond = ast.unparse(child.test)
                    if '_df_has_boll' in cond and '_boll_columns' in cond:
                        # 检查 if 体内是否直接更新 _update_set / setattr
                        body_source = '\n'.join([
                            ast.unparse(stmt) for stmt in child.body[:3]
                        ])
                        if 'update_set.update' in body_source or 'setattr' in body_source:
                            issues.append(
                                f"  line {child.lineno}: 存在旧的条件性 BOLL 更新模式 "
                                f"(if {cond[:50]}...) — 应替换为统一的 _ALL_BOLL_COLUMNS 遍历"
                            )
            break

    if issues:
        print("❌ GATE-C: save_daily_data() 陈旧 BOLL 处理不完整:")
        for i in issues:
            print(i)
        print()
        print("期望: 两个写入路径均遍历 _ALL_BOLL_COLUMNS，用条件赋值 'val if col in _boll_columns else None'")
        return False

    if passes >= 2:
        print(f"✅ GATE-C: save_daily_data() 陈旧 BOLL 处理正确 ({passes} 个路径遍历 _ALL_BOLL_COLUMNS)")
        return True
    else:
        print(f"❌ GATE-C: 只找到 {passes}/2 个 _ALL_BOLL_COLUMNS 遍历路径")
        return False


def _get_iter_source(node) -> str:
    """获取 for 循环迭代源的名称。"""
    try:
        return ast.unparse(node)
    except Exception:
        return ''


def _check_conditional_assignment(body: list) -> bool:
    """检查 body 中是否有 if col in _boll_columns else None 模式。"""
    for stmt in body:
        text = ast.unparse(stmt) if hasattr(ast, 'unparse') else ''
        if 'in _boll_columns' in text and 'None' in text:
            return True
        # 也检查 comprehension 或更深层的条件
        for child_node in ast.walk(stmt):
            if isinstance(child_node, ast.IfExp):
                text2 = ast.unparse(child_node) if hasattr(ast, 'unparse') else ''
                if 'in _boll_columns' in text2:
                    return True
    return False


if __name__ == "__main__":
    ok = check_save_daily_data()
    sys.exit(0 if ok else 1)