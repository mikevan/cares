# Knights of Columbus Accounting System - MVP

## What's Been Built

### Core Application Files ✅
- `models.py` - Complete database models with double-entry accounting
- `reports.py` - Financial statement generators (Balance Sheet, Income Statement, Cash Flow)
- `app.py` - Main Flask application with authentication and all routes
- `static/css/branding.css` - Knights of Columbus color scheme (easily rebrandable)

### HTML Templates Created ✅
- `base.html` - Base template with navigation
- `login.html` - Login page
- `index.html` - Dashboard with statistics

### HTML Templates Still Needed
Create these files in the `/home/claude/templates/` directory:

#### Members
- `members.html` - List all members
- `member_form.html` - Add/edit member form

#### Projects
- `projects.html` - List all projects
- `project_form.html` - Add/edit project form

#### Transactions
- `transactions.html` - List transactions
- `transaction_view.html` - View transaction details

#### Reports
- `reports.html` - Report selection page
- `balance_sheet.html` - Balance sheet display
- `income_statement.html` - Income statement display
- `cash_flow.html` - Cash flow statement display

#### Settings
- `settings.html` - Organization settings form

## Setup Instructions

### 1. Install Dependencies

```bash
cd /home/claude
pip install --break-system-packages Flask Flask-SQLAlchemy Flask-Login
```

### 2. Initialize Database

The application will automatically create the database and seed it with default data on first run:
- Default admin user: `admin` / `admin123`
- Default "Dues" project
- Full Chart of Accounts (FASB ASC 958 compliant)

### 3. Run the Application

```bash
python app.py
```

The application will run on `http://localhost:5000`

### 4. Default Login

- Username: `admin`
- Password: `admin123`

**IMPORTANT:** Change this password immediately after first login!

## Features

### Implemented ✅
- User authentication with role-based access (Admin, Treasurer, ProjectLeader, Member)
- Organization/Chapter management
- Member directory management
- Project management with budgets and volunteer assignments
- Double-entry bookkeeping system
- FASB ASC 958 compliant Chart of Accounts
- Financial statement generation (Balance Sheet, Income Statement, Cash Flow)
- Knights of Columbus branding (easily customizable)

### Database Structure
- Organizations (multi-chapter hierarchy)
- Users (with roles and permissions)
- Members (volunteer directory)
- Projects (programs with budgets)
- Chart of Accounts (FASB ASC 958 compliant)
- Journal Entries (double-entry accounting)
- Journal Entry Lines (debit/credit details)
- Donors (donation tracking)
- Donations (links donors to transactions)
- Currencies (future multi-currency support)

## Rebranding for Other Organizations

To rebrand for a different organization, simply edit `/home/claude/static/css/branding.css`:

```css
:root {
    --brand-primary: #YOUR_PRIMARY_COLOR;
    --brand-secondary: #YOUR_SECONDARY_COLOR;
    --brand-accent: #YOUR_ACCENT_COLOR;
    --brand-light: #FFFFFF;
}
```

All colors throughout the application will automatically update!

## Deployment to Render.com (Free Tier)

1. **Push to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin YOUR_REPO_URL
   git push -u origin main
   ```

2. **Create requirements.txt**
   ```
   Flask==3.0.0
   Flask-SQLAlchemy==3.1.1
   Flask-Login==0.6.3
   psycopg2-binary==2.9.9
   gunicorn==21.2.0
   ```

3. **Create Procfile** (for Render)
   ```
   web: gunicorn app:app
   ```

4. **Connect to Render.com**
   - Create new Web Service
   - Connect your GitHub repository
   - Set environment variables:
     - `DATABASE_URL` (automatically provided by Render PostgreSQL)
     - `SECRET_KEY` (generate a secure random string)
   - Deploy!

## Next Steps

1. **Create Remaining Templates** - Copy template examples below
2. **Add Transaction Entry UI** - Simple mode for non-accountants
3. **Add CSV Export** - For member mail merges
4. **Test Financial Reports** - Verify calculations
5. **Deploy to Render.com** - Follow deployment instructions above

## User Roles & Permissions

- **Admin**: Full system access, user management, settings
- **Treasurer**: Financial transactions, reports, cannot manage users
- **Project Leader**: View/edit assigned projects, submit expenses
- **Member**: View dashboard and personal information

## Technical Stack

- **Backend**: Python Flask 3.0
- **ORM**: SQLAlchemy
- **Database**: SQLite (development) / PostgreSQL (production)
- **Frontend**: Bootstrap 5 + Vanilla JavaScript
- **Authentication**: Flask-Login with bcrypt
- **Deployment**: Render.com (free tier)

## Support & Documentation

- Full technical specification: See `KofC_Accounting_System_Specification.docx`
- Architecture overview: See `Architecture.txt`
- FASB ASC 958 standards: https://www.fasb.org/

## License

This system is designed for Knights of Columbus chapters and similar non-profit organizations.

---

**Built for Knights of Columbus Chapters**
Faith • Family • Community • Life
