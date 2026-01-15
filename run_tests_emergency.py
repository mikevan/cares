"""
Emergency Test Runner - Forces Report Generation
"""
import os
import subprocess
import sys

# Create reports directory
reports_dir = os.path.join('tests', 'reports')
os.makedirs(reports_dir, exist_ok=True)
print(f"✓ Reports directory created: {reports_dir}")

# Create htmlcov directory
htmlcov_dir = 'htmlcov'
os.makedirs(htmlcov_dir, exist_ok=True)
print(f"✓ Coverage directory created: {htmlcov_dir}")

print("\n" + "="*80)
print("Running tests with full error capture...")
print("="*80 + "\n")

# Run pytest with minimal options and capture output
cmd = [
    'pytest',
    'tests/',
    '-v',
    '--tb=long',  # Full tracebacks
    '--html=tests/reports/test_report.html',
    '--self-contained-html',
    '--capture=no',  # Show all output
]

# Run and capture to file
output_file = 'test_errors.txt'
with open(output_file, 'w', encoding='utf-8') as f:
    result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)

print(f"\n✓ Test output saved to: {output_file}")
print(f"✓ HTML report saved to: tests/reports/test_report.html")

# Show last 100 lines of output
print("\n" + "="*80)
print("LAST 100 LINES OF OUTPUT:")
print("="*80 + "\n")

with open(output_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()
    for line in lines[-100:]:
        print(line, end='')

print("\n" + "="*80)
print(f"Full error log: {output_file}")
print(f"HTML report: tests/reports/test_report.html")
print("="*80)

sys.exit(result.returncode)
