import os
import json
import re
from pathlib import Path
from html.parser import HTMLParser
import fitz  # PyMuPDF

class HTMLFilter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.ignore = False

    def handle_starttag(self, tag, attrs):
        if tag in ["script", "style", "noscript", "nav", "footer"]:
            self.ignore = True

    def handle_endtag(self, tag):
        if tag in ["script", "style", "noscript", "nav", "footer"]:
            self.ignore = False
        elif tag in ["p", "br", "div", "h1", "h2", "h3", "h4", "tr", "li"]:
            self.text.append("\n")

    def handle_data(self, data):
        if not self.ignore:
            self.text.append(data)

def clean_html_file(file_path: str, start_marker: str, end_marker: str = "") -> str:
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    parser = HTMLFilter()
    parser.feed(raw)
    raw_text = "".join(parser.text)
    
    # Locate main body
    start_idx = raw_text.find(start_marker)
    if start_idx != -1:
        raw_text = raw_text[start_idx:]
    
    if end_marker:
        end_idx = raw_text.find(end_marker)
        if end_idx != -1:
            raw_text = raw_text[:end_idx]

    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    return "\n\n".join(lines)

def create_pdf_from_text(title: str, document_code: str, text: str, output_path: str, lines_per_page: int = 42) -> int:
    """Renders text into a clean multi-page PDF using PyMuPDF with page headers and footers."""
    doc = fitz.open()
    paragraphs = text.split("\n\n")
    
    # Flatten paragraphs into wrapped lines
    all_lines = []
    for p in paragraphs:
        words = p.split(" ")
        current_line = []
        for w in words:
            if len(" ".join(current_line + [w])) > 80:
                all_lines.append(" ".join(current_line))
                current_line = [w]
            else:
                current_line.append(w)
        if current_line:
            all_lines.append(" ".join(current_line))
        all_lines.append("")  # Empty line between paragraphs

    # Group lines into pages
    page_chunks = []
    chunk = []
    for line in all_lines:
        chunk.append(line)
        if len(chunk) >= lines_per_page:
            page_chunks.append(chunk)
            chunk = []
    if chunk:
        page_chunks.append(chunk)

    total_pages = len(page_chunks)

    for page_idx, page_lines in enumerate(page_chunks, start=1):
        page = doc.new_page(width=595, height=842)  # Standard A4
        # Header
        page.insert_text(
            (50, 40),
            f"RESERVE BANK OF INDIA  |  {document_code}",
            fontsize=8,
            color=(0.3, 0.3, 0.3)
        )
        page.draw_line((50, 46), (545, 46), color=(0.7, 0.7, 0.7), width=0.5)

        # Body text
        y = 65
        for line in page_lines:
            if y > 800:
                break
            if line:
                page.insert_text((50, y), line, fontsize=9.5, color=(0.1, 0.1, 0.1))
            y += 16

        # Footer
        page.draw_line((50, 815), (545, 815), color=(0.7, 0.7, 0.7), width=0.5)
        page.insert_text(
            (50, 828),
            f"{title}  --  Page {page_idx} of {total_pages}",
            fontsize=8,
            color=(0.4, 0.4, 0.4)
        )

    doc.save(output_path)
    doc.close()
    return total_pages

def main():
    corpus_dir = Path("/Users/bot/Desktop/safestrata/data/corpus")
    corpus_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Parse Real RBI Documents
    kyc_raw = clean_html_file(
        "/Users/bot/.gemini/antigravity-ide/brain/990425bc-b9e7-42c0-b528-f7607dd05d31/.system_generated/steps/576/content.md",
        start_marker="Master Direction - Know Your Customer (KYC) Direction, 2016",
        end_marker="67        DBR.AML.BC.No.77/14.01.001/2014-15"
    )
    kyc_pdf = str(corpus_dir / "rbi_kyc_master_direction_2016.pdf")
    kyc_pages = create_pdf_from_text(
        title="RBI Master Direction - KYC Direction, 2016",
        document_code="RBI/DBR/2015-16/18 Master Direction DBR.AML.BC.No.81/14.01.001/2015-16",
        text=kyc_raw,
        output_path=kyc_pdf,
        lines_per_page=40
    )
    print(f"Generated KYC Master Direction PDF: {kyc_pages} pages")

    it_raw = clean_html_file(
        "/Users/bot/.gemini/antigravity-ide/brain/990425bc-b9e7-42c0-b528-f7607dd05d31/.system_generated/steps/586/content.md",
        start_marker="Master Direction on Information Technology Governance, Risk, Controls and Assurance Practices",
        end_marker="Annex\nRepealed Circulars"
    )
    it_pdf = str(corpus_dir / "rbi_it_governance_framework_2023.pdf")
    it_pages = create_pdf_from_text(
        title="RBI Master Direction - IT Governance & Risk Framework, 2023",
        document_code="RBI/2023-24/107 DoS.CO.CSITEG/SEC.7/31.01.015/2023-24",
        text=it_raw,
        output_path=it_pdf,
        lines_per_page=40
    )
    print(f"Generated IT Governance PDF: {it_pages} pages")

    digital_raw = clean_html_file(
        "/Users/bot/.gemini/antigravity-ide/brain/990425bc-b9e7-42c0-b528-f7607dd05d31/.system_generated/steps/592/content.md",
        start_marker="Guidelines on Digital Lending",
        end_marker="Other Publications"
    )
    digital_pdf = str(corpus_dir / "rbi_digital_lending_guidelines_2022.pdf")
    digital_pages = create_pdf_from_text(
        title="RBI Guidelines on Digital Lending, 2022",
        document_code="RBI/2022-23/111 DOR.CRE.REC.66/21.07.001/2022-23",
        text=digital_raw,
        output_path=digital_pdf,
        lines_per_page=38
    )
    print(f"Generated Digital Lending PDF: {digital_pages} pages")

    print(f"Total Real RBI PDF pages: {kyc_pages + it_pages + digital_pages}")

    # 2. Generate Synthetic Fixtures (clearly labelled)
    hr_text = """SYNTHETIC FIXTURE: SAFESTRATA INTERNAL HR LEAVE AND ATTENDANCE POLICY 2026
Document ID: POL-HR-2026-V2 | Effective Date: 2026-01-01 | Classification: Internal All Employees

1. PURPOSE AND APPLICABILITY
This policy sets forth the statutory and discretionary leave entitlements for all regular full-time employees, probationers, and contractual staff of SafeStrata Financial Services.

2. CASUAL LEAVE (CL)
All eligible employees are credited with twelve (12) working days of Casual Leave at the commencement of each calendar year. Casual leave is intended for unanticipated personal exigencies and short-duration absences. An employee may not avail more than three (3) consecutive days of Casual Leave without prior approval from their reporting manager. Casual leave cannot be combined with Privilege Leave or Sick Leave. Unavailed Casual Leave lapses on December 31 each year and cannot be encashed.

3. SICK AND MEDICAL LEAVE (SL)
Employees are entitled to ten (10) working days of Paid Sick Leave annually. Any medical absence extending beyond two (2) consecutive working days requires submission of a fitness certificate issued by a registered medical practitioner (MBBS or equivalent). Sick leave may be accumulated up to a maximum ceiling of thirty (30) days over an employee's tenure.

4. PRIVILEGE LEAVE (PL / EARNED LEAVE)
Privilege leave accrues at the rate of 1.25 days per completed month of active service, amounting to fifteen (15) days per calendar year. Privilege leave requires advance written application submitted at least fourteen (14) days prior to the proposed leave commencement. A maximum of thirty (30) days of Privilege Leave may be carried forward into the subsequent calendar year. Any excess accumulated days beyond thirty (30) shall automatically be encashed at the prevailing basic pay rate on March 31.

5. MATERNITY AND PATERNITY LEAVE
Female employees who have completed at least eighty (80) days of active service in the twelve months preceding expected delivery are eligible for twenty-six (26) weeks of fully paid Maternity Leave as mandated under the Maternity Benefit Amendment Act. Male employees are entitled to ten (10) consecutive working days of Paid Paternity Leave within six months of childbirth.

6. BEREAVEMENT LEAVE
SafeStrata provides five (5) consecutive working days of paid compassionate bereavement leave upon the demise of an immediate family member (spouse, child, parent, sibling, or parent-in-law).
"""
    hr_pdf = str(corpus_dir / "synthetic_hr_leave_policy.pdf")
    hr_pages = create_pdf_from_text(
        title="SafeStrata HR Leave Policy 2026 [SYNTHETIC FIXTURE]",
        document_code="SYNTHETIC-FIXTURE-HR-POL-2026",
        text=hr_text,
        output_path=hr_pdf,
        lines_per_page=35
    )

    it_sec_text = """SYNTHETIC FIXTURE: SAFESTRATA INFORMATION SECURITY AND ACCESS CONTROL POLICY 2026
Document ID: POL-SEC-2026-V4 | Effective Date: 2026-02-15 | Classification: Confidential (Analyst, Compliance Manager, Auditor)

1. ACCESS CONTROL AND LEAST PRIVILEGE PRINCIPLES
Access to SafeStrata core compliance repositories, vector stores, and administrative dashboards must strictly adhere to the Principle of Least Privilege and Role-Based Access Control (RBAC). Default access for newly created accounts is Viewer. Escalation to Analyst, Compliance Manager, or Auditor requires written business justification and approvals from the Chief Information Security Officer (CISO).

2. PASSWORD COMPLEXITY AND LIFECYCLE REQUIREMENTS
All SafeStrata domain and system passwords must satisfy the following baseline standards:
- Minimum length of fourteen (14) alphanumeric characters.
- Must contain at least one uppercase letter (A-Z), one lowercase letter (a-z), one numeric digit (0-9), and at least one approved special character (!@#$%^&*).
- Passwords must be rotated every ninety (90) calendar days.
- The previous twelve (12) passwords cannot be reused.
- Account lockout is triggered automatically upon five (5) consecutive failed authentication attempts. Lockout duration is thirty (30) minutes unless manually unlocked by an authorized administrator.

3. MULTI-FACTOR AUTHENTICATION (MFA)
Multi-Factor Authentication via hardware security keys (FIDO2/WebAuthn) or time-based one-time password (TOTP) apps is mandatory for all access. SMS-based OTP is prohibited for administrative and analyst access tiers due to SIM-swapping vulnerabilities.

4. SESSION TIMEOUT AND SCREEN LOCK
All workstations and browser sessions connected to SafeStrata services must enforce an idle timeout of fifteen (15) minutes. After fifteen minutes of inactivity, the session must automatically lock, requiring re-authentication.

5. REMOVABLE MEDIA AND USB RESTRICTION
The use of external USB storage media, flash drives, and portable hard drives is blocked by default across all endpoint devices via Endpoint Detection and Response (EDR) policy. Any temporary exception requires formal CISO sign-off and is logged in the compliance audit repository.
"""
    it_sec_pdf = str(corpus_dir / "synthetic_it_security_policy.pdf")
    it_sec_pages = create_pdf_from_text(
        title="SafeStrata IT Security Policy [SYNTHETIC FIXTURE]",
        document_code="SYNTHETIC-FIXTURE-IT-SEC-2026",
        text=it_sec_text,
        output_path=it_sec_pdf,
        lines_per_page=35
    )

    restricted_audit_text = """SYNTHETIC FIXTURE: SAFESTRATA CONFIDENTIAL INTERNAL AUDIT AML MEMORANDUM 2026
Document ID: AUD-CONF-AML-2026-09 | Effective Date: 2026-03-01 | Classification: STRICTLY CONFIDENTIAL (Compliance Manager Only)

WARNING: THIS DOCUMENT CONTAINS HIGHLY RESTRICTED COMPLIANCE AUDIT OBSERVATIONS. ACCESS IS RESTRICTED STRICTLY TO COMPLIANCE MANAGERS.

1. EXECUTIVE SUMMARY AND AUDIT CANARY
During the Q1 2026 comprehensive internal audit inspection, the Internal Audit Directorate reviewed anti-money laundering alert backlogs, automated transaction monitoring thresholds, and customer due diligence records.
Internal Audit Reference Canary: AUDIT_REF_AML_2026_XYZ99.

2. TRANSACTION MONITORING AND ESCALATION THRESHOLDS
The review observed that cash transactions exceeding Indian Rupees Ten Lakhs (INR 10,00,000) or its foreign currency equivalent must be aggregated over thirty days and submitted via Cash Transaction Reports (CTR) to FIU-IND by the 15th of the succeeding month. The automated surveillance rules currently flag any cross-border inward remittance exceeding INR 5,00,000 to high-risk jurisdictions.

3. HIGH-RISK CUSTOMER DUE DILIGENCE REMEDIATION
A total of forty-two customer accounts flagged under Politically Exposed Persons (PEP) categorization lacked updated source-of-wealth verifications. Compliance Managers must ensure remediation by April 30, 2026. Failure to close outstanding documentation will lead to systematic account operational freezing under Rule 9 of PMLA.
"""
    restricted_audit_pdf = str(corpus_dir / "synthetic_restricted_audit_memo.pdf")
    audit_pages = create_pdf_from_text(
        title="Confidential Internal Audit AML Memo [SYNTHETIC FIXTURE]",
        document_code="SYNTHETIC-FIXTURE-AUDIT-MEMO-2026",
        text=restricted_audit_text,
        output_path=restricted_audit_pdf,
        lines_per_page=35
    )

    pii_sample_text = """SYNTHETIC FIXTURE: ONBOARDING FORMS WITH SYNTHETIC TEST PII
Document ID: SYNTH-PII-SAMPLE-01 | Effective Date: 2026-01-10 | Classification: Synthetic Data Testing

NOTICE: ALL PERSONAL IDENTIFIABLE INFORMATION (PII) IN THIS DOCUMENT IS SYNTHETIC AND FABRICATED FOR VERIFYING REDACTION CONTROLS.

Customer Record 1 (Synthetic):
Full Legal Name: Rajesh Kumar Varma
PAN Number: ABCDE1234F
Aadhaar Number: 9999 4105 1238
Mobile Telephone: +91 9876543210
Tax Registration GSTIN: 27ABCDE1234F1Z5
Bank Branch IFSC: HDFC0001234
Account Status: Active verified savings account.

Customer Record 2 (Synthetic):
Full Legal Name: Priya Ananya Sharma
PAN Number: BKRPK9876Q
Aadhaar Number: 2345 6789 0123
Mobile Telephone: +91 9123456789
Bank Branch IFSC: SBIN0000456
Account Status: KYC document pending verification.
"""
    pii_pdf = str(corpus_dir / "synthetic_customer_data_with_pii.pdf")
    pii_pages = create_pdf_from_text(
        title="Synthetic Customer Records with Fake PII [SYNTHETIC FIXTURE]",
        document_code="SYNTHETIC-FIXTURE-PII-SAMPLE-2026",
        text=pii_sample_text,
        output_path=pii_pdf,
        lines_per_page=35
    )

    # 3. Create corpus_manifest.json
    manifest = [
        {
            "id": "doc-rbi-kyc-2016",
            "filename": "rbi_kyc_master_direction_2016.pdf",
            "title": "RBI Master Direction - Know Your Customer (KYC) Direction, 2016",
            "allowed_roles": ["viewer", "analyst", "compliance_manager", "auditor"],
            "is_synthetic": False,
            "effective_date": "2016-02-25",
            "page_count": kyc_pages,
            "description": "Official Reserve Bank of India Master Direction governing Customer Due Diligence, CIP, and KYC norms."
        },
        {
            "id": "doc-rbi-it-framework-2023",
            "filename": "rbi_it_governance_framework_2023.pdf",
            "title": "RBI Master Direction on Information Technology Governance, Risk, Controls and Assurance Practices, 2023",
            "allowed_roles": ["analyst", "compliance_manager", "auditor"],
            "is_synthetic": False,
            "effective_date": "2023-11-07",
            "page_count": it_pages,
            "description": "Official RBI Master Direction on IT governance, cyber resilience, and IS audit standards."
        },
        {
            "id": "doc-rbi-digital-lending-2022",
            "filename": "rbi_digital_lending_guidelines_2022.pdf",
            "title": "RBI Guidelines on Digital Lending, 2022",
            "allowed_roles": ["viewer", "analyst", "compliance_manager", "auditor"],
            "is_synthetic": False,
            "effective_date": "2022-09-02",
            "page_count": digital_pages,
            "description": "Official RBI regulatory framework on digital lending apps, loan disbursements, and consumer transparency."
        },
        {
            "id": "doc-synthetic-hr-leave",
            "filename": "synthetic_hr_leave_policy.pdf",
            "title": "SafeStrata Employee Leave & Attendance Policy 2026 [SYNTHETIC FIXTURE]",
            "allowed_roles": ["viewer", "analyst", "compliance_manager", "auditor"],
            "is_synthetic": True,
            "effective_date": "2026-01-01",
            "page_count": hr_pages,
            "description": "Clearly labelled synthetic fixture detailing annual casual, privilege, and sick leave guidelines for all employees."
        },
        {
            "id": "doc-synthetic-it-sec",
            "filename": "synthetic_it_security_policy.pdf",
            "title": "SafeStrata IT Security & Access Control Policy [SYNTHETIC FIXTURE]",
            "allowed_roles": ["analyst", "compliance_manager", "auditor"],
            "is_synthetic": True,
            "effective_date": "2026-02-15",
            "page_count": it_sec_pages,
            "description": "Clearly labelled synthetic fixture specifying password requirements, MFA, and USB restrictions for analysts and managers."
        },
        {
            "id": "doc-synthetic-audit-memo",
            "filename": "synthetic_restricted_audit_memo.pdf",
            "title": "SafeStrata Confidential Internal Audit AML Memo [SYNTHETIC FIXTURE]",
            "allowed_roles": ["compliance_manager"],
            "is_synthetic": True,
            "effective_date": "2026-03-01",
            "page_count": audit_pages,
            "description": "Clearly labelled restricted synthetic fixture containing canary AUDIT_REF_AML_2026_XYZ99 for Compliance Managers only."
        },
        {
            "id": "doc-synthetic-pii",
            "filename": "synthetic_customer_data_with_pii.pdf",
            "title": "SafeStrata Sample Customer Forms with Synthetic PII [SYNTHETIC FIXTURE]",
            "allowed_roles": ["compliance_manager"],
            "is_synthetic": True,
            "effective_date": "2026-01-10",
            "page_count": pii_pages,
            "description": "Clearly labelled synthetic customer records with fake India PAN, Aadhaar, GSTIN, and phone numbers to test ingestion redaction."
        }
    ]

    manifest_path = corpus_dir / "corpus_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Wrote corpus manifest with {len(manifest)} documents to {manifest_path}")

if __name__ == "__main__":
    main()
