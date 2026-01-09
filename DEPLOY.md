# CARES - Community Accounting & Resource Engagement System - Deployment Guide

**Version 1.0**

Complete deployment instructions for local development, testing, and production environments.

---

## 📋 Table of Contents

- [Local Development](#-local-development)
- [Production Deployment](#-production-deployment-rendercom)
- [Alternative Hosting](#-alternative-hosting-options)
- [Database Migration](#-database-migration)
- [Environment Configuration](#-environment-configuration)
- [Troubleshooting](#-troubleshooting)
- [Monitoring & Maintenance](#-monitoring--maintenance)

---

## 💻 Local Development

### System Requirements

**Minimum:**
- Python 3.8 or higher
- 512MB RAM
- 1GB disk space
- Modern web browser (Chrome, Firefox, Safari, Edge)

**Recommended:**
- Python 3.10+
- 2GB RAM
- 5GB disk space (for development + database)
- Git for version control

---

### Step 1: Clone Repository

```bash
# Clone the repository
git clone https://github.com/yourusername/kofc-accounting.git
cd kofc-accounting

# Or download ZIP and extract
```

---

### Step 2: Install Dependencies

#### Option A: Using pip (Standard)

```bash
pip install -r requirements.txt
```

#### Option B: Using pip with system packages (Linux)

```bash
pip install --break-system-packages -r requirements.txt
```

#### Option C: Using virtual environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Mac/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

### Step 3: Configure Environment Variables (Optional)

Create a `.env` file in the project root:

```bash
# .env file
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///kofc_accounting.db
FLASK_ENV=development
FLASK_DEBUG=True
```

**Generate a secure secret key:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

### Step 4: Initialize Database

The database is automatically created on first run with:
- ✅ Default admin user: `admin` / `admin123`
- ✅ Sample organization
- ✅ Complete Chart of Accounts (35+ accounts)
- ✅ Default "Dues" project

**No manual database setup required!**

---

### Step 5: Run the Application

```bash
python app.py
```

You should see:
```
 * Serving Flask app 'app'
 * Debug mode: on
 * Running on http://127.0.0.1:5000
 * Running on http://0.0.0.0:5000
```

---

### Step 6: Access the Application

1. Open browser to: **http://localhost:5000**
2. Login with default credentials:
   - **Username:** `admin`
   - **Password:** `admin123`
3. **IMMEDIATELY go to Settings → Users and change the admin password!**

---

### Development Tips

#### Auto-Reload on Code Changes
Flask's debug mode automatically reloads when you save files.

#### Database Reset (Fresh Start)
```bash
# Delete the database file
rm kofc_accounting.db

# Restart app.py - database will be recreated
python app.py
```

#### View Database Contents (SQLite)
```bash
# Install SQLite browser
# Windows: Download from https://sqlitebrowser.org/
# Mac: brew install --cask db-browser-for-sqlite
# Linux: sudo apt install sqlitebrowser

# Open database
sqlitebrowser kofc_accounting.db
```

#### Running on Different Port
```bash
# Edit app.py, change the last line:
app.run(debug=True, host='0.0.0.0', port=8080)
```

---

## 🚀 Production Deployment (Render.com)

**Why Render.com?**
- ✅ **Free tier available** - Perfect for small nonprofits
- ✅ **Automatic deployments** - Push to Git, auto-deploy
- ✅ **PostgreSQL included** - Free database tier
- ✅ **SSL certificates** - Automatic HTTPS
- ✅ **Simple setup** - No DevOps experience needed

**Free Tier Limits:**
- Web service: 750 hours/month (enough for one app)
- Database: 90 days, then $7/month
- 512MB RAM (sufficient for typical nonprofit)

---

### Prerequisites

1. **GitHub Account** - Store your code
2. **Render.com Account** - Free signup at https://render.com

---

### Step 1: Prepare Your Repository

#### 1.1 Initialize Git (if not already done)

```bash
git init
git add .
git commit -m "Initial commit - CARES - Community Accounting & Resource Engagement System v1.0"
```

#### 1.2 Create GitHub Repository

1. Go to https://github.com/new
2. Create repository (public or private)
3. Copy the repository URL

#### 1.3 Push to GitHub

```bash
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git branch -M main
git push -u origin main
```

---

### Step 2: Verify Required Files

Ensure these files exist in your repository:

#### `requirements.txt`
```
Flask==3.0.0
Flask-SQLAlchemy==3.1.1
Flask-Login==0.6.3
Werkzeug==3.0.1
psycopg2-binary==2.9.9
gunicorn==21.2.0
```

#### `Procfile` (create if missing)
```
web: gunicorn app:app
```

#### `.gitignore` (recommended)
```
*.pyc
__pycache__/
venv/
.env
*.db
.DS_Store
```

---

### Step 3: Create PostgreSQL Database on Render

1. Log into **https://dashboard.render.com**
2. Click **"New +"** → **"PostgreSQL"**
3. Configure database:
   - **Name:** `kofc-accounting-db`
   - **Database:** `kofc_accounting`
   - **User:** `kofc_user` (auto-generated)
   - **Region:** Choose closest to your users
   - **PostgreSQL Version:** 15 (or latest)
   - **Plan:** **Free** (or paid plan if needed)
4. Click **"Create Database"**
5. Wait for database to provision (~2-3 minutes)
6. **Copy the "Internal Database URL"** - you'll need this!

**Database URL Format:**
```
postgresql://kofc_user:password@hostname/kofc_accounting
```

---

### Step 4: Create Web Service on Render

1. Click **"New +"** → **"Web Service"**
2. Click **"Connect a repository"**
3. Select your GitHub repository
4. Configure web service:

**Basic Settings:**
   - **Name:** `kofc-accounting` (or your-chapter-name)
   - **Region:** Same as database
   - **Branch:** `main`
   - **Root Directory:** (leave blank)
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`

**Plan:**
   - **Instance Type:** Free (or paid for better performance)

5. Click **"Advanced"** to add environment variables

---

### Step 5: Configure Environment Variables

Add these environment variables in Render:

| Key | Value | Notes |
|-----|-------|-------|
| `DATABASE_URL` | *(paste Internal Database URL from Step 3)* | **CRITICAL** |
| `SECRET_KEY` | *(generate random string)* | **CRITICAL** |
| `FLASK_ENV` | `production` | Optional |

**Generate SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output and paste into Render.

**Important:** Use the **Internal Database URL**, not the External one!

---

### Step 6: Deploy

1. Click **"Create Web Service"**
2. Wait for deployment (~3-5 minutes)
3. Watch build logs for errors

**Successful deployment shows:**
```
==> Build successful 🎉
==> Deploying...
==> Your service is live 🎉
```

---

### Step 7: Access Your Live Application

1. Render provides a URL like: `https://kofc-accounting.onrender.com`
2. Open in browser
3. Login with: `admin` / `admin123`
4. **IMMEDIATELY:**
   - Go to **Settings → Users**
   - Create a new admin user with YOUR email
   - Change the default admin password
   - (Optional) Delete the default admin account

---

### Step 8: Configure Custom Domain (Optional)

#### Using Render's Free Domain
Your app is accessible at: `https://your-app-name.onrender.com`

#### Using Your Own Domain

1. Purchase domain (e.g., GoDaddy, Namecheap)
2. In Render dashboard → Settings → Custom Domains
3. Add your domain: `accounting.yourchapter.org`
4. Add CNAME record in your DNS provider:
   ```
   CNAME: accounting
   Points to: your-app.onrender.com
   ```
5. Wait for DNS propagation (5 minutes - 48 hours)
6. Render automatically provisions SSL certificate

**Free SSL:** Render provides free SSL certificates via Let's Encrypt!

---

## 🔄 Continuous Deployment

Once set up, deployment is automatic:

```bash
# Make code changes locally
git add .
git commit -m "Add new feature"
git push origin main
```

**Render automatically:**
1. ✅ Detects the push
2. ✅ Pulls latest code
3. ✅ Runs build command
4. ✅ Deploys new version
5. ✅ Zero downtime deployment

**Deployment takes ~2-3 minutes**

---

## 🔧 Alternative Hosting Options

### Heroku

**Setup:**
```bash
# Install Heroku CLI
# Create Heroku app
heroku create kofc-accounting

# Add PostgreSQL
heroku addons:create heroku-postgresql:mini

# Set environment variables
heroku config:set SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")

# Deploy
git push heroku main

# Open app
heroku open
```

**Cost:** $7-25/month (no free tier anymore)

---

### Railway.app

1. Go to https://railway.app
2. Click "Start a New Project"
3. Connect GitHub repository
4. Add PostgreSQL database
5. Configure environment variables
6. Deploy

**Cost:** $5/month base + usage

---

### AWS (Advanced)

**Components:**
- EC2 instance (t2.micro)
- RDS PostgreSQL
- Elastic Load Balancer
- Route 53 for DNS

**Cost:** ~$15-30/month

**Setup:** See AWS deployment guide (advanced users only)

---

### Self-Hosted (Own Server)

**Requirements:**
- Linux server (Ubuntu 20.04+ recommended)
- Nginx or Apache
- PostgreSQL
- Python 3.8+
- SSL certificate (Let's Encrypt)

**Quick Setup:**
```bash
# On Ubuntu 22.04 server
sudo apt update
sudo apt install python3-pip postgresql nginx

# Clone repository
git clone YOUR_REPO_URL
cd kofc-accounting

# Install dependencies
pip3 install -r requirements.txt

# Setup PostgreSQL
sudo -u postgres createdb kofc_accounting
sudo -u postgres createuser kofc_user -P

# Configure Nginx (see nginx.conf example)
# Setup systemd service (see kofc-accounting.service example)

# Start service
sudo systemctl start kofc-accounting
sudo systemctl enable kofc-accounting
```

**Full guide:** See `docs/self-hosting.md` *(coming soon)*

---

## 📊 Database Migration

### Backing Up Data

#### SQLite (Development)
```bash
# Copy the database file
cp kofc_accounting.db kofc_accounting_backup_$(date +%Y%m%d).db
```

#### PostgreSQL (Production)
```bash
# From Render dashboard
# Go to your database → Backups → Create Manual Backup

# Or via command line
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql
```

### Restoring Data

#### SQLite
```bash
# Replace current database
cp backup.db kofc_accounting.db
```

#### PostgreSQL
```bash
# Restore from backup
psql $DATABASE_URL < backup.sql
```

---

## ⚙️ Environment Configuration

### Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `sqlite:///kofc_accounting.db` | Database connection string |
| `SECRET_KEY` | Yes | Random on startup | Flask secret key (MUST set in production!) |
| `FLASK_ENV` | No | `production` | Environment mode |
| `FLASK_DEBUG` | No | `False` | Debug mode (never True in production!) |
| `PORT` | No | `5000` | Application port |

### Security Best Practices

✅ **DO:**
- Use strong, random SECRET_KEY (32+ characters)
- Use PostgreSQL in production (not SQLite)
- Enable HTTPS (automatic on Render)
- Change default admin password immediately
- Restrict admin access to trusted users
- Regular database backups

❌ **DON'T:**
- Use `admin123` password in production
- Commit `.env` file to Git
- Enable DEBUG in production
- Use SQLite for production (no concurrent users)
- Share SECRET_KEY publicly

---

## 🔍 Troubleshooting

### Common Issues

#### 1. Application Won't Start

**Error:** `ModuleNotFoundError: No module named 'flask'`

**Solution:**
```bash
pip install -r requirements.txt
```

---

#### 2. Database Connection Error

**Error:** `sqlalchemy.exc.OperationalError: Unable to connect to database`

**Solutions:**
```bash
# Check DATABASE_URL is set correctly
echo $DATABASE_URL

# Verify database exists
# For PostgreSQL, check Render dashboard
# For SQLite, check file exists: ls -la *.db
```

---

#### 3. Import Errors (Blueprints)

**Error:** `ModuleNotFoundError: No module named 'blueprints.chart_of_accounts'`

**Solution:**
```bash
# Ensure you're running from project root
cd /path/to/kofc-accounting
python app.py

# Check blueprints directory exists
ls -la blueprints/
```

---

#### 4. CSS Not Loading

**Problem:** Pages load but no styling

**Solutions:**
- Clear browser cache (Ctrl+Shift+R or Cmd+Shift+R)
- Check static files are being served
- Verify `branding.css` exists at `/static/css/branding.css`
- Check browser console for 404 errors

---

#### 5. Login Doesn't Work

**Error:** Invalid username or password

**Solutions:**
```bash
# Reset database (loses all data!)
rm kofc_accounting.db
python app.py

# Default credentials:
# Username: admin
# Password: admin123
```

---

#### 6. Render Deployment Fails

**Check build logs for:**
- Missing dependencies in `requirements.txt`
- Python version incompatibility
- Database connection string format

**Common fixes:**
```bash
# Ensure Procfile exists
cat Procfile
# Should show: web: gunicorn app:app

# Ensure all dependencies listed
cat requirements.txt
```

---

### Render-Specific Issues

#### Free Tier Limitations

**Problem:** App "spins down" after 15 minutes of inactivity

**Symptom:** First load after inactivity takes 30-60 seconds

**Solutions:**
- Upgrade to paid plan ($7/month) for always-on
- Accept the limitation (fine for low-traffic sites)
- Use uptime monitoring service to ping every 10 minutes

---

#### Database Connection Pool Exhausted

**Error:** Too many database connections

**Solution:**
```python
# In app.py, configure SQLAlchemy pool
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 5,
    'pool_recycle': 3600,
    'pool_pre_ping': True
}
```

---

#### PostgreSQL URL Format

**Problem:** Render uses `postgres://` but SQLAlchemy needs `postgresql://`

**Solution:**
```python
# In app.py
import os
database_url = os.environ.get('DATABASE_URL', '')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
```

---

## 📈 Monitoring & Maintenance

### Health Checks

**Render provides:**
- Automatic health checks every 30 seconds
- Email alerts on downtime
- Application logs in dashboard

**Access logs:**
1. Go to Render dashboard
2. Select your web service
3. Click "Logs" tab
4. View real-time logs

---

### Performance Monitoring

**Basic metrics (free):**
- Response time
- Error rate
- Memory usage
- CPU usage

**View in Render:**
Dashboard → Your Service → Metrics

---

### Database Maintenance

#### Regular Backups (Recommended Schedule)

- **Daily:** Automatic (Render handles this)
- **Weekly:** Manual backup before major changes
- **Monthly:** Download backup to local storage

#### Backup Retention
- Free tier: 7 days
- Paid tier: Configurable (7-365 days)

---

### Scaling Considerations

#### When to Upgrade

**Indicators you need paid tier:**
- ⚠️ App frequently "spins down"
- ⚠️ Slow response times (>2 seconds)
- ⚠️ Database >97 hours/month connection time
- ⚠️ >10 concurrent users
- ⚠️ >1,000 transactions/month

#### Upgrade Options

| Plan | Web Service | Database | Total | Best For |
|------|-------------|----------|-------|----------|
| Free | $0 | $0* | $0 | Testing, very small chapters |
| Starter | $7 | $7 | $14/mo | Small chapters (<100 members) |
| Standard | $25 | $20 | $45/mo | Medium chapters (<500 members) |
| Pro | $85+ | $50+ | $135+/mo | Large chapters, multi-chapter |

*Database free for 90 days, then $7/month

---

### Update Procedure

#### Minor Updates (Bug Fixes)

```bash
# Pull latest code
git pull origin main

# Push to production (auto-deploys)
git push origin main
```

#### Major Updates (New Features)

1. Test locally first
2. Create backup
3. Deploy during low-usage period
4. Monitor logs for errors
5. Verify functionality

---

### Security Updates

**Monthly:**
- Check for dependency updates: `pip list --outdated`
- Update requirements.txt
- Test thoroughly
- Deploy

**Update command:**
```bash
pip install --upgrade -r requirements.txt
pip freeze > requirements.txt
```

---

## 🆘 Support

### Self-Service
- Check [README.md](README.md) for feature documentation
- Search [GitHub Issues](https://github.com/yourusername/kofc-accounting/issues)
- Review [Troubleshooting](#-troubleshooting) section above

### Community Support
- [GitHub Discussions](https://github.com/yourusername/kofc-accounting/discussions)
- [Submit Bug Report](https://github.com/yourusername/kofc-accounting/issues/new)
- [Request Feature](https://github.com/yourusername/kofc-accounting/issues/new?template=feature_request.md)

### Professional Support
For paid support, training, or custom development:
- Email: support@example.com *(update this)*
- Book consultation: calendly.com/yourname *(update this)*

---

## 📋 Deployment Checklist

Use this checklist for production deployments:

### Pre-Deployment
- [ ] Code tested locally
- [ ] All tests passing
- [ ] Database backup created
- [ ] Requirements.txt updated
- [ ] Environment variables documented
- [ ] Deployment plan reviewed

### Deployment
- [ ] Push code to GitHub
- [ ] Monitor build logs
- [ ] Verify deployment success
- [ ] Test login functionality
- [ ] Test critical features
- [ ] Check error logs

### Post-Deployment
- [ ] Change default admin password
- [ ] Create organization-specific admin users
- [ ] Configure organization settings
- [ ] Import member data (if applicable)
- [ ] Set up Chart of Accounts (if customizing)
- [ ] Train users
- [ ] Document any custom configurations

### Ongoing
- [ ] Daily: Monitor error logs
- [ ] Weekly: Review performance metrics
- [ ] Monthly: Database backup verification
- [ ] Quarterly: Security updates
- [ ] Annually: Comprehensive testing

---

## 🎉 Success!

Your CARES site is now live!

**Next Steps:**
1. Change admin password
2. Add your chapter's information
3. Import members
4. Start recording transactions
5. Generate your first financial report

---

**Questions?** Open an issue on GitHub or contact support.

**Built with ❤️ for nonprofit organizations**

---

*Last Updated: January 2026*
*Version: 1.0.0*
