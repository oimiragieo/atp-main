#!/usr/bin/env python3
"""
CLI tool for managing Advanced PII Detection and Redaction System
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

from advanced_pii import (
    AdvancedPIISystem, PIIDetector, PIIRedactor, PIIType, DataClassification,
    RedactionAction, RedactionPolicy, detect_pii, redact_text
)


def setup_argparser() -> argparse.ArgumentParser:
    """Set up command line argument parser"""
    parser = argparse.ArgumentParser(
        description="Advanced PII Detection and Redaction CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Detect PII in text
  python pii_cli.py detect "Contact John Doe at john@example.com"
  
  # Redact PII from text
  python pii_cli.py redact "Call me at (555) 123-4567" --classification confidential
  
  # Test PII detection on a file
  python pii_cli.py test-file input.txt --output results.json
  
  # View audit trail
  python pii_cli.py audit --tenant test_tenant --days 7
  
  # Handle data subject request
  python pii_cli.py data-subject-request john@example.com export
  
  # Add custom pattern
  python pii_cli.py add-pattern employee_id "EMP\\d{6}" --type custom
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Detect command
    detect_parser = subparsers.add_parser('detect', help='Detect PII in text')
    detect_parser.add_argument('text', help='Text to analyze')
    detect_parser.add_argument('--config', help='Configuration file path')
    detect_parser.add_argument('--output', help='Output file for results (JSON)')
    detect_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    # Redact command
    redact_parser = subparsers.add_parser('redact', help='Redact PII from text')
    redact_parser.add_argument('text', help='Text to redact')
    redact_parser.add_argument('--classification', '-c', 
                              choices=['public', 'internal', 'confidential', 'restricted', 'top_secret'],
                              default='confidential', help='Data classification level')
    redact_parser.add_argument('--config', help='Configuration file path')
    redact_parser.add_argument('--tenant', help='Tenant ID for audit trail')
    redact_parser.add_argument('--user', help='User ID for audit trail')
    redact_parser.add_argument('--output', help='Output file for results')
    
    # Test file command
    test_parser = subparsers.add_parser('test-file', help='Test PII detection on a file')
    test_parser.add_argument('input_file', help='Input file to process')
    test_parser.add_argument('--output', '-o', help='Output file for results (JSON)')
    test_parser.add_argument('--classification', '-c',
                            choices=['public', 'internal', 'confidential', 'restricted', 'top_secret'],
                            default='confidential', help='Data classification level')
    test_parser.add_argument('--config', help='Configuration file path')
    
    # Audit command
    audit_parser = subparsers.add_parser('audit', help='View audit trail')
    audit_parser.add_argument('--tenant', help='Filter by tenant ID')
    audit_parser.add_argument('--days', type=int, default=7, help='Number of days to look back')
    audit_parser.add_argument('--output', help='Output file for results (JSON)')
    audit_parser.add_argument('--format', choices=['json', 'table'], default='table', help='Output format')
    
    # Data subject request command
    dsr_parser = subparsers.add_parser('data-subject-request', help='Handle data subject requests')
    dsr_parser.add_argument('subject_id', help='Subject identifier (email, user ID, etc.)')
    dsr_parser.add_argument('request_type', choices=['export', 'delete'], help='Type of request')
    dsr_parser.add_argument('--output', help='Output file for export results')
    
    # Add pattern command
    pattern_parser = subparsers.add_parser('add-pattern', help='Add custom PII pattern')
    pattern_parser.add_argument('name', help='Pattern name')
    pattern_parser.add_argument('pattern', help='Regex pattern')
    pattern_parser.add_argument('--type', choices=[t.value for t in PIIType], 
                               default='custom', help='PII type')
    pattern_parser.add_argument('--config', help='Configuration file to update')
    
    # Benchmark command
    benchmark_parser = subparsers.add_parser('benchmark', help='Run performance benchmarks')
    benchmark_parser.add_argument('--text-size', type=int, default=1000, help='Size of test text')
    benchmark_parser.add_argument('--iterations', type=int, default=100, help='Number of iterations')
    benchmark_parser.add_argument('--methods', nargs='+', choices=['rules', 'ml', 'both'], 
                                 default=['both'], help='Detection methods to benchmark')
    
    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate configuration')
    validate_parser.add_argument('config_file', help='Configuration file to validate')
    
    return parser


def detect_command(args) -> None:
    """Handle detect command"""
    detector = PIIDetector(args.config)
    matches = detector.detect_pii(args.text)
    
    if args.verbose:
        print(f"Analyzed text: {args.text}")
        print(f"Found {len(matches)} PII matches:")
        print("-" * 50)
    
    results = []
    for match in matches:
        result = {
            "type": match.pii_type.value,
            "text": match.text,
            "start": match.start,
            "end": match.end,
            "confidence": match.confidence,
            "method": match.detection_method,
            "context": match.context
        }
        results.append(result)
        
        if args.verbose:
            print(f"Type: {match.pii_type.value}")
            print(f"Text: {match.text}")
            print(f"Position: {match.start}-{match.end}")
            print(f"Confidence: {match.confidence:.2f}")
            print(f"Method: {match.detection_method}")
            if match.context:
                print(f"Context: ...{match.context}...")
            print("-" * 30)
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {args.output}")
    elif not args.verbose:
        print(json.dumps(results, indent=2))


def redact_command(args) -> None:
    """Handle redact command"""
    classification = DataClassification(args.classification)
    system = AdvancedPIISystem(args.config)
    
    redacted_text, matches, audit_entry = system.process_text(
        args.text,
        classification,
        tenant_id=args.tenant,
        user_id=args.user,
        return_matches=True
    )
    
    result = {
        "original_text": args.text,
        "redacted_text": redacted_text,
        "classification": args.classification,
        "matches_found": len(matches),
        "matches": [
            {
                "type": match.pii_type.value,
                "text": match.text,
                "start": match.start,
                "end": match.end,
                "confidence": match.confidence
            }
            for match in matches
        ]
    }
    
    if audit_entry:
        result["audit_id"] = audit_entry.id
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"Results saved to {args.output}")
    else:
        print("Redacted text:")
        print(redacted_text)
        print(f"\nFound {len(matches)} PII matches")


def test_file_command(args) -> None:
    """Handle test-file command"""
    if not Path(args.input_file).exists():
        print(f"Error: Input file {args.input_file} not found")
        sys.exit(1)
    
    with open(args.input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    classification = DataClassification(args.classification)
    system = AdvancedPIISystem(args.config)
    
    print(f"Processing file: {args.input_file}")
    print(f"File size: {len(content)} characters")
    
    start_time = datetime.now()
    redacted_text, matches, audit_entry = system.process_text(
        content,
        classification,
        return_matches=True
    )
    processing_time = (datetime.now() - start_time).total_seconds()
    
    result = {
        "input_file": args.input_file,
        "file_size": len(content),
        "processing_time_seconds": processing_time,
        "classification": args.classification,
        "matches_found": len(matches),
        "redacted_text": redacted_text,
        "matches": [
            {
                "type": match.pii_type.value,
                "text": match.text,
                "start": match.start,
                "end": match.end,
                "confidence": match.confidence,
                "method": match.detection_method
            }
            for match in matches
        ]
    }
    
    if audit_entry:
        result["audit_id"] = audit_entry.id
    
    print(f"Processing completed in {processing_time:.2f} seconds")
    print(f"Found {len(matches)} PII matches")
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"Results saved to {args.output}")


def audit_command(args) -> None:
    """Handle audit command"""
    system = AdvancedPIISystem()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    
    entries = system.get_audit_trail(
        tenant_id=args.tenant,
        start_date=start_date,
        end_date=end_date
    )
    
    if args.format == 'json':
        result = {
            "query": {
                "tenant_id": args.tenant,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": args.days
            },
            "entries_found": len(entries),
            "entries": entries
        }
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"Audit trail saved to {args.output}")
        else:
            print(json.dumps(result, indent=2))
    
    else:  # table format
        print(f"Audit Trail (last {args.days} days)")
        if args.tenant:
            print(f"Tenant: {args.tenant}")
        print("-" * 80)
        print(f"{'Timestamp':<20} {'Tenant':<15} {'User':<15} {'PII Types':<20} {'Status'}")
        print("-" * 80)
        
        for entry in entries:
            timestamp = entry['timestamp'][:19]  # Remove microseconds
            tenant = entry.get('tenant_id', 'N/A')[:14]
            user = entry.get('user_id', 'N/A')[:14]
            pii_types = ', '.join(set(match['pii_type'] for match in entry.get('pii_matches', [])))[:19]
            
            print(f"{timestamp:<20} {tenant:<15} {user:<15} {pii_types:<20} Redacted")
        
        print(f"\nTotal entries: {len(entries)}")


def data_subject_request_command(args) -> None:
    """Handle data subject request command"""
    system = AdvancedPIISystem()
    
    result = system.handle_data_subject_request(args.subject_id, args.request_type)
    
    if args.request_type == 'export' and args.output:
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"Export data saved to {args.output}")
    else:
        print(json.dumps(result, indent=2))


def add_pattern_command(args) -> None:
    """Handle add pattern command"""
    detector = PIIDetector(args.config)
    
    try:
        pii_type = PIIType(args.type)
        detector.add_custom_pattern(pii_type, args.pattern, args.name)
        print(f"Successfully added pattern '{args.name}' for type '{args.type}'")
        
        # Test the pattern
        test_text = input("Enter test text to validate pattern (or press Enter to skip): ")
        if test_text.strip():
            matches = detector.detect_pii_rules(test_text)
            custom_matches = [m for m in matches if m.detection_method.startswith('custom')]
            if custom_matches:
                print(f"Pattern matched: {custom_matches[0].text}")
            else:
                print("Pattern did not match in test text")
                
    except ValueError as e:
        print(f"Error adding pattern: {e}")
        sys.exit(1)


def benchmark_command(args) -> None:
    """Handle benchmark command"""
    import time
    import random
    import string
    
    # Generate test text
    def generate_test_text(size: int) -> str:
        base_text = ''.join(random.choices(string.ascii_letters + string.digits + ' ', k=size-100))
        # Add some PII
        pii_samples = [
            "john.doe@example.com",
            "(555) 123-4567", 
            "123-45-6789",
            "John Smith",
            "4532 1234 5678 9012"
        ]
        return base_text + " " + " ".join(random.choices(pii_samples, k=3))
    
    test_text = generate_test_text(args.text_size)
    detector = PIIDetector()
    
    print(f"Benchmarking PII detection")
    print(f"Text size: {len(test_text)} characters")
    print(f"Iterations: {args.iterations}")
    print("-" * 50)
    
    for method in args.methods:
        if method == 'rules':
            start_time = time.time()
            for _ in range(args.iterations):
                detector.detect_pii_rules(test_text)
            end_time = time.time()
            
            total_time = end_time - start_time
            avg_time = total_time / args.iterations
            print(f"Rules-based detection:")
            print(f"  Total time: {total_time:.3f}s")
            print(f"  Average time: {avg_time*1000:.2f}ms")
            print(f"  Throughput: {args.iterations/total_time:.1f} ops/sec")
        
        elif method == 'ml':
            start_time = time.time()
            for _ in range(args.iterations):
                detector.detect_pii_ml(test_text)
            end_time = time.time()
            
            total_time = end_time - start_time
            avg_time = total_time / args.iterations
            print(f"ML-based detection:")
            print(f"  Total time: {total_time:.3f}s")
            print(f"  Average time: {avg_time*1000:.2f}ms")
            print(f"  Throughput: {args.iterations/total_time:.1f} ops/sec")
        
        elif method == 'both':
            start_time = time.time()
            for _ in range(args.iterations):
                detector.detect_pii(test_text)
            end_time = time.time()
            
            total_time = end_time - start_time
            avg_time = total_time / args.iterations
            print(f"Combined detection:")
            print(f"  Total time: {total_time:.3f}s")
            print(f"  Average time: {avg_time*1000:.2f}ms")
            print(f"  Throughput: {args.iterations/total_time:.1f} ops/sec")
        
        print()


def validate_command(args) -> None:
    """Handle validate command"""
    if not Path(args.config_file).exists():
        print(f"Error: Configuration file {args.config_file} not found")
        sys.exit(1)
    
    try:
        with open(args.config_file, 'r') as f:
            config = json.load(f)
        
        # Basic validation
        required_fields = ['enable_ml_detection', 'enable_rule_detection']
        missing_fields = [field for field in required_fields if field not in config]
        
        if missing_fields:
            print(f"Error: Missing required fields: {missing_fields}")
            sys.exit(1)
        
        # Validate redaction policies if present
        if 'redaction_policies' in config:
            for classification, policies in config['redaction_policies'].items():
                if classification not in [c.value for c in DataClassification]:
                    print(f"Warning: Unknown data classification: {classification}")
                
                for pii_type, policy in policies.items():
                    if pii_type not in [t.value for t in PIIType]:
                        print(f"Warning: Unknown PII type: {pii_type}")
                    
                    if 'action' in policy:
                        if policy['action'] not in [a.value for a in RedactionAction]:
                            print(f"Warning: Unknown redaction action: {policy['action']}")
        
        print("Configuration validation passed!")
        print(f"ML detection: {'enabled' if config.get('enable_ml_detection') else 'disabled'}")
        print(f"Rule detection: {'enabled' if config.get('enable_rule_detection') else 'disabled'}")
        
        if 'redaction_policies' in config:
            print(f"Redaction policies defined for {len(config['redaction_policies'])} classifications")
        
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in configuration file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error validating configuration: {e}")
        sys.exit(1)


def main():
    """Main CLI entry point"""
    parser = setup_argparser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        if args.command == 'detect':
            detect_command(args)
        elif args.command == 'redact':
            redact_command(args)
        elif args.command == 'test-file':
            test_file_command(args)
        elif args.command == 'audit':
            audit_command(args)
        elif args.command == 'data-subject-request':
            data_subject_request_command(args)
        elif args.command == 'add-pattern':
            add_pattern_command(args)
        elif args.command == 'benchmark':
            benchmark_command(args)
        elif args.command == 'validate':
            validate_command(args)
        else:
            print(f"Unknown command: {args.command}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()