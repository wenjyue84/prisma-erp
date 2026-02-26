# **Product Requirements Document: LHDN-Compliant Payroll e-Invoicing Integration for ERPNext**

## **1\. Executive Summary and Strategic Architectural Vision**

This comprehensive Product Requirements Document establishes the exhaustive architectural, functional, and technical specifications required to develop a seamless, highly resilient integration between the Frappe Human Resources Management System (HRMS) module, operating within ERPNext versions 15 and 16, and the Malaysian Inland Revenue Board's (LHDN \- Lembaga Hasil Dalam Negeri) MyInvois system. The fundamental objective of this engineering endeavor is to achieve strict, verifiable, and automated compliance with the Malaysian e-Invoicing mandate specifically concerning complex payroll, commission, and reimbursement workflows for the Year of Assessment 2026 and beyond.1

The integration strategy mandates the utilization of the existing open-source myinvois extension developed by ERPGulf. This foundational application is currently engineered to handle the cryptographic and network-layer complexities of the LHDN integration, including Continuous Transaction Control transmission, Application Programming Interface authentication, digital certificate management, and Extensible Markup Language digital signature requirements.5 The primary scope of this document is to define the intricate bridge logic, data transformation pipelines, and asynchronous event handlers required to accurately translate native HRMS and Payroll events—specifically focusing on the Salary Slip, Payroll Entry, and Expense Claim Document Types—into LHDN-compliant Universal Business Language (UBL 2.1) JavaScript Object Notation payloads without compromising the performance of the core Enterprise Resource Planning system.3

Accuracy, data integrity, and statutory compliance are prioritized above execution speed or minimal code footprint. The architectural design explicitly mandates the use of asynchronous background processing via the Frappe framework's queuing system to ensure that bulk payroll processing—which may involve hundreds or thousands of concurrent document submissions—does not induce Hypertext Transfer Protocol timeouts, exhaust Gunicorn worker threads, or create database transaction deadlocks when communicating with external LHDN endpoints.9 Furthermore, the system must elegantly handle the profound regulatory nuances of the Malaysian tax code, distinguishing mathematically and logically between standard exempted employment income, mandatory self-billed e-Invoices for independent contractors, and the specific treatment of employee out-of-pocket reimbursements.12 This document serves as the definitive blueprint for the autonomous coding agent to execute the integration according to established software engineering best practices within the Frappe ecosystem.

## **2\. Comprehensive LHDN Regulatory Framework and Compliance Context**

To design a structurally sound and legally accurate integration, the development architecture must be grounded in a profound comprehension of the statutory boundaries of the LHDN e-Invoice mandate as it applies exclusively to human resources, payroll operations, and vendor management. The MyInvois system operates on a Continuous Transaction Control model, a framework that requires near real-time validation, transmission, and storage of transactional data by the tax authority prior to the finalization of the commercial or financial event.15 This represents a paradigm shift from traditional post-audit tax compliance, necessitating deep hooks into the ERPNext document lifecycle.

### **2.1 Implementation Timelines, Turnover Thresholds, and Statutory Grace Periods**

The phased rollout of the Malaysian e-Invoicing mandate is fundamentally dictated by a corporate entity's historical annual turnover, specifically referencing the Year of Assessment 2022\. However, recent regulatory pronouncements and budgetary updates have introduced crucial interim relaxation periods that fundamentally alter the optimal deployment strategy and software architecture required for compliance. The integration must be flexible enough to operate within both the relaxed grace period framework and the strict real-time enforcement framework.

| Implementation Phase | Targeted Taxpayers (Based on YA 2022 Annual Turnover) | Original Mandatory Implementation Date | Expiration of Grace Period and Penalty Relief |
| :---- | :---- | :---- | :---- |
| Phase 1 | Exceeding RM100 million | 1 August 2024 | 31 January 2025 3 |
| Phase 2 | Exceeding RM25 million and up to RM100 million | 1 January 2025 | 30 June 2025 3 |
| Phase 3 | Exceeding RM5 million and up to RM25 million | 1 July 2025 | 31 December 2025 3 |
| Phase 4 | Exceeding RM1 million and up to RM5 million | 1 January 2026 | 31 December 2026 (Extended) 3 |
| Exempt | Up to RM1 million | Permanently Exempted | Not Applicable (Voluntary adoption welcomed) 3 |
| New Entities | Commencing operations between 2023–2025 with turnover \> RM1 million | 1 July 2026 | Dependent on operational commencement 2 |

The architecture must explicitly account for the extension of the Phase 4 grace period to December 31, 2026\. This extension allows businesses within this revenue bracket to utilize consolidated e-Invoices for all transactions, including self-billed circumstances, without facing punitive measures or strict real-time reporting requirements.4 Consequently, the development must support dual operational modes: a consolidated monthly batch submission mechanism utilized during the grace period, and a transactional, real-time submission mechanism triggered upon document finalization for strict enforcement post-grace period. Furthermore, the system must recognize that from January 1, 2026, individual e-invoices are strictly mandatory for any single transaction exceeding RM10,000 across all industries, immediately nullifying the consolidation allowance for that specific high-value transaction.3

### **2.2 Navigating HRMS Applicability: Strict Exemptions Versus Mandatory Transmissions**

A pervasive point of failure in poorly designed Enterprise Resource Planning integrations is the indiscriminate and automated transmission of all financial records to the tax authority. This approach violates the specific boundaries of the mandate, wastes API bandwidth, and generates invalid tax records. The LHDN specifically exempts certain human resource payments while strictly mandating others, requiring the ERPNext integration to possess highly selective filtering logic prior to payload generation.

#### **2.2.1 Exempted Transactions: Standard Employment Income**

Under Section 1.6 of the Inland Revenue Board of Malaysia e-Invoice Guidelines, standard employment income is explicitly exempt from the e-Invoice mechanism.12 The ERPNext integration must programmatically evaluate the nature of the payee and explicitly filter out standard Salary Slip records generated for regular employees operating under a standard contract of service.

Standard salaries, performance bonuses, fixed allowances, and statutory deductions processed through the standard payroll cycle for personnel under a contract of service are exempt, meaning no e-Invoice, including self-billed variations, is required to be submitted to the MyInvois portal.13 Similarly, disbursements for pensions and alimony payments, should they be managed through the corporate financial system, are categorically exempted from transmission.13 Furthermore, deductions made directly via payroll for Zakat contributions are exempt from the e-Invoice requirements, requiring the system to bypass these specific line items entirely during any data aggregation processes.13 The integration must inherently trust the native HRMS records as sufficient proof of expense for these categories without external validation.

#### **2.2.2 Mandated Transmissions: The Self-Billed e-Invoice Framework**

The complexity of the integration significantly increases when the payee is not a standard employee under a contract of service, or when the payment relates to specific commercial activities defined by the Inland Revenue Board. In these scenarios, the payer, which is the employer or corporate entity operating ERPNext, must assume the statutory role of the supplier and generate a self-billed e-Invoice.12 This constitutes a fundamental inversion of the standard invoicing data model.

Payments rendered to independent contractors, consultants, and freelancers who provide services but are not conducting a registered business entity capable of issuing their own compliant e-Invoices mandate the generation of a self-billed e-Invoice by the employer.12 A critical area of enforcement revolves around Agents, Dealers, and Distributors. Commission payments, performance incentives, and any form of financial remuneration paid to these entities, whether monetary or non-monetary such as incentives in kind, strictly require the generation and submission of self-billed e-Invoices.14 The system must be capable of issuing these on a net basis, calculated as the gross commission amount minus any associated reversals or clawbacks, ensuring the submitted data matches the actual financial disbursement.15

Additionally, if the entity providing the service or labor is a foreign worker or a non-resident supplier who does not possess a valid Malaysian Tax Identification Number, the Malaysian employer is legally obligated to issue a self-billed e-Invoice to document the expense. In this specific programmatic edge case, the system must automatically inject the designated general Tax Identification Number provided by the authorities for foreign entities to ensure the payload passes the API validation layer.15

#### **2.2.3 Nuances of Employee Reimbursements and Disbursements**

The programmatic treatment of out-of-pocket expenses, typically managed via the ERPNext Expense Claim Document Type, requires sophisticated logic to remain compliant without creating duplicate tax records.14 The Inland Revenue Board acknowledges the practical difficulties of forcing all commercial vendors to issue invoices directly in the name of the employer when an employee is traveling or making incidental purchases.

A major regulatory concession allows that if an employee pays for a legitimate business expense, such as accommodation, mileage, toll fees, or telecommunications, the employer is permitted to utilize the e-Invoice issued in the employee's personal name as valid proof of expense for corporate tax deduction purposes.12 From an architectural standpoint, this means the ERPNext integration does not need to generate a new self-billed e-Invoice for these specific claims. Instead, the Expense Claim module must be enhanced to record, store, and validate the existing e-Invoice's Unique Identifier and Quick Response code URL provided by the employee, maintaining the audit trail without triggering a new transmission.

For expenses incurred overseas by an employee acting on behalf of the employer, the regulatory burden is further reduced. Neither the employer nor the employee is required to issue a self-billed e-Invoice; the original foreign receipt or invoice serves as legally valid proof of expense.12 The integration must provide a mechanism to flag these specific international expense claims to bypass the e-Invoice generation queue entirely. Conversely, if the company pays a domestic supplier directly for an employee benefit or perquisite without an overarching corporate policy dictating the transaction, the company must actively request the compliant e-Invoice from that supplier, treating it as a standard procurement event rather than a payroll event.24

## **3\. Statutory Payroll Deductions Configuration and Mathematical Integrity**

While the myinvois extension handles the network transmission, the foundational ERPNext Human Resources Management System must calculate 2026 payroll figures with absolute mathematical precision. The LHDN MyInvois Application Programming Interface conducts rigorous structural and mathematical validation on all submitted payloads.8 Specifically, the sum of the Total Excluding Tax and the Total Tax Amount must perfectly equal the Total Including Tax at both the line item and header levels. Any rounding discrepancies, floating-point arithmetic errors, or misconfigurations introduced by the ERPNext payroll engine during the calculation of statutory deductions will result in an immediate API rejection with a Status 3 Invalid response.8

The development implementation must ensure that the Salary Structure and Salary Component configurations are meticulously aligned with the updated 2026 Malaysian statutory rates prior to any e-Invoice payload generation.22

| Statutory Deduction Category | 2026 Implementation Parameters and Mathematical Constraints |
| :---- | :---- |
| **Social Security Organization (SOCSO / PERKESO)** | The monthly wage ceiling is strictly capped at RM6,000. Employee contribution rates are calculated at approximately 0.5%, while Employer contribution rates are approximately 1.75%, dictated by specific tabular brackets rather than raw percentages.28 |
| **Employment Insurance System (EIS / SIP)** | The monthly wage ceiling remains capped at RM6,000. The Employee rate is exactly 0.2%, and the Employer rate is exactly 0.2%, resulting in a total combined contribution of 0.4% based on the tabular brackets.28 |
| **Employees Provident Fund (EPF / KWSP) \- Citizens and Permanent Residents** | The standard Employee contribution rate is 11%. The Employer contribution rate is dependent on the base salary: 13% for salaries up to and including RM5,000, and 12% for salaries exceeding RM5,000.31 |
| **Employees Provident Fund (EPF / KWSP) \- Foreign Workers** | Effective incrementally through October 2025 and into 2026, the Employee contribution rate is set at 2%, and the Employer contribution rate is matching at 2%.32 |
| **Monthly Tax Deduction (MTD / PCB)** | Must strictly adhere to the LHDN Progressive Tax Rates utilizing the official Computerised Calculation Method. The payroll engine must accommodate new 2026 tax reliefs, including the permanent RM3,000 relief for registered childcare fees and expanded exemptions for specific medical treatments and vaccinations.33 |

The integration must guarantee that when a self-billed e-Invoice is generated for a commission agent or contractor who may be subject to a flat withholding tax or specific deductions, the gross amounts, deduction amounts, and net payable amounts are serialized into the JSON payload without losing precision. The specification for the Computerised Calculation Method for 2026 dictates exact treatment of floating-point numbers, and the ERPNext Python backend must utilize the decimal library for all monetary aggregations prior to JSON serialization to prevent IEEE 754 precision errors from causing API rejections.34

## **4\. System Architecture and Middleware Component Design**

To ensure system stability, maintainability, and upgrade compatibility, the solution requires a highly modular, non-invasive architecture leveraging the Frappe framework's sophisticated event hook system. The integration will not modify the core files of ERPNext, the HRMS module, or the myinvois\_erpgulf repository directly. Instead, a dedicated custom application, designated conceptually as lhdn\_payroll\_integration, will act as the intelligent middleware orchestrating the data flow between the HR system and the transmission engine.

### **4.1 The Frappe and ERPNext HRMS Ecosystem**

The native HRMS module dictates the fundamental flow of financial and personnel data.22 The integration must deeply understand and interact with several core Document Types. The Employee master document serves as the repository for all demographic and tax-related information, including Tax Identification Numbers, identification types, and industrial classification codes.22 The Salary Component Document Type defines whether a financial movement is an earning or a deduction, and must be enhanced to carry specific LHDN classification routing instructions.22

The Salary Slip is the primary transactional document, generated individually per employee for a specific payroll period, containing the aggregated financial data required for the e-Invoice payload.22 The Expense Claim Document Type handles reimbursements and out-of-pocket expenses, requiring its own specific workflow to handle the unique regulatory concessions surrounding employee-provided receipts.22 Finally, the Payroll Entry serves as the batch processing mechanism, meaning the integration must be capable of handling high-volume, concurrent document submissions when a Payroll Entry is finalized and hundreds of associated Salary Slips are submitted simultaneously.22

### **4.2 The ERPGulf MyInvois Extension Infrastructure**

The myinvois application developed by ERPGulf is designed to manage the heavy lifting of LHDN compliance and network communication.5 It provides the necessary Document Types to store authentication tokens, manage environment variables, and handle digital certificate configurations required by the Inland Revenue Board.6

Crucially, it exposes Python functions designed to serialize structured data into the required XML or JSON formats, mathematically sign the payload using the configured digital certificates to ensure non-repudiation, and transmit the resulting secure payload to the official api.myinvois.hasil.gov.my endpoints.6 It also includes native mechanisms to parse the response, tracking LHDN document statuses such as Submitted, Valid, or Invalid, and storing the returned validation Quick Response codes.6 The custom middleware must construct the raw data dictionaries and pass them to these exposed functions rather than attempting to rebuild the cryptographic and network layers from scratch.

### **4.3 Integration Workflow Architecture and the Observer Pattern**

The core execution architecture relies entirely on the Observer Pattern implemented via Frappe's hooks.py configuration file. This ensures the integration logic executes silently in the background whenever specific business events occur within the HRMS.

The workflow initiates when a human resources manager or an automated process submits a Salary Slip or approves an Expense Claim.22 The on\_submit document event hook intercepts this database transaction immediately after the core ERPNext validation logic completes.38 The middleware script then evaluates the document to determine if it falls within the scope of the e-Invoice mandate. If the associated employee's employment type is categorized as standard employment income, the script terminates execution silently, honoring the regulatory exemption.13 If the type dictates a self-billed requirement, such as a commission agent or independent contractor, the script proceeds.12

To prevent blocking the primary Web Server Gateway Interface worker, and to decisively decouple the database commit from the inherently latent external API call, the script pushes the payload generation and transmission logic into Redis using the frappe.enqueue function.10 The background worker then maps the Frappe Object-Relational Mapping objects to the required Universal Business Language JSON schema.3 The worker calls the myinvois\_erpgulf API to submit the document, awaits the response, and finally updates the original Salary Slip or Expense Claim with the official LHDN Document Unique Identifier, the validation status, and the Quick Response code URL for future reference and audit compliance.6

## **5\. Functional Requirements and Master Data Enhancements**

To support dynamic payload generation without relying on fragile, hardcoded values within the Python scripts, the system must extend the standard database schema. The coding agent is required to write robust setup scripts, executed via after\_install and after\_migrate hooks, to inject specific Custom Fields into standard ERPNext Document Types using the Custom Field API.

### **5.1 Schema Modifications for the Employee Document Type**

The Employee master record must be enhanced to store critical tax metadata required by the LHDN MyInvois Application Programming Interface.

* custom\_lhdn\_tin: A Data field designated for the Tax Identification Number. Validation logic must enforce the strict formatting rules, such as requiring the "IG" prefix for individual taxpayers (e.g., IG123456789) and ensuring the string adheres to the 14-character limit. For non-individual entities operating as contractors, the TIN must end with a zero.25  
* custom\_id\_type: A Select field allowing the human resources team to specify the identification document type, containing options strictly mapped to LHDN requirements, such as NRIC, Passport, or Business Registration Number.  
* custom\_id\_value: A Data field storing the actual alphanumeric value of the selected identification type.  
* custom\_msic\_code: A Link field connecting to a newly created LHDN MSIC Code Document Type. While standard human resource provision is categorized under code 78300, independent agents must be mapped to the Malaysia Standard Industrial Classification code applicable to their specific trade or commercial activity to ensure accurate economic reporting.41  
* custom\_requires\_self\_billed\_invoice: A Checkbox field serving as the master boolean switch. The on\_submit hook evaluates this specific field to bypass standard employees efficiently, preventing unnecessary processing overhead for the vast majority of standard payroll records.

### **5.2 Schema Modifications for Financial Document Types**

The configuration of financial components and the resulting transactional documents must be extended to support data categorization and response tracking.

* **Salary Component Document Type:** Must include custom\_lhdn\_classification\_code, a Select field populated with the 45 official LHDN classification codes. This allows the finance team to dictate exactly how specific earnings or deductions are categorized in the final e-Invoice payload.20  
* **Salary Slip and Expense Claim Document Types:** These transactional records must include several Read-Only fields to store the API response data. custom\_lhdn\_uuid will store the unique identifier returned by the Inland Revenue Board. custom\_lhdn\_status will be a Select field mirroring the API statuses: Pending, Submitted, Valid, and Invalid.25 custom\_lhdn\_qr\_code will be an HTML or Image field designed to render the validation Quick Response code required for visual representation compliance.6 Finally, custom\_error\_log will be a Text Editor field utilized to capture and display raw JSON validation errors if a Status 3 Invalid response is returned by the authorities, aiding in rapid troubleshooting.

## **6\. LHDN Classification and Industrial Code Mapping**

The integration must accurately categorize every transaction line item to comply with the Inland Revenue Board's stringent reporting requirements. The coding agent must configure the system architecture to dynamically map specific payroll events to the following critical LHDN Classification Codes, ensuring precise economic categorization 20:

| LHDN Classification Code | Official Description | Architectural Application within ERPNext HRMS and Payroll |
| :---- | :---- | :---- |
| **027** | Reimbursement | Specifically mapped to Expense Claim line items where the employer financially reimburses an employee for valid out-of-pocket business expenses incurred on behalf of the company.44 |
| **032** | Foreign income | Applied to self-billed e-Invoices generated for services rendered by non-resident foreign contractors or entities operating without a local Malaysian Tax Identification Number.44 |
| **037** | Self-billed \- Monetary payment to agents, dealers or distributors | The primary code utilized for Salary Slip components representing monetary commission payouts, performance bonuses, or direct financial incentives distributed to independent agents and distributors.20 |
| **044** | Vouchers, gift cards, loyalty points, etc. | Utilized for categorizing non-monetary benefits, perquisites, or allowances provided to personnel in lieu of direct monetary compensation.44 |
| **045** | Self-billed \- Non-monetary payment to agents, dealers or distributors | Specifically used for incentives paid in kind, such as physical goods or travel rewards, provided to agents and distributors.20 |
| **004** | Consolidated e-Invoice | The critical code used during the regulatory grace period (applicable up to December 31, 2026\) for the generation of batched, month-end submissions aggregating multiple self-billed transactions into a single compliant payload.14 |

## **7\. Universal Business Language (UBL 2.1) JSON Payload Construction**

The LHDN MyInvois system accepts and validates payloads strictly based on the Universal Business Language (UBL 2.1) international standard.3 A fundamental conceptual requirement for the coding agent is managing the data inversion inherent in self-billed e-Invoices. When generating a self-billed e-Invoice from an ERPNext Salary Slip, the payer—which is the Employer operating the ERP system—assumes the statutory role of the Buyer. Conversely, the payee—the Independent Contractor or Agent—assumes the statutory role of the Supplier.12

The middleware must construct a deeply nested Python dictionary that strictly adheres to the schema required by the myinvois\_erpgulf integration, mapping the Frappe variables to the UBL structure.8

### **7.1 Core Header and Document Metadata Mapping**

The root of the JSON payload establishes the document's identity and basic parameters.

* \_eInvoiceVersion: Must be dynamically configured to "1.0" or "1.1" depending on the current Software Development Kit version enforced by the LHDN environment being targeted.6  
* \_eInvoiceTypeCode: Typically "01" for a standard Invoice, but the script must utilize the specific code mandated for Self-Billed Invoices as defined in the latest SDK documentation.8  
* \_eInvoiceCode: Directly mapped to doc.name, representing the unique Salary Slip or Expense Claim ID generated by ERPNext, ensuring traceability between the two systems.8  
* \_eInvoiceDateTime: Mapped to Frappe's native frappe.utils.now\_datetime() function, formatted strictly to the UTC ISO 8601 standard required by the API.  
* InvoiceCurrencyCode: Mapped from doc.currency (e.g., "MYR"). Crucially, if the currency is not Malaysian Ringgit, the CurrencyExchangeRate element becomes mathematically mandatory and must be fetched from the ERPNext currency exchange records.8

### **7.2 Supplier Information Mapping (The Payee / Contractor)**

In the inverted self-billing model, the individual receiving the funds is documented as the supplier.

* SupplierName: Mapped to doc.employee\_name or the designated full name on the contractor record.  
* SupplierTIN: Mapped from the newly created employee.custom\_lhdn\_tin. If the individual is a foreign entity lacking a registered TIN, the script must inject the official general TIN EI00000000010 to satisfy validation.15  
* SupplierRegistrationNumber: Mapped from employee.custom\_id\_value. In specific edge cases where the supplier only provides a TIN and possesses no other valid identification number, the script should input "000000000000" into this field as mandated by LHDN guidelines.21  
* SupplierAddress: Mapped to the Employee's linked primary Address document in ERPNext. The payload must include specific administrative breakdowns, mapping the CityName, StateCode (utilizing the official LHDN two-digit codes, e.g., "14" for Kuala Lumpur), and the ISO 3166-1 alpha-3 CountryCode (e.g., "MYS").8  
* SupplierMSICCode: Mapped from employee.custom\_msic\_code. While defaulting to "00000" is technically permitted if the information is genuinely unavailable, it is highly discouraged for compliance reasons.14

### **7.3 Buyer Information Mapping (The Payer / Employer)**

The corporate entity operating the ERPNext instance is documented as the buyer.

* BuyerName: Mapped to the Company document's name field.  
* BuyerTIN: Mapped to the company's officially registered Tax Identification Number.  
* BuyerRegistrationNumber: Mapped to the company's Business Registration Number.  
* BuyerAddress: Mapped comprehensively to the company's primary registered address, following the same strict State Code and Country Code formatting rules as the supplier address.

### **7.4 Invoice Line Items and Taxation Aggregation**

The script must programmatically iterate over the doc.earnings and doc.deductions child tables within the active Salary Slip.

* Classification: Mapped dynamically from the salary\_component.custom\_lhdn\_classification\_code field configured by the finance team.  
* Description: Mapped directly to the salary\_component.name or a concatenated string providing sufficient context for the tax authorities.  
* UnitPrice: Mapped to the absolute value of the component's amount.  
* TaxType: Generally defaulted to "E" (Tax Exempt) for standard human resource and payroll payments, unless the specific classification of the contractor's service subjects it to specific sales or service taxes under Malaysian law.8  
* Subtotal: The gross mathematical amount of the specific line item prior to any aggregate deductions.

## **8\. Data Sanitization and Strict Validation Rules**

The LHDN Application Programming Interface enforces aggressive data sanitization rules that were significantly updated in the December 2025 Software Development Kit release.46 The coding agent must implement these exact validations natively within Frappe using Python string manipulation techniques prior to payload submission to drastically minimize costly API rejections.

* **Date Formatting Strictness:** All date fields transmitted in the JSON payload must strictly and unequivocally follow the YYYY-MM-DD format. Legacy submissions containing strings such as "N/A" or empty strings where legitimate dates are expected by the schema will trigger an immediate and unrecoverable validation failure.46  
* **Bank Account Truncation:** The supplier's bank account number string, utilized heavily in self-billing scenarios to document where the payroll funds were deposited, must be verified to not exceed 150 characters.46  
* **Document Identification Length:** The core Frappe document name, which serves as the e-Invoice Code/Number (e.g., HR-SAL-2026-0001), must not exceed a maximum length of 50 characters.46 If the ERPNext naming series is configured to produce longer strings, the middleware must implement a deterministic hashing or truncation algorithm to comply.  
* **Taxpayer Identification Number Verification:** The system must run a regex verification ensuring individual TINs begin with IG. Non-individual TINs must be checked to ensure they end with the digit 0 (e.g., C1234567890), stripping or appending zeros programmatically if the raw database entry is malformed.25

## **9\. Implementation Patterns and Asynchronous Background Processing**

Directly executing synchronous Hypertext Transfer Protocol requests during an on\_submit database event hook is a severe anti-pattern in Frappe development. Doing so will cause the database transaction to hang open while waiting for the LHDN server to respond, inevitably leading to system-wide deadlocks and WSGI worker timeouts if the external API experiences latency.10

### **9.1 Background Job Queue Architecture**

The integration must leverage Frappe's native enqueue functionality to push the complex payload generation and transmission logic into the Redis-backed background worker queues.

Python

import frappe

def enqueue\_salary\_slip\_submission(doc, method):  
    \# Retrieve the associated employee record to check compliance requirements  
    employee \= frappe.get\_doc("Employee", doc.employee)  
      
    \# Crucial compliance filter: Standard employment income is statutorily exempt  
    if not employee.custom\_requires\_self\_billed\_invoice:  
        return 

    \# Enqueue the background job to prevent blocking the primary web worker  
    frappe.enqueue(  
        'lhdn\_payroll\_integration.services.submit\_to\_lhdn',  
        queue='short',  
        timeout=300,  
        is\_async=True,  
        \# Mandatory: Ensure the Salary Slip is fully committed to the MariaDB instance   
        \# before the background worker attempts to fetch and process it.  
        enqueue\_after\_commit=True,   
        docname=doc.name,  
        doctype=doc.doctype  
    )

Setting the enqueue\_after\_commit=True parameter is absolutely critical to the system's stability. If the background job worker attempts to fetch the Salary Slip document from the database before the primary transaction concludes and commits, it will encounter a DoesNotExistError, causing the submission to fail silently.10

### **9.2 LHDN API Status Handling, Polling, and Error Parsing**

The MyInvois API operates asynchronously and returns specific integer statuses that must be handled by the middleware: 1 (Submitted), 2 (Valid), and 3 (Invalid).25

* **Status 1 (Submitted):** The document has successfully passed initial structural and schema checks but requires deep backend verification by the tax authority's systems. The Frappe middleware must implement a polling mechanism, such as an hourly scheduled job defined in hooks.py, to query the LHDN endpoints for the finalized status of all documents currently marked as Pending.  
* **Status 3 (Invalid):** The payload has failed deep business logic validation, such as mathematical inconsistencies, invalid MSIC codes, or unregistered Tax Identification Numbers. The background job must programmatically parse the JSON error response, extract the specific human-readable error messages, and append them directly to the custom\_error\_log field on the corresponding Frappe document.25 The document's internal status must be updated to "Invalid", alerting the finance team to correct the data and re-trigger the submission.  
* **Network Resilience and Retry Mechanisms:** Network timeouts, Domain Name System resolution failures, or HTTP 500 Internal Server Errors originating from the LHDN portal must be gracefully caught using standard Python try/except blocks. Failed transmission attempts caused by external network issues should be automatically rescheduled in the Redis queue utilizing an exponential backoff algorithm to prevent overwhelming the external servers while ensuring eventual consistency.10

### **9.3 Document Cancellation Workflows**

If a human resources manager or payroll administrator attempts to cancel a previously submitted and validated Salary Slip within ERPNext, the custom on\_cancel event hook must intercept the action.38 The system will enqueue a specialized job to call the specific LHDN cancellation API endpoint, passing the stored custom\_lhdn\_uuid.

It is vital to note that the Inland Revenue Board restricts straightforward cancellations to a highly specific timeframe, typically within 72 hours post-validation. If the cancellation action occurs outside this strictly enforced window, the system must block the native Frappe cancellation and instead instruct the user to generate a compliant Credit Note e-Invoice to reverse the transaction financially, ensuring the immutable ledger principle of the continuous transaction control model is maintained.13

## **10\. Advanced Edge Cases: Consolidated e-Invoicing and Version 16 Bugs**

### **10.1 Consolidated e-Invoice Generation Logic**

Given that the Inland Revenue Board has officially allowed the use of consolidated self-billed e-Invoices during the extended relaxation period applicable up to December 31, 2026, the system architecture must provide an automated alternative to real-time, per-document submission to reduce API overhead and simplify compliance for mid-tier enterprises.3

* **Execution Mechanism:** A scheduled cron job, configured as monthly within the custom application's hooks.py, must execute automatically within the first seven days following the month-end.14  
* **Aggregation Logic:** The script queries the database for all submitted Salary Slip and Expense Claim documents that are explicitly flagged for self-billing and possess a custom\_lhdn\_status of "Pending" for the previous chronological month.  
* **Consolidated Payload Format:** The script aggregates the financial totals and generates a single, massive JSON payload utilizing the specific Classification Code 004 (Consolidated e-Invoice).20 In this specific consolidation scenario, the buyer's contact number field can be safely defaulted to the string "NA" as permitted by the specific consolidation rules within the SDK.8 The line items within the consolidated payload must reference the original ERPNext document IDs to maintain a rigorous internal audit trail, linking the massive tax document back to the individual payroll records.6

### **10.2 Circumventing the ERPNext Version 16 Aggregation Bug**

The coding agent must be explicitly aware of a critical, documented bug existing within the ERPNext version 16 beta architecture that directly impacts payroll calculations. Specifically, a frappe.exceptions.PermissionError stating Invalid field format for SELECT: sum(net\_pay) as net\_sum is thrown by the new query builder when the compute\_year\_to\_date function attempts to aggregate Year-To-Date amounts during the generation of Salary Slips.49

This core framework bug causes the Salary Slip validation sequence to abort prematurely, blocking the entire payroll run. Consequently, the custom payload generation script must not rely on the native HRMS Year-To-Date fields or aggregation functions when constructing the mathematical totals required for the LHDN submission. Instead, the middleware must independently calculate the correct line item totals directly from the current document's localized state, traversing the child tables manually in Python to ensure data integrity and avoid triggering the underlying framework exception during the critical e-Invoice generation phase.

## **11\. Security, Data Privacy Configurations, and Sandbox Testing**

Payroll data constitutes highly sensitive Personally Identifiable Information. Transmitting HRMS data outside the localized, secured ERP environment to a government portal introduces significant risk vectors that must be actively mitigated through careful software design.

### **11.1 Security Protocols and Data Sanitization**

* **Transport Layer Security:** The middleware must ensure that all external network interactions with the api.myinvois.hasil.gov.my endpoints strictly utilize TLS 1.2 or higher cryptographic protocols. The official SDK notes that SSL certificates undergo periodic renewal (for example, a renewal scheduled for February 8, 2026). Therefore, the Frappe server must rely on updated operating system root trust stores rather than implementing rigid certificate pinning, which would cause catastrophic transmission failures upon LHDN certificate rotation.46  
* **Payload Sanitization:** The generated JSON payload must strictly contain only the minimum necessary fields legally required by the LHDN schema. Internal human resources remarks, sensitive employee performance metrics, or non-taxable internal alphanumeric identifiers must be aggressively stripped or sanitized from the Description fields before serialization occurs.  
* **Role-Based Access Control:** Access to view the sensitive custom\_lhdn\_uuid, the generated validation QR codes, or the administrative ability to manually trigger a re-submission of a failed document should be strictly restricted to users possessing the "HR Manager" and "System Manager" roles, utilizing Frappe's native, highly granular permissions framework.22

### **11.2 Pre-Production Sandbox Testing Strategy**

Prior to deploying the integration to the production MyInvois environment and transmitting live financial data, rigorous automated and manual testing must occur utilizing the LHDN pre-production sandbox.

* **Environment Configuration:** The coding agent must implement site configuration variables utilizing frappe.conf.get() to allow system administrators to seamlessly toggle the transmission endpoints between the Sandbox URL (preprod-api.myinvois.hasil.gov.my) and the Production URL (api.myinvois.hasil.gov.my) without modifying the underlying Python codebase.25  
* **Mandatory Testing Scenarios:** The following test cases must pass without error during Quality Assurance:  
  1. Submit a standard employee Salary Slip. (Expected Result: The script identifies the exemption, terminates gracefully, and no payload is generated or transmitted).  
  2. Submit an Independent Contractor Salary Slip. (Expected Result: The self-billed payload is accurately generated, transmitted asynchronously, Status 2 Valid is returned, and the QR code is successfully attached to the ERPNext document).  
  3. Submit a Salary Slip containing intentionally malformed TIN formatting. (Expected Result: The LHDN sandbox rejects the payload with Status 3, and the Frappe middleware successfully parses the error and updates the custom\_error\_log field).  
  4. Simulate a severe network timeout during the asynchronous submission process. (Expected Result: The background job fails gracefully, does not crash the server, and remains safely in the RQ queue for a scheduled retry utilizing exponential backoff).  
  5. Execute the end-of-month consolidated script. (Expected Result: All unsubmitted, eligible records are successfully merged into a single mathematically sound 004 coded payload and transmitted).

By adhering strictly to these exhaustive architectural, mathematical, and functional mandates, the resulting Frappe application will provide a highly robust, legally compliant, and performant bridge between ERPNext's advanced human resources module and the rigorous continuous transaction control requirements dictated by the Malaysian tax authority.

#### **Works cited**

1. e-Invoice Implementation Timeline | Lembaga Hasil Dalam Negeri Malaysia, accessed on February 26, 2026, [https://www.hasil.gov.my/en/e-invoice/implementation-of-e-invoicing-in-malaysia/e-invoice-implementation-timeline](https://www.hasil.gov.my/en/e-invoice/implementation-of-e-invoicing-in-malaysia/e-invoice-implementation-timeline)  
2. Malaysia | E-invoicing compliance | Thomson Reuters \- Pagero, accessed on February 26, 2026, [https://www.pagero.com/compliance/regulatory-updates/malaysia](https://www.pagero.com/compliance/regulatory-updates/malaysia)  
3. e-Invoicing in Malaysia: Guidelines, Requirements and Exemption 2026 \- ClearTax, accessed on February 26, 2026, [https://www.cleartax.com/my/en/e-invoicing-malaysia](https://www.cleartax.com/my/en/e-invoicing-malaysia)  
4. 6 Major Malaysia Tax Announcements 2026 | Tax Updates 2026 & Malaysia eInvoice Guide \- JomeInvoice, accessed on February 26, 2026, [https://jomeinvoice.my/major-tax-updates-malaysia-2026/](https://jomeinvoice.my/major-tax-updates-malaysia-2026/)  
5. \*\*We've released Malaysian E-Invoicing APP for ERPNext – MyInvois. \- ERPGulf, accessed on February 26, 2026, [https://cloud.erpgulf.com/blog/blogs/malaysia](https://cloud.erpgulf.com/blog/blogs/malaysia)  
6. ERPGulf/myinvois: E-Invoicing for Malaysia for ERPNext \- GitHub, accessed on February 26, 2026, [https://github.com/ERPGulf/myinvois](https://github.com/ERPGulf/myinvois)  
7. Malaysia Compliance | Frappe Cloud Marketplace, accessed on February 26, 2026, [https://cloud.frappe.io/marketplace/apps/myinvois\_erpgulf](https://cloud.frappe.io/marketplace/apps/myinvois_erpgulf)  
8. Invoice v1.0, accessed on February 26, 2026, [https://sdk.myinvois.hasil.gov.my/documents/invoice-v1-0/](https://sdk.myinvois.hasil.gov.my/documents/invoice-v1-0/)  
9. Payroll entry customization \- ERPNext \- Frappe Forum, accessed on February 26, 2026, [https://discuss.frappe.io/t/payroll-entry-customization/118845](https://discuss.frappe.io/t/payroll-entry-customization/118845)  
10. Background Jobs \- Documentation for Frappe Apps, accessed on February 26, 2026, [https://docs.frappe.io/framework/user/en/api/background\_jobs](https://docs.frappe.io/framework/user/en/api/background_jobs)  
11. Running Background Jobs \- Documentation for Frappe Apps, accessed on February 26, 2026, [https://docs.frappe.io/framework/user/en/guides/app-development/running-background-jobs](https://docs.frappe.io/framework/user/en/guides/app-development/running-background-jobs)  
12. The Inland Revenue Board's new and updated guidelines on e-Invoices | EY Malaysia, accessed on February 26, 2026, [https://www.ey.com/en\_my/technical/tax-alerts/the-inland-revenue-boards-new-and-updated-guidelines-on-e-invoices](https://www.ey.com/en_my/technical/tax-alerts/the-inland-revenue-boards-new-and-updated-guidelines-on-e-invoices)  
13. E-INVOICE GUIDELINE INLAND REVENUE BOARD OF MALAYSIA TABLE OF CONTENT, accessed on February 26, 2026, [https://www.hasil.gov.my/media/fzagbaj2/irbm-e-invoice-guideline.pdf](https://www.hasil.gov.my/media/fzagbaj2/irbm-e-invoice-guideline.pdf)  
14. E-INVOICE SPECIFIC GUIDELINE INLAND REVENUE BOARD OF MALAYSIA TABLE OF CONTENTS, accessed on February 26, 2026, [https://www.hasil.gov.my/media/uwwehxwq/irbm-e-invoice-specific-guideline.pdf](https://www.hasil.gov.my/media/uwwehxwq/irbm-e-invoice-specific-guideline.pdf)  
15. IMPLEMENTATION OF E-INVOICE IN MALAYSIA FREQUENTLY ASKED QUESTIONS (FAQs) PART 1, accessed on February 26, 2026, [https://www.hasil.gov.my/media/0xqitc2t/lhdnm-e-invoice-general-faqs.pdf](https://www.hasil.gov.my/media/0xqitc2t/lhdnm-e-invoice-general-faqs.pdf)  
16. e-Invoice | Lembaga Hasil Dalam Negeri Malaysia, accessed on February 26, 2026, [https://www.hasil.gov.my/en/e-invoice/](https://www.hasil.gov.my/en/e-invoice/)  
17. Updated e-Invoice Specific Guideline and General FAQs: 5 January 2026 | Grant Thornton, accessed on February 26, 2026, [https://www.grantthornton.com.my/insights/Tax/Tax-Alert-6-January-2026/](https://www.grantthornton.com.my/insights/Tax/Tax-Alert-6-January-2026/)  
18. LHDN e-Invoice Update \[January 2026\]: e-Invoice Implementation Timeline, Penalties, Businesses Compliance in Malaysia | JomeInvoice, accessed on February 26, 2026, [https://jomeinvoice.my/lhdn-e-invoice-implementation-update-2026/](https://jomeinvoice.my/lhdn-e-invoice-implementation-update-2026/)  
19. Latest E-Invoice Implementation Timeline | Crowe Malaysia PLT, accessed on February 26, 2026, [https://www.crowe.com/my/news/latest-e-invoice-implementation-timeline](https://www.crowe.com/my/news/latest-e-invoice-implementation-timeline)  
20. E-Invoice Classification Codes: A Key Component in Tax Reporting and Compliance, accessed on February 26, 2026, [https://biztrak.com/e-invoice-classification-codes/](https://biztrak.com/e-invoice-classification-codes/)  
21. Self-Billed e-Invoice Malaysia: Requirements, Process and Examples \- ClearTax, accessed on February 26, 2026, [https://www.cleartax.com/my/en/self-billed-e-invoice-malaysia](https://www.cleartax.com/my/en/self-billed-e-invoice-malaysia)  
22. ERPNext v15 HR Module: Detailed Overview and Deep Dive \- ClefinCode, accessed on February 26, 2026, [https://clefincode.com/blog/global-digital-vibes/en/erpnext-v15-hr-module-detailed-overview-and-deep-dive](https://clefincode.com/blog/global-digital-vibes/en/erpnext-v15-hr-module-detailed-overview-and-deep-dive)  
23. E-INVOICE ILLUSTRATIVE GUIDE, accessed on February 26, 2026, [https://www.hasil.gov.my/media/iawfa2eu/e-invoice-illustrative-guide.pdf](https://www.hasil.gov.my/media/iawfa2eu/e-invoice-illustrative-guide.pdf)  
24. A Complete Guide to e-Invoice, Consolidated, and Self-Billed Issuance \- L & Co, accessed on February 26, 2026, [https://landco.my/information-sharing/einvoice-flow-chart/](https://landco.my/information-sharing/einvoice-flow-chart/)  
25. Frequently Asked Questions \- Software Development Kit (SDK) for Lembaga Hasil Dalam Negeri Malaysia (LHDNM) MyInvois System, accessed on February 26, 2026, [https://sdk.myinvois.hasil.gov.my/faq/](https://sdk.myinvois.hasil.gov.my/faq/)  
26. Mastering Payroll Processing in ERPNext: A Comprehensive Guide for Businesses | by Turqosoft Solutions Pvt. Ltd. | Medium, accessed on February 26, 2026, [https://medium.com/@turqosoft/mastering-payroll-processing-in-erpnext-a-comprehensive-guide-for-businesses-44afd1f803b4](https://medium.com/@turqosoft/mastering-payroll-processing-in-erpnext-a-comprehensive-guide-for-businesses-44afd1f803b4)  
27. Human Resource Setup \- Documentation for Frappe Apps, accessed on February 26, 2026, [https://docs.frappe.io/erpnext/v12/user/manual/en/human-resources/human-resource-setup](https://docs.frappe.io/erpnext/v12/user/manual/en/human-resources/human-resource-setup)  
28. SOCSO Table 2026 Malaysia | PERKESO \+ EIS Rates \- Salary Calculator, accessed on February 26, 2026, [https://malaysiasalarycalculator.com/socso-contribution-table/](https://malaysiasalarycalculator.com/socso-contribution-table/)  
29. Rate of Contribution \- Perkeso, accessed on February 26, 2026, [https://www.perkeso.gov.my/en/rate-of-contribution.html](https://www.perkeso.gov.my/en/rate-of-contribution.html)  
30. EIS Contribution Table 2026 Malaysia – Rates, Salary Ceiling and Calculation Guide, accessed on February 26, 2026, [https://www.ajobthing.com/resources/blog/eis-contribution-table-2026-malaysia-rates-salary-ceiling-and-calculation-guide](https://www.ajobthing.com/resources/blog/eis-contribution-table-2026-malaysia-rates-salary-ceiling-and-calculation-guide)  
31. PCB Calculator Malaysia 2026 | EPF, Payroll & Salary Calculator \- Info-Tech, accessed on February 26, 2026, [https://www.info-tech.com.my/pcb-calculator](https://www.info-tech.com.my/pcb-calculator)  
32. EPF, SOCSO, and EIS Employer Contributions in Malaysia (2026 Update) | Foundingbird, accessed on February 26, 2026, [https://foundingbird.com/my/blog/what-employers-should-know-about-epf-socso-and-eis/](https://foundingbird.com/my/blog/what-employers-should-know-about-epf-socso-and-eis/)  
33. PCB Calculation in Malaysia 2026: Employer Guide, accessed on February 26, 2026, [https://www.rockbell.com.my/pcb-calculation-for-employees-a-simple-guide-for-employers/](https://www.rockbell.com.my/pcb-calculation-for-employees-a-simple-guide-for-employers/)  
34. AMENDMENT TO: SPECIFICATION FOR MONTHLY TAX DEDUCTION (MTD) CALCULATIONS USING COMPUTERIZED CALCULATION FOR, accessed on February 26, 2026, [https://www.hasil.gov.my/media/arvlrzh5/spesifikasi-kaedah-pengiraan-berkomputer-pcb-2026.pdf](https://www.hasil.gov.my/media/arvlrzh5/spesifikasi-kaedah-pengiraan-berkomputer-pcb-2026.pdf)  
35. Malaysia: MTD Calculations Changes for 2026 \- Mercans, accessed on February 26, 2026, [https://mercans.com/resources/statutory-alerts/malaysia-mtd-calculations-changes-for-2026/](https://mercans.com/resources/statutory-alerts/malaysia-mtd-calculations-changes-for-2026/)  
36. MONTHLY TAX DEDUCTION (MTD) TESTING QUESTIONS USING COMPUTERISED CALCULATION METHOD 2026, accessed on February 26, 2026, [https://www.hasil.gov.my/media/kdspkhrf/mtd-testing-question-2026.pdf](https://www.hasil.gov.my/media/kdspkhrf/mtd-testing-question-2026.pdf)  
37. Employer (Payroll) \- Data Specification \- Lembaga Hasil Dalam Negeri Malaysia, accessed on February 26, 2026, [https://www.hasil.gov.my/en/employers/employer-payroll-data-specification/](https://www.hasil.gov.my/en/employers/employer-payroll-data-specification/)  
38. Need Help on Document Event Hooks for Standard DocTypes \- Frappe Forum, accessed on February 26, 2026, [https://discuss.frappe.io/t/need-help-on-document-event-hooks-for-standard-doctypes/98010](https://discuss.frappe.io/t/need-help-on-document-event-hooks-for-standard-doctypes/98010)  
39. hooks.py \- frappe/hrms \- GitHub, accessed on February 26, 2026, [https://github.com/frappe/hrms/blob/develop/hrms/hooks.py](https://github.com/frappe/hrms/blob/develop/hrms/hooks.py)  
40. How to add background job to queue from server script \- ERPNext \- Frappe Forum, accessed on February 26, 2026, [https://discuss.frappe.io/t/how-to-add-background-job-to-queue-from-server-script/85247](https://discuss.frappe.io/t/how-to-add-background-job-to-queue-from-server-script/85247)  
41. Understanding Malaysia Standard Industrial Classification (MSIC) Codes \- Taxilla, accessed on February 26, 2026, [https://www.taxilla.com/blog/malaysia-standard-industrial-classification-MSIC-codes](https://www.taxilla.com/blog/malaysia-standard-industrial-classification-MSIC-codes)  
42. new business codes \- The page is not found, accessed on February 26, 2026, [http://lampiran1.hasil.gov.my/pdf/pdfam/NewBusinessCodes\_MSIC2008\_2.pdf](http://lampiran1.hasil.gov.my/pdf/pdfam/NewBusinessCodes_MSIC2008_2.pdf)  
43. Malaysia Standard Industrial Classification (MSIC) Codes, accessed on February 26, 2026, [https://sdk.myinvois.hasil.gov.my/codes/msic-codes/](https://sdk.myinvois.hasil.gov.my/codes/msic-codes/)  
44. Classification Codes, accessed on February 26, 2026, [https://sdk.myinvois.hasil.gov.my/codes/classification-codes/](https://sdk.myinvois.hasil.gov.my/codes/classification-codes/)  
45. The 45 Types of Classification Codes for e-Invoice \- L\&CO \- L & Co, accessed on February 26, 2026, [https://landco.my/social/classification-code/](https://landco.my/social/classification-code/)  
46. SDK 1.0 Release, accessed on February 26, 2026, [https://sdk.myinvois.hasil.gov.my/sdk-1-0-release/](https://sdk.myinvois.hasil.gov.my/sdk-1-0-release/)  
47. Code Tables \- Software Development Kit (SDK) for Lembaga Hasil Dalam Negeri Malaysia (LHDNM) MyInvois System, accessed on February 26, 2026, [https://sdk.myinvois.hasil.gov.my/codes/](https://sdk.myinvois.hasil.gov.my/codes/)  
48. 26- "Mastering Background Jobs and Schedulers in ERPNext with Frappe" \- YouTube, accessed on February 26, 2026, [https://www.youtube.com/watch?v=6CEiMjlC54w](https://www.youtube.com/watch?v=6CEiMjlC54w)  
49. \[regression v16.0.0-beta.1\] Payroll Entry fails: “Invalid field format for SELECT: sum(net\_pay) as net\_sum” · Issue \#3769 · frappe/hrms \- GitHub, accessed on February 26, 2026, [https://github.com/frappe/hrms/issues/3769](https://github.com/frappe/hrms/issues/3769)  
50. Salary Slip Creation Error v15 \- bug \- Frappe Forum, accessed on February 26, 2026, [https://discuss.frappe.io/t/salary-slip-creation-error-v15/118358](https://discuss.frappe.io/t/salary-slip-creation-error-v15/118358)  
51. Multiple problems with Payroll \- ERPNext \- Frappe Forum, accessed on February 26, 2026, [https://discuss.frappe.io/t/multiple-problems-with-payroll/147931](https://discuss.frappe.io/t/multiple-problems-with-payroll/147931)