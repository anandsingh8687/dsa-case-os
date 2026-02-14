"""
LLM-Based Report Generation Service

Generates narrative, human-readable reports using LLM instead of showing raw field values.
Uses Kimi 2.5 (Moonshot AI) for natural language generation.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime as dt
from openai import AsyncOpenAI

from app.core.config import settings
from app.db.database import get_db_session

logger = logging.getLogger(__name__)


class LLMReportService:
    """Service for generating LLM-powered narrative reports."""

    def __init__(self):
        self.llm_client = None
        if settings.LLM_API_KEY:
            self.llm_client = AsyncOpenAI(
                api_key=settings.LLM_API_KEY,
                base_url=settings.LLM_BASE_URL,
            )

    async def generate_borrower_profile_report(
        self,
        case_id: str
    ) -> Dict[str, Any]:
        """
        Generate a narrative borrower profile report.

        Instead of showing:
        - Name: John Doe
        - CIBIL: 720
        - Vintage: 2.5 years

        Generates:
        "John Doe operates a proprietorship business with 2.5 years of operational
        history. The business demonstrates strong creditworthiness with a CIBIL
        score of 720, indicating reliable repayment history..."

        Args:
            case_id: Case ID

        Returns:
            {
                'case_id': str,
                'report_type': 'profile',
                'narrative': str,
                'sections': {
                    'business_overview': str,
                    'financial_health': str,
                    'credit_profile': str,
                    'risk_assessment': str
                },
                'generated_at': str
            }
        """
        # Fetch case data
        case_data = await self._fetch_case_data(case_id)

        if not case_data:
            return {
                'success': False,
                'error': 'Case not found or insufficient data'
            }

        # Generate report using LLM
        report = await self._generate_profile_narrative(case_data)

        return {
            'success': True,
            'case_id': case_id,
            'report_type': 'profile',
            **report,
            'generated_at': dt.utcnow().isoformat()
        }

    async def generate_eligibility_report(
        self,
        case_id: str
    ) -> Dict[str, Any]:
        """
        Generate a narrative eligibility report.

        Instead of showing:
        - Lenders passed: 12/45
        - Score: 65/100

        Generates:
        "The applicant qualifies for financing from 12 lenders out of 45 evaluated.
        The eligibility analysis reveals strong creditworthiness (CIBIL 720) and
        adequate business vintage (2.5 years), making them eligible for most
        standard business loan products. However, limited monthly turnover
        (₹3.5L) restricts access to higher-ticket-size lenders..."

        Args:
            case_id: Case ID

        Returns:
            {
                'case_id': str,
                'report_type': 'eligibility',
                'narrative': str,
                'sections': {...},
                'generated_at': str
            }
        """
        # Fetch eligibility data
        eligibility_data = await self._fetch_eligibility_data(case_id)

        if not eligibility_data:
            return {
                'success': False,
                'error': 'Eligibility data not available'
            }

        # Generate report using LLM
        report = await self._generate_eligibility_narrative(eligibility_data)

        return {
            'success': True,
            'case_id': case_id,
            'report_type': 'eligibility',
            **report,
            'generated_at': dt.utcnow().isoformat()
        }

    async def generate_document_summary(
        self,
        case_id: str
    ) -> Dict[str, Any]:
        """
        Generate a narrative document summary.

        Instead of showing:
        - 5 documents uploaded
        - GST Certificate: verified
        - Bank Statements: 6 months

        Generates:
        "The application includes comprehensive documentation with 5 verified
        documents. GST certification confirms the business is registered and
        tax-compliant. Six months of bank statements provide detailed insights
        into cash flow patterns, showing consistent monthly inflows of ₹4.5L..."

        Args:
            case_id: Case ID

        Returns:
            Narrative document summary report
        """
        # Fetch document data
        document_data = await self._fetch_document_data(case_id)

        if not document_data:
            return {
                'success': False,
                'error': 'No documents found'
            }

        # Generate report using LLM
        report = await self._generate_document_narrative(document_data)

        return {
            'success': True,
            'case_id': case_id,
            'report_type': 'documents',
            **report,
            'generated_at': dt.utcnow().isoformat()
        }

    async def generate_comprehensive_report(
        self,
        case_id: str
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive case report combining all aspects.

        This is a full narrative report including:
        - Borrower profile
        - Financial analysis
        - Credit assessment
        - Document verification
        - Eligibility summary
        - Recommendations

        Args:
            case_id: Case ID

        Returns:
            Full comprehensive narrative report
        """
        # Fetch all data
        case_data = await self._fetch_case_data(case_id)
        eligibility_data = await self._fetch_eligibility_data(case_id)
        document_data = await self._fetch_document_data(case_id)

        if not case_data:
            return {
                'success': False,
                'error': 'Case not found'
            }

        # Combine all data
        comprehensive_data = {
            'case': case_data,
            'eligibility': eligibility_data,
            'documents': document_data
        }

        # Generate comprehensive report using LLM
        report = await self._generate_comprehensive_narrative(comprehensive_data)

        return {
            'success': True,
            'case_id': case_id,
            'report_type': 'comprehensive',
            **report,
            'generated_at': dt.utcnow().isoformat()
        }

    # ============================================================
    # DATA FETCHING
    # ============================================================

    async def _fetch_case_data(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Fetch comprehensive case and borrower data."""
        try:
            async with get_db_session() as db:
                query = """
                    SELECT
                        c.case_id,
                        c.borrower_name,
                        c.entity_type,
                        c.business_vintage_years,
                        c.industry_type,
                        c.pincode,
                        c.loan_amount_requested,
                        c.gstin,
                        c.gst_data,
                        bf.full_name,
                        bf.pan_number,
                        bf.entity_type as feature_entity_type,
                        bf.business_vintage_years as feature_vintage,
                        bf.monthly_turnover,
                        bf.avg_monthly_balance,
                        bf.bounced_cheques_count,
                        bf.cibil_score,
                        bf.active_loan_count,
                        bf.overdue_count,
                        bf.enquiry_count_6m
                    FROM cases c
                    LEFT JOIN borrower_features bf ON c.id = bf.case_id
                    WHERE c.case_id = $1
                """

                row = await db.fetchrow(query, case_id)

                if not row:
                    return None

                return dict(row)

        except Exception as e:
            logger.error(f"Error fetching case data: {e}")
            return None

    async def _fetch_eligibility_data(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Fetch eligibility analysis data."""
        try:
            async with get_db_session() as db:
                # Get case UUID
                case_query = "SELECT id FROM cases WHERE case_id = $1"
                case_row = await db.fetchrow(case_query, case_id)

                if not case_row:
                    return None

                case_uuid = case_row['id']

                # Fetch eligibility results
                query = """
                    SELECT
                        lender_name,
                        product_name,
                        passed,
                        score,
                        failed_criteria
                    FROM eligibility_results
                    WHERE case_id = $1
                    ORDER BY passed DESC, score DESC
                """

                rows = await db.fetch(query, case_uuid)

                if not rows:
                    return None

                results = [dict(row) for row in rows]

                # Calculate summary stats
                total = len(results)
                passed = sum(1 for r in results if r['passed'])

                return {
                    'total_lenders': total,
                    'lenders_passed': passed,
                    'pass_rate': (passed / total * 100) if total > 0 else 0,
                    'results': results
                }

        except Exception as e:
            logger.error(f"Error fetching eligibility data: {e}")
            return None

    async def _fetch_document_data(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Fetch document data."""
        try:
            async with get_db_session() as db:
                # Get case UUID
                case_query = "SELECT id FROM cases WHERE case_id = $1"
                case_row = await db.fetchrow(case_query, case_id)

                if not case_row:
                    return None

                case_uuid = case_row['id']

                # Fetch documents
                query = """
                    SELECT
                        original_filename,
                        doc_type,
                        status,
                        classification_confidence,
                        page_count,
                        created_at
                    FROM documents
                    WHERE case_id = $1
                    ORDER BY created_at ASC
                """

                rows = await db.fetch(query, case_uuid)

                documents = [dict(row) for row in rows]

                # Group by doc_type
                doc_types = {}
                for doc in documents:
                    dtype = doc['doc_type']
                    if dtype not in doc_types:
                        doc_types[dtype] = []
                    doc_types[dtype].append(doc)

                return {
                    'total_documents': len(documents),
                    'documents': documents,
                    'by_type': doc_types
                }

        except Exception as e:
            logger.error(f"Error fetching document data: {e}")
            return None

    # ============================================================
    # LLM NARRATIVE GENERATION
    # ============================================================

    async def _generate_profile_narrative(
        self,
        case_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate narrative profile report using LLM."""
        if not self.llm_client:
            return self._generate_fallback_profile(case_data)

        # Build prompt
        prompt = self._build_profile_prompt(case_data)

        try:
            response = await self.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                max_tokens=2000,
                temperature=0.3,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_report_system_prompt()
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            narrative = response.choices[0].message.content

            # Parse sections if LLM provided them
            sections = self._parse_sections(narrative)

            return {
                'narrative': narrative,
                'sections': sections
            }

        except Exception as e:
            logger.error(f"Error generating profile narrative: {e}")
            return self._generate_fallback_profile(case_data)

    async def _generate_eligibility_narrative(
        self,
        eligibility_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate narrative eligibility report using LLM."""
        if not self.llm_client:
            return self._generate_fallback_eligibility(eligibility_data)

        prompt = self._build_eligibility_prompt(eligibility_data)

        try:
            response = await self.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                max_tokens=2000,
                temperature=0.3,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_report_system_prompt()
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            narrative = response.choices[0].message.content
            sections = self._parse_sections(narrative)

            return {
                'narrative': narrative,
                'sections': sections
            }

        except Exception as e:
            logger.error(f"Error generating eligibility narrative: {e}")
            return self._generate_fallback_eligibility(eligibility_data)

    async def _generate_document_narrative(
        self,
        document_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate narrative document summary using LLM."""
        if not self.llm_client:
            return self._generate_fallback_documents(document_data)

        prompt = self._build_document_prompt(document_data)

        try:
            response = await self.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                max_tokens=1500,
                temperature=0.3,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_report_system_prompt()
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            narrative = response.choices[0].message.content
            sections = self._parse_sections(narrative)

            return {
                'narrative': narrative,
                'sections': sections
            }

        except Exception as e:
            logger.error(f"Error generating document narrative: {e}")
            return self._generate_fallback_documents(document_data)

    async def _generate_comprehensive_narrative(
        self,
        comprehensive_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate comprehensive narrative report using LLM."""
        if not self.llm_client:
            return self._generate_fallback_comprehensive(comprehensive_data)

        prompt = self._build_comprehensive_prompt(comprehensive_data)

        try:
            response = await self.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                max_tokens=3000,
                temperature=0.3,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_report_system_prompt()
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            narrative = response.choices[0].message.content
            sections = self._parse_sections(narrative)

            return {
                'narrative': narrative,
                'sections': sections
            }

        except Exception as e:
            logger.error(f"Error generating comprehensive narrative: {e}")
            return self._generate_fallback_comprehensive(comprehensive_data)

    # ============================================================
    # PROMPT BUILDING
    # ============================================================

    def _get_report_system_prompt(self) -> str:
        """System prompt for report generation."""
        return """You are a professional business loan analyst and report writer for DSAs (Direct Sales Agents) in India.

Your task is to generate clear, professional, narrative reports about loan applications. Instead of presenting data as bullet points or field-value pairs, write in flowing paragraphs that tell the borrower's story.

IMPORTANT RULES:
1. Write in professional, third-person narrative style
2. Use Indian financial terminology (Lakhs, Crores, CIBIL, GST, etc.)
3. Be specific with numbers and facts
4. Organize content into clear sections with headers
5. Focus on insights, not just data recitation
6. Highlight strengths and explain concerns
7. Keep paragraphs concise (3-5 sentences each)
8. Use section markers: ## Section Name

TONE:
- Professional but readable
- Objective and fact-based
- Constructive (highlight positives and areas of concern)
- Actionable (suggest what matters for loan approval)

OUTPUT FORMAT:
## Section 1
Narrative paragraph...

## Section 2
Narrative paragraph...

(Continue with all sections)
"""

    def _build_profile_prompt(self, case_data: Dict[str, Any]) -> str:
        """Build prompt for profile report."""
        return f"""Generate a professional borrower profile report based on the following data:

BORROWER INFORMATION:
- Name: {case_data.get('borrower_name') or case_data.get('full_name') or 'Not provided'}
- PAN: {case_data.get('pan_number') or 'Not provided'}
- Entity Type: {case_data.get('entity_type') or 'Not provided'}
- Industry: {case_data.get('industry_type') or 'Not provided'}
- Pincode: {case_data.get('pincode') or 'Not provided'}
- GSTIN: {case_data.get('gstin') or 'Not provided'}

BUSINESS METRICS:
- Business Vintage: {case_data.get('business_vintage_years') or case_data.get('feature_vintage') or 'Not available'} years
- Monthly Turnover: ₹{case_data.get('monthly_turnover') or 'Not available'}
- Average Monthly Balance: ₹{case_data.get('avg_monthly_balance') or 'Not available'}
- Bounced Cheques: {case_data.get('bounced_cheques_count') or '0'}

CREDIT PROFILE:
- CIBIL Score: {case_data.get('cibil_score') or 'Not available'}
- Active Loans: {case_data.get('active_loan_count') or '0'}
- Overdues: {case_data.get('overdue_count') or '0'}
- Recent Enquiries (6m): {case_data.get('enquiry_count_6m') or '0'}

LOAN REQUEST:
- Amount Requested: ₹{case_data.get('loan_amount_requested') or 'Not specified'}

Generate a professional narrative report with these sections:
## Business Overview
## Financial Health
## Credit Profile
## Risk Assessment

Write in flowing paragraphs, not bullet points. Be specific and insightful."""

    def _build_eligibility_prompt(self, eligibility_data: Dict[str, Any]) -> str:
        """Build prompt for eligibility report."""
        return f"""Generate a professional eligibility analysis report based on the following results:

ELIGIBILITY SUMMARY:
- Total Lenders Evaluated: {eligibility_data.get('total_lenders', 0)}
- Lenders Passed: {eligibility_data.get('lenders_passed', 0)}
- Pass Rate: {eligibility_data.get('pass_rate', 0):.1f}%

TOP MATCHING LENDERS (sample):
{self._format_top_lenders(eligibility_data.get('results', [])[:5])}

Generate a professional narrative report with these sections:
## Eligibility Summary
## Qualifying Lenders
## Key Strengths
## Areas of Concern

Write in flowing paragraphs explaining what this means for the borrower's loan prospects."""

    def _build_document_prompt(self, document_data: Dict[str, Any]) -> str:
        """Build prompt for document summary."""
        doc_summary = self._format_document_summary(document_data)

        return f"""Generate a professional document verification report based on the following:

DOCUMENT SUMMARY:
- Total Documents: {document_data.get('total_documents', 0)}

DOCUMENTS BY TYPE:
{doc_summary}

Generate a professional narrative report with these sections:
## Document Coverage
## Verification Status
## Data Quality

Write in flowing paragraphs explaining the completeness and quality of documentation."""

    def _build_comprehensive_prompt(self, comprehensive_data: Dict[str, Any]) -> str:
        """Build prompt for comprehensive report."""
        case_data = comprehensive_data.get('case', {})
        eligibility_data = comprehensive_data.get('eligibility', {})
        document_data = comprehensive_data.get('documents', {})

        return f"""Generate a comprehensive loan application report combining all aspects:

{self._build_profile_prompt(case_data)}

ELIGIBILITY:
{eligibility_data.get('lenders_passed', 0)}/{eligibility_data.get('total_lenders', 0)} lenders passed

DOCUMENTS:
{document_data.get('total_documents', 0)} documents submitted

Generate a comprehensive professional narrative report with these sections:
## Executive Summary
## Borrower Profile
## Financial Analysis
## Credit Assessment
## Eligibility Results
## Documentation Review
## Recommendations

Write a complete, flowing narrative suitable for presenting to senior management or lenders."""

    # ============================================================
    # HELPER METHODS
    # ============================================================

    def _parse_sections(self, narrative: str) -> Dict[str, str]:
        """Parse narrative into sections based on ## headers."""
        sections = {}
        current_section = None
        current_content = []

        for line in narrative.split('\n'):
            if line.strip().startswith('##'):
                # Save previous section
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()

                # Start new section
                current_section = line.strip().replace('##', '').strip().lower().replace(' ', '_')
                current_content = []
            else:
                current_content.append(line)

        # Save last section
        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()

        return sections

    def _format_top_lenders(self, lenders: List[Dict[str, Any]]) -> str:
        """Format top lenders for prompt."""
        if not lenders:
            return "None available"

        lines = []
        for lender in lenders:
            status = "✓ Passed" if lender.get('passed') else "✗ Failed"
            lines.append(f"- {lender.get('lender_name')} ({lender.get('product_name')}): {status}")

        return '\n'.join(lines)

    def _format_document_summary(self, document_data: Dict[str, Any]) -> str:
        """Format document summary for prompt."""
        by_type = document_data.get('by_type', {})

        if not by_type:
            return "No documents available"

        lines = []
        for doc_type, docs in by_type.items():
            count = len(docs)
            lines.append(f"- {doc_type}: {count} document(s)")

        return '\n'.join(lines)

    # ============================================================
    # FALLBACK METHODS (when LLM unavailable)
    # ============================================================

    def _generate_fallback_profile(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate basic profile report without LLM."""
        name = case_data.get('borrower_name') or 'Unknown'
        entity = case_data.get('entity_type') or 'Unknown'
        vintage = case_data.get('business_vintage_years') or 'Unknown'
        cibil = case_data.get('cibil_score') or 'Not available'

        narrative = f"""## Business Overview
{name} operates as a {entity} with {vintage} years of business history.

## Credit Profile
CIBIL Score: {cibil}

## Summary
Basic profile information available. Full narrative report requires LLM service."""

        return {
            'narrative': narrative,
            'sections': self._parse_sections(narrative)
        }

    def _generate_fallback_eligibility(self, eligibility_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate basic eligibility report without LLM."""
        passed = eligibility_data.get('lenders_passed', 0)
        total = eligibility_data.get('total_lenders', 0)

        narrative = f"""## Eligibility Summary
The applicant qualified for {passed} out of {total} lenders evaluated.

## Summary
Basic eligibility information available. Full narrative report requires LLM service."""

        return {
            'narrative': narrative,
            'sections': self._parse_sections(narrative)
        }

    def _generate_fallback_documents(self, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate basic document report without LLM."""
        total = document_data.get('total_documents', 0)

        narrative = f"""## Document Summary
Total of {total} documents have been uploaded.

## Summary
Basic document information available. Full narrative report requires LLM service."""

        return {
            'narrative': narrative,
            'sections': self._parse_sections(narrative)
        }

    def _generate_fallback_comprehensive(self, comprehensive_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate basic comprehensive report without LLM."""
        narrative = """## Summary
Comprehensive report generation requires LLM service. Please check LLM configuration."""

        return {
            'narrative': narrative,
            'sections': self._parse_sections(narrative)
        }

    async def generate_pincode_market_summary(
        self,
        pincode: str,
        lender_details: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Generate AI-powered market intelligence summary for a pincode (Fix 5).

        Args:
            pincode: The 6-digit pincode
            lender_details: List of lenders with their products and parameters

        Returns:
            A 2-3 line market summary for DSAs, or None if LLM unavailable
        """
        if not self.llm_client or not lender_details:
            return None

        # Extract key metrics for the prompt
        lender_count = len(lender_details)
        all_cibil_scores = []
        all_max_tickets = []

        for lender in lender_details:
            if lender.get('cibil_range', {}).get('min'):
                all_cibil_scores.append(lender['cibil_range']['min'])
            if lender.get('ticket_range', {}).get('max'):
                all_max_tickets.append(lender['ticket_range']['max'])

        cibil_min = min(all_cibil_scores) if all_cibil_scores else "N/A"
        cibil_max = max(all_cibil_scores) if all_cibil_scores else "N/A"
        ticket_min = min(all_max_tickets) if all_max_tickets else "N/A"
        ticket_max = max(all_max_tickets) if all_max_tickets else "N/A"

        # Get lender names
        lender_names = [l['lender_name'] for l in lender_details[:5]]  # Top 5

        prompt = f"""Given that pincode {pincode} is served by {lender_count} lenders for Business Loans
with CIBIL cutoffs ranging from {cibil_min}-{cibil_max} and max tickets from ₹{ticket_min:.0f}L-₹{ticket_max:.0f}L,
generate a one-paragraph market summary for a DSA prospecting in this area.

Top lenders: {', '.join(lender_names)}

Generate a concise 2-3 line summary that highlights:
1. Market coverage strength
2. CIBIL range acceptance (sub-prime vs prime)
3. Ticket size range

Keep it professional and actionable for DSAs."""

        try:
            response = await self.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a lending market analyst helping DSAs understand pincode-level lender coverage."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=200
            )

            summary = response.choices[0].message.content.strip()
            logger.info(f"Generated market summary for pincode {pincode}")
            return summary

        except Exception as e:
            logger.error(f"Failed to generate market summary: {str(e)}")
            return None

    async def generate_eligibility_clarity_summary(
        self,
        borrower_data: Dict[str, Any],
        passed_lenders: List[Dict[str, Any]],
        failed_lenders: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Generate AI-powered eligibility explanation (Fix 4: BRE Clarity).

        Args:
            borrower_data: Dict with borrower info (CIBIL, turnover, vintage, etc.)
            passed_lenders: List of lenders that passed
            failed_lenders: List of lenders that failed with rejection reasons

        Returns:
            Dict with overall_summary, top_improvements, and lender_explanations
        """
        if not self.llm_client:
            return None

        # Build prompt with borrower profile
        borrower_summary = (
            f"CIBIL: {borrower_data.get('cibil_score', 'N/A')}, "
            f"Turnover: ₹{borrower_data.get('annual_turnover', 'N/A')}L, "
            f"Vintage: {borrower_data.get('business_vintage_years', 'N/A')}y, "
            f"Entity: {borrower_data.get('entity_type', 'N/A')}, "
            f"Pincode: {borrower_data.get('pincode', 'N/A')}"
        )

        # Format passed lenders
        passed_str = "\n".join([
            f"- {l['lender_name']} (₹{l.get('expected_ticket_max', 'N/A')}L, {l.get('approval_probability', 'N/A')})"
            for l in passed_lenders[:5]  # Top 5
        ]) if passed_lenders else "None"

        # Format failed lenders with reasons
        failed_str = "\n".join([
            f"- {l['lender_name']}: {', '.join(l.get('failure_reasons', []))}"
            for l in failed_lenders[:5]  # Top 5
        ]) if failed_lenders else "None"

        prompt = f"""You are a lending advisor. Given these eligibility results for a borrower, generate:
1. A 2-line summary of their overall eligibility status
2. Top 3 actionable improvement suggestions ranked by impact
3. For each rejected lender, one sentence explaining why and what would change the outcome

Borrower: {borrower_summary}

Passed lenders ({len(passed_lenders)}):
{passed_str}

Failed lenders ({len(failed_lenders)}):
{failed_str}

Return as JSON:
{{
  "overall_summary": "2-line eligibility summary here",
  "top_improvements": ["improvement 1", "improvement 2", "improvement 3"],
  "lender_explanations": {{
    "Lender Name": "explanation why rejected and what needs to change"
  }}
}}"""

        try:
            response = await self.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a lending advisor helping DSAs understand eligibility results."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=500
            )

            # Parse JSON response
            import json
            content = response.choices[0].message.content.strip()
            # Remove markdown code blocks if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            result = json.loads(content)
            logger.info("Generated eligibility clarity summary")
            return result

        except Exception as e:
            logger.error(f"Failed to generate eligibility summary: {str(e)}")
            return None


# Singleton instance
llm_report_service = LLMReportService()


# Convenience function for pincode market summaries
async def generate_pincode_market_summary(pincode: str, lender_details: List[Dict[str, Any]]) -> Optional[str]:
    """Convenience wrapper for generating pincode market summaries."""
    return await llm_report_service.generate_pincode_market_summary(pincode, lender_details)


async def generate_eligibility_clarity_summary(
    borrower_data: Dict[str, Any],
    passed_lenders: List[Dict[str, Any]],
    failed_lenders: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Convenience wrapper for generating eligibility clarity summaries."""
    return await llm_report_service.generate_eligibility_clarity_summary(
        borrower_data, passed_lenders, failed_lenders
    )
