"""
Tests for Bollinger Bands (BOLL) technical indicator feature.

Covers:
- Config validation (_validate_boll_periods)
- BOLL calculation in data provider (conditional on BOLL_ENABLED)
- Prompt schema conditional (enabled vs disabled)
- History report reconstruction includes boll_analysis
"""

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock


# ============================================================
# Config validation
# ============================================================

class TestBollConfigValidation:
    """Test _validate_boll_periods config validation."""

    def test_valid_default(self):
        from src.config import _validate_boll_periods
        assert _validate_boll_periods("5,10,20") == "5,10,20"

    def test_valid_subset(self):
        from src.config import _validate_boll_periods
        assert _validate_boll_periods("5") == "5"
        assert _validate_boll_periods("10") == "10"
        assert _validate_boll_periods("20") == "20"
        assert _validate_boll_periods("5,20") == "5,20"

    def test_valid_different_order(self):
        from src.config import _validate_boll_periods
        result = _validate_boll_periods("20,5,10")
        assert "5" in result and "10" in result and "20" in result
        assert result == "20,5,10"

    def test_valid_with_spaces(self):
        from src.config import _validate_boll_periods
        assert _validate_boll_periods(" 5 , 10 , 20 ") == "5,10,20"

    def test_normalizes_canonical_form(self):
        """'05' should normalize to '5'."""
        from src.config import _validate_boll_periods
        assert _validate_boll_periods("05,10,20") == "5,10,20"

    def test_valid_removes_duplicates(self):
        from src.config import _validate_boll_periods
        result = _validate_boll_periods("5,5,10,10,20")
        assert result == "5,10,20"

    def test_rejects_unsupported_period(self):
        from src.config import _validate_boll_periods
        result = _validate_boll_periods("5,10,20,30")
        assert result == "5,10,20"

    def test_rejects_invalid_value(self):
        from src.config import _validate_boll_periods
        result = _validate_boll_periods("abc,5,10")
        assert result == "5,10"

    def test_all_invalid_falls_back(self):
        from src.config import _validate_boll_periods
        result = _validate_boll_periods("30,40")
        assert result == "5,10,20"

    def test_empty_falls_back(self):
        from src.config import _validate_boll_periods
        result = _validate_boll_periods("")
        assert result == "5,10,20"


# ============================================================
# BOLL calculation in data provider
# ============================================================

def _make_test_df():
    """Create a simple 20-row OHLCV DataFrame for testing."""
    return pd.DataFrame({
        'close': [10.0, 11.0, 12.0, 11.5, 10.5, 11.0, 12.5, 13.0, 12.0, 11.0,
                  10.5, 11.5, 12.0, 13.5, 13.0, 12.5, 14.0, 13.5, 14.5, 14.0],
        'high': [11.0, 12.0, 13.0, 12.0, 11.0, 11.5, 13.0, 13.5, 12.5, 11.5,
                 11.0, 12.0, 12.5, 14.0, 13.5, 13.0, 14.5, 14.0, 15.0, 14.5],
        'low': [9.5, 10.5, 11.5, 11.0, 10.0, 10.5, 12.0, 12.5, 11.5, 10.5,
                10.0, 11.0, 11.5, 13.0, 12.5, 12.0, 13.5, 13.0, 14.0, 13.5],
        'volume': [1000] * 20,
    })


class TestBollCalculation:
    """Test that BOLL calculation respects BOLL_ENABLED flag."""

    def _calculate(self, boll_enabled: bool):
        """Run _calculate_indicators with a given BOLL_ENABLED setting."""
        from data_provider.base import BaseFetcher

        df = _make_test_df()
        # Use a MagicMock that passes isinstance checks and has required attrs
        fetcher = MagicMock(spec=BaseFetcher)
        fetcher.name = "TestFetcher"

        with patch('src.config.get_config') as mock_get_config:
            mock_config = MagicMock()
            mock_config.boll_enabled = boll_enabled
            mock_get_config.return_value = mock_config
            result = BaseFetcher._calculate_indicators(fetcher, df)
        return result

    def test_boll_calculated_when_enabled(self):
        """When BOLL_ENABLED=true, BOLL columns should exist."""
        result = self._calculate(boll_enabled=True)
        for suffix in ['5u', '5m', '5l', '5_width', '10u', '20u', '20_width']:
            assert f'boll_{suffix}' in result.columns, f"Missing boll_{suffix}"

    def test_boll_not_calculated_when_disabled(self):
        """When BOLL_ENABLED=false, BOLL columns should NOT exist."""
        result = self._calculate(boll_enabled=False)
        boll_cols = [c for c in result.columns if c.startswith('boll_')]
        assert boll_cols == [], f"Unexpected BOLL columns: {boll_cols}"

    def test_boll_values_are_reasonable(self):
        """Sanity check: upper > middle > lower for BOLL."""
        result = self._calculate(boll_enabled=True)
        for p in [5, 10, 20]:
            last_idx = -1
            assert result[f'boll_{p}u'].iloc[last_idx] > result[f'boll_{p}m'].iloc[last_idx]
            assert result[f'boll_{p}m'].iloc[last_idx] > result[f'boll_{p}l'].iloc[last_idx]
            assert result[f'boll_{p}_width'].iloc[last_idx] > 0


# ============================================================
# Prompt schema conditional
# ============================================================

class TestBollPromptConditional:
    """Test that the BOLL schema field is conditional in the prompt."""

    def _make_analyzer(self, boll_enabled: bool):
        from src.analyzer import GeminiAnalyzer
        analyzer = GeminiAnalyzer()
        mock_config = MagicMock()
        mock_config.boll_enabled = boll_enabled
        mock_config.boll_periods = "5,10,20"
        analyzer._config_override = mock_config
        return analyzer

    def test_boll_schema_empty_when_disabled(self):
        """When BOLL_ENABLED=false, schema should contain empty boll_analysis."""
        analyzer = self._make_analyzer(boll_enabled=False)
        prompt = analyzer._get_analysis_system_prompt("zh", "600519")
        assert '"boll_analysis": "",' in prompt

    def test_boll_schema_full_when_enabled(self):
        """When BOLL_ENABLED=true, schema should contain full boll_analysis field."""
        analyzer = self._make_analyzer(boll_enabled=True)
        prompt = analyzer._get_analysis_system_prompt("zh", "600519")
        assert '"boll_analysis"' in prompt
        assert '布林带分析' in prompt

    def test_no_json_comment_when_disabled(self):
        """When BOLL disabled, the schema must not contain # comments (invalid JSON)."""
        import re
        analyzer = self._make_analyzer(boll_enabled=False)
        prompt = analyzer._get_analysis_system_prompt("zh", "600519")
        match = re.search(r'"boll_analysis"\s*:\s*"[^"]*"', prompt)
        assert match is not None, "boll_analysis field not found in prompt"
        assert '#' not in match.group(0)

    def test_boll_schema_empty_in_both_templates(self):
        """Verify the disabled boll_analysis field does NOT include full description."""
        analyzer = self._make_analyzer(boll_enabled=False)
        prompt = analyzer._get_analysis_system_prompt("zh", "600519")
        assert '"boll_analysis": "",' in prompt
        # The full Chinese description should not appear in the output when disabled
        assert '布林带分析（基于BOLL数据' not in prompt


# ============================================================
# History report reconstruction
# ============================================================

class TestBollHistoryReconstruction:
    """Test that boll_analysis is properly mapped in history report rebuild."""

    def _make_mock_record(self, **kwargs):
        class MockRecord:
            pass
        record = MockRecord()
        record.code = kwargs.get('code', '600519')
        record.name = kwargs.get('name', '贵州茅台')
        record.sentiment_score = kwargs.get('sentiment_score', 50)
        record.trend_prediction = kwargs.get('trend_prediction', '')
        record.operation_advice = kwargs.get('operation_advice', '')
        record.news_content = kwargs.get('news_content', '')
        record.analysis_summary = kwargs.get('analysis_summary', '')
        return record

    def test_rebuild_includes_boll_analysis(self):
        """_rebuild_analysis_result should map boll_analysis from raw_result."""
        from src.services.history_service import HistoryService

        service = HistoryService()
        raw_result = {
            "code": "600519",
            "name": "贵州茅台",
            "sentiment_score": 55,
            "boll_analysis": "股价位于布林带中轨附近，带宽收窄等待变盘。",
            "dashboard": {},
        }
        record = self._make_mock_record(sentiment_score=55)
        result = service._rebuild_analysis_result(raw_result, record)
        assert result is not None
        assert result.boll_analysis == "股价位于布林带中轨附近，带宽收窄等待变盘。"

    def test_rebuild_empty_boll_analysis(self):
        """When raw_result has no boll_analysis, should default to empty string."""
        from src.services.history_service import HistoryService

        service = HistoryService()
        raw_result = {"code": "600519", "name": "贵州茅台", "sentiment_score": 50, "dashboard": {}}
        record = self._make_mock_record()
        result = service._rebuild_analysis_result(raw_result, record)
        assert result is not None
        assert result.boll_analysis == ""


# ============================================================
# Backfill detection (has_boll_data)
# ============================================================

class TestBollBackfill:
    """Test that has_boll_data detects missing BOLL values correctly."""

    def test_has_boll_data_returns_true_when_populated(self):
        """has_boll_data should return True when boll_5u is non-null."""
        from src.storage import get_db, StockDaily
        db = get_db()
        assert hasattr(StockDaily, 'boll_5u'), "StockDaily must have boll_5u column"
        assert callable(getattr(db, 'has_boll_data', None)), "StorageService must have has_boll_data method"


# ============================================================
# Regression: BOLL_ENABLED=false upsert preserves existing data
# ============================================================

class TestBollDisabledUpsertRegression:
    """Test that save_daily_data does NOT overwrite existing BOLL data
    when the incoming DataFrame lacks BOLL columns (BOLL_ENABLED=false)."""

    @pytest.fixture(autouse=True)
    def _setup_db(self):
        """Create a clean isolated SQLite DB before each test."""
        import tempfile, os
        from src.storage import DatabaseManager, get_db
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from src.storage import Base

        self._tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self._db_path = self._tmp.name
        self._tmp.close()

        # Reset singleton and create a new instance pointing to temp DB
        DatabaseManager.reset_instance()
        self.db = get_db()
        # Point engine to temp DB
        self.db._db_url = f'sqlite:///{self._db_path}'
        self.db._engine = create_engine(self.db._db_url, echo=False)
        self.db._is_sqlite_engine = True
        # Rebuild session factory bound to the new engine
        self.db._SessionLocal = sessionmaker(
            bind=self.db._engine,
            autoflush=False,
        )
        Base.metadata.create_all(self.db._engine)
        self.db._initialized = True

        yield

        DatabaseManager.reset_instance()
        try:
            os.unlink(self._db_path)
        except OSError:
            pass

    def _make_df_with_boll(self):
        """DataFrame WITH BOLL columns (simulating BOLL_ENABLED=true)."""
        import pandas as pd
        from datetime import date, timedelta
        today = date.today()
        df = pd.DataFrame({
            'date': [today - timedelta(days=i) for i in range(3, -1, -1)],
            'open': [10.0, 11.0, 12.0, 11.5],
            'high': [11.0, 12.0, 13.0, 12.0],
            'low': [9.5, 10.5, 11.5, 11.0],
            'close': [10.5, 11.5, 12.5, 11.8],
            'volume': [1000, 1200, 1100, 1300],
            'amount': [10500, 13800, 13750, 15340],
            'pct_chg': [1.0, 0.5, -0.3, 0.8],
            'ma5': [10.5, 11.0, 11.5, 11.8],
            'ma10': [10.2, 10.8, 11.2, 11.5],
            'ma20': [10.0, 10.5, 11.0, 11.3],
            'volume_ratio': [1.0, 1.2, 1.1, 1.3],
            'boll_5u': [12.0, 13.0, 14.0, 13.5],
            'boll_5m': [10.5, 11.0, 11.5, 11.8],
            'boll_5l': [9.0, 9.0, 9.0, 10.1],
            'boll_5_width': [28.57, 36.36, 43.48, 28.81],
            'boll_10u': [11.8, 12.8, 13.5, 13.2],
            'boll_10m': [10.2, 10.8, 11.2, 11.5],
            'boll_10l': [8.6, 8.8, 8.9, 9.8],
            'boll_10_width': [31.37, 37.04, 41.07, 29.57],
            'boll_20u': [11.5, 12.5, 13.0, 12.8],
            'boll_20m': [10.0, 10.5, 11.0, 11.3],
            'boll_20l': [8.5, 8.5, 9.0, 9.8],
            'boll_20_width': [30.00, 38.10, 36.36, 26.55],
        })
        return df

    def _make_df_without_boll(self):
        """DataFrame WITHOUT BOLL columns (simulating BOLL_ENABLED=false)."""
        import pandas as pd
        from datetime import date, timedelta
        today = date.today()
        df = pd.DataFrame({
            'date': [today - timedelta(days=i) for i in range(3, -1, -1)],
            'open': [10.5, 11.5, 12.5, 12.0],
            'high': [11.5, 12.5, 13.5, 12.5],
            'low': [10.0, 11.0, 12.0, 11.5],
            'close': [11.0, 12.0, 13.0, 12.2],
            'volume': [1100, 1300, 1200, 1400],
            'amount': [12100, 15600, 15600, 17080],
            'pct_chg': [1.5, 0.8, -0.2, 1.0],
            'ma5': [10.8, 11.3, 11.8, 12.0],
            'ma10': [10.4, 11.0, 11.4, 11.7],
            'ma20': [10.2, 10.7, 11.2, 11.5],
            'volume_ratio': [1.1, 1.3, 1.2, 1.4],
        })
        return df

    def test_upsert_without_boll_preserves_existing_boll_data(self):
        """After saving with BOLL then saving without BOLL, BOLL data should persist."""
        from datetime import date, timedelta
        from src.storage import StockDaily
        from sqlalchemy import select

        today = date.today()

        # Step 1: Save with BOLL columns (enabled)
        df_with = self._make_df_with_boll()
        inserted = self.db.save_daily_data(df_with, '600519', 'TestFetcher')
        assert inserted >= 0

        # Verify BOLL data was saved
        with self.db.get_session() as session:
            for row_date in [today - timedelta(days=i) for i in range(3, -1, -1)]:
                row = session.execute(
                    select(StockDaily).where(
                        StockDaily.code == '600519',
                        StockDaily.date == row_date,
                    )
                ).scalar_one_or_none()
                assert row is not None, f"Row for {row_date} not found"
                assert row.boll_5u is not None, f"boll_5u for {row_date} should be set"

        # Step 2: Save WITHOUT BOLL columns (disabled) - same dates
        df_without = self._make_df_without_boll()
        inserted = self.db.save_daily_data(df_without, '600519', 'TestFetcher')

        # Step 3: Verify BOLL data is STILL intact
        with self.db.get_session() as session:
            for row_date in [today - timedelta(days=i) for i in range(3, -1, -1)]:
                row = session.execute(
                    select(StockDaily).where(
                        StockDaily.code == '600519',
                        StockDaily.date == row_date,
                    )
                ).scalar_one_or_none()
                assert row is not None, f"Row for {row_date} not found"
                assert row.boll_5u is not None, \
                    f"boll_5u for {row_date} was wiped! BOLL data lost after disabled upsert"
                assert row.boll_5m is not None
                assert row.boll_5l is not None
                assert row.boll_20_width is not None
                # Verify non-BOLL fields WERE updated by the second save
                assert row.close == 11.0 or row.close == 12.0 or row.close == 13.0 or row.close == 12.2

    def test_new_record_without_boll_stores_null(self):
        """Saving a brand new record without BOLL columns should store NULL."""
        from datetime import date
        from src.storage import StockDaily
        from sqlalchemy import select

        df_without = self._make_df_without_boll()
        inserted = self.db.save_daily_data(df_without, '000001', 'TestFetcher')

        today = date.today()
        with self.db.get_session() as session:
            row = session.execute(
                select(StockDaily).where(
                    StockDaily.code == '000001',
                    StockDaily.date == today,
                )
            ).scalar_one_or_none()
            assert row is not None, "New record should exist"
            assert row.boll_5u is None, "BOLL columns should be NULL for new records without BOLL data"
            assert row.boll_5m is None
            assert row.boll_5l is None
            assert row.close == 12.2


# ============================================================
# Regression: BOLL_PERIODS subset (e.g. only period 10) write paths
# ============================================================

class TestBollSubsetUpsert:
    """Test that save_daily_data handles BOLL_PERIODS subset correctly.
    BOLL_PERIODS=10 should only write boll_10* columns, not touch others."""

    @pytest.fixture(autouse=True)
    def _setup_db(self):
        """Create a clean isolated SQLite DB before each test."""
        import tempfile, os
        from src.storage import DatabaseManager, get_db
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from src.storage import Base

        self._tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self._db_path = self._tmp.name
        self._tmp.close()

        # Reset singleton and create a new instance pointing to temp DB
        DatabaseManager.reset_instance()
        self.db = get_db()
        # Point engine to temp DB
        self.db._db_url = f'sqlite:///{self._db_path}'
        self.db._engine = create_engine(self.db._db_url, echo=False)
        self.db._is_sqlite_engine = True
        # Rebuild session factory bound to the new engine
        self.db._SessionLocal = sessionmaker(
            bind=self.db._engine,
            autoflush=False,
        )
        Base.metadata.create_all(self.db._engine)
        yield
        DatabaseManager.reset_instance()
        try:
            os.unlink(self._db_path)
        except OSError:
            pass

    def _make_df_full_boll(self):
        """DataFrame with ALL BOLL columns (period 5/10/20)."""
        import pandas as pd
        from datetime import date, timedelta
        today = date.today()
        df = pd.DataFrame({
            'date': [today - timedelta(days=i) for i in range(3, -1, -1)],
            'open': [10.0, 11.0, 12.0, 11.5],
            'high': [11.0, 12.0, 13.0, 12.0],
            'low': [9.5, 10.5, 11.5, 11.0],
            'close': [10.5, 11.5, 12.5, 11.8],
            'volume': [1000, 1200, 1100, 1300],
            'amount': [10500, 13800, 13750, 15340],
            'pct_chg': [1.0, 0.5, -0.3, 0.8],
            'ma5': [10.5, 11.0, 11.5, 11.8],
            'ma10': [10.2, 10.8, 11.2, 11.5],
            'ma20': [10.0, 10.5, 11.0, 11.3],
            'volume_ratio': [1.0, 1.2, 1.1, 1.3],
            'boll_5u': [12.0, 13.0, 14.0, 13.5],
            'boll_5m': [10.5, 11.0, 11.5, 11.8],
            'boll_5l': [9.0, 9.0, 9.0, 10.1],
            'boll_5_width': [28.57, 36.36, 43.48, 28.81],
            'boll_10u': [11.8, 12.8, 13.5, 13.2],
            'boll_10m': [10.2, 10.8, 11.2, 11.5],
            'boll_10l': [8.6, 8.8, 8.9, 9.8],
            'boll_10_width': [31.37, 37.04, 41.07, 29.57],
            'boll_20u': [11.5, 12.5, 13.0, 12.8],
            'boll_20m': [10.0, 10.5, 11.0, 11.3],
            'boll_20l': [8.5, 8.5, 9.0, 9.8],
            'boll_20_width': [30.00, 38.10, 36.36, 26.55],
        })
        return df

    def _make_df_boll_period_10_only(self):
        """DataFrame with ONLY boll_10* columns (simulating BOLL_PERIODS=10)."""
        import pandas as pd
        from datetime import date, timedelta
        today = date.today()
        df = pd.DataFrame({
            'date': [today - timedelta(days=i) for i in range(3, -1, -1)],
            'open': [11.0, 12.0, 13.0, 12.5],
            'high': [12.0, 13.0, 14.0, 13.0],
            'low': [10.5, 11.5, 12.5, 12.0],
            'close': [11.5, 12.5, 13.5, 12.8],
            'volume': [1100, 1300, 1200, 1400],
            'amount': [12650, 16250, 16200, 17920],
            'pct_chg': [1.2, 0.6, -0.2, 0.9],
            'ma5': [10.8, 11.3, 11.8, 12.0],
            'ma10': [10.4, 11.0, 11.4, 11.7],
            'ma20': [10.2, 10.7, 11.2, 11.5],
            'volume_ratio': [1.1, 1.3, 1.2, 1.4],
            # Only boll_10* columns — no boll_5* or boll_20*
            'boll_10u': [12.5, 13.5, 14.2, 13.8],
            'boll_10m': [10.8, 11.3, 11.8, 12.0],
            'boll_10l': [9.1, 9.1, 9.4, 10.2],
            'boll_10_width': [31.48, 38.94, 40.68, 30.00],
        })
        return df

    def test_subset_save_preserves_existing_full_boll_data(self):
        """
        After saving with full BOLL (period 5/10/20), saving with subset
        (period 10 only) should NOT wipe period 5 or 20 data.
        """
        from datetime import date, timedelta
        from src.storage import StockDaily
        from sqlalchemy import select

        today = date.today()

        # Step 1: Save with full BOLL columns
        df_full = self._make_df_full_boll()
        self.db.save_daily_data(df_full, '600001', 'TestFetcher')

        # Verify all periods were saved
        with self.db.get_session() as session:
            row = session.execute(
                select(StockDaily).where(
                    StockDaily.code == '600001',
                    StockDaily.date == today,
                )
            ).scalar_one_or_none()
            assert row is not None
            assert row.boll_5u is not None, "boll_5 should exist after full save"
            assert row.boll_10u is not None
            assert row.boll_20u is not None

        # Step 2: Save with subset (period 10 only) — simulates config change
        df_subset = self._make_df_boll_period_10_only()
        self.db.save_daily_data(df_subset, '600001', 'TestFetcher')

        # Verify period 5 and 20 data are still intact (NOT wiped)
        with self.db.get_session() as session:
            row = session.execute(
                select(StockDaily).where(
                    StockDaily.code == '600001',
                    StockDaily.date == today,
                )
            ).scalar_one_or_none()
            assert row is not None
            # Period 5 should still have its original values
            assert row.boll_5u is not None, \
                "boll_5u was wiped! Subset save should NOT overwrite non-configured period columns"
            assert row.boll_5m is not None
            assert row.boll_5l is not None
            # Period 20 should still have its original values
            assert row.boll_20u is not None, \
                "boll_20u was wiped! Subset save should NOT overwrite non-configured period columns"
            assert row.boll_20m is not None
            assert row.boll_20l is not None
            # Period 10 should have been updated to new values
            assert row.boll_10u == 13.8, \
                f"boll_10u should be updated to 13.8, got {row.boll_10u}"

    def test_subset_save_only_writes_configured_columns(self):
        """
        Saving with BOLL_PERIODS=10 only should write boll_10* columns,
        leave boll_5* and boll_20* as NULL for new records.
        """
        from datetime import date, timedelta
        from src.storage import StockDaily
        from sqlalchemy import select

        today = date.today()

        # Save with period 10 only (no prior data)
        df_subset = self._make_df_boll_period_10_only()
        self.db.save_daily_data(df_subset, '600002', 'TestFetcher')

        # Verify
        with self.db.get_session() as session:
            row = session.execute(
                select(StockDaily).where(
                    StockDaily.code == '600002',
                    StockDaily.date == today,
                )
            ).scalar_one_or_none()
            assert row is not None
            # Period 10 should have values
            assert row.boll_10u is not None
            assert row.boll_10m is not None
            assert row.boll_10l is not None
            assert row.boll_10_width is not None
            # Period 5 should be NULL (never configured)
            assert row.boll_5u is None, \
                "boll_5u should be NULL when only period 10 is configured"
            assert row.boll_5m is None
            assert row.boll_5l is None
            assert row.boll_5_width is None
            # Period 20 should be NULL (never configured)
            assert row.boll_20u is None, \
                "boll_20u should be NULL when only period 10 is configured"
            assert row.boll_20m is None
            assert row.boll_20l is None
            assert row.boll_20_width is None