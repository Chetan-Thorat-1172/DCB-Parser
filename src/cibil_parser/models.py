"""
Pydantic models representing the structured output schema for a CIBIL Credit Report.

Every field is Optional to handle missing data gracefully.
All models are serializable to JSON / dict for downstream pipelines.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Report metadata
# ---------------------------------------------------------------------------
class ReportMetadata(BaseModel):
    """Top-level metadata about the credit report itself."""

    consumer_name: Optional[str] = Field(None, description="Consumer name from header")
    member_id: Optional[str] = Field(None, description="Member ID from header")
    member_reference_number: Optional[str] = Field(None, description="Member reference number")
    report_date: Optional[str] = Field(None, description="Date the report was generated")
    report_time: Optional[str] = Field(None, description="Time the report was generated")
    control_number: Optional[str] = Field(None, description="Control number")


# ---------------------------------------------------------------------------
# Consumer Information
# ---------------------------------------------------------------------------
class ConsumerInformation(BaseModel):
    """Personal details of the consumer."""

    name: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None


# ---------------------------------------------------------------------------
# CIBIL Score
# ---------------------------------------------------------------------------
class CibilScore(BaseModel):
    """CIBIL TransUnion credit score details."""

    score_name: Optional[str] = None
    score: Optional[int] = None
    scoring_factors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Identification
# ---------------------------------------------------------------------------
class Identification(BaseModel):
    """An identity document on the report."""

    identification_type: Optional[str] = None
    identification_number: Optional[str] = None
    issue_date: Optional[str] = None
    expiration_date: Optional[str] = None


# ---------------------------------------------------------------------------
# Telephone
# ---------------------------------------------------------------------------
class Telephone(BaseModel):
    """A telephone entry."""

    telephone_type: Optional[str] = None
    telephone_number: Optional[str] = None
    telephone_extension: Optional[str] = None


# ---------------------------------------------------------------------------
# Email Contact
# ---------------------------------------------------------------------------
class EmailContact(BaseModel):
    """An email address entry."""

    email_address: Optional[str] = None


# ---------------------------------------------------------------------------
# Address
# ---------------------------------------------------------------------------
class Address(BaseModel):
    """A reported address."""

    address: Optional[str] = None
    category: Optional[str] = None
    residence_code: Optional[str] = None
    date_reported: Optional[str] = None
    state_code: Optional[str] = None
    pin_code: Optional[str] = None


# ---------------------------------------------------------------------------
# Employment Information
# ---------------------------------------------------------------------------
class EmploymentInformation(BaseModel):
    """Employment record entry."""

    account: Optional[str] = None
    account_type: Optional[str] = None
    date_reported: Optional[str] = None
    occupation_code: Optional[str] = None
    income: Optional[str] = None
    net_gross_income_indicator: Optional[str] = None
    monthly_annual_income_indicator: Optional[str] = None


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
class AccountSummary(BaseModel):
    """Summary statistics for accounts."""

    account_type: Optional[str] = None
    total_accounts: Optional[int] = None
    high_credit_sanctioned_amount: Optional[int] = None
    current_balance: Optional[int] = None
    overdue_accounts: Optional[int] = None
    overdue_balance: Optional[int] = None
    zero_balance_accounts: Optional[int] = None
    recent_date_opened: Optional[str] = None
    oldest_date_opened: Optional[str] = None


class EnquirySummary(BaseModel):
    """Summary statistics for enquiries."""

    enquiry_purpose: Optional[str] = None
    total: Optional[int] = None
    past_30_days: Optional[int] = None
    past_12_months: Optional[int] = None
    past_24_months: Optional[int] = None
    recent: Optional[str] = None


class Summary(BaseModel):
    """Combined summary of accounts and enquiries."""

    account_summary: Optional[AccountSummary] = None
    enquiry_summary: Optional[EnquirySummary] = None


# ---------------------------------------------------------------------------
# Account (Credit Facility)
# ---------------------------------------------------------------------------
class DaysPaymentHistory(BaseModel):
    """A single month's DPD entry."""

    month_year: Optional[str] = None
    dpd_value: Optional[str] = None


class Account(BaseModel):
    """A single credit account / trade line."""

    member_name: Optional[str] = None
    account_number: Optional[str] = None
    account_type: Optional[str] = None
    ownership: Optional[str] = None

    # Dates
    opened_date: Optional[str] = None
    reported_and_certified: Optional[str] = None
    pmt_hist_start: Optional[str] = None
    pmt_hist_end: Optional[str] = None
    last_payment_date: Optional[str] = None

    # Amounts
    high_credit_amount: Optional[int] = None
    current_balance: Optional[int] = None
    emi: Optional[int] = None
    payment_frequency: Optional[str] = None
    repayment_tenure: Optional[int] = None
    amount_overdue: Optional[int] = None

    # Status
    account_closed_date: Optional[str] = None

    # Payment history (DPD)
    days_past_due: list[DaysPaymentHistory] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Enquiry
# ---------------------------------------------------------------------------
class Enquiry(BaseModel):
    """A single enquiry entry."""

    member: Optional[str] = None
    enquiry_date: Optional[str] = None
    enquiry_purpose: Optional[str] = None
    enquiry_amount: Optional[int] = None


# ---------------------------------------------------------------------------
# Top-level Credit Report
# ---------------------------------------------------------------------------
class CreditReport(BaseModel):
    """
    Root model representing a fully parsed CIBIL Credit Report.
    This is the final output of the parsing pipeline.
    """

    report_metadata: Optional[ReportMetadata] = None
    consumer_information: Optional[ConsumerInformation] = None
    cibil_score: Optional[CibilScore] = None
    identifications: list[Identification] = Field(default_factory=list)
    telephones: list[Telephone] = Field(default_factory=list)
    email_contacts: list[EmailContact] = Field(default_factory=list)
    addresses: list[Address] = Field(default_factory=list)
    employment_information: list[EmploymentInformation] = Field(default_factory=list)
    summary: Optional[Summary] = None
    accounts: list[Account] = Field(default_factory=list)
    enquiries: list[Enquiry] = Field(default_factory=list)
