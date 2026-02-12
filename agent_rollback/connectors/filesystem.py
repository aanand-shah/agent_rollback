"""
File system connector for tracking file changes.

Implements copy-on-write backups for file system state management.
"""

import os
import hashlib
import base64
import shutil
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

from agent_rollback.connectors.base import BaseConnector


class FileSystemConnector(BaseConnector):
    """Connector for file system state tracking.

    Captures file system state by recording file metadata and contents.
    Supports restoration by recreating files from snapshots.
    """

    connector_type: str = "filesystem"

    def __init__(self, connector_id: str, config: Optional[dict[str, Any]] = None):
        """Initialize the file system connector.

        Config options:
            - base_path: Root directory to track
            - patterns: Glob patterns for files to include
            - exclude_patterns: Glob patterns for files to exclude
            - max_file_size: Maximum file size to capture (bytes)
            - store_contents: Whether to store file contents (vs just metadata)
            - backup_dir: Directory for copy-on-write backups
        """
        super().__init__(connector_id, config)
        self.base_path = Path(self.config.get("base_path", "."))
        self.patterns = self.config.get("patterns", ["**/*"])
        self.exclude_patterns = self.config.get("exclude_patterns", [])
        self.max_file_size = self.config.get("max_file_size", 10 * 1024 * 1024)  # 10MB
        self.store_contents = self.config.get("store_contents", True)
        self.backup_dir = Path(self.config.get("backup_dir", ".agent_rollback_backups"))

    async def capture_state(self) -> dict[str, Any]:
        """Capture the current file system state.

        Returns:
            Dictionary containing file metadata and optionally contents
        """
        state = {
            "timestamp": datetime.utcnow().isoformat(),
            "base_path": str(self.base_path.absolute()),
            "files": {},
            "directories": [],
            "metadata": {
                "connector_type": self.connector_type,
                "connector_id": self.connector_id,
            },
        }

        if not self.base_path.exists():
            return state

        for pattern in self.patterns:
            for file_path in self.base_path.glob(pattern):
                if self._should_exclude(file_path):
                    continue

                rel_path = str(file_path.relative_to(self.base_path))

                if file_path.is_dir():
                    state["directories"].append(rel_path)
                elif file_path.is_file():
                    state["files"][rel_path] = await self._capture_file(file_path)

        return state

    async def restore_state(self, state: dict[str, Any]) -> bool:
        """Restore the file system to a previous state.

        Args:
            state: The state to restore

        Returns:
            True if restoration was successful
        """
        try:
            base_path = Path(state.get("base_path", self.base_path))

            # Create backup of current state before restoring
            await self._create_backup()

            # Restore directories
            for dir_path in state.get("directories", []):
                full_path = base_path / dir_path
                full_path.mkdir(parents=True, exist_ok=True)

            # Restore files
            for rel_path, file_data in state.get("files", {}).items():
                full_path = base_path / rel_path
                await self._restore_file(full_path, file_data)

            # Remove files that exist now but didn't exist in snapshot
            current_files = set()
            for pattern in self.patterns:
                for file_path in base_path.glob(pattern):
                    if file_path.is_file():
                        current_files.add(str(file_path.relative_to(base_path)))

            snapshot_files = set(state.get("files", {}).keys())
            for extra_file in current_files - snapshot_files:
                if not self._should_exclude(base_path / extra_file):
                    (base_path / extra_file).unlink(missing_ok=True)

            return True
        except Exception:
            return False

    async def validate_state(self, state: dict[str, Any]) -> bool:
        """Validate that a file system state can be restored.

        Args:
            state: The state to validate

        Returns:
            True if the state is valid
        """
        if "files" not in state and "directories" not in state:
            return False

        files = state.get("files", {})
        if not isinstance(files, dict):
            return False

        for rel_path, file_data in files.items():
            if not isinstance(file_data, dict):
                return False
            # Must have either content or hash
            if "content" not in file_data and "hash" not in file_data:
                return False

        return True

    def _should_exclude(self, path: Path) -> bool:
        """Check if a path should be excluded.

        Args:
            path: Path to check

        Returns:
            True if path should be excluded
        """
        rel_path = str(path.relative_to(self.base_path)) if path.is_relative_to(self.base_path) else str(path)

        for pattern in self.exclude_patterns:
            if Path(rel_path).match(pattern):
                return True

        # Always exclude backup directory
        if str(self.backup_dir) in str(path):
            return True

        return False

    async def _capture_file(self, file_path: Path) -> dict[str, Any]:
        """Capture a single file's state.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with file metadata and optionally contents
        """
        stat = file_path.stat()
        file_data = {
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "mode": stat.st_mode,
        }

        # Calculate hash
        with open(file_path, "rb") as f:
            content = f.read()
            file_data["hash"] = hashlib.sha256(content).hexdigest()

        # Store contents if enabled and file is small enough
        if self.store_contents and stat.st_size <= self.max_file_size:
            try:
                # Try to store as text
                file_data["content"] = content.decode("utf-8")
                file_data["encoding"] = "utf-8"
            except UnicodeDecodeError:
                # Store as base64
                file_data["content"] = base64.b64encode(content).decode("ascii")
                file_data["encoding"] = "base64"

        return file_data

    async def _restore_file(self, file_path: Path, file_data: dict[str, Any]) -> None:
        """Restore a single file.

        Args:
            file_path: Path where file should be restored
            file_data: The file data to restore
        """
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if "content" in file_data:
            encoding = file_data.get("encoding", "utf-8")
            if encoding == "base64":
                content = base64.b64decode(file_data["content"])
            else:
                content = file_data["content"].encode("utf-8")

            with open(file_path, "wb") as f:
                f.write(content)

            # Restore file mode if available
            if "mode" in file_data:
                os.chmod(file_path, file_data["mode"])

    async def _create_backup(self) -> Optional[str]:
        """Create a backup of the current state.

        Returns:
            Path to backup directory, or None if backup failed
        """
        if not self.base_path.exists():
            return None

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / timestamp

        try:
            backup_path.mkdir(parents=True, exist_ok=True)
            for pattern in self.patterns:
                for file_path in self.base_path.glob(pattern):
                    if file_path.is_file() and not self._should_exclude(file_path):
                        rel_path = file_path.relative_to(self.base_path)
                        dest = backup_path / rel_path
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(file_path, dest)
            return str(backup_path)
        except Exception:
            return None

    async def list_files(self) -> list[str]:
        """List all tracked files.

        Returns:
            List of relative file paths
        """
        files = []
        if self.base_path.exists():
            for pattern in self.patterns:
                for file_path in self.base_path.glob(pattern):
                    if file_path.is_file() and not self._should_exclude(file_path):
                        files.append(str(file_path.relative_to(self.base_path)))
        return files

    async def get_file_hash(self, rel_path: str) -> Optional[str]:
        """Get the hash of a file.

        Args:
            rel_path: Relative path to the file

        Returns:
            SHA256 hash of the file, or None if file doesn't exist
        """
        file_path = self.base_path / rel_path
        if not file_path.exists() or not file_path.is_file():
            return None

        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
