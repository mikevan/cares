# CARES Test Harness - Production Deployment Guide

## ⚠️ CRITICAL: Test Artifacts Exclusion

**The CARES Test Harness is for DEVELOPMENT ONLY.** Most test files should **NOT** be deployed to production.

---

## 🚫 DO NOT DEPLOY (Excluded Files)

The following files and directories must be excluded from production deployment:

### Test Directories
```
tests/unit/                 # Unit tests
tests/integration/          # Integration tests
tests/functional/           # Functional tests
tests/uat/                  # UAT tests
tests/fixtures/             # Test data factories
tests/reports/              # Generated test reports
tests/conftest.py           # Test fixtures configuration
tests/pytest.ini            # Pytest configuration
tests/__pycache__/          # Python cache
```

### Test Scripts
```
run_tests.py                # Main test runner
run_tests.bat               # Windows test launcher
run_tests.sh                # Linux/Mac test launcher
```

### Development Dependencies
```
requirements-dev.txt        # Development dependencies
```

### Test Artifacts
```
htmlcov/                    # Coverage HTML reports
.coverage                   # Coverage data file
coverage.xml                # Coverage XML report
.pytest_cache/              # Pytest cache
*.pyc                       # Compiled Python files
__pycache__/                # Python cache directories
```

---

## ✅ SAFE TO DEPLOY (Smoke Tests Only)

**Only the smoke tests directory can be deployed to production:**

```
tests/smoke/                # Production health checks
tests/smoke/__init__.py
tests/smoke/test_health_checks.py
```

These tests are designed to:
- ✓ Verify system health
- ✓ Check database connectivity
- ✓ Validate route availability
- ✓ Test authentication system
- ✓ **NOT modify any data**

---

## 📦 Deployment Methods

### Method 1: .gitignore (Recommended)

The `.gitignore` file already excludes test artifacts:

```bash
# Commit only production code
git add .
git commit -m "Production deployment"
git push origin main

# Test artifacts are automatically excluded
```

### Method 2: Render.com Deployment

In your `render.yaml`:

```yaml
services:
  - type: web
    name: cares
    env: python
    buildCommand: "pip install -r requirements.txt"  # NOT requirements-dev.txt
    startCommand: "gunicorn app:app"
```

**Key Points:**
- ✓ Use `requirements.txt` (NOT `requirements-dev.txt`)
- ✓ Only smoke tests are in Git (others excluded by .gitignore)
- ✓ No test runners deployed

### Method 3: Manual Deployment

If deploying manually, exclude these patterns:

```bash
# Create deployment package WITHOUT test files
tar -czf cares-deploy.tar.gz \
  --exclude='tests/unit' \
  --exclude='tests/integration' \
  --exclude='tests/functional' \
  --exclude='tests/uat' \
  --exclude='tests/fixtures' \
  --exclude='tests/conftest.py' \
  --exclude='tests/pytest.ini' \
  --exclude='run_tests.*' \
  --exclude='requirements-dev.txt' \
  --exclude='htmlcov' \
  --exclude='.coverage' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  .
```

---

## 🔍 Running Smoke Tests in Production

If you want to run health checks in production:

```bash
# SSH into production server
ssh user@production-server

# Run ONLY smoke tests
pytest tests/smoke/ -v

# Or check specific health aspects
pytest tests/smoke/test_health_checks.py::TestDatabaseConnectivity -v
```

**Important:** Smoke tests are read-only and safe for production.

---

## ✓ Verification Checklist

Before deploying, verify:

- [ ] `.gitignore` is properly configured
- [ ] `requirements-dev.txt` is NOT in production
- [ ] `run_tests.*` scripts are NOT in production
- [ ] `tests/unit/` directory is NOT in production
- [ ] `tests/integration/` directory is NOT in production
- [ ] `tests/functional/` directory is NOT in production
- [ ] `tests/uat/` directory is NOT in production
- [ ] `tests/fixtures/` directory is NOT in production
- [ ] Only `tests/smoke/` exists (if desired)
- [ ] Database is production PostgreSQL (not test container)

---

## 🚨 Common Mistakes to Avoid

### ❌ Mistake 1: Installing Dev Dependencies in Production
```bash
# WRONG
pip install -r requirements-dev.txt

# CORRECT
pip install -r requirements.txt
```

### ❌ Mistake 2: Running Full Test Suite in Production
```bash
# WRONG - Will fail (no testcontainers in production)
python run_tests.py

# CORRECT - Only smoke tests if needed
pytest tests/smoke/ -v
```

### ❌ Mistake 3: Using Test Database Configuration
```bash
# WRONG
DATABASE_URL=postgresql://postgres:test123@localhost/kofc_test

# CORRECT
DATABASE_URL=postgresql://user:password@production-host/production_db
```

---

## 📊 Production vs Development Comparison

| Aspect | Development | Production |
|--------|-------------|------------|
| **Database** | Docker PostgreSQL (test) | Managed PostgreSQL |
| **Dependencies** | requirements-dev.txt | requirements.txt |
| **Tests** | All test types | Smoke tests only |
| **Test Runner** | Available | NOT available |
| **Coverage Tools** | Installed | NOT installed |
| **Factory Boy** | Installed | NOT installed |
| **Testcontainers** | Installed | NOT installed |

---

## 🔒 Security Notes

### Test Data Contains:
- Fake member information (Faker library)
- Test user accounts with weak passwords
- Sample financial data
- Mock organization details

**These should NEVER exist in production.**

### Environment Variables

Development:
```bash
SQLALCHEMY_DATABASE_URI=postgresql://postgres:dev123@localhost/kofc_accounting
SECRET_KEY=dev-secret-key-change-in-production
TESTING=True
```

Production:
```bash
SQLALCHEMY_DATABASE_URI=postgresql://user:strong_password@prod-host/prod_db
SECRET_KEY=<long random string from secrets manager>
TESTING=False  # or not set
```

---

## 📞 Questions?

**Q: Can I run smoke tests in production?**  
A: Yes, smoke tests are designed to be production-safe.

**Q: What if I accidentally deployed test files?**  
A: Redeploy without test files. They won't harm production but waste space.

**Q: Why exclude test files at all?**  
A: Security, performance, and clarity. Production shouldn't have development tools.

**Q: Can I test in production?**  
A: Only use smoke tests. Never run full test suite with Testcontainers in production.

---

**Last Updated:** January 2026  
**Version:** 1.0
