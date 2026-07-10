#!/usr/bin/env python3
"""
Gate A: 运行时验证 has_boll_data() 检查每个周期的全部 4 列 (u, m, l, _width)

通过创建临时 SQLite 数据库，实际调用 has_boll_data 验证：
- 全部 4 列存在 → True
- 缺少任一列 → False
- 无数据 → False
"""
import sys
import tempfile
import os
from datetime import date, timedelta


def check_by_runtime() -> bool:
    # 确保能从项目根目录导入
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(os.path.dirname(_script_dir))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    from src.storage import DatabaseManager, StockDaily
    from sqlalchemy import select

    # 创建临时数据库
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = tmp.name
    tmp.close()

    try:
        DatabaseManager.reset_instance()
        db = DatabaseManager(db_url=f'sqlite:///{db_path}')

        # 插入一行测试数据：所有 BOLL 列非空
        today = date.today()
        with db.get_session() as session:
            row = StockDaily(
                code='999999',
                date=today,
                open=10.0, high=11.0, low=9.5, close=10.5,
                volume=1000, amount=10500, pct_chg=0.5,
                ma5=10.5, ma10=10.2, ma20=10.0, volume_ratio=1.0,
                data_source='Test',
                boll_5u=12.0, boll_5m=10.5, boll_5l=9.0, boll_5_width=28.57,
                boll_10u=11.8, boll_10m=10.2, boll_10l=8.6, boll_10_width=31.37,
                boll_20u=11.5, boll_20m=10.0, boll_20l=8.5, boll_20_width=30.00,
            )
            session.add(row)
            session.commit()

        # 验证 1: 全量列非空 → True
        assert db.has_boll_data('999999', today) is True, \
            "所有 12 列非空应返回 True"
        print("  ✅ 全量列非空 → True")

        # 验证 2: 同一周期缺部分列 → False
        # 手动将 boll_5_width 置 NULL
        with db.get_session() as session:
            r = session.execute(
                select(StockDaily).where(
                    StockDaily.code == '999999',
                    StockDaily.date == today,
                )
            ).scalar_one()
            r.boll_5_width = None
            session.commit()
        assert db.has_boll_data('999999', today) is False, \
            "boll_5_width 为 NULL 应返回 False"
        print("  ✅ 同周期缺少 1 列 → False")

        # 验证 3: 无数据 → False
        assert db.has_boll_data('000000', today) is False, \
            "无数据应返回 False"
        print("  ✅ 无数据 → False")

        # 验证 4: 子集周期检查（BOLL_PERIODS=10）
        # 恢复 boll_5_width
        with db.get_session() as session:
            r = session.execute(
                select(StockDaily).where(
                    StockDaily.code == '999999',
                    StockDaily.date == today,
                )
            ).scalar_one()
            r.boll_5_width = 28.57
            r.boll_5u = None  # 仅缺 boll_5u（但子集只查 10）
            session.commit()
        assert db.has_boll_data('999999', today, boll_periods='10') is True, \
            "子集只查 10，boll_5u 为空不应影响"
        print("  ✅ 子集检查 → True（只查配置周期）")

        print("✅ GATE-A: has_boll_data() 列完整性检查通过")
        return True

    except AssertionError as e:
        print(f"❌ GATE-A: 断言失败: {e}")
        return False
    except Exception as e:
        print(f"❌ GATE-A: 运行时验证失败: {e}")
        return False
    finally:
        DatabaseManager.reset_instance()
        try:
            os.unlink(db_path)
        except OSError:
            pass


if __name__ == "__main__":
    ok = check_by_runtime()
    sys.exit(0 if ok else 1)
