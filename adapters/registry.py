#!/usr/bin/env python3
"""
Enterprise AI Platform - Adapter Registry

Consolidated registry for all AI provider adapters.
"""

import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
import importlib.util

logger = logging.getLogger(__name__)

class AdapterRegistry:
    """Central registry for all AI provider adapters."""
    
    def __init__(self):
        self.adapters: Dict[str, Any] = {}
        self.adapter_configs: Dict[str, Dict] = {}
        
    def register_adapter(self, name: str, adapter_class: Any, config: Dict = None):
        """Register an adapter with the registry."""
        self.adapters[name] = adapter_class
        self.adapter_configs[name] = config or {}
        logger.info(f"Registered adapter: {name}")
    
    def get_adapter(self, name: str) -> Optional[Any]:
        """Get an adapter by name."""
        return self.adapters.get(name)
    
    def list_adapters(self) -> List[str]:
        """List all registered adapters."""
        return list(self.adapters.keys())
    
    def get_adapter_config(self, name: str) -> Dict:
        """Get configuration for an adapter."""
        return self.adapter_configs.get(name, {})
    
    def auto_discover_adapters(self):
        """Auto-discover and register adapters from the python directory."""
        python_adapters_path = Path(__file__).parent / "python"
        
        if not python_adapters_path.exists():
            logger.warning("Python adapters directory not found")
            return
        
        for adapter_dir in python_adapters_path.iterdir():
            if adapter_dir.is_dir() and not adapter_dir.name.startswith('__'):
                self._load_adapter_from_directory(adapter_dir)
    
    def _load_adapter_from_directory(self, adapter_dir: Path):
        """Load an adapter from a directory."""
        adapter_name = adapter_dir.name.replace('_adapter', '')
        adapter_file = adapter_dir / "adapter.py"
        
        if not adapter_file.exists():
            logger.warning(f"No adapter.py found in {adapter_dir}")
            return
        
        try:
            spec = importlib.util.spec_from_file_location(
                f"{adapter_name}_adapter", 
                adapter_file
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Look for adapter class (usually named like OpenAIAdapter)
            adapter_class_name = f"{adapter_name.title()}Adapter"
            if hasattr(module, adapter_class_name):
                adapter_class = getattr(module, adapter_class_name)
                self.register_adapter(adapter_name, adapter_class)
            else:
                logger.warning(f"No {adapter_class_name} class found in {adapter_file}")
                
        except Exception as e:
            logger.error(f"Failed to load adapter from {adapter_dir}: {e}")

# Global adapter registry instance
adapter_registry = AdapterRegistry()

def get_registry() -> AdapterRegistry:
    """Get the global adapter registry."""
    return adapter_registry

def initialize_adapters():
    """Initialize all adapters."""
    logger.info("Initializing adapter registry...")
    adapter_registry.auto_discover_adapters()
    logger.info(f"Loaded {len(adapter_registry.list_adapters())} adapters")

if __name__ == "__main__":
    # Test the registry
    initialize_adapters()
    print("Available adapters:", adapter_registry.list_adapters())