# Welcome to CARES! A Friendly Guide for New Developers and Volunteers

## Table of Contents
1. What is CARES? (And why is it awesome?)
2. The CARES Way: Our Happy Philosophy
3. Meet the Test Harness: Your Superhero Sidekick
4. Let’s Write Your First Test—Step by Step!
5. How the Project is Organized (A Tour!)
6. CARES Coding Habits: Best Practices for Everyone
7. How to Make CARES Work for Your Organization
8. Oops! Troubleshooting and Getting Help
9. CARES Words: A Simple Glossary
10. You Belong Here! (Final Encouragement)

---

## 1. What is CARES? (And why is it awesome?)
CARES stands for Community Accounting & Resource Engagement System. It’s a big name, but the idea is simple: CARES helps nonprofits and community groups keep track of money, people, and projects—all in one place! It’s open-source, which means anyone can use it, change it, and make it better. And yes, that means YOU!

## 2. The CARES Way: Our Happy Philosophy
- **Safety First!** We never want to break real data. All our tests and code changes are safe to try.
- **Keep it Simple!** We write code and tests that are easy to read—even for someone brand new.
- **Teamwork!** Everyone’s ideas matter. If you’re here, you’re part of the team.
- **Learning is Fun!** Don’t worry if you’re new. We’ll help you learn as you go.

## 3. Meet the Test Harness: Your Superhero Sidekick
Imagine you had a magic sandbox where you could build, break, and rebuild castles all day—and your real castle at home would never get messy. That’s what our test harness does for CARES!

- **Safe Playground:** Every time you run a test, CARES makes a brand-new pretend database just for you. You can’t break anything important!
- **Ready-to-Go Data:** The test harness fills your sandbox with sample data (like fake members, accounts, and projects) so you can play right away.
- **Helpers (Fixtures):** You get special helpers called fixtures. They set up everything you need for your test, so you don’t have to do any heavy lifting.
- **No Leftovers:** When your test is done, the sandbox is cleaned up. No mess, no fuss!

### What to Watch Out For
- Don’t try to use the real database (called app.db or production data) in your tests.
- Don’t write tests that depend on other tests. Each test should work on its own.
- Always use the helpers (fixtures) we give you. They’re here to make your life easier!

## 4. Let’s Write Your First Test—Step by Step!
Let’s say you want to check that the login page works. Here’s how you do it:

```python
import pytest

@pytest.mark.functional
def test_login_page_accessible(client):
    response = client.get('/login')
    assert response.status_code == 200  # Did the page load?
    assert b'Login' in response.data    # Does it say 'Login'?
```

**What’s Happening Here?**
- `client` is your magic web browser for testing. It’s given to you by the test harness.
- You ask it to visit the login page.
- You check that the page loads (status 200) and that it says “Login.”
- That’s it! No setup, no cleanup—just the fun part.

## 5. How the Project is Organized (A Tour!)
Here’s a quick map of the CARES project:
- `app.py` – The main door to the app.
- `models.py` – The blueprints for all the things (like members, accounts, etc.).
- `blueprints/` – Special folders for different parts of the app (like reports, users, and more).
- `services/` – The brains behind the scenes (business logic and reports).
- `templates/` – The art studio! All the HTML pages live here.
- `static/` – Where we keep our style (CSS), pictures, and scripts.
- `tests/` – All the test files, sorted by type (functional, integration, unit, etc.).
- `scripts/` – Handy tools for setting up or fixing things.

## 6. CARES Coding Habits: Best Practices for Everyone
- **One Test, One Job:** Each test should check just one thing. If you want to check more, write another test!
- **Keep it Simple:** Try not to use “if” or “for” in your tests. If you need them, maybe split the test up.
- **Small Files:** No more than 2 test cases (functions or classes) in a file, unless you really need more (and then explain why at the top).
- **Clear Names:** Name your files and tests so anyone can guess what they do.
- **Use the Helpers:** Always use the fixtures for setup. Don’t try to set up the database yourself.
- **No Sneaky Stuff:** Don’t change the database by hand in your tests. The harness does it for you!

## 7. How to Make CARES Work for Your Organization
Want to use CARES for your own group? Awesome! Here’s how you can make it fit:

### Step 1: Think About Your Group
- What do you need to track? (People, money, projects?)
- Do you have special types of accounts or members?

### Step 2: Make It Yours
- Update `models.py` if you need new types of things.
- Add new accounts or categories in the Chart of Accounts.
- Change the look: update the logo or colors in `templates/` and `static/css/`.

### Step 3: Add Your Data
- Write a script in `scripts/` to load your group’s info.
- Use the test harness to make sure it loads and looks right.

### Step 4: Add New Features
- Want a new report or page? Add a new blueprint in `blueprints/`.
- Make a new template or update an old one.
- Don’t forget to write a test for your new feature!

### Step 5: Test, Test, Test!
- Run all the tests: `pytest --disable-warnings -v`
- Add new tests for anything you change.
- If something breaks, don’t panic—ask for help!

## 8. Oops! Troubleshooting and Getting Help
- **A test failed!**
  - Read the error message. It usually tells you what went wrong.
  - Make sure you used the right fixture (helper).
  - Check the DEVELOPER_TEST_GUIDE.md and TESTING_ENVIRONMENT.md for tips.
- **Need more data?**
  - Update your data loader or ask for help in the chat.
- **Totally stuck?**
  - That’s okay! Ask in the project chat, open an issue, or talk to a project leader. We’re here for you.

## 9. CARES Words: A Simple Glossary
- **Test Harness:** The magic sandbox that keeps your tests safe.
- **Fixture:** A helper that sets things up for your test.
- **Blueprint:** A folder of related web pages and logic.
- **Chart of Accounts:** The list of all the money buckets your group uses.
- **Session:** A way to talk to the database.

## 10. You Belong Here! (Final Encouragement)
We’re so glad you’re here! CARES is built by people like you—volunteers who want to help their communities. You don’t have to be a computer whiz. If you can read, ask questions, and try new things, you can help make CARES better. Every test you write, every page you help with, and every question you ask makes a difference. Let’s build something great together!

---
_Last updated: January 14, 2026_
