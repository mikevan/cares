# CARES - Community Accounting & Resource Engagement System

**Version 1.0 - Production Ready**

> Visible application name is configurable in `config.py` via the `APP_NAME` value.
> CARES supports organization-specific editions, including **REGALIA** for Knights of Columbus chapters.


![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)
![Flask 3.0](https://img.shields.io/badge/Flask-3.0-green.svg)

---

## 📖 Table of Contents

- [Overview](#-overview)
- [Value Proposition](#-value-proposition)
- [Current Features (v1.0)](#-current-features-v10)
- [Technical Stack](#-technical-stack)
- [Installation](#-installation)
- [User Roles & Permissions](#-user-roles--permissions)
- [Roadmap](#-roadmap)
- [Rebranding](#-rebranding-for-other-organizations)
- [Support](#-support--documentation)

---

## 🎯 Overview

The **CARES - Community Accounting & Resource Engagement System** is a comprehensive, FASB ASC 958-compliant accounting solution designed specifically for nonprofit organizations. Built by accountants for organizations run by volunteers, this system makes professional-grade financial management accessible to users with no accounting background while maintaining the rigor required for grant applications, Form 990 preparation, and audit compliance.


## 🧩 Editions

CARES supports **organization-specific editions** that apply tailored branding, defaults, and workflows while sharing the same compliant accounting core.

### REGALIA — A CARES Edition for Knights of Columbus

**REGALIA** is the Knights of Columbus edition of CARES.  
It includes Knights-specific terminology, branding, and chapter-oriented workflows, while preserving the same CARES accounting engine, reporting structure, and security model.

If you are using REGALIA, you are using CARES.


### Purpose

Traditional accounting software (QuickBooks, Xero, etc.) is designed for businesses, not nonprofits. These solutions:
- ❌ Don't support FASB ASC 958 (nonprofit accounting standards)
- ❌ Lack nonprofit-specific reports (Statement of Functional Expenses)
- ❌ Are too complex for volunteer treasurers
- ❌ Don't track projects, programs, and volunteers
- ❌ Cost $30-100/month with limited multi-user support

This system solves these problems with a **free, open-source, nonprofit-native accounting platform**.

---

## 💎 Value Proposition

### For Small Nonprofits (Annual Budget < $250K)
- ✅ **Free to deploy** - No monthly fees, runs on free hosting (Render.com)
- ✅ **Volunteer-friendly** - Simple mode requires zero accounting knowledge
- ✅ **Grant-ready** - Generate professional financial statements in seconds
- ✅ **IRS compliant** - FASB ASC 958 standards built-in
- ✅ **Multi-user** - Unlimited users with role-based permissions
- ✅ **Audit trail** - Every transaction tracked with user, date, and purpose

### For nonprofit chapters
- ✅ **Edition branding** - organization-specific colors and styling (e.g., REGALIA for Knights of Columbus)
- ✅ **Chapter-specific features** - Dues tracking, member management, project tracking
- ✅ **Multi-chapter ready** - Architecture supports state/district consolidation
- ✅ **Form 990 ready** - All data structured for easy tax filing

### For Professional Accountants
- ✅ **Double-entry bookkeeping** - Proper debits and credits
- ✅ **Full Chart of Accounts** - Customizable, hierarchical account structure
- ✅ **FASB ASC 958 compliant** - All four required financial statements
- ✅ **Audit-ready** - Complete transaction history and documentation
- ✅ **Flexible journal entries** - Full control for accountants when needed

### Cost Comparison

| Solution | Monthly Cost | Setup Cost | Annual Cost |
|----------|--------------|------------|-------------|
| QuickBooks Nonprofit | $40-100 | $0 | $480-1,200 |
| Aplos | $79-139 | $500 | $948-2,168 |
| **CARES (Self-Hosted)** | **$0-14** | **$0** | **$0-168** |

*CARES can run entirely free on Render.com's free tier, or $14/month for premium hosting*

---

## 🎉 Current Features (v1.0)

### Release: Version 1.0 (January 2026)
**Status:** ✅ Production Ready

---

### 🔐 **Authentication & User Management**

#### **Multi-User System with Role-Based Access**
- Four permission levels: Admin, Treasurer, Project Leader, Member
- Secure password hashing (bcrypt)
- Session management with Flask-Login
- Last login tracking
- User activation/deactivation

**Why it matters:** Allows multiple volunteers to access the system safely, each seeing only what they're authorized to see. A project leader can submit expenses without accessing sensitive financial data.

#### **User Management Interface**
- Create, edit, delete users
- Assign roles and permissions
- Password change functionality
- User profile management
- Activity tracking

**Admin tools:**
- Bulk user operations
- Password reset for users
- Role-based dashboard customization

---

### 👥 **Member Management**

#### **Volunteer & Member Directory**
Complete member database with:
- Full contact information (name, email, phone, address)
- Membership status (active/inactive)
- Join date tracking
- Custom member fields

**Use cases:**
- Track all chapter members
- Maintain accurate contact information
- Email list generation
- Attendance tracking preparation

#### **Member Import/Export**
- **CSV Import:** Bulk upload hundreds of members at once
- **CSV Export:** Download complete member database for mail merges
- **Template Generator:** Downloadable CSV template with examples
- **Validation:** Automatic duplicate detection and error reporting

**Real-world scenario:** During membership drive, import all new members from your Excel spreadsheet in one upload instead of entering them individually.

---

### 📊 **Project & Program Management**

#### **Project Tracking System**
Manage all organizational initiatives with:
- Project name and description
- Budget allocation per project
- Start and end dates
- Status tracking (Active, Completed, On Hold)
- Volunteer assignment
- Leader designation

**Examples of projects:**
- Annual Fish Fry
- Scholarship Fund
- Charity Raffle
- Community Service Programs
- Special Events

#### **Volunteer Assignment**
- Assign volunteers to multiple projects
- Designate project leaders
- Track participation across programs
- Export project rosters

**Why it matters:** Know who's working on what, track volunteer hours preparation, ensure proper coverage for events.

#### **Project Reporting**
- Budget vs. actual by project
- Project profitability analysis
- Volunteer participation reports
- Export project data to CSV

---

### 💰 **Double-Entry Accounting System**

#### **Two Entry Modes for Different Users**

**Simple Mode (For Volunteers):**
- Select transaction type from dropdown (Received Dues, Paid Rent, etc.)
- Enter amount and description
- System automatically creates proper journal entries
- No accounting knowledge required

**Accountant Mode (For Professionals):**
- Full journal entry interface
- Manual debit/credit entry
- Multiple line items per transaction
- Real-time balancing validation
- Complete audit trail

**Why both modes?** Your volunteer treasurer can post basic transactions all year, then your CPA can make complex adjusting entries at year-end.

#### **Transaction Features**
- Reference number tracking (check numbers, invoice numbers)
- Project allocation (every transaction tied to a program)
- Transaction voiding (with audit trail)
- Date flexibility (post transactions on any date)
- Memo fields for detailed notes

#### **Pre-Defined Transaction Types**
Common transactions built-in:
- ✅ Received Membership Dues
- ✅ Received Donation
- ✅ Received Grant
- ✅ Paid Vendor/Supplier
- ✅ Paid Rent
- ✅ Paid Utilities
- ✅ Paid Salary/Wages

---

### 📚 **Chart of Accounts Management**

#### **FASB ASC 958 Compliant Account Structure**
Pre-configured with 35+ accounts:

**Assets (1000-1999)**
- Cash accounts (checking, savings, petty cash)
- Accounts receivable
- Fixed assets (land, buildings, equipment)
- Accumulated depreciation

**Liabilities (2000-2999)**
- Accounts payable
- Credit card payable
- Accrued expenses
- Long-term debt

**Net Assets (3000-3999)**
- Without donor restrictions (unrestricted)
- With donor restrictions - time
- With donor restrictions - purpose

**Revenue (4000-4999)**
- Contributions (individual, corporate)
- Grants
- Membership dues
- Program fees
- Investment income

**Expenses (5000-5999)**
- Personnel (salaries, payroll taxes)
- Occupancy (rent, utilities)
- Supplies (office, program)
- Professional fees
- Fundraising costs

#### **Chart of Accounts Features**
- **Full CRUD:** Create, read, update, deactivate accounts
- **Hierarchical Structure:** Parent-child account relationships
- **Search & Filter:** Find accounts by number, name, or type
- **Account Types:** Asset, Liability, Net Asset, Revenue, Expense
- **Normal Balance:** Automatic debit/credit determination
- **Inactive Accounts:** Hide old accounts without deleting history

**Why it matters:** Customize your chart of accounts to match your organization's specific needs while maintaining compliance with accounting standards.

---

### 📈 **Financial Reporting (FASB ASC 958)**

#### **Statement of Financial Position (Balance Sheet)**
Shows what you own, what you owe, and your net assets as of any date:
- Total assets by category
- Total liabilities by category
- Net assets (restricted and unrestricted)
- Clean, professional format suitable for board meetings

**Use case:** Board wants to see financial position before approving a major purchase.

#### **Statement of Activities (Income Statement)**
Shows revenue and expenses for any period:
- All revenue sources summarized
- All expenses by category
- Net income (surplus or deficit)
- Year-over-year comparison ready

**Use case:** Generate annual income statement for Form 990 or grant applications.

#### **Statement of Cash Flows**
Tracks how cash moved in and out:
- Operating activities
- Investing activities
- Financing activities
- Beginning and ending cash balances

**Use case:** Understand why your bank balance changed even when income statement shows profit.

#### **Statement of Functional Expenses** ⭐
**Required by FASB ASC 958** - shows expenses by both nature and function:
- **Nature:** What you spent (salaries, rent, supplies)
- **Function:** Why you spent it (program, management, fundraising)
- Matrix format with totals
- Percentage breakdown

**Why critical:** This report is REQUIRED for Form 990 and many grant applications. Most small nonprofit software doesn't provide it.

#### **Report Features**
- **Any date range:** Custom period selection
- **PDF/Print ready:** Clean formatting for professional distribution
- **Board-ready:** Suitable for board packets without modification
- **Grant-ready:** Meets funder requirements

---

### 📤 **Data Import/Export**

#### **Member Import**
- CSV upload with validation
- Duplicate detection
- Error reporting with line numbers
- Bulk upload hundreds of members
- Downloadable template

#### **Export Functions**
- **Members:** Full contact database → CSV
- **Projects:** All project details → CSV
- **Transactions:** Detailed journal entries → CSV
  - Includes all debit/credit lines
  - Full account details
  - Project allocations

**Use cases:**
- Mail merge for newsletters
- Data backup
- External analysis in Excel
- Data migration to other systems

---

### ⚙️ **Organization Settings**

#### **Chapter Configuration**
- Organization name and type
- EIN (Tax ID) storage
- Full contact information
- Fiscal year start month (for accurate reporting)
- Multi-chapter hierarchy support (for future state/district rollup)

**Why fiscal year matters:** Many nonprofits use July 1 - June 30 instead of calendar year. System handles both.

---

### 🎨 **Professional Branding**

#### **REGALIA Official Colors (Knights of Columbus Edition)**
- Primary: Oxford Blue (#003595)
- Secondary: Gold (#FAA514)
- Accent: Red (#FE0000)
- Official color meanings documented

These colors apply to the **REGALIA** edition. CARES can be rebranded for any nonprofit by changing the branding CSS variables.

#### **Easily Rebrandable**
Change one CSS file to rebrand for any organization:
- Update color variables
- Replace logo
- Modify fonts
- Instant application-wide changes

**Perfect for:**
- State councils
- District chapters
- Other Catholic organizations
- Any nonprofit

---

### 🔒 **Security & Compliance**

#### **Built-In Security**
- Password hashing with bcrypt
- Session management
- Role-based access control
- SQL injection prevention
- CSRF protection
- Secure password requirements

#### **Audit Trail**
Every transaction tracks:
- Who created it
- When it was created
- What project it's for
- Full change history

#### **Data Integrity**
- Double-entry balancing enforced
- Foreign key constraints
- Transaction isolation
- Data validation on all inputs

---

## 🛠 Technical Stack

### Backend
- **Python 3.8+** - Modern, maintainable language
- **Flask 3.0** - Lightweight, flexible web framework
- **SQLAlchemy** - Powerful ORM with relationship management
- **Flask-Login** - Secure authentication
- **Werkzeug** - Password hashing and security

### Database
- **SQLite** - Development and small deployments
- **PostgreSQL** - Production deployments
- **Supports:** MySQL, MariaDB (with minor config changes)

### Frontend
- **Bootstrap 5** - Responsive, mobile-friendly UI
- **Vanilla JavaScript** - No framework overhead
- **Bootstrap Icons** - Comprehensive icon set
- **Chart.js ready** - Prepared for data visualization

### Architecture
- **Blueprint-based** - Modular, maintainable code structure
- **Jinja2 templates** - Clean separation of concerns
- **RESTful design** - Standard HTTP methods
- **MVC pattern** - Industry-standard architecture

### Deployment
- **Render.com** - Free tier available
- **Heroku** - Supported
- **AWS/Azure/GCP** - Compatible
- **Self-hosted** - Run on any Linux server

---

## 🚀 Installation

### Quick Start (5 minutes)

1. **Clone the repository**
```bash
git clone https://github.com/mikevan/cares.git
cd cares
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Run the application**
```bash
python app.py
```

4. **Access the system**
- Open browser to `http://localhost:5000`
- Login: `admin` / `admin123`
- **IMMEDIATELY change the default password!**

### First-Time Setup

The system automatically creates:
- ✅ Default admin user
- ✅ Default organization
- ✅ Complete Chart of Accounts (35+ accounts)
- ✅ Default "Dues" project
- ✅ Sample data structure

### Requirements
- Python 3.8 or higher
- 512MB RAM minimum
- 1GB disk space

See [DEPLOY.md](DEPLOY.md) for production deployment instructions.

---

## 👤 User Roles & Permissions

### 🔴 Admin (Full Access)
**Can do everything:**
- ✅ Manage users (create, edit, delete)
- ✅ Configure organization settings
- ✅ Post all transactions
- ✅ Generate all reports
- ✅ Manage Chart of Accounts
- ✅ Import/export data
- ✅ Void transactions
- ✅ Manage members and projects

**Typical users:** Grand Knight, Financial Secretary

---

### 🟡 Treasurer (Financial Operations)
**Can manage finances, but not users:**
- ✅ Post all transactions
- ✅ Generate all reports
- ✅ Manage Chart of Accounts
- ✅ Manage members and projects
- ✅ Import/export data
- ❌ Cannot create/delete users
- ❌ Cannot modify organization settings

**Typical users:** Treasurer, Deputy Treasurer

---

### 🔵 Project Leader (Limited Access)
**Can manage assigned projects:**
- ✅ View assigned projects
- ✅ View project budgets
- ✅ View member lists
- ✅ Submit expense requests (future feature)
- ❌ Cannot post transactions
- ❌ Cannot view other projects
- ❌ Cannot access financial reports

**Typical users:** Program Chairs, Committee Heads

---

### ⚪ Member (View Only)
**Can view basic information:**
- ✅ View dashboard
- ✅ View own profile
- ✅ View project rosters they're on
- ❌ No financial access
- ❌ Cannot modify any data

**Typical users:** General members, volunteers

---

## 🗺 Roadmap

### 🎨 **Phase 1.5: UI/UX Overhaul** (Next - Q1 2026)
**Status:** 🚧 Planned
**Timeline:** 4-6 weeks

#### Visual Design System
- Professional color palette refinement
- Typography system
- Consistent spacing and layout
- Component library

#### Dashboard Redesign
- Visual charts and graphs (Chart.js)
- Key metrics at-a-glance
- Quick action cards
- Alert notifications

#### Navigation Improvements
- Sidebar navigation with icons
- Breadcrumb trails
- Mobile-first responsive design
- Touch-friendly targets

#### Form Experience
- Inline validation
- Smart defaults and autocomplete
- Date pickers and masked inputs
- Loading states and progress indicators

#### Data Tables
- Sortable columns
- Advanced filtering
- Column visibility controls
- Export options (CSV, PDF)

#### Mobile Responsiveness
- Touch-optimized interface
- Swipe gestures
- Responsive tables
- Mobile navigation

**Estimated effort:** 25-30 hours

---

### 📱 **Phase 1.6: Mobile App (PWA)** (Q1 2026)
**Status:** 📋 Planned
**Timeline:** 6-8 weeks

#### Progressive Web App
- Installable on iOS and Android
- Offline functionality
- Push notifications
- Home screen icon

#### Mobile-Optimized Features
- Quick transaction entry
- Receipt photo capture
- Voice memos for descriptions
- GPS location tagging

#### Mobile Reports
- Simplified, scrollable reports
- Charts optimized for small screens
- Share via email/text

**Estimated effort:** 40-60 hours

---

### 💼 **Phase 2: Advanced Accounting** (Q2 2026)
**Status:** 📋 Planned

#### 1. Bank Reconciliation ⭐ CRITICAL
- Monthly reconciliation workflow
- Import bank statements (CSV/OFX)
- Automatic transaction matching
- Discrepancy identification
- Reconciliation reports

**Why critical:** Required for accurate financial reporting and audit readiness.

#### 2. Budget Management
- Annual budget creation
- Budget vs. actual reports
- Variance analysis
- Budget approval workflow
- Multi-year comparison

#### 3. Recurring Transactions
- Monthly rent, utilities
- Quarterly dues
- Annual insurance
- Template-based entry

#### 4. Advanced Journal Entries
- Journal entry templates
- Batch import
- Audit trail enhancements
- Entry reversal

#### 5. Donor Management
- Enhanced donor profiles
- Donation history
- Pledge tracking
- Thank you letters
- Tax receipts (IRS Form 1098)

#### 6. Grant Tracking
- Grant proposal tracking
- Grant budget vs. actual
- Deliverable tracking
- Funder-specific reports

**Estimated effort:** 40-50 hours

---

### 📊 **Phase 3: Reporting & Analytics** (Q3 2026)
**Status:** 📋 Planned

#### 1. Dashboard Enhancements
- Customizable widgets
- Real-time metrics
- Visual charts
- Year-over-year comparisons

#### 2. Custom Report Builder
- Drag-and-drop designer
- Custom field selection
- Save and schedule reports
- PDF/Excel export

#### 3. Financial Analysis
- Trend analysis
- Ratio analysis
- Cash flow projections
- What-if scenarios

#### 4. Form 990 Preparation ⭐
- Pre-populated Form 990
- Schedule mapping
- IRS validation
- Export to tax software

**Estimated effort:** 30-36 hours

---

### 🏢 **Phase 4: Multi-Chapter** (Q4 2026)
**Status:** 📋 Planned

#### 1. State/District Consolidation
- Roll-up reporting
- District dashboard
- Inter-chapter comparisons
- Consolidated statements

#### 2. Chapter Management
- Chapter directory
- Onboarding workflow
- Template sharing
- Best practices library

#### 3. Data Migration
- QuickBooks import
- Excel import with mapping
- Generic CSV import
- Data cleanup tools

**Estimated effort:** 30-37 hours

---

### 🔌 **Phase 5: Integrations** (2027)
**Status:** 💡 Conceptual

#### Payment Processing
- Stripe for online dues
- PayPal integration
- ACH payments
- Recurring billing

#### Email Notifications
- Transaction alerts
- Budget warnings
- Monthly statements
- Newsletter integration

#### Document Management
- Receipt storage (AWS S3)
- Invoice generation
- Document search

#### API Development
- RESTful API
- OAuth2 authentication
- Webhooks
- API documentation

**Estimated effort:** 34-42 hours

---

## 🎨 Rebranding for Other Organizations

### Quick Rebrand (5 minutes)

Edit `/static/css/branding.css`:

```css
:root {
    /* Change these colors */
    --brand-primary: #YOUR_PRIMARY_COLOR;
    --brand-secondary: #YOUR_SECONDARY_COLOR;
    --brand-accent: #YOUR_ACCENT_COLOR;
}
```

### Full Rebrand

1. **Colors:** Update CSS variables
2. **Logo:** Replace logo image
3. **Name:** Update organization name in settings
4. **Typography:** Modify font families if desired

**Perfect for:**
- Other Catholic organizations (Serra Club, St. Vincent de Paul)
- Fraternal organizations (Lions, Rotary, Elks)
- Community nonprofits
- Church parishes
- Youth organizations

---

## 📚 Support & Documentation

### Documentation
- **[DEPLOY.md](DEPLOY.md)** - Production deployment guide
- **[Technical Specification](docs/specification.md)** - Complete system architecture
- **FASB ASC 958 Standards** - https://www.fasb.org/

### Community Support
- **GitHub Issues** - Bug reports and feature requests
- **Discussions** - Community Q&A
- **Wiki** - User guides and tutorials

### Professional Services Available
- Custom development
- Implementation assistance
- Training workshops
- Ongoing support contracts

---

## 📄 License

ASF 2.0 (Apache Software Foundation License 2.0) - 

This project is licensed under the Apache License 2.0. It is a permissive license that allows for:
Commercial & Non-profit use: You can use, modify, and distribute the software for any purpose.
Patent Rights: Contributors provide an express grant of patent rights to users.
Modifications: You can distribute modified versions under different terms.
For more details, see the LICENSE file.

Copyright (c) 2026 CARES - Community Accounting & Resource Engagement System

---

## 🙏 Acknowledgments

Built with ❤️ for nonprofit organizations by accountants who understand your challenges.

**Special thanks to:**
- Knights of Columbus for inspiration and the REGALIA edition styling
- FASB for nonprofit accounting standards
- The Flask community for excellent documentation
- All volunteer treasurers keeping nonprofits running

---

## 🚀 Quick Links

- [Installation Guide](#-installation)
- [User Manual](docs/user-manual.md) *(coming soon)*
- [Administrator Guide](docs/admin-guide.md) *(coming soon)*
- [API Documentation](docs/api.md) *(future)*
- [Contributing Guidelines](CONTRIBUTING.md) *(coming soon)*

---

**Built for community-service nonprofits**

**REGALIA Edition:** Built for Knights of Columbus chapters

*Faith • Family • Community • Life*

---

## 📊 Project Stats

- **Lines of Code:** ~15,000
- **Database Tables:** 12
- **Routes:** 50+
- **Templates:** 30+
- **Test Coverage:** 85%+ *(planned)*
- **FASB Compliant:** ✅ Yes
- **Production Ready:** ✅ Yes

---

*Last Updated: January 2026*
*Version: 1.0.0*
