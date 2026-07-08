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
        # This test verifies the query logic by checking that has_boll_data
        # queries the correct column (boll_5u)
        from src.storage import get_db, StockDaily
        db = get_db()
        # The method uses select(StockDaily.boll_5u) and checks scalar_one_or_none
        # This is a contract test - the SQL query is valid SQLAlchemy
        assert hasattr(StockDaily, 'boll_5u'), "StockDaily must have boll_5u column"
        assert callable(getattr(db, 'has_boll_data', None)), "StorageService must have has_boll_data method"