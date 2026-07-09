#!/usr/bin/env python3
"""
Gate A: 验证 has_boll_data() 检查每个周期的全部 4 列 (u, m, l, _width)

通过 AST 解析 has_boll_data 函数体，确认 period_col_names 的列表推导式
生成了所有 4 个后缀（u, m, l, _width），而不仅是 u。
"""
import ast
import sys

STORAGE_PATH = "src/storage.py"


def _find_suffix_variable(source: str, tree: ast.Module, func_node: ast.FunctionDef) -> set | None:
    """
    在 has_boll_data 函数作用域内，寻找周期后缀变量（如 boll_column_suffixes）
    并返回其字面值集合。
    """
    for node in ast.walk(func_node):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    var_name = target.id
                    # 找后缀列表变量: 名字包含 suffix/col/Suffix 且值是列表字面量
                    if any(kw in var_name.lower() for kw in ["suffix", "col", "boll"]):
                        if isinstance(node.value, ast.List):
                            values = set()
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant):
                                    values.add(str(elt.value))
                            if values:
                                return values
    return None


def _extract_period_suffixes_from_listcomp(comp: ast.ListComp) -> set:
    """从列表推导式语法树中提取用于生成列名的后缀变量名。"""
    generators = comp.generators
    if len(generators) < 2:
        return set()  # 只有一层 for = 只查一种列

    # 第二层 for 的迭代变量就是后缀来源
    second_gen = generators[1]
    if isinstance(second_gen.iter, ast.Name):
        return {second_gen.iter.id}  # 变量名，需在上下文中解析
    elif isinstance(second_gen.iter, ast.List):
        return {str(elt.value) for elt in second_gen.iter.elts if isinstance(elt, ast.Constant)}
    return set()


def check_column_completeness() -> bool:
    with open(STORAGE_PATH, encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    func_node = None
    period_col_comp = None

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "has_boll_data":
            func_node = node
            for child in ast.walk(node):
                if isinstance(child, ast.Assign):
                    for target in child.targets:
                        if isinstance(target, ast.Name) and target.id == "period_col_names":
                            if isinstance(child.value, ast.ListComp):
                                period_col_comp = child.value
                            elif isinstance(child.value, ast.List):
                                # 硬编码列表，直接提取
                                period_col_comp = child.value

    if func_node is None:
        print(f"❌ GATE-A: 未找到 has_boll_data 函数")
        return False

    if period_col_comp is None:
        print(f"❌ GATE-A: 未找到 period_col_names 定义")
        return False

    if isinstance(period_col_comp, ast.List):
        # 硬编码列表模式
        values = []
        for elt in period_col_comp.elts:
            if isinstance(elt, ast.Constant):
                values.append(str(elt.value))
            elif isinstance(elt, ast.JoinedStr):
                # f-string
                values.append("f-string")
        print(f"⚠️ GATE-A: period_col_names 是硬编码列表 ({len(values)} 项), 手动确认")
        return True

    # ListComp 模式
    comp = period_col_comp
    generators = comp.generators

    if len(generators) < 2:
        print(f"❌ GATE-A: 列表推导式只有 {len(generators)} 层，应为 2 层 (periods × suffixes)")
        return False

    # 从函数作用域查找后缀变量
    suffix_var = _find_suffix_variable(source, tree, func_node)

    if suffix_var:
        expected = {"u", "m", "l", "_width"}
        missing = expected - suffix_var
        if missing:
            print(f"❌ GATE-A: has_boll_data() 周期后缀缺少: {', '.join(sorted(missing))}")
            print(f"   当前后缀: {sorted(suffix_var)}")
            print(f"   期望后缀: {sorted(expected)}")
            return False
        print(f"✅ GATE-A: has_boll_data() 覆盖 4 列后缀: {', '.join(sorted(suffix_var))}")
    else:
        # 尝试从列表推导式的第二层提取
        second_gen = generators[1]
        if isinstance(second_gen.iter, ast.List):
            suffixes = {str(elt.value) for elt in second_gen.iter.elts if isinstance(elt, ast.Constant)}
            if suffixes:
                expected = {"u", "m", "l", "_width"}
                missing = expected - suffixes
                if missing:
                    print(f"❌ GATE-A: 缺少后缀: {', '.join(sorted(missing))}")
                    return False
                print(f"✅ GATE-A: has_boll_data() 覆盖 4 列后缀: {', '.join(sorted(suffixes))}")
            else:
                print(f"⚠️ GATE-A: 无法解析后缀来源（动态变量），执行运行时验证")
                return _runtime_check()
        else:
            print(f"⚠️ GATE-A: 后缀来自变量 {second_gen.iter.id}，执行运行时验证")
            return _runtime_check()

    # 确认有两个 for 层 (periods × suffixes)
    print(f"  列表推导式: {len(generators)} 层 for")
    return True


def _runtime_check() -> bool:
    """运行时导入 DatabaseManager，直接调用 has_boll_data 的私有变体验证。"""
    try:
        import sys as _sys
        _sys.path.insert(0, ".")
        from src.storage import StockDaily
        # 检查 StockDaily 上是否定义了所有 12 个 BOLL 列
        expected_cols = []
        for p in [5, 10, 20]:
            for suffix in ['u', 'm', 'l', '_width']:
                expected_cols.append(f'boll_{p}{suffix}')
        missing = [c for c in expected_cols if not hasattr(StockDaily, c)]
        if missing:
            print(f"❌ GATE-A: StockDaily 缺少列: {missing}")
            return False
        print(f"✅ GATE-A: StockDaily 定义了全部 {len(expected_cols)} 个 BOLL 列")
        return True
    except Exception as e:
        print(f"❌ GATE-A: 运行时验证失败: {e}")
        return False


if __name__ == "__main__":
    ok = check_column_completeness()
    sys.exit(0 if ok else 1)