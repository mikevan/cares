# Render Deployment - Quick Reference Card

## Before You Start
```bash
# Generate secret key (save this!)
python -c "import secrets; print(secrets.token_hex(32))"

# Push code to GitHub
git add Procfile .gitignore
git commit -m "Add Render deployment files"
git push origin main
```

## Step 1: Create PostgreSQL Database
1. Render Dashboard → New + → PostgreSQL
2. Name: `kofc-accounting-db`
3. Instance Type: **Free**
4. Copy **Internal Database URL** after creation

## Step 2: Create Web Service
1. Render Dashboard → New + → Web Service
2. Connect: `mikevan/kofc-accounting-system`
3. Settings:
   - Runtime: **Python 3**
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app`
   - Instance Type: **Free**

## Step 3: Environment Variables
Add these in Advanced settings:
- `DATABASE_URL` = Internal Database URL from Step 1
- `SECRET_KEY` = Generated secret from before
- `FLASK_ENV` = production

## Step 4: Deploy & Test
1. Click "Create Web Service"
2. Wait 2-5 minutes
3. Visit your URL
4. Login: admin / admin123
5. **CHANGE PASSWORD IMMEDIATELY!**

## Your URLs
- Render Dashboard: https://dashboard.render.com
- Your App: https://kofc-accounting.onrender.com

## Auto-Deploy
Every `git push` to main branch automatically deploys!

## Free Tier Notes
- Web service sleeps after 15 min inactivity
- First request after sleep: ~30 seconds
- PostgreSQL: 90 days free trial
