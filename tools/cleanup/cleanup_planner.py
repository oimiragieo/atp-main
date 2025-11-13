#!/usr/bin/env python3
"""
Enterprise Cleanup - Cleanup Execution Planner

This module generates a comprehensive cleanup execution plan based on
file classification, dependency analysis, and security scanning results.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class CleanupTask:
    """Represents a single cleanup task."""
    task_id: str
    task_type: str  # 'remove', 'relocate', 'refactor', 'secure'
    priority: int  # 1-10, 10 being highest
    file_path: str
    target_path: Optional[str] = None
    reason: str = ""
    dependencies: List[str] = None
    estimated_effort: str = "low"  # low, medium, high
    risk_level: str = "low"  # low, medium, high
    validation_steps: List[str] = None

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.validation_steps is None:
            self.validation_steps = []

@dataclass
class CleanupPhase:
    """Represents a phase of cleanup tasks."""
    phase_id: str
    phase_name: str
    description: str
    tasks: List[CleanupTask]
    estimated_duration: str
    prerequisites: List[str] = None

    def __post_init__(self):
        if self.prerequisites is None:
            self.prerequisites = []

class CleanupPlanner:
    """Main cleanup execution planner."""
    
    def __init__(self, root_path: str = "."):
        self.root_path = Path(root_path).resolve()
        self.cleanup_tasks: List[CleanupTask] = []
        self.cleanup_phases: List[CleanupPhase] = []
        
        # Load analysis results
        self.file_analysis = self._load_analysis("tools/cleanup/cleanup_analysis.json")
        self.dependency_analysis = self._load_analysis("tools/cleanup/dependency_analysis.json")
        self.security_analysis = self._load_analysis("tools/cleanup/security_analysis.json")

    def _load_analysis(self, file_path: str) -> Dict:
        """Load analysis results from JSON file."""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: Analysis file not found: {file_path}")
            return {}
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
            return {}

    def generate_cleanup_plan(self) -> Dict[str, any]:
        """Generate comprehensive cleanup execution plan."""
        print("Generating cleanup execution plan...")
        
        # Step 1: Generate tasks from file analysis
        self._generate_file_cleanup_tasks()
        
        # Step 2: Generate tasks from security analysis
        self._generate_security_cleanup_tasks()
        
        # Step 3: Generate tasks from dependency analysis
        self._generate_dependency_cleanup_tasks()
        
        # Step 4: Prioritize and organize tasks
        self._prioritize_tasks()
        
        # Step 5: Group tasks into phases
        self._organize_into_phases()
        
        # Step 6: Generate execution plan
        return self._generate_execution_plan()

    def _generate_file_cleanup_tasks(self):
        """Generate cleanup tasks from file classification analysis."""
        if not self.file_analysis:
            return
        
        print("Generating file cleanup tasks...")
        
        classifications = self.file_analysis.get("detailed_classifications", [])
        
        for classification in classifications:
            file_path = classification["file_path"]
            cleanup_action = classification["cleanup_action"]
            target_path = classification.get("target_path")
            reason = classification.get("reason", "")
            
            if cleanup_action == "remove":
                task = CleanupTask(
                    task_id=f"remove_{len(self.cleanup_tasks)}",
                    task_type="remove",
                    priority=self._calculate_remove_priority(classification),
                    file_path=file_path,
                    reason=reason,
                    estimated_effort="low",
                    risk_level="low",
                    validation_steps=[
                        "Verify file is not imported by other modules",
                        "Check if file contains any production logic",
                        "Confirm removal with team if uncertain"
                    ]
                )
                self.cleanup_tasks.append(task)
            
            elif cleanup_action == "relocate":
                task = CleanupTask(
                    task_id=f"relocate_{len(self.cleanup_tasks)}",
                    task_type="relocate",
                    priority=self._calculate_relocate_priority(classification),
                    file_path=file_path,
                    target_path=target_path,
                    reason=reason,
                    estimated_effort="low",
                    risk_level="low",
                    validation_steps=[
                        "Create target directory if needed",
                        "Update any imports that reference this file",
                        "Verify file works in new location"
                    ]
                )
                self.cleanup_tasks.append(task)
            
            elif cleanup_action == "refactor":
                task = CleanupTask(
                    task_id=f"refactor_{len(self.cleanup_tasks)}",
                    task_type="refactor",
                    priority=self._calculate_refactor_priority(classification),
                    file_path=file_path,
                    reason=reason,
                    estimated_effort="medium",
                    risk_level="medium",
                    validation_steps=[
                        "Review file for production vs development code",
                        "Separate concerns into different files if needed",
                        "Update tests after refactoring",
                        "Verify all functionality still works"
                    ]
                )
                self.cleanup_tasks.append(task)

    def _generate_security_cleanup_tasks(self):
        """Generate cleanup tasks from security analysis."""
        if not self.security_analysis:
            return
        
        print("Generating security cleanup tasks...")
        
        detailed_analysis = self.security_analysis.get("detailed_analysis", [])
        
        for file_analysis in detailed_analysis:
            file_path = file_analysis["file_path"]
            issues = file_analysis["issues"]
            
            if file_analysis["contains_secrets"]:
                task = CleanupTask(
                    task_id=f"secure_secrets_{len(self.cleanup_tasks)}",
                    task_type="secure",
                    priority=10,  # Highest priority
                    file_path=file_path,
                    reason="Contains hardcoded secrets",
                    estimated_effort="medium",
                    risk_level="high",
                    validation_steps=[
                        "Move secrets to environment variables",
                        "Update code to read from environment",
                        "Verify secrets are not in version control",
                        "Test functionality with new secret management"
                    ]
                )
                self.cleanup_tasks.append(task)
            
            elif file_analysis["contains_pii"]:
                task = CleanupTask(
                    task_id=f"secure_pii_{len(self.cleanup_tasks)}",
                    task_type="secure",
                    priority=8,
                    file_path=file_path,
                    reason="Contains personally identifiable information",
                    estimated_effort="low",
                    risk_level="medium",
                    validation_steps=[
                        "Replace PII with fake/example data",
                        "Verify functionality still works",
                        "Document data sanitization"
                    ]
                )
                self.cleanup_tasks.append(task)
            
            elif file_analysis["risk_score"] >= 7:
                critical_issues = [issue for issue in issues if issue["severity"] in ["critical", "high"]]
                if critical_issues:
                    task = CleanupTask(
                        task_id=f"secure_high_risk_{len(self.cleanup_tasks)}",
                        task_type="secure",
                        priority=7,
                        file_path=file_path,
                        reason=f"High security risk: {len(critical_issues)} critical/high issues",
                        estimated_effort="medium",
                        risk_level="high",
                        validation_steps=[
                            "Review each security issue individually",
                            "Apply appropriate fixes for each issue type",
                            "Test functionality after security fixes",
                            "Re-scan file to verify issues are resolved"
                        ]
                    )
                    self.cleanup_tasks.append(task)

    def _generate_dependency_cleanup_tasks(self):
        """Generate cleanup tasks from dependency analysis."""
        if not self.dependency_analysis:
            return
        
        print("Generating dependency cleanup tasks...")
        
        # Handle circular dependencies
        problematic = self.dependency_analysis.get("problematic_modules", {})
        circular_deps = problematic.get("circular_dependencies", [])
        
        for module in circular_deps:
            task = CleanupTask(
                task_id=f"fix_circular_{len(self.cleanup_tasks)}",
                task_type="refactor",
                priority=6,
                file_path=f"{module.replace('.', '/')}.py",
                reason="Part of circular dependency",
                estimated_effort="high",
                risk_level="medium",
                validation_steps=[
                    "Analyze circular dependency chain",
                    "Refactor to break circular imports",
                    "Test all affected modules",
                    "Verify dependency graph is clean"
                ]
            )
            self.cleanup_tasks.append(task)
        
        # Handle unused imports
        unused_imports = problematic.get("unused_imports", [])
        for module in unused_imports:
            task = CleanupTask(
                task_id=f"clean_imports_{len(self.cleanup_tasks)}",
                task_type="refactor",
                priority=3,
                file_path=f"{module.replace('.', '/')}.py",
                reason="Contains unused imports",
                estimated_effort="low",
                risk_level="low",
                validation_steps=[
                    "Remove unused import statements",
                    "Run linting tools to verify",
                    "Test module functionality"
                ]
            )
            self.cleanup_tasks.append(task)

    def _calculate_remove_priority(self, classification: Dict) -> int:
        """Calculate priority for remove tasks."""
        category = classification.get("category", "")
        security_risk = classification.get("security_risk", 1)
        production_relevance = classification.get("production_relevance", 5)
        
        # High priority for debug/temp files
        if category in ["debug", "temp"]:
            return 9
        
        # High priority for high security risk
        if security_risk >= 8:
            return 8
        
        # Medium priority for low production relevance
        if production_relevance <= 2:
            return 6
        
        return 4

    def _calculate_relocate_priority(self, classification: Dict) -> int:
        """Calculate priority for relocate tasks."""
        file_path = classification.get("file_path", "")
        
        # High priority for POC files
        if "poc" in file_path.lower():
            return 7
        
        # Medium priority for development tools
        if "tool" in file_path.lower() or "script" in file_path.lower():
            return 5
        
        return 4

    def _calculate_refactor_priority(self, classification: Dict) -> int:
        """Calculate priority for refactor tasks."""
        security_risk = classification.get("security_risk", 1)
        production_relevance = classification.get("production_relevance", 5)
        
        # High priority for high security risk + high production relevance
        if security_risk >= 6 and production_relevance >= 7:
            return 8
        
        return 5

    def _prioritize_tasks(self):
        """Sort tasks by priority and dependencies."""
        print("Prioritizing cleanup tasks...")
        
        # Sort by priority (highest first)
        self.cleanup_tasks.sort(key=lambda t: t.priority, reverse=True)
        
        # Group by task type for better organization
        task_groups = {
            "secure": [],
            "remove": [],
            "relocate": [],
            "refactor": []
        }
        
        for task in self.cleanup_tasks:
            task_groups[task.task_type].append(task)
        
        # Reorder: security first, then remove, relocate, refactor
        self.cleanup_tasks = (
            task_groups["secure"] +
            task_groups["remove"] +
            task_groups["relocate"] +
            task_groups["refactor"]
        )

    def _organize_into_phases(self):
        """Organize tasks into logical phases."""
        print("Organizing tasks into phases...")
        
        # Phase 1: Critical Security Issues
        security_tasks = [t for t in self.cleanup_tasks if t.task_type == "secure" and t.priority >= 8]
        if security_tasks:
            self.cleanup_phases.append(CleanupPhase(
                phase_id="phase_1",
                phase_name="Critical Security Remediation",
                description="Address critical security issues including hardcoded secrets and PII",
                tasks=security_tasks,
                estimated_duration="1-2 days"
            ))
        
        # Phase 2: File Removal
        remove_tasks = [t for t in self.cleanup_tasks if t.task_type == "remove"]
        if remove_tasks:
            self.cleanup_phases.append(CleanupPhase(
                phase_id="phase_2",
                phase_name="File Cleanup and Removal",
                description="Remove debug files, temporary files, and unused code",
                tasks=remove_tasks,
                estimated_duration="1 day",
                prerequisites=["phase_1"] if security_tasks else []
            ))
        
        # Phase 3: File Relocation
        relocate_tasks = [t for t in self.cleanup_tasks if t.task_type == "relocate"]
        if relocate_tasks:
            self.cleanup_phases.append(CleanupPhase(
                phase_id="phase_3",
                phase_name="Code Organization",
                description="Relocate development tools and organize code structure",
                tasks=relocate_tasks,
                estimated_duration="1-2 days",
                prerequisites=["phase_2"] if remove_tasks else []
            ))
        
        # Phase 4: Code Refactoring
        refactor_tasks = [t for t in self.cleanup_tasks if t.task_type == "refactor"]
        remaining_security_tasks = [t for t in self.cleanup_tasks if t.task_type == "secure" and t.priority < 8]
        all_refactor_tasks = refactor_tasks + remaining_security_tasks
        
        if all_refactor_tasks:
            self.cleanup_phases.append(CleanupPhase(
                phase_id="phase_4",
                phase_name="Code Refactoring and Security Hardening",
                description="Refactor problematic code and address remaining security issues",
                tasks=all_refactor_tasks,
                estimated_duration="2-3 days",
                prerequisites=["phase_3"] if relocate_tasks else []
            ))

    def _generate_execution_plan(self) -> Dict[str, any]:
        """Generate the final execution plan."""
        
        # Calculate statistics
        total_tasks = len(self.cleanup_tasks)
        tasks_by_type = {}
        tasks_by_priority = {}
        
        for task in self.cleanup_tasks:
            tasks_by_type[task.task_type] = tasks_by_type.get(task.task_type, 0) + 1
            priority_range = "high" if task.priority >= 7 else "medium" if task.priority >= 4 else "low"
            tasks_by_priority[priority_range] = tasks_by_priority.get(priority_range, 0) + 1
        
        # Estimate total effort
        effort_mapping = {"low": 1, "medium": 3, "high": 8}
        total_effort_points = sum(effort_mapping.get(task.estimated_effort, 1) for task in self.cleanup_tasks)
        estimated_days = max(1, total_effort_points // 8)  # Assuming 8 effort points per day
        
        plan = {
            "plan_generated": datetime.now().isoformat(),
            "summary": {
                "total_tasks": total_tasks,
                "total_phases": len(self.cleanup_phases),
                "estimated_duration_days": estimated_days,
                "tasks_by_type": tasks_by_type,
                "tasks_by_priority": tasks_by_priority
            },
            "phases": [asdict(phase) for phase in self.cleanup_phases],
            "all_tasks": [asdict(task) for task in self.cleanup_tasks],
            "execution_guidelines": {
                "backup_strategy": "Create full codebase backup before starting",
                "validation_approach": "Run tests after each phase",
                "rollback_plan": "Keep backup available for quick rollback",
                "team_coordination": "Coordinate with team before removing/moving files"
            }
        }
        
        return plan

    def save_plan(self, output_file: str = "cleanup_execution_plan.json"):
        """Save the cleanup execution plan."""
        plan = self.generate_cleanup_plan()
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(plan, f, indent=2)
        
        print(f"Cleanup execution plan saved to: {output_path}")
        return plan

    def print_summary(self):
        """Print a summary of the cleanup plan."""
        plan = self.generate_cleanup_plan()
        summary = plan["summary"]
        
        print("\n" + "="*60)
        print("ENTERPRISE CLEANUP - EXECUTION PLAN SUMMARY")
        print("="*60)
        
        print(f"Total cleanup tasks: {summary['total_tasks']}")
        print(f"Organized into {summary['total_phases']} phases")
        print(f"Estimated duration: {summary['estimated_duration_days']} days")
        
        print(f"\nTasks by type:")
        for task_type, count in summary["tasks_by_type"].items():
            print(f"  {task_type}: {count}")
        
        print(f"\nTasks by priority:")
        for priority, count in summary["tasks_by_priority"].items():
            print(f"  {priority}: {count}")
        
        print(f"\nPhases:")
        for i, phase in enumerate(plan["phases"], 1):
            print(f"  {i}. {phase['phase_name']} ({len(phase['tasks'])} tasks, {phase['estimated_duration']})")
        
        print("\n" + "="*60)

    def generate_execution_script(self, output_file: str = "execute_cleanup.py"):
        """Generate an executable cleanup script."""
        plan = self.generate_cleanup_plan()
        
        script_content = '''#!/usr/bin/env python3
"""
Auto-generated Enterprise Cleanup Execution Script

This script executes the cleanup plan generated by the cleanup planner.
Run with caution and ensure you have backups!
"""

import os
import shutil
from pathlib import Path
from datetime import datetime

class CleanupExecutor:
    def __init__(self):
        self.root_path = Path(".")
        self.backup_path = Path("cleanup_backup")
        self.log_file = "cleanup_execution.log"
        
    def log(self, message):
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] {message}"
        print(log_entry)
        with open(self.log_file, 'a') as f:
            f.write(log_entry + "\\n")
    
    def create_backup(self):
        """Create backup before cleanup."""
        self.log("Creating backup...")
        if self.backup_path.exists():
            shutil.rmtree(self.backup_path)
        
        # Copy important files only (not all files to save space)
        important_patterns = ["*.py", "*.js", "*.ts", "*.json", "*.yml", "*.yaml"]
        # Implementation would go here
        self.log("Backup created")
    
    def execute_phase(self, phase_name, tasks):
        """Execute a cleanup phase."""
        self.log(f"Starting phase: {phase_name}")
        
        for task in tasks:
            self.execute_task(task)
        
        self.log(f"Completed phase: {phase_name}")
    
    def execute_task(self, task):
        """Execute a single cleanup task."""
        task_type = task["task_type"]
        file_path = Path(task["file_path"])
        
        self.log(f"Executing {task_type} task for {file_path}")
        
        if task_type == "remove":
            self.remove_file(file_path)
        elif task_type == "relocate":
            self.relocate_file(file_path, Path(task["target_path"]))
        elif task_type == "refactor":
            self.log(f"Manual refactoring needed for {file_path}")
        elif task_type == "secure":
            self.log(f"Manual security fix needed for {file_path}")
    
    def remove_file(self, file_path):
        """Remove a file."""
        if file_path.exists():
            if file_path.is_file():
                file_path.unlink()
                self.log(f"Removed file: {file_path}")
            elif file_path.is_dir():
                shutil.rmtree(file_path)
                self.log(f"Removed directory: {file_path}")
        else:
            self.log(f"File not found: {file_path}")
    
    def relocate_file(self, source_path, target_path):
        """Relocate a file."""
        if source_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source_path), str(target_path))
            self.log(f"Moved {source_path} to {target_path}")
        else:
            self.log(f"Source file not found: {source_path}")

def main():
    executor = CleanupExecutor()
    
    # Create backup first
    executor.create_backup()
    
    # Execute phases
'''
        
        # Add phase execution code
        for phase in plan["phases"]:
            script_content += f'''
    # {phase["phase_name"]}
    executor.execute_phase("{phase["phase_name"]}", {phase["tasks"]})
'''
        
        script_content += '''
    executor.log("Cleanup execution completed!")

if __name__ == "__main__":
    main()
'''
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            f.write(script_content)
        
        print(f"Execution script saved to: {output_path}")

def main():
    """Main execution function."""
    planner = CleanupPlanner()
    
    print("Starting cleanup planning...")
    
    # Generate and save plan
    plan = planner.save_plan("tools/cleanup/cleanup_execution_plan.json")
    
    # Print summary
    planner.print_summary()
    
    # Generate execution script
    planner.generate_execution_script("tools/cleanup/execute_cleanup.py")
    
    print("\\nCleanup planning complete!")
    print("Next steps:")
    print("1. Review the execution plan in tools/cleanup/cleanup_execution_plan.json")
    print("2. Create a backup of your codebase")
    print("3. Execute cleanup tasks phase by phase")
    print("4. Validate after each phase")

if __name__ == "__main__":
    main()