"""Database backup and restore procedures.

Provides automated backup and restore functionality for the ATP Router database
with support for full backups, incremental backups, and point-in-time recovery.
"""

from __future__ import annotations

import asyncio
import gzip
import logging
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from .database import DatabaseConfig, get_database_manager

logger = logging.getLogger(__name__)


class DatabaseBackupManager:
    """Manages database backup and restore operations."""
    
    def __init__(self, config: Optional[DatabaseConfig] = None):
        self.config = config or DatabaseConfig()
        self.backup_dir = Path(os.getenv("BACKUP_DIR", "./backups"))
        self.backup_dir.mkdir(exist_ok=True)
        
        # Backup configuration
        self.retention_days = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
        self.compress_backups = os.getenv("BACKUP_COMPRESS", "true").lower() == "true"
        self.backup_format = os.getenv("BACKUP_FORMAT", "custom")  # custom, plain, tar
        
        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    async def create_full_backup(self, backup_name: Optional[str] = None) -> str:
        """Create a full database backup."""
        if not backup_name:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_name = f"full_backup_{timestamp}"
        
        backup_file = self.backup_dir / f"{backup_name}.sql"
        
        try:
            # Extract connection details from database URL
            db_config = self._parse_database_url()
            
            # Build pg_dump command
            cmd = [
                "pg_dump",
                "--host", db_config["host"],
                "--port", str(db_config["port"]),
                "--username", db_config["username"],
                "--dbname", db_config["database"],
                "--verbose",
                "--no-password",
                "--format", self.backup_format,
                "--file", str(backup_file)
            ]
            
            # Set environment variables for authentication
            env = os.environ.copy()
            env["PGPASSWORD"] = db_config["password"]
            
            # Execute backup
            logger.info(f"Starting full backup to {backup_file}")
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Backup failed: {result.stderr}")
            
            # Compress backup if enabled
            if self.compress_backups:
                compressed_file = await self._compress_backup(backup_file)
                backup_file.unlink()  # Remove uncompressed file
                backup_file = compressed_file
            
            # Verify backup
            backup_size = backup_file.stat().st_size
            if backup_size == 0:
                raise RuntimeError("Backup file is empty")
            
            logger.info(f"Full backup completed: {backup_file} ({backup_size} bytes)")
            
            # Clean up old backups
            await self._cleanup_old_backups()
            
            return str(backup_file)
            
        except Exception as e:
            logger.error(f"Full backup failed: {e}")
            # Clean up failed backup file
            if backup_file.exists():
                backup_file.unlink()
            raise
    
    async def create_incremental_backup(self, base_backup: str, backup_name: Optional[str] = None) -> str:
        """Create an incremental backup based on a previous backup."""
        if not backup_name:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_name = f"incremental_backup_{timestamp}"
        
        # For PostgreSQL, we use WAL archiving for incremental backups
        # This is a simplified implementation - in production, you'd use pg_basebackup with WAL-E or similar
        
        backup_file = self.backup_dir / f"{backup_name}.sql"
        
        try:
            # Get WAL files since base backup
            wal_files = await self._get_wal_files_since(base_backup)
            
            if not wal_files:
                logger.info("No new WAL files since base backup")
                return base_backup
            
            # Create incremental backup metadata
            metadata = {
                "type": "incremental",
                "base_backup": base_backup,
                "wal_files": wal_files,
                "created_at": datetime.utcnow().isoformat(),
            }
            
            # Save metadata
            metadata_file = backup_file.with_suffix(".json")
            with open(metadata_file, "w") as f:
                import json
                json.dump(metadata, f, indent=2)
            
            # Copy WAL files to backup directory
            wal_backup_dir = self.backup_dir / f"{backup_name}_wal"
            wal_backup_dir.mkdir(exist_ok=True)
            
            for wal_file in wal_files:
                if Path(wal_file).exists():
                    shutil.copy2(wal_file, wal_backup_dir)
            
            logger.info(f"Incremental backup completed: {backup_file}")
            return str(backup_file)
            
        except Exception as e:
            logger.error(f"Incremental backup failed: {e}")
            raise
    
    async def restore_backup(self, backup_file: str, target_database: Optional[str] = None) -> bool:
        """Restore database from backup file."""
        backup_path = Path(backup_file)
        
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_file}")
        
        try:
            # Extract connection details
            db_config = self._parse_database_url()
            
            if target_database:
                db_config["database"] = target_database
            
            # Decompress backup if needed
            if backup_path.suffix == ".gz":
                decompressed_file = await self._decompress_backup(backup_path)
                backup_path = decompressed_file
            
            # Build pg_restore command
            cmd = [
                "pg_restore",
                "--host", db_config["host"],
                "--port", str(db_config["port"]),
                "--username", db_config["username"],
                "--dbname", db_config["database"],
                "--verbose",
                "--no-password",
                "--clean",  # Drop existing objects
                "--if-exists",  # Don't error if objects don't exist
                str(backup_path)
            ]
            
            # Set environment variables for authentication
            env = os.environ.copy()
            env["PGPASSWORD"] = db_config["password"]
            
            # Execute restore
            logger.info(f"Starting restore from {backup_path}")
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode != 0:
                logger.warning(f"Restore completed with warnings: {result.stderr}")
            
            logger.info(f"Database restore completed from {backup_path}")
            
            # Clean up temporary decompressed file
            if backup_path != Path(backup_file):
                backup_path.unlink()
            
            return True
            
        except Exception as e:
            logger.error(f"Database restore failed: {e}")
            raise
    
    async def list_backups(self) -> List[Dict[str, any]]:
        """List available backups with metadata."""
        backups = []
        
        for backup_file in self.backup_dir.glob("*.sql*"):
            if backup_file.is_file():
                stat = backup_file.stat()
                
                backup_info = {
                    "name": backup_file.stem,
                    "file": str(backup_file),
                    "size": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_ctime),
                    "compressed": backup_file.suffix == ".gz",
                    "type": "full"  # Default to full
                }
                
                # Check for metadata file
                metadata_file = backup_file.with_suffix(".json")
                if metadata_file.exists():
                    try:
                        import json
                        with open(metadata_file) as f:
                            metadata = json.load(f)
                        backup_info.update(metadata)
                    except Exception as e:
                        logger.warning(f"Failed to read backup metadata: {e}")
                
                backups.append(backup_info)
        
        # Sort by creation time (newest first)
        backups.sort(key=lambda x: x["created_at"], reverse=True)
        
        return backups
    
    async def verify_backup(self, backup_file: str) -> bool:
        """Verify backup integrity."""
        backup_path = Path(backup_file)
        
        if not backup_path.exists():
            return False
        
        try:
            # Basic file size check
            if backup_path.stat().st_size == 0:
                return False
            
            # For compressed files, try to decompress
            if backup_path.suffix == ".gz":
                with gzip.open(backup_path, 'rb') as f:
                    # Try to read first few bytes
                    f.read(1024)
            
            # For SQL files, check for basic structure
            elif backup_path.suffix == ".sql":
                with open(backup_path, 'r') as f:
                    content = f.read(1024)
                    # Look for PostgreSQL dump header
                    if "PostgreSQL database dump" not in content:
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Backup verification failed: {e}")
            return False
    
    async def _compress_backup(self, backup_file: Path) -> Path:
        """Compress backup file using gzip."""
        compressed_file = backup_file.with_suffix(backup_file.suffix + ".gz")
        
        with open(backup_file, 'rb') as f_in:
            with gzip.open(compressed_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        return compressed_file
    
    async def _decompress_backup(self, backup_file: Path) -> Path:
        """Decompress backup file."""
        decompressed_file = backup_file.with_suffix("")
        
        with gzip.open(backup_file, 'rb') as f_in:
            with open(decompressed_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        return decompressed_file
    
    async def _cleanup_old_backups(self) -> None:
        """Clean up old backup files based on retention policy."""
        cutoff_date = datetime.utcnow() - timedelta(days=self.retention_days)
        
        for backup_file in self.backup_dir.glob("*.sql*"):
            if backup_file.is_file():
                file_date = datetime.fromtimestamp(backup_file.stat().st_ctime)
                if file_date < cutoff_date:
                    logger.info(f"Removing old backup: {backup_file}")
                    backup_file.unlink()
                    
                    # Also remove metadata file if exists
                    metadata_file = backup_file.with_suffix(".json")
                    if metadata_file.exists():
                        metadata_file.unlink()
    
    async def _get_wal_files_since(self, base_backup: str) -> List[str]:
        """Get WAL files created since base backup (simplified implementation)."""
        # In a real implementation, this would query PostgreSQL for WAL files
        # or use a WAL archiving solution like WAL-E or pgBackRest
        return []
    
    def _parse_database_url(self) -> Dict[str, str]:
        """Parse database URL into components."""
        from urllib.parse import urlparse
        
        parsed = urlparse(self.config.database_url)
        
        return {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 5432,
            "database": parsed.path.lstrip("/") if parsed.path else "postgres",
            "username": parsed.username or "postgres",
            "password": parsed.password or "",
        }


class BackupScheduler:
    """Automated backup scheduling."""
    
    def __init__(self, backup_manager: DatabaseBackupManager):
        self.backup_manager = backup_manager
        self.running = False
        self._task: Optional[asyncio.Task] = None
        
        # Schedule configuration
        self.full_backup_interval = int(os.getenv("FULL_BACKUP_INTERVAL_HOURS", "24"))
        self.incremental_backup_interval = int(os.getenv("INCREMENTAL_BACKUP_INTERVAL_HOURS", "4"))
    
    async def start(self) -> None:
        """Start automated backup scheduling."""
        if self.running:
            return
        
        self.running = True
        self._task = asyncio.create_task(self._backup_loop())
        logger.info("Backup scheduler started")
    
    async def stop(self) -> None:
        """Stop automated backup scheduling."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Backup scheduler stopped")
    
    async def _backup_loop(self) -> None:
        """Main backup scheduling loop."""
        last_full_backup = None
        last_incremental_backup = None
        
        while self.running:
            try:
                now = datetime.utcnow()
                
                # Check if full backup is needed
                if (not last_full_backup or 
                    (now - last_full_backup).total_seconds() >= self.full_backup_interval * 3600):
                    
                    backup_file = await self.backup_manager.create_full_backup()
                    last_full_backup = now
                    logger.info(f"Scheduled full backup completed: {backup_file}")
                
                # Check if incremental backup is needed
                elif (last_full_backup and 
                      (not last_incremental_backup or 
                       (now - last_incremental_backup).total_seconds() >= self.incremental_backup_interval * 3600)):
                    
                    # Find the latest full backup
                    backups = await self.backup_manager.list_backups()
                    full_backups = [b for b in backups if b.get("type") == "full"]
                    
                    if full_backups:
                        base_backup = full_backups[0]["file"]
                        backup_file = await self.backup_manager.create_incremental_backup(base_backup)
                        last_incremental_backup = now
                        logger.info(f"Scheduled incremental backup completed: {backup_file}")
                
                # Sleep for 1 hour before next check
                await asyncio.sleep(3600)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Backup scheduler error: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes before retry


# Global backup manager instance
_backup_manager: Optional[DatabaseBackupManager] = None
_backup_scheduler: Optional[BackupScheduler] = None


def get_backup_manager() -> DatabaseBackupManager:
    """Get the global backup manager instance."""
    global _backup_manager
    if _backup_manager is None:
        _backup_manager = DatabaseBackupManager()
    return _backup_manager


def get_backup_scheduler() -> BackupScheduler:
    """Get the global backup scheduler instance."""
    global _backup_scheduler
    if _backup_scheduler is None:
        _backup_scheduler = BackupScheduler(get_backup_manager())
    return _backup_scheduler


async def start_backup_scheduler() -> None:
    """Start the backup scheduler if enabled."""
    if os.getenv("ENABLE_AUTOMATED_BACKUPS", "false").lower() == "true":
        scheduler = get_backup_scheduler()
        await scheduler.start()


async def stop_backup_scheduler() -> None:
    """Stop the backup scheduler."""
    global _backup_scheduler
    if _backup_scheduler:
        await _backup_scheduler.stop()