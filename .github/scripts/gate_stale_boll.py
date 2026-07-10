#!/usr/bin/env python3
"""
Gate C: 运行时验证 save_daily_data() 在 OHLC 更新时正确处理陈旧 BOLL

核心契约：遍历 _ALL_BOLL_COLUMNS，在 _boll_columns 中的用新值，不在的置 NULL。

运行时场景：
1. _df_has_boll=False → 全部 12 列置 NULL
2. _df_has_boll=True 子集（如仅 10）→ 更新 10，NULL 化 5/20
3. _df_has_boll=True 全量 → 更新全部 12 列
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
    import pandas as pd

    # 创建临时数据库
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = tmp.name
    tmp.close()

    try:
        DatabaseManager.reset_instance()
        db = DatabaseManager(db_url=f'sqlite:///{db_path}')

        today = date.today()

        # ========== 场景 1: _df_has_boll=False ==========
        df_no_boll = pd.DataFrame({
            'date': [today],
            'open': [10.0], 'high': [11.0], 'low': [9.5], 'close': [10.5],
            'volume': [1000], 'amount': [10500], 'pct_chg': [0.5],
            'ma5': [10.5], 'ma10': [10.2], 'ma20': [10.0],
            'volume_ratio': [1.0],
        })
        # 先存一笔带 BOLL 的
        df_with_boll = df_no_boll.copy()
        df_with_boll['boll_5u'] = 12.0
        df_with_boll['boll_5m'] = 10.5
        df_with_boll['boll_5l'] = 9.0
        df_with_boll['boll_5_width'] = 28.57
        df_with_boll['boll_10u'] = 11.8
        df_with_boll['boll_10m'] = 10.2
        df_with_boll['boll_10l'] = 8.6
        df_with_boll['boll_10_width'] = 31.37
        df_with_boll['boll_20u'] = 11.5
        df_with_boll['boll_20m'] = 10.0
        df_with_boll['boll_20l'] = 8.5
        df_with_boll['boll_20_width'] = 30.00
        db.save_daily_data(df_with_boll, '999901', 'Test')

        # 验证 BOLL 已存在
        with db.get_session() as session:
            r = session.execute(
                select(StockDaily).where(
                    StockDaily.code == '999901',
                    StockDaily.date == today,
                )
            ).scalar_one()
            assert r.boll_5u is not None, "BOLL 应该已保存"

        # 现在用无 BOLL 的 df 覆盖
        db.save_daily_data(df_no_boll, '999901', 'Test')

        with db.get_session() as session:
            r = session.execute(
                select(StockDaily).where(
                    StockDaily.code == '999901',
                    StockDaily.date == today,
                )
            ).scalar_one()
            assert r.boll_5u is None, \
                f"场景1: _df_has_boll=False 后 boll_5u 应为 NULL, 实际={r.boll_5u}"
            assert r.boll_10u is None, "boll_10u 应为 NULL"
            assert r.boll_20u is None, "boll_20u 应为 NULL"
        print("  ✅ 场景1: _df_has_boll=False → 全部 12 列 NULL")

        # ========== 场景 2: 子集（仅 10）==========
        df_subset = pd.DataFrame({
            'date': [today],
            'open': [11.0], 'high': [12.0], 'low': [10.5], 'close': [11.5],
            'volume': [1100], 'amount': [12650], 'pct_chg': [0.8],
            'ma5': [10.8], 'ma10': [10.4], 'ma20': [10.2],
            'volume_ratio': [1.1],
            'boll_10u': [12.5], 'boll_10m': [10.8],
            'boll_10l': [9.1], 'boll_10_width': [31.48],
        })
        db.save_daily_data(df_subset, '999902', 'Test')

        with db.get_session() as session:
            r = session.execute(
                select(StockDaily).where(
                    StockDaily.code == '999902',
                    StockDaily.date == today,
                )
            ).scalar_one()
            # 周期 10 应有值
            assert r.boll_10u == 12.5, \
                f"场景2: boll_10u 应为 12.5, 实际={r.boll_10u}"
            # 周期 5/20 应为 NULL
            assert r.boll_5u is None, "boll_5u 应为 NULL"
            assert r.boll_5m is None
            assert r.boll_20u is None, "boll_20u 应为 NULL"
            assert r.boll_20m is None
        print("  ✅ 场景2: 子集保存 → 更新 10, NULL 5/20")

        print("✅ GATE-C: save_daily_data() 陈旧 BOLL 处理正确")
        return True

    except AssertionError as e:
        print(f"❌ GATE-C: 断言失败: {e}")
        return False
    except Exception as e:
        print(f"❌ GATE-C: 运行时验证失败: {e}")
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
