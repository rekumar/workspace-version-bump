#!/usr/bin/env python3
"""
Pre-commit hook for automatic version bumping in UV workspace.

This script:
1. Scans the repository for all `pyproject.toml` files to identify potential packages.
2. Filters out the root project and any specified ignored directories.
3. Analyzes git diff to identify changed packages among the remaining candidates.
4. Checks if versions have been manually updated.
5. Auto-bumps patch version for packages with changes but no version bump.
6. Bumps root version if any subpackages were bumped (unless disabled).
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Set, Tuple

import tomlkit


def run_git_command(cmd: List[str]) -> str:
    """Run a git command and return the output."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, cwd=Path.cwd()
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Git command failed: {' '.join(cmd)}")
        print(f"Error: {e.stderr}")
        sys.exit(1) # Exit if git command fails, crucial for pre-commit


def get_changed_files(
    commit_before: str | None,
    commit_after: str | None
) -> Set[str]:
    """Get list of changed files from git.
    If commit_before and commit_after are provided, diffs between them.
    Otherwise, defaults to staged files (for pre-commit hook usage).
    """
    if commit_before and commit_after:
        # Handle the case for the very first commit to a new branch where `before` is all zeros
        if commit_before == "0000000000000000000000000000000000000000":
            print(f"Diffing against empty tree for initial commit/new branch: {commit_after}")
            # This gets all files in the commit_after (the current commit)
            # git diff-tree --no-commit-id --name-only -r <commit_sha>
            output = run_git_command(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_after])
        else:
            print(f"Diffing between commits: {commit_before} and {commit_after}")
            output = run_git_command(["git", "diff", "--name-only", commit_before, commit_after])
    else:
        print("Defaulting to staged files (git diff --cached --name-only)")
        output = run_git_command(["git", "diff", "--cached", "--name-only"])
    return set(output.split("\n")) if output else set()


def get_changed_packages(
    staged_files: Set[str],
    ignore_dirs_patterns_str: List[str],
    root_pyproject_path_obj: Path
) -> Set[Path]:
    """
    Identify package directories that have staged changes.

    1. Finds all `pyproject.toml` files in the current working directory.
    2. Excludes the root `pyproject.toml`'s directory.
    3. Excludes directories specified in `ignore_dirs_patterns_str`.
    4. For the remaining, checks if any staged files are within them.
    Returns a set of relative paths to changed package directories.
    """
    changed_pkgs_set = set()
    repo_root = Path.cwd()

    # Resolve root pyproject path for reliable comparison
    abs_root_package_dir = root_pyproject_path_obj.parent.resolve()
    
    # Compile ignore regex patterns
    compiled_ignore_patterns = []
    for pattern_str in ignore_dirs_patterns_str: # Renamed from ignore_package_dirs
        try:
            compiled_ignore_patterns.append(re.compile(pattern_str))
        except re.error as e:
            print(f"⚠️ Invalid regex pattern in --ignore-dirs: '{pattern_str}'. Error: {e}. Skipping this pattern.")
            continue

    for pyproject_file in repo_root.rglob("pyproject.toml"):
        package_dir_abs = pyproject_file.parent.resolve()

        # Skip if it's the root project's directory
        if package_dir_abs == abs_root_package_dir:
            continue

        # Convert to relative path for regex matching and reporting
        try:
            package_dir_rel = package_dir_abs.relative_to(repo_root)
        except ValueError:
            print(f"⚠️ Could not make path relative for {package_dir_abs}, skipping.")
            continue

        # Skip if it matches any ignore regex pattern
        ignored_by_regex = False
        for pattern in compiled_ignore_patterns:
            # Use search to find the pattern anywhere in the relative path string
            # Paths are converted to strings and use forward slashes on all platforms by Path objects
            if pattern.search(str(package_dir_rel).replace('\\', '/')):
                print(f"🚫 Ignoring directory '{package_dir_rel}' as it matches ignore pattern: '{pattern.pattern}'.")
                ignored_by_regex = True
                break
        if ignored_by_regex:
            continue
        
        # Check if any staged file is within this package directory
        for staged_file_str in staged_files:
            staged_file_path = Path(staged_file_str)
            # Ensure staged_file_path is relative to repo_root for is_relative_to to work as expected
            # Path.is_relative_to needs both paths to be absolute or both relative to the same root.
            # Staged files from git are usually relative to repo root.
            try:
                # Path.is_relative_to() works correctly if staged_file_path is relative
                # and package_dir_abs is absolute, by making staged_file_path absolute first.
                # However, to be explicit and safe with various path states:
                if staged_file_path.resolve().is_relative_to(package_dir_abs):
                    changed_pkgs_set.add(package_dir_rel)
                    # print(f"Found change in {package_dir_rel} due to {staged_file_str}") # Debug
                    break  # Found a change in this package, move to next pyproject.toml
            except ValueError: # Not relative
                continue
            except Exception as e: # other potential errors like file not existing if resolve fails
                print(f"Error checking staged file {staged_file_str} against {package_dir_abs}: {e}")
                continue
                
    return changed_pkgs_set


def parse_version(version_str: str) -> Tuple[int, int, int]:
    """Parse semantic version string into tuple of integers."""
    # Remove any pre-release or build metadata
    version_core = version_str.split("-")[0].split("+")[0]
    parts = version_core.split(".")

    if len(parts) != 3:
        raise ValueError(f"Invalid semantic version: {version_str}")

    return tuple(int(part) for part in parts)


def increment_patch_version(version_str: str) -> str:
    """Increment the patch version of a semantic version string."""
    major, minor, patch = parse_version(version_str)
    return f"{major}.{minor}.{patch + 1}"


def get_version_from_pyproject(pyproject_path: Path) -> str:
    """Extract version from pyproject.toml using tomlkit."""
    try:
        with open(pyproject_path, "r") as f:
            content = f.read()
        data = tomlkit.parse(content)
        
        project_data = data.get("project")
        if project_data and "version" in project_data:
            return str(project_data["version"]) # Ensure it's a string
        
        tool_data = data.get("tool")
        if tool_data and "poetry" in tool_data and "version" in tool_data["poetry"]:
            return str(tool_data["poetry"]["version"]) # Ensure it's a string
            
        print(f"Warning: Could not find version in {pyproject_path} under [project] or [tool.poetry]")
        return None
    except (FileNotFoundError, tomlkit.exceptions.ParseError) as e: # Updated exception type
        print(f"Error reading or parsing version from {pyproject_path}: {e}")
        return None


def set_version_in_pyproject(pyproject_path: Path, new_version: str) -> bool:
    """Update version in pyproject.toml using tomlkit to preserve formatting."""
    try:
        with open(pyproject_path, "r") as f:
            content = f.read()
        
        data = tomlkit.parse(content)
        updated = False

        # Try to update [project.version]
        if "project" in data and "version" in data["project"]:
            # Ensure we are replacing a string item, not creating a new table if it was malformed
            if isinstance(data["project"]["version"], str) or isinstance(data["project"]["version"], tomlkit.items.String):
                current_version = str(data["project"]["version"])
                if current_version != new_version:
                    data["project"]["version"] = new_version
                    updated = True
            else:
                print(f"Warning: 'project.version' in {pyproject_path} is not a string. Skipping update here.")

        # Else, try to update [tool.poetry.version] (only if project.version wasn't found/updated)
        elif "tool" in data and "poetry" in data["tool"] and "version" in data["tool"]["poetry"]:
             # Ensure we are replacing a string item
            if isinstance(data["tool"]["poetry"]["version"], str) or isinstance(data["tool"]["poetry"]["version"], tomlkit.items.String):
                current_version = str(data["tool"]["poetry"]["version"])
                if current_version != new_version:
                    data["tool"]["poetry"]["version"] = new_version
                    updated = True
            else:
                print(f"Warning: 'tool.poetry.version' in {pyproject_path} is not a string. Skipping update here.")
        else:
            print(f"Error: 'version' field not found under [project] or [tool.poetry] in {pyproject_path}. Cannot update.")
            return False

        if updated:
            with open(pyproject_path, "w") as f:
                f.write(tomlkit.dumps(data))
            return True
        return False # No update was made (e.g. version was already the new_version)

    except (FileNotFoundError, tomlkit.exceptions.ParseError) as e: # Updated exception type
        print(f"Error reading, parsing, or writing {pyproject_path}: {e}")
        return False
    except Exception as e: # Catch other potential errors
        print(f"An unexpected error occurred while setting version in {pyproject_path}: {e}")
        return False


def get_version_from_diff(pyproject_path: str) -> str | None:
    """Check if the version line has changed in the staged diff."""

    # Get the staged diff for this file
    try:
        diff_output = run_git_command(
            ["git", "diff", "--cached", "--unified=0", pyproject_path]
        )

        # Look for version changes in the diff
        version_pattern = r"\+version\s*=\s*[\"']([^\"']+)[\"']"
        match = re.search(version_pattern, diff_output)
        if match:
            return match.group(1)
        return None
    except Exception:
        return None


def stage_file(file_path: str) -> bool:
    """Stage a file with git add."""
    try:
        subprocess.run(["git", "add", file_path], check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def main() -> int:
    """Main function for the version bump hook."""
    print("🔍 Checking for version bumps in changed packages...")

    parser = argparse.ArgumentParser(description="UV Workspace Version Bump Pre-commit Hook")
    parser.add_argument(
        "--ignore-dirs", # Renamed from --ignore-package-dirs
        nargs="+",
        default=[],
        help="List of regex patterns for directory paths to ignore (e.g., 'tests/fixtures', '_build/'). Default: []",
    )
    parser.add_argument(
        "--root-pyproject-path",
        default="pyproject.toml",
        help="Path to the root pyproject.toml file. Default: 'pyproject.toml'",
    )
    parser.add_argument(
        "--dont-bump-root",
        action="store_true",
        help="Whether to skip version bumps in the root pyproject.toml. Default: False",
    )
    parser.add_argument(
        "--commit-before",
        type=str,
        default=None,
        help="The commit SHA before changes (for GitHub Action context)."
    )
    parser.add_argument(
        "--commit-after",
        type=str,
        default=None,
        help="The commit SHA after changes (for GitHub Action context)."
    )
    args = parser.parse_args()

    root_pyproject_path_obj = Path(args.root_pyproject_path)
    if not root_pyproject_path_obj.exists():
        print(f"❌ Root pyproject.toml not found at {args.root_pyproject_path}. Exiting.")
        return 1


    # Get staged files and identify changed packages
    changed_file_paths = get_changed_files(args.commit_before, args.commit_after)

    if not changed_file_paths:
        print("No changed files found.")
        return 0

    changed_packages_all = get_changed_packages(changed_file_paths, args.ignore_dirs, root_pyproject_path_obj)
    if not changed_packages_all:
        print("No package changes detected in scanned project directories (after filtering).")
        return 0
        
    changed_packages = changed_packages_all # Use the direct result

    if not changed_packages:
        print("No package changes detected after filtering ignored packages.") # This message might be redundant now
        return 0
        
    print(f"📦 Changed packages (after filtering): {', '.join(sorted(str(p) for p in changed_packages))}")

    packages_bumped = [] # Stores display names of packages handled (bumped or acknowledged manual bump)
    
    # Check each changed package
    for package_path_rel in sorted(list(changed_packages)): # Iterate in a defined order
        package_display_name = str(package_path_rel) 
        pyproject_path = package_path_rel / "pyproject.toml" # This is now a relative path object

        # This check should be redundant if get_changed_packages ensures pyproject.toml exists
        # but keeping it as a safeguard
        if not pyproject_path.exists(): 
            print(f"⚠️  No pyproject.toml found for package: {package_display_name} (at {pyproject_path}) - this should not happen.")
            continue

        current_version_str = get_version_from_pyproject(pyproject_path)
        diff_version_str = get_version_from_diff(str(pyproject_path))
        
        if current_version_str is None:
            print(f"⚠️  Could not read current version for {package_display_name}. Skipping.")
            continue

        original_version = None
        try:
            # Construct relative path to pyproject.toml from CWD for git show
            git_show_path = str(pyproject_path) # Already relative from get_changed_packages
            original_version_content = run_git_command(["git", "show", f"HEAD:{git_show_path}"])
            if original_version_content:
                match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', original_version_content)
                if match:
                    original_version = match.group(1)
        except Exception as e:
            print(f"Could not get HEAD version for {package_display_name}: {e}")


        if str(pyproject_path) in changed_file_paths and diff_version_str is not None:
            if original_version and diff_version_str != original_version:
                 print(f"✅ Version for {package_display_name} was manually changed and staged: {original_version} → {diff_version_str}. Skipping auto-bump.")
                 packages_bumped.append(package_display_name) 
                 continue
            elif not original_version and diff_version_str: 
                 print(f"✅ New package {package_display_name} has staged version: {diff_version_str}. Skipping auto-bump.")
                 packages_bumped.append(package_display_name)
                 continue

        new_version = increment_patch_version(current_version_str)

        if set_version_in_pyproject(pyproject_path, new_version):
            print(f"🔄 Bumped {package_display_name}: {current_version_str} → {new_version}")

            if stage_file(str(pyproject_path)):
                packages_bumped.append(package_display_name)
            else:
                print(f"⚠️  Failed to stage {pyproject_path}")
        else:
            print(f"⚠️  Failed to update version for {package_display_name}")

    # If any packages were bumped (or acknowledged), also bump the root version
    if packages_bumped and not args.dont_bump_root:
        # root_pyproject_path_obj is already defined from args
        if root_pyproject_path_obj.exists(): # Should exist due to check at start
            current_root_version_str = get_version_from_pyproject(root_pyproject_path_obj)
            staged_root_version_str = get_version_from_diff(str(root_pyproject_path_obj))

            original_root_version = None
            try:
                # Ensure path is relative to CWD for git show
                git_show_root_path = str(root_pyproject_path_obj.relative_to(Path.cwd())) if root_pyproject_path_obj.is_absolute() else str(root_pyproject_path_obj)
                original_root_version_content = run_git_command(["git", "show", f"HEAD:{git_show_root_path}"])
                if original_root_version_content:
                    match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', original_root_version_content)
                    if match:
                        original_root_version = match.group(1)
            except Exception as e:
                 print(f"Could not get HEAD version for root pyproject {args.root_pyproject_path}: {e}")


            user_manually_bumped_root = False
            if str(root_pyproject_path_obj) in changed_file_paths and staged_root_version_str is not None:
                if original_root_version and staged_root_version_str != original_root_version:
                    print(f"✅ Root version ({args.root_pyproject_path}) was manually changed and staged: {original_root_version} → {staged_root_version_str}. Skipping auto-bump for root.")
                    user_manually_bumped_root = True
                elif not original_root_version and staged_root_version_str:
                     print(f"✅ New root pyproject ({args.root_pyproject_path}) has staged version: {staged_root_version_str}. Skipping auto-bump for root.")
                     user_manually_bumped_root = True
            
            if not user_manually_bumped_root:
                if current_root_version_str:
                    new_root_version = increment_patch_version(current_root_version_str)
                    if set_version_in_pyproject(root_pyproject_path_obj, new_root_version):
                        print(
                            f"🔄 Bumped root version ({args.root_pyproject_path}): {current_root_version_str} → {new_root_version}"
                        )
                        if not stage_file(str(root_pyproject_path_obj)):
                            print(f"⚠️  Failed to stage {args.root_pyproject_path}")
                    else:
                        print(f"⚠️  Failed to update root version at {args.root_pyproject_path}")
                elif not current_root_version_str : # Only print if not manually handled and no current version
                     print(f"⚠️  Could not read current root version from {args.root_pyproject_path}. Skipping root bump.")


    if packages_bumped:
        print(f"✨ Version processing completed. Touched/acknowledged packages: {', '.join(sorted(packages_bumped))}")
    else:
        print("No version bumps were needed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
