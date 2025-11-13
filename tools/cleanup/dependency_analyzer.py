#!/usr/bin/env python3
"""
Enterprise Cleanup - Dependency Analysis Tool

This module analyzes dependencies across the codebase to identify
circular dependencies, unused imports, and critical dependency chains.
"""

import os
import ast
import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import networkx as nx

@dataclass
class DependencyInfo:
    """Information about a dependency relationship."""
    source_file: str
    target_module: str
    import_type: str  # 'import', 'from_import', 'relative_import'
    line_number: int
    is_external: bool
    is_relative: bool

@dataclass
class ModuleAnalysis:
    """Analysis results for a single module."""
    file_path: str
    imports: List[DependencyInfo]
    exports: List[str]  # Functions, classes exported
    unused_imports: List[str]
    circular_dependencies: List[str]
    dependency_depth: int
    is_leaf_module: bool
    is_root_module: bool

class DependencyAnalyzer:
    """Main dependency analysis engine."""
    
    def __init__(self, root_path: str = "."):
        self.root_path = Path(root_path).resolve()
        self.dependency_graph = nx.DiGraph()
        self.module_analyses: Dict[str, ModuleAnalysis] = {}
        self.external_dependencies: Set[str] = set()
        self.internal_modules: Set[str] = set()
        
        # Standard library modules (partial list)
        self.stdlib_modules = {
            'os', 'sys', 'json', 'time', 'datetime', 'pathlib', 'typing',
            'collections', 'itertools', 'functools', 'operator', 'math',
            'random', 'string', 'uuid', 're', 'hashlib', 'base64',
            'urllib', 'http', 'socket', 'threading', 'asyncio', 'concurrent',
            'multiprocessing', 'subprocess', 'logging', 'unittest', 'pytest',
            'dataclasses', 'enum', 'abc', 'contextlib', 'warnings'
        }

    def analyze_dependencies(self) -> Dict[str, any]:
        """Analyze all dependencies in the codebase."""
        print(f"Analyzing dependencies from: {self.root_path}")
        
        # Step 1: Discover all Python modules
        self._discover_modules()
        
        # Step 2: Parse imports from each module
        self._parse_imports()
        
        # Step 3: Build dependency graph
        self._build_dependency_graph()
        
        # Step 4: Analyze circular dependencies
        self._find_circular_dependencies()
        
        # Step 5: Find unused imports
        self._find_unused_imports()
        
        # Step 6: Calculate dependency metrics
        self._calculate_metrics()
        
        return self._generate_report()

    def _discover_modules(self):
        """Discover all Python modules in the codebase."""
        print("Discovering Python modules...")
        
        for root, dirs, files in os.walk(self.root_path):
            # Skip certain directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {
                '__pycache__', 'node_modules', 'venv', 'env'
            }]
            
            for file in files:
                if file.endswith('.py'):
                    file_path = Path(root) / file
                    relative_path = file_path.relative_to(self.root_path)
                    module_name = self._path_to_module_name(relative_path)
                    self.internal_modules.add(module_name)
        
        print(f"Found {len(self.internal_modules)} Python modules")

    def _path_to_module_name(self, file_path: Path) -> str:
        """Convert file path to module name."""
        parts = list(file_path.parts)
        if parts[-1] == '__init__.py':
            parts = parts[:-1]
        elif parts[-1].endswith('.py'):
            parts[-1] = parts[-1][:-3]
        
        return '.'.join(parts)

    def _parse_imports(self):
        """Parse imports from all Python files."""
        print("Parsing imports...")
        
        processed = 0
        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {
                '__pycache__', 'node_modules', 'venv', 'env'
            }]
            
            for file in files:
                if file.endswith('.py'):
                    file_path = Path(root) / file
                    relative_path = file_path.relative_to(self.root_path)
                    
                    try:
                        self._parse_file_imports(relative_path)
                        processed += 1
                        
                        if processed % 50 == 0:
                            print(f"Parsed {processed} files...")
                            
                    except Exception as e:
                        print(f"Error parsing {relative_path}: {e}")
        
        print(f"Parsed imports from {processed} files")

    def _parse_file_imports(self, file_path: Path):
        """Parse imports from a single Python file."""
        full_path = self.root_path / file_path
        module_name = self._path_to_module_name(file_path)
        
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            tree = ast.parse(content)
            imports = []
            exports = []
            
            for node in ast.walk(tree):
                # Parse import statements
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(DependencyInfo(
                            source_file=str(file_path),
                            target_module=alias.name,
                            import_type='import',
                            line_number=node.lineno,
                            is_external=not self._is_internal_module(alias.name),
                            is_relative=False
                        ))
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(DependencyInfo(
                            source_file=str(file_path),
                            target_module=node.module,
                            import_type='from_import',
                            line_number=node.lineno,
                            is_external=not self._is_internal_module(node.module),
                            is_relative=node.level > 0
                        ))
                
                # Parse exports (functions and classes)
                elif isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith('_'):
                        exports.append(node.name)
            
            self.module_analyses[module_name] = ModuleAnalysis(
                file_path=str(file_path),
                imports=imports,
                exports=exports,
                unused_imports=[],
                circular_dependencies=[],
                dependency_depth=0,
                is_leaf_module=False,
                is_root_module=False
            )
            
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")

    def _is_internal_module(self, module_name: str) -> bool:
        """Check if a module is internal to the project."""
        if not module_name:
            return False
        
        # Check if it's a standard library module
        root_module = module_name.split('.')[0]
        if root_module in self.stdlib_modules:
            return False
        
        # Check if it's in our internal modules
        for internal_module in self.internal_modules:
            if module_name == internal_module or module_name.startswith(internal_module + '.'):
                return True
            if internal_module.startswith(module_name + '.'):
                return True
        
        return False

    def _build_dependency_graph(self):
        """Build the dependency graph."""
        print("Building dependency graph...")
        
        for module_name, analysis in self.module_analyses.items():
            self.dependency_graph.add_node(module_name)
            
            for dep in analysis.imports:
                if not dep.is_external and dep.target_module in self.module_analyses:
                    self.dependency_graph.add_edge(module_name, dep.target_module)
                elif dep.is_external:
                    self.external_dependencies.add(dep.target_module)

    def _find_circular_dependencies(self):
        """Find circular dependencies in the graph."""
        print("Finding circular dependencies...")
        
        try:
            cycles = list(nx.simple_cycles(self.dependency_graph))
            
            for cycle in cycles:
                for module in cycle:
                    if module in self.module_analyses:
                        self.module_analyses[module].circular_dependencies.extend(cycle)
            
            print(f"Found {len(cycles)} circular dependency cycles")
            
        except Exception as e:
            print(f"Error finding cycles: {e}")

    def _find_unused_imports(self):
        """Find unused imports in each module."""
        print("Finding unused imports...")
        
        for module_name, analysis in self.module_analyses.items():
            try:
                full_path = self.root_path / analysis.file_path
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # Simple heuristic: check if imported names are used in the file
                for dep in analysis.imports:
                    if dep.import_type == 'import':
                        # For "import module", check if "module" is used
                        module_parts = dep.target_module.split('.')
                        if not any(part in content for part in module_parts):
                            analysis.unused_imports.append(dep.target_module)
                    
            except Exception as e:
                print(f"Error checking unused imports in {analysis.file_path}: {e}")

    def _calculate_metrics(self):
        """Calculate dependency metrics for each module."""
        print("Calculating dependency metrics...")
        
        for module_name, analysis in self.module_analyses.items():
            # Calculate dependency depth
            try:
                if module_name in self.dependency_graph:
                    # Find shortest path to any leaf node
                    leaf_nodes = [n for n in self.dependency_graph.nodes() 
                                if self.dependency_graph.out_degree(n) == 0]
                    
                    if leaf_nodes:
                        depths = []
                        for leaf in leaf_nodes:
                            try:
                                if nx.has_path(self.dependency_graph, module_name, leaf):
                                    path_length = nx.shortest_path_length(
                                        self.dependency_graph, module_name, leaf
                                    )
                                    depths.append(path_length)
                            except:
                                pass
                        
                        analysis.dependency_depth = min(depths) if depths else 0
                    
                    # Check if it's a leaf or root module
                    analysis.is_leaf_module = self.dependency_graph.out_degree(module_name) == 0
                    analysis.is_root_module = self.dependency_graph.in_degree(module_name) == 0
                    
            except Exception as e:
                print(f"Error calculating metrics for {module_name}: {e}")

    def _generate_report(self) -> Dict[str, any]:
        """Generate comprehensive dependency analysis report."""
        
        # Count statistics
        total_modules = len(self.module_analyses)
        total_imports = sum(len(a.imports) for a in self.module_analyses.values())
        internal_imports = sum(
            len([imp for imp in a.imports if not imp.is_external])
            for a in self.module_analyses.values()
        )
        external_imports = total_imports - internal_imports
        
        # Find modules with issues
        modules_with_cycles = [
            name for name, analysis in self.module_analyses.items()
            if analysis.circular_dependencies
        ]
        
        modules_with_unused = [
            name for name, analysis in self.module_analyses.items()
            if analysis.unused_imports
        ]
        
        # Find highly connected modules
        if self.dependency_graph.nodes():
            in_degrees = dict(self.dependency_graph.in_degree())
            out_degrees = dict(self.dependency_graph.out_degree())
            
            highly_depended_on = sorted(
                in_degrees.items(), key=lambda x: x[1], reverse=True
            )[:10]
            
            highly_dependent = sorted(
                out_degrees.items(), key=lambda x: x[1], reverse=True
            )[:10]
        else:
            highly_depended_on = []
            highly_dependent = []
        
        # Most common external dependencies
        external_dep_counts = defaultdict(int)
        for analysis in self.module_analyses.values():
            for dep in analysis.imports:
                if dep.is_external:
                    root_module = dep.target_module.split('.')[0]
                    external_dep_counts[root_module] += 1
        
        top_external_deps = sorted(
            external_dep_counts.items(), key=lambda x: x[1], reverse=True
        )[:15]
        
        report = {
            "analysis_timestamp": "2024-01-01T00:00:00",  # Will be updated
            "summary": {
                "total_modules": total_modules,
                "total_imports": total_imports,
                "internal_imports": internal_imports,
                "external_imports": external_imports,
                "external_dependencies": len(self.external_dependencies),
                "circular_dependency_cycles": len(modules_with_cycles),
                "modules_with_unused_imports": len(modules_with_unused)
            },
            "problematic_modules": {
                "circular_dependencies": modules_with_cycles,
                "unused_imports": modules_with_unused
            },
            "highly_connected": {
                "most_depended_on": highly_depended_on,
                "most_dependent": highly_dependent
            },
            "external_dependencies": {
                "top_dependencies": top_external_deps,
                "all_dependencies": sorted(list(self.external_dependencies))
            },
            "detailed_analysis": {
                module_name: asdict(analysis)
                for module_name, analysis in self.module_analyses.items()
            }
        }
        
        return report

    def save_report(self, output_file: str = "dependency_analysis.json"):
        """Save the dependency analysis report."""
        report = self._generate_report()
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"Dependency analysis report saved to: {output_path}")
        return report

    def print_summary(self):
        """Print a summary of the dependency analysis."""
        report = self._generate_report()
        summary = report["summary"]
        
        print("\n" + "="*60)
        print("ENTERPRISE CLEANUP - DEPENDENCY ANALYSIS SUMMARY")
        print("="*60)
        
        print(f"Total modules: {summary['total_modules']}")
        print(f"Total imports: {summary['total_imports']}")
        print(f"  Internal imports: {summary['internal_imports']}")
        print(f"  External imports: {summary['external_imports']}")
        print(f"External dependencies: {summary['external_dependencies']}")
        
        print(f"\nProblematic modules:")
        print(f"  Circular dependencies: {summary['circular_dependency_cycles']}")
        print(f"  Unused imports: {summary['modules_with_unused_imports']}")
        
        print(f"\nTop external dependencies:")
        for dep, count in report["external_dependencies"]["top_dependencies"][:10]:
            print(f"  {dep}: {count} imports")
        
        if report["highly_connected"]["most_depended_on"]:
            print(f"\nMost depended-on modules:")
            for module, count in report["highly_connected"]["most_depended_on"][:5]:
                print(f"  {module}: {count} dependents")
        
        print("\n" + "="*60)

    def generate_cleanup_recommendations(self) -> List[str]:
        """Generate specific cleanup recommendations."""
        recommendations = []
        
        report = self._generate_report()
        
        # Recommend removing modules with unused imports
        if report["problematic_modules"]["unused_imports"]:
            recommendations.append(
                f"Clean up unused imports in {len(report['problematic_modules']['unused_imports'])} modules"
            )
        
        # Recommend refactoring circular dependencies
        if report["problematic_modules"]["circular_dependencies"]:
            recommendations.append(
                f"Refactor {len(report['problematic_modules']['circular_dependencies'])} modules with circular dependencies"
            )
        
        # Recommend consolidating external dependencies
        external_deps = report["external_dependencies"]["all_dependencies"]
        if len(external_deps) > 50:
            recommendations.append(
                f"Consider consolidating {len(external_deps)} external dependencies"
            )
        
        return recommendations

def main():
    """Main execution function."""
    analyzer = DependencyAnalyzer()
    
    print("Starting dependency analysis...")
    analyzer.analyze_dependencies()
    
    # Save detailed report
    report = analyzer.save_report("tools/cleanup/dependency_analysis.json")
    
    # Print summary
    analyzer.print_summary()
    
    # Generate recommendations
    recommendations = analyzer.generate_cleanup_recommendations()
    
    print(f"\nCleanup Recommendations:")
    for i, rec in enumerate(recommendations, 1):
        print(f"{i}. {rec}")
    
    # Save recommendations
    with open("tools/cleanup/dependency_recommendations.txt", 'w') as f:
        for rec in recommendations:
            f.write(f"{rec}\n")
    
    print(f"\nRecommendations saved to: tools/cleanup/dependency_recommendations.txt")

if __name__ == "__main__":
    main()