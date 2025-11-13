#!/usr/bin/env python3
"""
Enterprise Cleanup - Security Scanner

This module scans the codebase for security risks including hardcoded secrets,
credentials, sensitive test data, and other security vulnerabilities.
"""

import os
import re
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import base64

@dataclass
class SecurityIssue:
    """Represents a security issue found in the codebase."""
    file_path: str
    line_number: int
    issue_type: str
    severity: str  # 'critical', 'high', 'medium', 'low'
    description: str
    matched_text: str
    context: str  # Surrounding lines for context
    recommendation: str

@dataclass
class FileSecurityAnalysis:
    """Security analysis results for a single file."""
    file_path: str
    issues: List[SecurityIssue]
    risk_score: int  # 1-10
    contains_secrets: bool
    contains_pii: bool
    contains_test_data: bool

class SecurityScanner:
    """Main security scanning engine."""
    
    def __init__(self, root_path: str = "."):
        self.root_path = Path(root_path).resolve()
        self.file_analyses: List[FileSecurityAnalysis] = []
        
        # Secret patterns (more comprehensive)
        self.secret_patterns = {
            'openai_api_key': {
                'pattern': r'sk-[a-zA-Z0-9]{48}',
                'severity': 'critical',
                'description': 'OpenAI API key detected'
            },
            'google_api_key': {
                'pattern': r'AIza[0-9A-Za-z-_]{35}',
                'severity': 'critical',
                'description': 'Google API key detected'
            },
            'anthropic_api_key': {
                'pattern': r'sk-ant-[a-zA-Z0-9-_]{95}',
                'severity': 'critical',
                'description': 'Anthropic API key detected'
            },
            'aws_access_key': {
                'pattern': r'AKIA[0-9A-Z]{16}',
                'severity': 'critical',
                'description': 'AWS Access Key ID detected'
            },
            'aws_secret_key': {
                'pattern': r'[A-Za-z0-9/+=]{40}',
                'severity': 'high',
                'description': 'Potential AWS Secret Access Key detected'
            },
            'github_token': {
                'pattern': r'ghp_[a-zA-Z0-9]{36}',
                'severity': 'critical',
                'description': 'GitHub Personal Access Token detected'
            },
            'jwt_token': {
                'pattern': r'eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*',
                'severity': 'high',
                'description': 'JWT token detected'
            },
            'generic_api_key': {
                'pattern': r'api[_-]?key\s*[=:]\s*["\'][a-zA-Z0-9_-]{20,}["\']',
                'severity': 'high',
                'description': 'Generic API key pattern detected'
            },
            'password_assignment': {
                'pattern': r'password\s*[=:]\s*["\'][^"\']{8,}["\']',
                'severity': 'high',
                'description': 'Hardcoded password detected'
            },
            'secret_assignment': {
                'pattern': r'secret\s*[=:]\s*["\'][^"\']{8,}["\']',
                'severity': 'high',
                'description': 'Hardcoded secret detected'
            },
            'token_assignment': {
                'pattern': r'token\s*[=:]\s*["\'][^"\']{20,}["\']',
                'severity': 'high',
                'description': 'Hardcoded token detected'
            },
            'private_key': {
                'pattern': r'-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----',
                'severity': 'critical',
                'description': 'Private key detected'
            },
            'certificate': {
                'pattern': r'-----BEGIN CERTIFICATE-----',
                'severity': 'medium',
                'description': 'Certificate detected'
            }
        }
        
        # PII patterns
        self.pii_patterns = {
            'email': {
                'pattern': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                'severity': 'medium',
                'description': 'Email address detected'
            },
            'phone': {
                'pattern': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
                'severity': 'medium',
                'description': 'Phone number detected'
            },
            'ssn': {
                'pattern': r'\b\d{3}-\d{2}-\d{4}\b',
                'severity': 'high',
                'description': 'Social Security Number detected'
            },
            'credit_card': {
                'pattern': r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
                'severity': 'high',
                'description': 'Credit card number pattern detected'
            },
            'ip_address': {
                'pattern': r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
                'severity': 'low',
                'description': 'IP address detected'
            }
        }
        
        # Suspicious patterns
        self.suspicious_patterns = {
            'hardcoded_localhost': {
                'pattern': r'localhost|127\.0\.0\.1',
                'severity': 'low',
                'description': 'Hardcoded localhost reference'
            },
            'debug_flag': {
                'pattern': r'debug\s*[=:]\s*True',
                'severity': 'medium',
                'description': 'Debug flag enabled'
            },
            'test_credentials': {
                'pattern': r'(test|demo|example).*[=:].*(password|secret|key)',
                'severity': 'medium',
                'description': 'Test credentials detected'
            },
            'sql_injection_risk': {
                'pattern': r'execute\s*\(\s*["\'].*%s.*["\']',
                'severity': 'high',
                'description': 'Potential SQL injection risk'
            },
            'eval_usage': {
                'pattern': r'\beval\s*\(',
                'severity': 'high',
                'description': 'Use of eval() function'
            },
            'exec_usage': {
                'pattern': r'\bexec\s*\(',
                'severity': 'high',
                'description': 'Use of exec() function'
            }
        }
        
        # File extensions to scan
        self.scannable_extensions = {
            '.py', '.js', '.ts', '.jsx', '.tsx', '.json', '.yml', '.yaml',
            '.env', '.conf', '.config', '.ini', '.toml', '.md', '.txt',
            '.sh', '.bat', '.ps1', '.sql', '.xml', '.html', '.css'
        }
        
        # Directories to skip
        self.skip_dirs = {
            '__pycache__', '.git', '.pytest_cache', '.mypy_cache',
            '.ruff_cache', '.hypothesis', '.build_cache', 'node_modules',
            '.vscode', '.idea', 'venv', 'env', '.env'
        }

    def scan_codebase(self) -> Dict[str, any]:
        """Scan the entire codebase for security issues."""
        print(f"Scanning codebase for security issues from: {self.root_path}")
        
        total_files = 0
        scanned_files = 0
        
        for root, dirs, files in os.walk(self.root_path):
            # Skip certain directories
            dirs[:] = [d for d in dirs if d not in self.skip_dirs]
            
            for file in files:
                total_files += 1
                file_path = Path(root) / file
                relative_path = file_path.relative_to(self.root_path)
                
                # Only scan certain file types
                if file_path.suffix.lower() in self.scannable_extensions:
                    try:
                        analysis = self._scan_file(relative_path)
                        if analysis.issues:  # Only store files with issues
                            self.file_analyses.append(analysis)
                        scanned_files += 1
                        
                        if scanned_files % 100 == 0:
                            print(f"Scanned {scanned_files} files...")
                            
                    except Exception as e:
                        print(f"Error scanning {relative_path}: {e}")
        
        print(f"Security scan complete: {scanned_files} files scanned, {len(self.file_analyses)} files with issues")
        return self._generate_report()

    def _scan_file(self, file_path: Path) -> FileSecurityAnalysis:
        """Scan a single file for security issues."""
        full_path = self.root_path / file_path
        issues = []
        
        try:
            # Try to read as text
            content = full_path.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')
            
            # Scan for all pattern types
            all_patterns = {
                **self.secret_patterns,
                **self.pii_patterns,
                **self.suspicious_patterns
            }
            
            for line_num, line in enumerate(lines, 1):
                for pattern_name, pattern_info in all_patterns.items():
                    matches = re.finditer(pattern_info['pattern'], line, re.IGNORECASE)
                    
                    for match in matches:
                        # Get context (surrounding lines)
                        context_start = max(0, line_num - 3)
                        context_end = min(len(lines), line_num + 2)
                        context = '\n'.join(lines[context_start:context_end])
                        
                        # Generate recommendation
                        recommendation = self._get_recommendation(pattern_name, pattern_info)
                        
                        issue = SecurityIssue(
                            file_path=str(file_path),
                            line_number=line_num,
                            issue_type=pattern_name,
                            severity=pattern_info['severity'],
                            description=pattern_info['description'],
                            matched_text=match.group(),
                            context=context,
                            recommendation=recommendation
                        )
                        issues.append(issue)
            
            # Calculate risk score and flags
            risk_score = self._calculate_risk_score(issues)
            contains_secrets = any(issue.issue_type in self.secret_patterns for issue in issues)
            contains_pii = any(issue.issue_type in self.pii_patterns for issue in issues)
            contains_test_data = 'test' in str(file_path).lower() and (contains_secrets or contains_pii)
            
            return FileSecurityAnalysis(
                file_path=str(file_path),
                issues=issues,
                risk_score=risk_score,
                contains_secrets=contains_secrets,
                contains_pii=contains_pii,
                contains_test_data=contains_test_data
            )
            
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return FileSecurityAnalysis(
                file_path=str(file_path),
                issues=[],
                risk_score=1,
                contains_secrets=False,
                contains_pii=False,
                contains_test_data=False
            )

    def _calculate_risk_score(self, issues: List[SecurityIssue]) -> int:
        """Calculate overall risk score for a file."""
        if not issues:
            return 1
        
        severity_scores = {
            'critical': 10,
            'high': 7,
            'medium': 4,
            'low': 2
        }
        
        total_score = sum(severity_scores.get(issue.severity, 1) for issue in issues)
        return min(10, max(1, total_score))

    def _get_recommendation(self, pattern_name: str, pattern_info: Dict) -> str:
        """Get specific recommendation for a security issue."""
        recommendations = {
            'openai_api_key': 'Move to environment variable or secure secret store',
            'google_api_key': 'Move to environment variable or secure secret store',
            'anthropic_api_key': 'Move to environment variable or secure secret store',
            'aws_access_key': 'Move to environment variable or IAM roles',
            'aws_secret_key': 'Move to environment variable or IAM roles',
            'github_token': 'Move to environment variable or GitHub secrets',
            'jwt_token': 'Ensure this is not a real token; use mock data for tests',
            'generic_api_key': 'Move to environment variable or secure secret store',
            'password_assignment': 'Move to environment variable or secure secret store',
            'secret_assignment': 'Move to environment variable or secure secret store',
            'token_assignment': 'Move to environment variable or secure secret store',
            'private_key': 'Move to secure key management system',
            'certificate': 'Verify if this should be in version control',
            'email': 'Replace with example.com email or anonymize',
            'phone': 'Replace with fake phone number (555-0123)',
            'ssn': 'Replace with fake SSN (123-45-6789)',
            'credit_card': 'Replace with test credit card number',
            'ip_address': 'Use 127.0.0.1 or example IP ranges',
            'hardcoded_localhost': 'Use configuration variable',
            'debug_flag': 'Set to False for production',
            'test_credentials': 'Use clearly fake test credentials',
            'sql_injection_risk': 'Use parameterized queries',
            'eval_usage': 'Avoid eval(); use safer alternatives',
            'exec_usage': 'Avoid exec(); use safer alternatives'
        }
        
        return recommendations.get(pattern_name, 'Review and secure this pattern')

    def _generate_report(self) -> Dict[str, any]:
        """Generate comprehensive security analysis report."""
        
        # Count issues by severity
        severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        issue_type_counts = {}
        
        for analysis in self.file_analyses:
            for issue in analysis.issues:
                severity_counts[issue.severity] += 1
                issue_type_counts[issue.issue_type] = issue_type_counts.get(issue.issue_type, 0) + 1
        
        # Find high-risk files
        high_risk_files = [
            analysis for analysis in self.file_analyses
            if analysis.risk_score >= 7
        ]
        
        # Find files with secrets
        files_with_secrets = [
            analysis for analysis in self.file_analyses
            if analysis.contains_secrets
        ]
        
        # Find files with PII
        files_with_pii = [
            analysis for analysis in self.file_analyses
            if analysis.contains_pii
        ]
        
        # Find test files with sensitive data
        test_files_with_sensitive_data = [
            analysis for analysis in self.file_analyses
            if analysis.contains_test_data
        ]
        
        # Top issue types
        top_issue_types = sorted(
            issue_type_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]
        
        report = {
            "scan_timestamp": datetime.now().isoformat(),
            "summary": {
                "total_files_scanned": len(self.file_analyses),
                "total_issues": sum(len(a.issues) for a in self.file_analyses),
                "files_with_issues": len(self.file_analyses),
                "high_risk_files": len(high_risk_files),
                "files_with_secrets": len(files_with_secrets),
                "files_with_pii": len(files_with_pii),
                "test_files_with_sensitive_data": len(test_files_with_sensitive_data)
            },
            "severity_breakdown": severity_counts,
            "top_issue_types": top_issue_types,
            "critical_findings": {
                "files_with_secrets": [a.file_path for a in files_with_secrets],
                "high_risk_files": [a.file_path for a in high_risk_files],
                "test_files_with_sensitive_data": [a.file_path for a in test_files_with_sensitive_data]
            },
            "detailed_analysis": [asdict(analysis) for analysis in self.file_analyses]
        }
        
        return report

    def save_report(self, output_file: str = "security_analysis.json"):
        """Save the security analysis report."""
        report = self._generate_report()
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"Security analysis report saved to: {output_path}")
        return report

    def print_summary(self):
        """Print a summary of the security analysis."""
        report = self._generate_report()
        summary = report["summary"]
        
        print("\n" + "="*60)
        print("ENTERPRISE CLEANUP - SECURITY ANALYSIS SUMMARY")
        print("="*60)
        
        print(f"Files scanned: {summary['total_files_scanned']}")
        print(f"Total security issues: {summary['total_issues']}")
        print(f"Files with issues: {summary['files_with_issues']}")
        
        print(f"\nSeverity breakdown:")
        for severity, count in report["severity_breakdown"].items():
            if count > 0:
                print(f"  {severity.capitalize()}: {count}")
        
        print(f"\nCritical findings:")
        print(f"  Files with secrets: {summary['files_with_secrets']}")
        print(f"  High-risk files: {summary['high_risk_files']}")
        print(f"  Test files with sensitive data: {summary['test_files_with_sensitive_data']}")
        
        if report["top_issue_types"]:
            print(f"\nTop issue types:")
            for issue_type, count in report["top_issue_types"][:5]:
                print(f"  {issue_type}: {count}")
        
        print("\n" + "="*60)

    def generate_remediation_plan(self) -> List[str]:
        """Generate specific remediation recommendations."""
        report = self._generate_report()
        remediation_steps = []
        
        # Critical issues first
        if report["summary"]["files_with_secrets"] > 0:
            remediation_steps.append(
                f"CRITICAL: Remove hardcoded secrets from {report['summary']['files_with_secrets']} files"
            )
        
        if report["summary"]["test_files_with_sensitive_data"] > 0:
            remediation_steps.append(
                f"HIGH: Sanitize sensitive data in {report['summary']['test_files_with_sensitive_data']} test files"
            )
        
        if report["severity_breakdown"]["critical"] > 0:
            remediation_steps.append(
                f"CRITICAL: Address {report['severity_breakdown']['critical']} critical security issues"
            )
        
        if report["severity_breakdown"]["high"] > 0:
            remediation_steps.append(
                f"HIGH: Address {report['severity_breakdown']['high']} high-severity security issues"
            )
        
        # Specific recommendations based on issue types
        for issue_type, count in report["top_issue_types"][:5]:
            if count > 5:  # Only recommend for frequent issues
                remediation_steps.append(
                    f"Address {count} instances of {issue_type.replace('_', ' ')}"
                )
        
        return remediation_steps

def main():
    """Main execution function."""
    scanner = SecurityScanner()
    
    print("Starting security analysis...")
    scanner.scan_codebase()
    
    # Save detailed report
    report = scanner.save_report("tools/cleanup/security_analysis.json")
    
    # Print summary
    scanner.print_summary()
    
    # Generate remediation plan
    remediation_steps = scanner.generate_remediation_plan()
    
    print(f"\nRemediation Plan:")
    for i, step in enumerate(remediation_steps, 1):
        print(f"{i}. {step}")
    
    # Save remediation plan
    with open("tools/cleanup/security_remediation.txt", 'w') as f:
        for step in remediation_steps:
            f.write(f"{step}\n")
    
    print(f"\nRemediation plan saved to: tools/cleanup/security_remediation.txt")
    
    # Save critical files list
    critical_files = report["critical_findings"]["files_with_secrets"]
    if critical_files:
        with open("tools/cleanup/critical_security_files.txt", 'w') as f:
            for file_path in sorted(critical_files):
                f.write(f"{file_path}\n")
        
        print(f"Critical files list saved to: tools/cleanup/critical_security_files.txt")

if __name__ == "__main__":
    main()