#!/usr/bin/env python3
"""
Pre-commit hook for automatic version bumping in UV workspace.

This script:
1. Analyzes git diff to identify changed packages based on specified package directories.
2. Checks if versions have been manually updated.
3. Auto-bumps patch version for packages with changes but no version bump, excluding ignored packages.
4. Bumps root version if any subpackages were bumped, using a configurable root pyproject.toml path.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Set, Tuple

import toml


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


def get_staged_files() -> Set[str]:
    """Get list of staged files from git."""
    output = run_git_command(["git", "diff", "--cached", "--name-only"])
    return set(output.split("\n")) if output else set()


def get_changed_packages(staged_files: Set[str], package_dirs_str: List[str]) -> Set[Path]:
    """Identify which package directories have changed files.

    Assumes that a package is structured as so:

    for `packages_dirs_str: List[str] = ["packages"]`

    packages/
        my_package/ #will catch this
            pyproject.toml 
            ...
        my_other_package/ #will catch this
            pyproject.toml
            ...
        my_subfolder/
            my_nested_package/ #will NOT catch this, since its not one level down. add "packages/my_subfolder/my_nested_package" to package_dirs_str to catch this.
                pyproject.toml
                ...
                
    """
    changed_pkgs_set = set()
    for p_dir_str in package_dirs_str:  # e.g., "packages", "libs"
        package_group_dir = Path(p_dir_str)
        if not package_group_dir.is_dir():
            print(f"⚠️  Configured package directory not found: {package_group_dir}")
            continue

        for file_path_str in staged_files:
            try:
                fp = Path(file_path_str)
                # Check if fp is relative to package_group_dir and has subdirectories
                if fp.is_relative_to(package_group_dir) and len(fp.parts) > len(package_group_dir.parts):
                    # The package name is the first directory inside the package_group_dir
                    package_sub_dir_name = fp.parts[len(package_group_dir.parts)]
                    actual_package_path = package_group_dir / package_sub_dir_name

                    if actual_package_path.is_dir() and (actual_package_path / "pyproject.toml").exists():
                        changed_pkgs_set.add(actual_package_path)
            except ValueError:
                # Path.is_relative_to raises ValueError if not relative
                continue
            except Exception as e:
                print(f"Error processing file {file_path_str} in {package_group_dir}: {e}")
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
    """Extract version from pyproject.toml."""
    try:
        with open(pyproject_path, "r") as f:
            data = toml.load(f)
        project_data = data.get("project") or data.get("tool", {}).get("poetry") # Handle poetry projects too
        if project_data and "version" in project_data:
            return project_data["version"]
        else:
            print(f"Warning: Could not find version in {pyproject_path} under [project] or [tool.poetry]")
            return None
    except (FileNotFoundError, toml.TomlDecodeError) as e:
        print(f"Error reading version from {pyproject_path}: {e}")
        return None


def set_version_in_pyproject(pyproject_path: Path, new_version: str) -> bool:
    """Update version in pyproject.toml."""
    try:
        with open(pyproject_path, "r") as f:
            content = f.read()
            lines = content.splitlines()

        # Try to find version under [project] or [tool.poetry]
        # More robust than regex for TOML structure but regex for line replacement
        # version_key_pattern = r'^\s*version\s*=\s*["\'](.*)["\']' # Original
        # More specific for project.version or tool.poetry.version
        
        # We will use regex to replace the version to preserve formatting as initially designed
        # This is simpler and less prone to TOML parsing/writing issues for just this one line.
        pattern = r'(version\s*=\s*["\'])([^"\']+)(["\'])'
        
        # Check if version exists first
        found_version_line = False
        for line in lines:
            if re.match(pattern, line.strip()): # Check if line matches pattern for version
                found_version_line = True
                break
        
        if not found_version_line:
            print(f"Error: 'version' field not found or not in expected format in {pyproject_path}")
            return False

        new_content = re.sub(pattern, f"\\g<1>{new_version}\\g<3>", content, count=1)


        if new_content != content:
            with open(pyproject_path, "w") as f:
                f.write(new_content)
        return True
    except Exception as e:
        print(f"Error updating version in {pyproject_path}: {e}")
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
        "--package-dirs",
        nargs="+",
        default=["packages"],
        help="Directories containing packages (e.g., packages libs). Default: ['packages']",
    )
    parser.add_argument(
        "--ignore-packages",
        nargs="+",
        default=[],
        help="List of package names (directory names) to ignore. Default: []",
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
    args = parser.parse_args()


    # Get staged files and identify changed packages
    staged_files = get_staged_files()
    if not staged_files:
        print("No staged files found.")
        return 0

    changed_packages_all = get_changed_packages(staged_files, args.package_dirs)
    if not changed_packages_all:
        print("No package changes detected in specified package directories.")
        return 0
        
    # Filter ignored packages
    changed_packages = set()
    for pkg_path in changed_packages_all:
        pkg_name = pkg_path.name # e.g. "my_package" from Path("packages/my_package")
        if pkg_name in args.ignore_packages:
            print(f"🚫 Ignoring package '{pkg_name}' as per --ignore-packages configuration.")
            continue
        changed_packages.add(pkg_path)

    if not changed_packages:
        print("No package changes detected after filtering ignored packages.")
        return 0
        
    print(f"📦 Changed packages (after filtering): {', '.join(sorted(str(p) for p in changed_packages))}")

    packages_bumped = []
    # packages_dir = Path("packages") # No longer needed, package_path is absolute

    # Check each changed package
    for package_path in sorted(list(changed_packages)): # Iterate in a defined order
        package_display_name = str(package_path) # e.g. "packages/my_pkg"
        pyproject_path = package_path / "pyproject.toml"

        if not pyproject_path.exists(): # Should not happen if get_changed_packages worked
            print(f"⚠️  No pyproject.toml found for package: {package_display_name} (at {pyproject_path})")
            continue

        # Check if version was manually changed in the diff
        current_version_str = get_version_from_pyproject(pyproject_path)
        # diff_version_str = get_version_from_diff(pyproject_path) # This was pyproject_path: str before
        diff_version_str = get_version_from_diff(str(pyproject_path))
        
        # Debug print, can be removed later
        # print(f"Processing {package_display_name}: current_version='{current_version_str}', diff_version='{diff_version_str}'")

        if current_version_str is None:
            print(f"⚠️  Could not read current version for {package_display_name}. Skipping.")
            continue

        # If version in diff is different from current disk version, it means user manually changed it.
        # However, the original logic compared diff_version with current_version.
        # The logic was: `if diff_version == current_version:`, means NO manual bump was staged.
        # This seems counter-intuitive. Let's re-evaluate.
        # get_version_from_diff gets the version from the *staged* file.
        # get_version_from_pyproject gets the version from the *working directory* file.

        # Correct logic:
        # 1. Get version from HEAD (or working dir before our changes)
        # 2. Get version from Staged (what user intends to commit)
        # If Staged version > HEAD version, user bumped it.
        # If Staged version == HEAD version, user did NOT bump it, so we might.

        # The current `get_version_from_pyproject` reads the current (potentially modified by user) working dir.
        # The current `get_version_from_diff` reads the staged version.

        # Let's simplify: if the staged file (`pyproject.toml`) has a version line changed,
        # we assume the user handled it. `get_version_from_diff` returns the *new* version from the diff.
        # `current_version_str` is from the *current state on disk* of pyproject.toml.

        # If `pyproject.toml` is staged, and its version changed:
        #   `diff_version_str` will be the new version.
        #   `current_version_str` (from disk) if not staged, is old. If staged and changed, could be new.
        # This part of the logic is a bit tricky.
        # The original code's `if diff_version == current_version:` was intended to mean:
        # "If the version in the staged changes IS THE SAME AS the version currently on disk (ignoring the staged changes),
        # then the user hasn't manually bumped it in a way that differs from the disk."
        # This is only true if the pyproject.toml was *not* staged with a version bump.

        # A clearer approach:
        # 1. Get original version (from HEAD for `pyproject.toml`)
        original_version_str = run_git_command(["git", "show", f"HEAD:{str(pyproject_path.relative_to(Path.cwd()))}"])
        original_version = None
        if original_version_str:
            # Quick parse of version from the raw file content. This is a bit fragile.
            match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', original_version_str)
            if match:
                original_version = match.group(1)
        
        staged_version_if_changed = diff_version_str # This is the version if '+version' line exists in diff

        # If the pyproject.toml for the package is part of the staged files AND its version line changed...
        if str(pyproject_path) in staged_files and staged_version_if_changed is not None:
            # User has staged a version change for this pyproject.toml
            # We should respect this and not auto-bump, provided it's a valid bump or different.
            if original_version and staged_version_if_changed != original_version:
                 print(f"✅ Version for {package_display_name} was manually changed and staged: {original_version} → {staged_version_if_changed}. Skipping auto-bump.")
                 packages_bumped.append(package_display_name) # Count as "handled"
                 continue
            elif not original_version and staged_version_if_changed: # New file with version
                 print(f"✅ New package {package_display_name} has staged version: {staged_version_if_changed}. Skipping auto-bump.")
                 packages_bumped.append(package_display_name) # Count as "handled"
                 continue


        # If we reach here, either:
        # - pyproject.toml was not staged with a version change.
        # - pyproject.toml was staged, but version line didn't change (e.g. only other lines changed)
        # - pyproject.toml was not staged at all (but other files in package were)
        # So, we proceed to auto-bump based on `current_version_str` (from disk).

        new_version = increment_patch_version(current_version_str)

        if set_version_in_pyproject(pyproject_path, new_version):
            print(f"🔄 Bumped {package_display_name}: {current_version_str} → {new_version}")

            if stage_file(str(pyproject_path)):
                packages_bumped.append(package_display_name)
            else:
                print(f"⚠️  Failed to stage {pyproject_path}")
                # Potentially return 1 here to fail the commit
        else:
            print(f"⚠️  Failed to update version for {package_display_name}")
            # Potentially return 1 here

    # If any packages were bumped, also bump the root version
    if packages_bumped and not args.dont_bump_root: # This means either we bumped it, or user bumped it and we acknowledged.
        root_pyproject_path = Path(args.root_pyproject_path)
        if root_pyproject_path.exists():
            current_root_version_str = get_version_from_pyproject(root_pyproject_path)
            # staged_root_version_str = get_version_from_diff(root_pyproject_path) # Needs str()
            staged_root_version_str = get_version_from_diff(str(root_pyproject_path))

            # Similar logic for root: if user manually staged a root version change, respect it.
            original_root_version_str_content = run_git_command(["git", "show", f"HEAD:{str(root_pyproject_path.relative_to(Path.cwd()))}"])
            original_root_version = None
            if original_root_version_str_content:
                match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', original_root_version_str_content)
                if match:
                    original_root_version = match.group(1)

            if str(root_pyproject_path) in staged_files and staged_root_version_str is not None:
                if original_root_version and staged_root_version_str != original_root_version:
                    print(f"✅ Root version was manually changed and staged: {original_root_version} → {staged_root_version_str}. Skipping auto-bump for root.")
                elif not original_root_version and staged_root_version_str:
                     print(f"✅ New root pyproject has staged version: {staged_root_version_str}. Skipping auto-bump for root.")
                # else: proceed to bump if current_root_version_str is valid
            
            # If not manually bumped or if no version change was staged for root pyproject.toml
            # and if current_root_version_str is available
            elif current_root_version_str:
                new_root_version = increment_patch_version(current_root_version_str)
                if set_version_in_pyproject(root_pyproject_path, new_root_version):
                    print(
                        f"🔄 Bumped root version ({args.root_pyproject_path}): {current_root_version_str} → {new_root_version}"
                    )
                    if not stage_file(str(root_pyproject_path)):
                        print(f"⚠️  Failed to stage {args.root_pyproject_path}")
                else:
                    print(f"⚠️  Failed to update root version at {args.root_pyproject_path}")
            elif not current_root_version_str:
                 print(f"⚠️  Could not read current root version from {args.root_pyproject_path}. Skipping root bump.")


    if packages_bumped:
        print(f"✨ Version processing completed. Touched/acknowledged: {', '.join(sorted(packages_bumped))}")
    else:
        print("No version bumps were needed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
