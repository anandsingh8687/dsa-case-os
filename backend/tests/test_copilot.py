"""Tests for the DSA Copilot functionality.

Tests cover:
- Query classification
- Data retrieval for different query types
- Kimi API integration (mocked)
- Endpoint responses
- Edge cases
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import json

from app.services.stages.stage7_retriever import (
    classify_query,
    QueryType,
    retrieve_lender_data,
)
from app.services.stages.stage7_copilot import (
    query_copilot,
    _generate_answer,
    _build_sources,
)


# ═══════════════════════════════════════════════════════════════
# QUERY CLASSIFICATION TESTS
# ═══════════════════════════════════════════════════════════════

class TestQueryClassification:
    """Test query classification logic."""

    def test_classify_cibil_query(self):
        """Test CIBIL score query classification."""
        queries = [
            "Which lenders accept CIBIL score of 650?",
            "lenders for 650 cibil",
            "score below 700",
            "credit score 680",
        ]

        for query in queries:
            query_type, params = classify_query(query)
            assert query_type == QueryType.CIBIL
            assert 'cibil_score' in params
            assert isinstance(params['cibil_score'], int)

    def test_classify_cibil_above_below(self):
        """Test CIBIL above/below detection."""
        # Below queries
        query = "lenders accepting below 650 cibil"
        query_type, params = classify_query(query)
        assert params['operator'] == '<='

        # Above queries
        query = "lenders requiring above 750 cibil"
        query_type, params = classify_query(query)
        assert params['operator'] == '>='

    def test_classify_pincode_query(self):
        """Test pincode query classification."""
        queries = [
            "who serves pincode 400001?",
            "lenders for 110001",
            "pincode 560001 coverage",
        ]

        for query in queries:
            query_type, params = classify_query(query)
            assert query_type == QueryType.PINCODE
            assert 'pincode' in params

    def test_classify_lender_specific_query(self):
        """Test lender-specific query classification."""
        queries = [
            "What's the policy for Bajaj Finance?",
            "Tell me about IIFL requirements",
            "Tata Capital products",
        ]

        for query in queries:
            query_type, params = classify_query(query)
            assert query_type == QueryType.LENDER_SPECIFIC
            assert 'lender_name' in params

    def test_classify_comparison_query(self):
        """Test comparison query classification."""
        query = "Compare Bajaj Finance and IIFL"
        query_type, params = classify_query(query)
        assert query_type == QueryType.COMPARISON
        assert 'lenders' in params
        assert len(params['lenders']) >= 2

    def test_classify_vintage_query(self):
        """Test vintage query classification."""
        queries = [
            "lenders accepting 1 year vintage",
            "2.5 years business vintage",
            "vintage of 3 years",
        ]

        for query in queries:
            query_type, params = classify_query(query)
            assert query_type == QueryType.VINTAGE
            assert 'vintage_years' in params
            assert isinstance(params['vintage_years'], float)

    def test_classify_turnover_query(self):
        """Test turnover query classification."""
        queries = [
            "50 lakh turnover requirement",
            "turnover of 100 lakh",
            "2 crore revenue",
        ]

        for query in queries:
            query_type, params = classify_query(query)
            assert query_type == QueryType.TURNOVER
            assert 'turnover' in params
            assert isinstance(params['turnover'], float)

    def test_classify_entity_type_query(self):
        """Test entity type query classification."""
        queries = [
            "proprietorship friendly lenders",
            "lenders for private limited companies",
            "partnership loans",
            "LLP financing",
        ]

        for query in queries:
            query_type, params = classify_query(query)
            assert query_type == QueryType.ENTITY_TYPE
            assert 'entity_type' in params

    def test_classify_requirement_query(self):
        """Test requirement-based query classification."""
        # No video KYC
        query = "lenders with no video KYC"
        query_type, params = classify_query(query)
        assert query_type == QueryType.REQUIREMENT
        assert params['requirement'] == 'video_kyc_required'
        assert params['value'] is False

        # With video KYC
        query = "lenders requiring video KYC"
        query_type, params = classify_query(query)
        assert params['value'] is True

    def test_classify_general_query(self):
        """Test general query classification."""
        queries = [
            "Tell me about business loans",
            "What options are available?",
            "Help me find a lender",
        ]

        for query in queries:
            query_type, params = classify_query(query)
            assert query_type == QueryType.GENERAL


# ═══════════════════════════════════════════════════════════════
# DATA RETRIEVAL TESTS (with mocked database)
# ═══════════════════════════════════════════════════════════════

class TestDataRetrieval:
    """Test data retrieval for different query types."""

    @pytest.mark.asyncio
    async def test_retrieve_by_cibil(self):
        """Test CIBIL-based retrieval."""
        mock_db = AsyncMock()
        mock_result = AsyncMock()
        mock_result.fetchall = AsyncMock(return_value=[
            {
                'lender_name': 'Bajaj Finance',
                'product_name': 'BL',
                'min_cibil_score': 650,
                'min_vintage_years': 2.0,
                'max_ticket_size': 75.0,
            }
        ])
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch('app.services.stages.stage7_retriever.get_db_session') as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_db

            query_type = QueryType.CIBIL
            params = {'cibil_score': 650, 'operator': '<='}

            results = await retrieve_lender_data(query_type, params)
            assert len(results) > 0
            assert results[0]['lender_name'] == 'Bajaj Finance'

    @pytest.mark.asyncio
    async def test_retrieve_by_pincode(self):
        """Test pincode-based retrieval."""
        mock_db = AsyncMock()
        mock_result = AsyncMock()
        mock_result.fetchall = AsyncMock(return_value=[
            {
                'lender_name': 'IIFL',
                'product_name': 'BL',
                'min_cibil_score': 675,
            }
        ])
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch('app.services.stages.stage7_retriever.get_db_session') as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_db

            query_type = QueryType.PINCODE
            params = {'pincode': '400001'}

            results = await retrieve_lender_data(query_type, params)
            assert len(results) > 0


# ═══════════════════════════════════════════════════════════════
# CLAUDE API INTEGRATION TESTS (mocked)
# ═══════════════════════════════════════════════════════════════

class TestKimiIntegration:
    """Test Kimi API integration with mocked responses."""

    @pytest.mark.asyncio
    async def test_generate_answer_with_api(self):
        """Test answer generation with mocked Kimi API."""
        mock_response = Mock()
        mock_response.content = [Mock(text="Found 5 lenders accepting CIBIL 650: Bajaj Finance, IIFL, Lendingkart, Flexiloans, Indifi.")]

        with patch('app.services.stages.stage7_copilot.AsyncOpenAI') as mock_openai:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_openai.return_value = mock_client

            with patch('app.services.stages.stage7_copilot.settings') as mock_settings:
                mock_settings.LLM_API_KEY = "test-key"
                mock_settings.LLM_MODEL = "kimi-latest"

                query_type = QueryType.CIBIL
                params = {'cibil_score': 650}
                lender_data = [
                    {'lender_name': 'Bajaj Finance', 'min_cibil_score': 650},
                    {'lender_name': 'IIFL', 'min_cibil_score': 675},
                ]

                answer = await _generate_answer("lenders for 650 cibil", query_type, params, lender_data)
                assert "Bajaj Finance" in answer or "lenders" in answer.lower()

    @pytest.mark.asyncio
    async def test_generate_answer_without_api(self):
        """Test fallback answer generation when API key is missing."""
        with patch('app.services.stages.stage7_copilot.settings') as mock_settings:
            mock_settings.LLM_API_KEY = None

            query_type = QueryType.CIBIL
            params = {'cibil_score': 650}
            lender_data = [
                {'lender_name': 'Bajaj Finance', 'min_cibil_score': 650},
            ]

            answer = await _generate_answer("lenders for 650 cibil", query_type, params, lender_data)
            assert "Bajaj Finance" in answer


# ═══════════════════════════════════════════════════════════════
# SOURCE FORMATTING TESTS
# ═══════════════════════════════════════════════════════════════

class TestSourceFormatting:
    """Test source list building."""

    def test_build_sources_basic(self):
        """Test basic source formatting."""
        lender_data = [
            {
                'lender_name': 'Bajaj Finance',
                'product_name': 'BL',
                'min_cibil_score': 650,
                'max_ticket_size': 75.0,
            },
            {
                'lender_name': 'IIFL',
                'product_name': 'STBL',
                'min_cibil_score': 675,
                'max_ticket_size': 50.0,
            },
        ]

        sources = _build_sources(lender_data, QueryType.CIBIL)
        assert len(sources) == 2
        assert sources[0]['lender_name'] == 'Bajaj Finance'
        assert sources[0]['min_cibil'] == 650

    def test_build_sources_with_entity_types(self):
        """Test source formatting with entity types."""
        lender_data = [
            {
                'lender_name': 'Bajaj Finance',
                'product_name': 'BL',
                'eligible_entity_types': ['proprietorship', 'partnership'],
            },
        ]

        sources = _build_sources(lender_data, QueryType.ENTITY_TYPE)
        assert len(sources) == 1
        assert 'entity_types' in sources[0]


# ═══════════════════════════════════════════════════════════════
# END-TO-END COPILOT TESTS
# ═══════════════════════════════════════════════════════════════

class TestCopilotEndToEnd:
    """Test complete copilot flow."""

    @pytest.mark.asyncio
    async def test_query_copilot_complete_flow(self):
        """Test complete copilot query flow with mocked database and API."""
        # Mock database
        mock_db = AsyncMock()
        mock_result = AsyncMock()
        mock_result.fetchall = AsyncMock(return_value=[
            {
                'lender_name': 'Bajaj Finance',
                'product_name': 'BL',
                'min_cibil_score': 650,
                'min_vintage_years': 2.0,
                'max_ticket_size': 75.0,
                'pincode_coverage': 1500,
            }
        ])
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Mock Kimi API
        mock_response = Mock()
        mock_response.content = [Mock(text="Found 1 lender accepting CIBIL 650: Bajaj Finance (BL product).")]

        with patch('app.services.stages.stage7_retriever.get_db_session') as mock_session, \
             patch('app.services.stages.stage7_copilot.get_db_session') as mock_log_session, \
             patch('app.services.stages.stage7_copilot.AsyncOpenAI') as mock_openai, \
             patch('app.services.stages.stage7_copilot.settings') as mock_settings:

            mock_session.return_value.__aenter__.return_value = mock_db
            mock_log_session.return_value.__aenter__.return_value = mock_db

            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_openai.return_value = mock_client

            mock_settings.LLM_API_KEY = "test-key"
            mock_settings.LLM_MODEL = "kimi-latest"

            # Execute copilot query
            response = await query_copilot("lenders for 650 cibil")

            # Assertions
            assert response.answer is not None
            assert len(response.answer) > 0
            assert response.response_time_ms > 0
            assert len(response.sources) > 0

    @pytest.mark.asyncio
    async def test_query_copilot_no_results(self):
        """Test copilot with no matching lenders."""
        mock_db = AsyncMock()
        mock_result = AsyncMock()
        mock_result.fetchall = AsyncMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch('app.services.stages.stage7_retriever.get_db_session') as mock_session, \
             patch('app.services.stages.stage7_copilot.get_db_session') as mock_log_session, \
             patch('app.services.stages.stage7_copilot.settings') as mock_settings:

            mock_session.return_value.__aenter__.return_value = mock_db
            mock_log_session.return_value.__aenter__.return_value = mock_db
            mock_settings.LLM_API_KEY = None

            response = await query_copilot("lenders for 200 cibil")

            assert "couldn't find" in response.answer.lower() or "no" in response.answer.lower()


# ═══════════════════════════════════════════════════════════════
# EDGE CASES AND ERROR HANDLING
# ═══════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_classify_empty_query(self):
        """Test classification of empty query."""
        query_type, params = classify_query("")
        assert query_type == QueryType.GENERAL

    def test_classify_numeric_only_query(self):
        """Test query with only numbers."""
        query_type, params = classify_query("123456")
        # Should detect as pincode
        assert query_type == QueryType.PINCODE

    def test_classify_mixed_signals_query(self):
        """Test query with multiple signals (should pick first match)."""
        query = "Bajaj Finance for 650 cibil in pincode 400001"
        query_type, params = classify_query(query)
        # Pincode check comes first in the classification logic
        assert query_type == QueryType.PINCODE

    @pytest.mark.asyncio
    async def test_query_copilot_api_error(self):
        """Test copilot when Kimi API throws an error."""
        mock_db = AsyncMock()
        mock_result = AsyncMock()
        mock_result.fetchall = AsyncMock(return_value=[
            {'lender_name': 'Bajaj Finance', 'product_name': 'BL'}
        ])
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch('app.services.stages.stage7_retriever.get_db_session') as mock_session, \
             patch('app.services.stages.stage7_copilot.get_db_session') as mock_log_session, \
             patch('app.services.stages.stage7_copilot.AsyncOpenAI') as mock_openai, \
             patch('app.services.stages.stage7_copilot.settings') as mock_settings:

            mock_session.return_value.__aenter__.return_value = mock_db
            mock_log_session.return_value.__aenter__.return_value = mock_db

            # Mock API to raise an exception
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(side_effect=Exception("API Error"))
            mock_openai.return_value = mock_client

            mock_settings.LLM_API_KEY = "test-key"
            mock_settings.LLM_MODEL = "kimi-latest"

            response = await query_copilot("test query")

            # Should fall back to basic answer
            assert response.answer is not None
            assert "Bajaj Finance" in response.answer or len(response.answer) > 0
