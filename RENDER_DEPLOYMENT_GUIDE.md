# Render.com Deployment - Step-by-Step Guide

## Prerequisites Checklist
- [x] GitHub account with repository: https://github.com/mikevan/kofc-accounting-system
- [x] Render.com account (linked to GitHub)
- [ ] Code pushed to GitHub (including new Procfile and .gitignore)
- [ ] Secret key generated

## STEP 1: Push Files to GitHub

1. Add the new files to your repository:
```bash
# Copy Procfile and .gitignore to your project root
# Then commit and push:
git add Procfile .gitignore
git commit -m "Add Render deployment files"
git push origin main
```

## STEP 2: Generate Secret Key

Run this command locally to generate a secure secret key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**IMPORTANT:** Copy this key - you'll need it in Step 4!

## STEP 3: Create PostgreSQL Database on Render

1. Go to https://dashboard.render.com
2. Click the **"New +"** button (top right)
3. Select **"PostgreSQL"**
4. Configure database:
   - **Name:** `kofc-accounting-db`
   - **Database:** `kofc_accounting`
   - **User:** `kofc_user`
   - **Region:** Choose closest to you (e.g., Oregon USA)
   - **PostgreSQL Version:** 16 (latest)
   - **Datadog API Key:** Leave blank
   - **Instance Type:** Select **"Free"**
5. Click **"Create Database"**
6. Wait for database to provision (1-2 minutes)
7. **IMPORTANT:** Once created, find and copy the **"Internal Database URL"**
   - It will look like: `postgresql://kofc_user:xxxxx@dpg-xxxxx/kofc_accounting`
   - Click the copy icon next to "Internal Database URL"
   - Save this somewhere - you'll need it in the next step!

## STEP 4: Create Web Service on Render

1. Still on Render dashboard, click **"New +"** again
2. Select **"Web Service"**
3. Click **"Connect Account"** if you haven't connected GitHub yet
4. Find and select your repository: **mikevan/kofc-accounting-system**
5. Configure web service:
   - **Name:** `kofc-accounting`
   - **Region:** Same as your database (e.g., Oregon USA)
   - **Branch:** `main`
   - **Root Directory:** Leave blank
   - **Runtime:** **Python 3**
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Instance Type:** Select **"Free"**

6. Click **"Advanced"** to expand advanced settings

7. Add Environment Variables:
   - Click **"Add Environment Variable"**
   - **Key:** `DATABASE_URL`
   - **Value:** Paste the Internal Database URL you copied in Step 3
   
   - Click **"Add Environment Variable"** again
   - **Key:** `SECRET_KEY`
   - **Value:** Paste the secret key you generated in Step 2
   
   - Click **"Add Environment Variable"** again
   - **Key:** `FLASK_ENV`
   - **Value:** `production`

8. Click **"Create Web Service"**

## STEP 5: Wait for Deployment

1. Render will now:
   - Clone your GitHub repository
   - Install dependencies from requirements.txt
   - Start your application with gunicorn
   
2. Watch the logs in real-time (they appear automatically)

3. Look for these success indicators:
   ```
   ==> Building...
   ==> Installing dependencies...
   ==> Starting service...
   ```

4. After 2-5 minutes, you should see:
   ```
   Your service is live 🎉
   ```

5. Your URL will be shown at the top, like:
   ```
   https://kofc-accounting.onrender.com
   ```

## STEP 6: First Login & Security

1. Click your deployed URL
2. You should see the login page
3. Login with default credentials:
   - **Username:** `admin`
   - **Password:** `admin123`

4. **IMMEDIATELY** do this:
   - Go to **Settings** → **Users**
   - Create a new admin user with a strong password
   - Log out and log back in as the new admin
   - Delete or disable the default 'admin' account

## STEP 7: Verify Everything Works

Test these features:
- [ ] Login/logout
- [ ] View dashboard
- [ ] Create a test transaction
- [ ] View financial reports
- [ ] Add a member
- [ ] Create a project

## Troubleshooting

### Deployment Failed
- Check the logs in Render dashboard
- Verify DATABASE_URL is correct (should be Internal URL, not External)
- Make sure SECRET_KEY is set

### Database Connection Error
- Verify both services are in the same region
- Check DATABASE_URL uses `postgresql://` (not `postgres://`)
- Database might take a minute to be ready - redeploy if needed

### Application Error 500
- Check environment variables are set correctly
- Look at the logs for specific error messages
- Verify all files were pushed to GitHub

### CSS Not Loading / Styling Issues
- Hard refresh your browser (Ctrl+Shift+R or Cmd+Shift+R)
- Check browser console for 404 errors
- Verify static files are in the repository

## Free Tier Limitations

Your free tier includes:
- **Web Service:** 750 hours/month (sleeps after 15 min of inactivity)
- **PostgreSQL:** 90 days, then expires
- **Note:** First request after sleep takes ~30 seconds to wake up

## Monitoring & Maintenance

### View Logs
- Go to your web service in Render dashboard
- Click the "Logs" tab
- Logs update in real-time

### Update Your App
Simply push to GitHub:
```bash
git add .
git commit -m "Your changes"
git push origin main
```
Render will automatically redeploy!

### Manual Redeploy
- Go to your web service in Render dashboard
- Click "Manual Deploy" → "Deploy latest commit"

## Need to Upgrade?

When you outgrow free tier:
- **Starter Web Service:** $7/month (no sleep, custom domain)
- **Starter PostgreSQL:** $7/month (permanent, 1GB storage)
- **Total:** $14/month for production deployment

---

## Quick Reference

**Your URLs:**
- Dashboard: https://dashboard.render.com
- Your App: https://kofc-accounting.onrender.com (or your specific URL)

**Support:**
- Render Docs: https://render.com/docs
- Community Forum: https://community.render.com

**Default Login (CHANGE IMMEDIATELY):**
- Username: admin
- Password: admin123
