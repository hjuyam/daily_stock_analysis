#!/usr/bin/env python3
"""
Gate C: 验证 save_daily_data() 在 OHLC 更新时正确处理陈旧 BOLL

检查条件：
- 当 _df_has_boll 为 False 时，所有写入路径必须将存量 BOLL 列置 NULL
- 否则 OHLC 更新但无新 BOLL → 陈旧 BOLL 保留 → has_boll_data() 误判为可用

检查的写入路径：
1. SQLite upsert (_update_set): _df_has_boll=False → _ALL_BOLL_COLUMNS 置 None
2. 非 SQLite ORM update: _df_has_boll=False → 所有现有 BOLL 列 setattr None
3. row_dict 构建（新记录）：无需处理（新记录无存量旧数据）
"""
import ast
import re
import sys

STORAGE_PATH = "src/storage.py"


def _find_boll_if_blocks(tree: ast.Module) -> list[dict]:
    """在 save_daily_data 函数中查找所有 _df_has_boll 条件分支。"""
    results = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "save_daily_data":
            for child in ast.walk(node):
                if isinstance(child, ast.If):
                    # 检查条件是否包含 _df_has_boll
                    source = ast.unparse(child.test) if hasattr(ast, 'unparse') else ''
                    if '_df_has_boll' in source:
                        has_else = child.orelse and len(child.orelse) > 0
                        results.append({
                            'lineno': child.lineno,
                            'condition': source,
                            'has_else': has_else,
                            'else_lineno': child.orelse[0].lineno if has_else else None,
                            'body_lines': [n.lineno for n in child.body],
                        })
            break  # only scan save_daily_data
    
    return results


def check_stale_boll_handling() -> bool:
    with open(STORAGE_PATH, encoding="utf-8") as f:
        source = f.read()
    
    tree = ast.parse(source)
    blocks = _find_boll_if_blocks(tree)
    
    if not blocks:
        print(f"❌ GATE-C: 在 save_daily_data 中未找到 _df_has_boll 条件分支")
        return False
    
    # 分类分支
    # 1. row_dict 构建（line ~2594）—— 新记录，无需处理
    # 2. SQLite upsert _update_set（line ~2662）—— 必须有 else
    # 3. 非 SQLite ORM update（line ~2706）—— 必须有 else
    
    issues = []
    for b in blocks:
        line = b['lineno']
        cond = b['condition']
        
        # 判断这是哪个路径
        is_row_dict = 'row_dict' in source[line:line+100] if line < len(source.split('\n')) else False
        is_update_set = 'update_set' in b['condition'] or 'set_' in source[:source.find('\n', source.find('\n', line)+100)]
        
        # 更可靠的判断：检查 body 中是否有 getattr(excluded, col) 或 setattr
        body_src = '\n'.join([source.split('\n')[l-1] for l in b['body_lines'] if l-1 < len(source.split('\n'))])
        
        is_excluded = 'getattr(excluded' in body_src or 'getattr(existing' in body_src
        
        if not b['has_else']:
            # 没有 else 分支 —— 仅在 row_dict 路径中可接受
            if is_excluded:
                # upsert/update 路径缺少 else → 风险！
                issues.append(
                    f"  line {line}: '{cond}' 缺少 else 分支 → "
                    f"OHLC 更新时陈旧 BOLL 不会被清空"
                )
    
    if issues:
        print("❌ GATE-C: save_daily_data() 陈旧 BOLL 处理不完整:")
        for i in issues:
            print(i)
        print()
        print("期望: 每个写入路径的 _df_has_boll 条件分支必须有 else 分支 NULL 化 _ALL_BOLL_COLUMNS")
        return False
    
    # 确认 else 分支确实 NULL 了 _ALL_BOLL_COLUMNS
    for b in blocks:
        if b['has_else'] and b['else_lineno']:
            # 读取 else 分支的前几行
            lines = source.split('\n')
            else_lines = lines[b['else_lineno']-1:b['else_lineno']+5]
            else_text = '\n'.join(else_lines)
            if '_ALL_BOLL_COLUMNS' not in else_text and 'None' not in else_text:
                issues.append(
                    f"  line {b['linode']}: else 分支存在但未 NULL 化 BOLL 列"
                )
    
    if issues:
        print("❌ GATE-C: else 分支内容不正确:")
        for i in issues:
            print(i)
        return False
    
    # 统计找到了多少个完整路径
    upsert_paths = [b for b in blocks if b['has_else']]
    print(f"✅ GATE-C: save_daily_data() 陈旧 BOLL 处理完整 ({len(upsert_paths)} 个写入路径含 else NULL 化)")
    for b in upsert_paths:
        print(f"   行 {b['lineno']}: {b['condition'][:60]}... → else 分支 @行 {b['else_lineno']}")
    return True


if __name__ == "__main__":
    ok = check_stale_boll_handling()
    sys.exit(0 if ok else 1)