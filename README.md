# 🔐 KYC Document Intelligence System

> AI-powered KYC verification platform for Banks, NBFCs, and FinTechs using Google Gemini, Google Vision AI, Streamlit, and SQLite.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-App-red)
![SQLite](https://img.shields.io/badge/Database-SQLite-green)
![AI](https://img.shields.io/badge/AI-Google%20Gemini-orange)
![License](https://img.shields.io/badge/License-MIT-blue)

---

# 📌 Overview

KYC Document Intelligence System is an AI-powered document verification platform that automates the Know Your Customer (KYC) process for Banks, NBFCs, and FinTech companies.

The system extracts information from customer documents, verifies consistency across multiple documents, calculates risk scores, generates verification reports, and maintains RBI-compliant audit logs.

Instead of manually checking documents, organizations can verify customer identities within seconds using Artificial Intelligence.

---

# ✨ Features

## 📄 AI Document Extraction

- Aadhaar Card Verification
- PAN Card Verification
- Salary Slip Verification
- OCR-based Text Extraction
- Structured JSON Output

---

## 🤖 AI Models

The system automatically falls back through multiple AI models.

1. Gemini 2.5 Flash
2. Gemini 2.0 Flash
3. Gemini 1.5 Flash
4. Gemini 1.5 Pro
5. Google Cloud Vision API

If one model fails, the system automatically tries the next model.

---

## ⚡ Batch Verification

Supports simultaneous verification of up to **10 customer applications**.

Each batch contains:

- Aadhaar
- PAN
- Salary Slip

All documents are processed in parallel using multithreading.

---

## 📊 Risk Engine

The system automatically checks:

- Name Match
- Date of Birth Match
- Salary Slip Name Match

Risk Score Categories

| Score | Decision |
|--------|----------|
| 0–20 | ✅ APPROVE |
| 21–50 | ⚠ MANUAL REVIEW |
| 51+ | ❌ REJECT |

---

## 📑 PDF Report Generation

Automatically generates verification reports containing

- Extracted Details
- Risk Score
- Verification Status
- Issues Found
- Final Recommendation

---

## 🗄 RBI-Compliant Database

The project includes a secure SQLite database designed for compliance.

### Stores

- Verification Results
- Audit Logs
- Consent Records
- API Usage Logs
- Session Management
- Temporary Processing Data
- Batch Processing Logs

---

## 🔒 Security Features

- SHA-256 User Hashing
- Consent Management
- Audit Trail
- Session Management
- Duplicate Detection
- Verification History
- Data Retention
- Temporary Data Purging

---

# 🏗 Project Architecture

```
                User Uploads Documents
                        │
                        ▼
                 Streamlit Interface
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
    Aadhaar          PAN Card      Salary Slip
        │               │               │
        └───────────────┼───────────────┘
                        ▼
             Gemini AI Document Extraction
                        │
            (Automatic Model Fallback)
                        ▼
             Google Vision API (Fallback)
                        ▼
              Structured JSON Extraction
                        ▼
                  Risk Assessment
                        ▼
               PDF Report Generation
                        ▼
             SQLite Database Storage
                        ▼
                Audit & Compliance
```

---

# 🛠 Technology Stack

### Frontend

- Streamlit

### Backend

- Python

### AI Models

- Google Gemini API
- Google Vision API

### Database

- SQLite

### Reporting

- ReportLab

### Concurrency

- ThreadPoolExecutor

### OCR

- Gemini Vision
- Google Cloud Vision

---

# 📂 Project Structure

```
KYC-DOCUMENT-INTELLIGENCE-SYSTEM/

│
├── file3.py
├── database.py
├── requirements.txt
├── README.md
├── kyc_verification.db
├── extract_cache.pkl
├── vision_cache.pkl
│
├── reports/
│
├── uploads/
│
└── screenshots/
```

---

# ⚙ Installation

Clone the repository

```bash
git clone https://github.com/yourusername/KYC-DOCUMENT-INTELLIGENCE-SYSTEM.git
```

Move into the project

```bash
cd KYC-DOCUMENT-INTELLIGENCE-SYSTEM
```

Install dependencies

```bash
pip install -r requirements.txt
```

Run Streamlit

```bash
streamlit run file3.py
```

---

# 🔑 Environment Variables

Create a `.env` file

```text
GOOGLE_API_KEY=YOUR_GEMINI_API_KEY
KYC_ENCRYPTION_KEY=YOUR_SECRET_KEY
```

---

# 📷 Supported Documents

✅ Aadhaar Card

✅ PAN Card

✅ Salary Slip

More document types can easily be added.

---

# 📊 Database Tables

- audit_logs
- consent_records
- verification_results
- api_usage
- sessions
- temp_processing_data
- batch_processing_logs

---

# 📈 Future Enhancements

- Face Matching
- Liveness Detection
- Passport Verification
- Driving License Verification
- Bank Statement Analysis
- GST Verification
- OCR Accuracy Dashboard
- REST API
- Docker Deployment
- Kubernetes Support
- AWS Deployment
- Azure Deployment

---

# 🎯 Use Cases

- Banks
- NBFCs
- FinTech Companies
- Lending Platforms
- Insurance Companies
- Digital KYC Platforms
- Customer Onboarding
- Loan Verification

---

# 🚀 Advantages

- Faster Customer Onboarding
- Reduced Manual Verification
- Lower Operational Costs
- Higher Accuracy
- AI-powered Decision Making
- RBI Compliance Ready
- Secure Data Handling
- Batch Processing Support
- Automatic Report Generation

---

# 📸 Screenshots

Add screenshots inside the `screenshots/` folder.

Example

```
screenshots/
    home.png
    batch_verification.png
    report.png
    dashboard.png
```

---

# 🤝 Contributing

Contributions are welcome.

1. Fork the repository
2. Create a new branch
3. Commit your changes
4. Push the branch
5. Open a Pull Request

---

# 📄 License

This project is licensed under the MIT License.

---

# 👨‍💻 Author

**Kshitij**

AI/ML Engineer | FinTech Builder | AI for Banking & NBFCs

Building AI-powered solutions to automate KYC, lending, and document intelligence for financial institutions.

---

## ⭐ If you found this project useful, please give it a Star on GitHub!
