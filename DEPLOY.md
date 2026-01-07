# Deployment Guide

## Local Development

1. Install dependencies:
```bash
pip install --break-system-packages -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

3. Access at http://localhost:5000
   - Default login: admin / admin123

## Deploy to Render.com (Free Tier)

### 1. Prepare Your Repository

```bash
git init
git add .
git commit -m "Initial commit - Knights of Columbus Accounting System"
```

Push to GitHub:
```bash
git remote add origin YOUR_GITHUB_REPO_URL
git push -u origin main
```

### 2. Set Up Render.com

1. Go to https://render.com and sign up
2. Click "New +" and select "PostgreSQL"
   - Name: kofc-accounting-db
   - Database: kofc_accounting
   - User: kofc_user
   - Region: Choose closest to you
   - Plan: **Free**
   - Click "Create Database"

3. Click "New +" and select "Web Service"
   - Connect your GitHub repository
   - Name: kofc-accounting
   - Environment: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
   - Plan: **Free**

4. Add Environment Variables:
   - `DATABASE_URL`: Copy from your PostgreSQL instance (Internal Database URL)
   - `SECRET_KEY`: Generate a secure random string (use: python -c "import secrets; print(secrets.token_hex(32))")

5. Click "Create Web Service"

### 3. First-Time Setup

After deployment:
1. Access your Render URL
2. Login with: admin / admin123
3. **IMMEDIATELY** go to Settings and create a new admin user
4. Delete or change the default admin password

### Database URL Format

Render provides PostgreSQL URLs in this format:
```
postgres://user:password@host:port/database
```

If you see `postgres://`, you may need to change it to `postgresql://` in some cases.

## Troubleshooting

### Database Connection Issues
- Verify DATABASE_URL is set correctly
- Check PostgreSQL instance is running
- Ensure your web service can access the database (same region helps)

### Application Won't Start
- Check logs in Render dashboard
- Verify all requirements are in requirements.txt
- Ensure Procfile is present and correct

### CSS Not Loading
- Check static files are being served
- Verify branding.css is in /static/css/

## Monitoring

- View logs in Render dashboard
- Check database connection hours (97 hours/month on free tier)
- Monitor web service uptime (750 hours/month on free tier)

## Scaling

When you outgrow the free tier:
- Starter Plan: $7/month for web service
- Starter Plan: $7/month for PostgreSQL (1GB storage)
- Total: $14/month for full production deployment
