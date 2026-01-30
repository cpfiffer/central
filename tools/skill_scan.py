"""
Skill Security Scanner - Basic pattern detection for skill files.

Usage:
    # Scan all skills
    uv run python -m tools.skill_scan
    
    # Scan specific skill
    uv run python -m tools.skill_scan comind-cognition
    
    # Generate hashes only
    uv run python -m tools.skill_scan --hash-only

Checks for:
- Environment variable access (credential theft vector)
- Network calls (data exfiltration vector)
- File system writes outside skill directory
- Subprocess/shell execution
- Base64 encoding (obfuscation)

Note: This is a basic pattern scanner, not a full security solution.
Consider adding YARA rules for more sophisticated detection.
"""

import argparse
import hashlib
import re
from pathlib import Path
from dataclasses import dataclass
from rich.console import Console
from rich.table import Table

console = Console()

# Suspicious patterns and their risk levels
PATTERNS = {
    'env_access': {
        'patterns': [
            r'os\.environ',
            r'getenv\(',
            r'\.env',
            r'dotenv',
            r'APP_PASSWORD',
            r'API_KEY',
            r'SECRET',
            r'TOKEN',
        ],
        'risk': 'HIGH',
        'description': 'Environment variable access - potential credential theft'
    },
    'network': {
        'patterns': [
            r'requests\.',
            r'httpx\.',
            r'urllib',
            r'socket\.',
            r'webhook',
            r'\.post\(',
            r'\.get\(',
        ],
        'risk': 'MEDIUM',
        'description': 'Network operations - potential data exfiltration'
    },
    'file_write': {
        'patterns': [
            r'open\(.+["\']w',
            r'\.write\(',
            r'shutil\.copy',
            r'Path\(.+\.write',
        ],
        'risk': 'MEDIUM',
        'description': 'File write operations'
    },
    'subprocess': {
        'patterns': [
            r'subprocess',
            r'os\.system',
            r'os\.popen',
            r'exec\(',
            r'eval\(',
            r'__import__',
        ],
        'risk': 'HIGH',
        'description': 'Code execution - potential arbitrary command execution'
    },
    'obfuscation': {
        'patterns': [
            r'base64',
            r'decode\(',
            r'\\x[0-9a-f]{2}',
            r'chr\(\d+\)',
        ],
        'risk': 'LOW',
        'description': 'Potential obfuscation techniques'
    }
}


@dataclass
class Finding:
    file: str
    line_num: int
    category: str
    risk: str
    pattern: str
    line_content: str


@dataclass
class SkillReport:
    name: str
    path: Path
    hash: str
    findings: list[Finding]
    files_scanned: int


def hash_skill(skill_path: Path) -> str:
    """Generate SHA256 hash of all skill contents."""
    hasher = hashlib.sha256()
    
    for file in sorted(skill_path.rglob('*')):
        if file.is_file():
            hasher.update(file.read_bytes())
    
    return hasher.hexdigest()[:16]  # Short hash for display


def scan_file(file_path: Path) -> list[Finding]:
    """Scan a single file for suspicious patterns."""
    findings = []
    
    try:
        content = file_path.read_text()
        lines = content.split('\n')
        
        for category, config in PATTERNS.items():
            for pattern in config['patterns']:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        findings.append(Finding(
                            file=str(file_path.name),
                            line_num=i,
                            category=category,
                            risk=config['risk'],
                            pattern=pattern,
                            line_content=line.strip()[:60]
                        ))
    except Exception:
        pass  # Skip binary/unreadable files
    
    return findings


def scan_skill(skill_path: Path) -> SkillReport:
    """Scan a skill directory for security issues."""
    findings = []
    files_scanned = 0
    
    for file in skill_path.rglob('*'):
        if file.is_file() and file.suffix in ('.py', '.md', '.sh', '.yaml', '.yml', '.json'):
            findings.extend(scan_file(file))
            files_scanned += 1
    
    return SkillReport(
        name=skill_path.name,
        path=skill_path,
        hash=hash_skill(skill_path),
        findings=findings,
        files_scanned=files_scanned
    )


def print_report(reports: list[SkillReport], hash_only: bool = False):
    """Print scan results."""
    
    if hash_only:
        table = Table(title="Skill Hashes")
        table.add_column("Skill")
        table.add_column("Hash")
        table.add_column("Files")
        
        for report in reports:
            table.add_row(report.name, report.hash, str(report.files_scanned))
        
        console.print(table)
        return
    
    # Summary table
    table = Table(title="Skill Security Scan")
    table.add_column("Skill")
    table.add_column("Hash")
    table.add_column("Files")
    table.add_column("HIGH", style="red")
    table.add_column("MED", style="yellow")
    table.add_column("LOW", style="dim")
    
    for report in reports:
        high = len([f for f in report.findings if f.risk == 'HIGH'])
        med = len([f for f in report.findings if f.risk == 'MEDIUM'])
        low = len([f for f in report.findings if f.risk == 'LOW'])
        
        table.add_row(
            report.name,
            report.hash,
            str(report.files_scanned),
            str(high) if high else "-",
            str(med) if med else "-",
            str(low) if low else "-"
        )
    
    console.print(table)
    
    # Detail findings for HIGH risk
    high_findings = []
    for report in reports:
        for f in report.findings:
            if f.risk == 'HIGH':
                high_findings.append((report.name, f))
    
    if high_findings:
        console.print("\n[red bold]HIGH Risk Findings:[/red bold]")
        for skill_name, finding in high_findings[:10]:  # Limit output
            console.print(f"  [{skill_name}] {finding.file}:{finding.line_num}")
            console.print(f"    {finding.category}: {finding.line_content}")


def main():
    parser = argparse.ArgumentParser(description="Scan skills for security issues")
    parser.add_argument("skill", nargs="?", help="Specific skill to scan")
    parser.add_argument("--hash-only", action="store_true", help="Only generate hashes")
    parser.add_argument("--skills-dir", default=".skills", help="Skills directory")
    
    args = parser.parse_args()
    
    skills_dir = Path(args.skills_dir)
    
    if not skills_dir.exists():
        console.print(f"[red]Skills directory not found: {skills_dir}[/red]")
        return
    
    # Get skills to scan
    if args.skill:
        skill_path = skills_dir / args.skill
        if not skill_path.exists():
            console.print(f"[red]Skill not found: {args.skill}[/red]")
            return
        skills = [skill_path]
    else:
        skills = [d for d in skills_dir.iterdir() if d.is_dir()]
    
    # Scan
    reports = [scan_skill(s) for s in skills]
    
    # Report
    print_report(reports, args.hash_only)


if __name__ == "__main__":
    main()
